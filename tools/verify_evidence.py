"""Check the evidence in `docs/05-evidence.md` against the artefacts it points at.

Every entry declares what would prove it, next to the claim, and this tool executes those
declarations: it runs the entry's command, captures the output, and recomputes any value that is a
function of committed data. It writes `.sota/verification.json` (the record the publish gate reads)
and `docs/verification.md` (the summary a reader reads), then exits non-zero if anything failed or
was left unchecked.

Usage:

    python3 tools/verify_evidence.py                  # every entry
    python3 tools/verify_evidence.py --only E-002     # one entry
    python3 tools/verify_evidence.py --timeout 1800   # longer-running commands

Declared checks (`**Verifies:**` lines in the ledger, one per line, in any number):

    exit-zero                                    the command must exit 0
    output-contains "text"                       the text must appear in the captured output
    output-contains-near 12.5 tolerance=0.1      some number in the output must be that value
    data-sha256 [path]                           the entry's committed data matches its checksum
    computed-from path path=dotted.into.json value=12.5 [tolerance=0.1] [agg=mean]
                                                 recompute the value from the data and compare;
                                                 a path may select ([key=value]), map over a
                                                 list ([]) and aggregate (agg=mean|median|sum|
                                                 min|max|count)
    repeat-identical [--runs N] path...          running the command N times writes identical bytes

A check name this tool does not implement is reported `unsupported` and fails: the failure mode
worth preventing is a check that reads as satisfied because nobody implemented it.

Two outcomes are neither pass nor fail: `unrunnable` means the environment the entry declares is
absent (a container runtime, a device, a service) and is recorded with its reason, so a reader can
see what was and was not re-verified here; `unchecked` means the entry declared no checks at all.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shlex
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

LEDGER = Path("docs/05-evidence.md")
RECORD = Path(".sota/verification.json")
SUMMARY = Path("docs/verification.md")
SUMMARY_START = "<!-- verification:start -->"
SUMMARY_END = "<!-- verification:end -->"

ENTRY_HEADING = re.compile(r"^###\s+(E-\d{3})\b(.*)$", re.MULTILINE)
COMMAND_BLOCK = re.compile(r"```(?:sh|bash|console|shell)?\n(.*?)```", re.DOTALL)
VERIFIES = re.compile(r"^\s*(?:[-*>]\s*)?\*{0,2}verifies\*{0,2}\s*:\*{0,2}\s*(.+?)\s*$",
                      re.IGNORECASE | re.MULTILINE)
KIND = re.compile(r"^\s*\*{0,2}\s*kind[*:]{1,3}\s*([A-Za-z][A-Za-z0-9_-]*)",
                  re.IGNORECASE | re.MULTILINE)
DATA_LINE = re.compile(r"^\s*\*{0,2}\s*Data[*:]{1,3}\s*(.+?)\s*$", re.IGNORECASE | re.MULTILINE)
ANSI = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")
NUMBER = re.compile(r"-?\d+(?:\.\d+)?")

KNOWN_CHECKS = frozenset({
    "exit-zero", "output-contains", "output-contains-near", "data-sha256", "computed-from",
    "repeat-identical",
})
# Commands that need one of these are reported unrunnable rather than failed when it is absent.
ENVIRONMENT_PROBES = {
    "docker": "docker",
    "podman": "podman",
    "go": "go",
    "node": "node",
    "cargo": "cargo",
}


@dataclass
class Check:
    name: str
    args: list[str]
    options: dict[str, str] = field(default_factory=dict)

    @property
    def supported(self) -> bool:
        return self.name in KNOWN_CHECKS

    @property
    def needs_run(self) -> bool:
        return self.name in {"exit-zero", "output-contains", "output-contains-near",
                             "repeat-identical"}


@dataclass
class Entry:
    eid: str
    title: str
    body: str
    command: str | None
    kind: str | None
    data_path: str | None
    data_sha256: str | None
    checks: list[Check]


@dataclass
class Outcome:
    eid: str
    outcome: str
    checks: list[str]
    reason: str = ""
    detail: list[str] = field(default_factory=list)


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.exists() else ""


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def normalise(text: str) -> str:
    return re.sub(r"\s+", " ", ANSI.sub("", text)).strip()


def parse_check(raw: str) -> Check:
    tokens = shlex.split(raw)
    name = tokens[0] if tokens else ""
    args: list[str] = []
    options: dict[str, str] = {}
    for token in tokens[1:]:
        if "=" in token and not token.startswith(('"', "'")):
            key, _, value = token.partition("=")
            options[key] = value
        else:
            args.append(token)
    return Check(name=name, args=args, options=options)


def parse_ledger(text: str) -> list[Entry]:
    text = re.sub(r"<!--.*?-->", "", text, flags=re.DOTALL)
    headings = list(ENTRY_HEADING.finditer(text))
    entries: list[Entry] = []
    for index, match in enumerate(headings):
        end = headings[index + 1].start() if index + 1 < len(headings) else len(text)
        body = text[match.end():end]
        block = COMMAND_BLOCK.search(body)
        kind = KIND.search(body)
        data = DATA_LINE.search(body)
        data_path = data_sha256 = None
        if data:
            path_part, _, checksum_part = data.group(1).partition("sha256:")
            data_path = path_part.replace("(sha256:", "").strip().rstrip("(").strip()
            data_sha256 = checksum_part.strip().rstrip(")").strip() or None
        entries.append(Entry(
            eid=match.group(1),
            title=match.group(2).strip(" —-"),
            body=body,
            command=block.group(1).strip() if block else None,
            kind=kind.group(1).lower() if kind else None,
            data_path=data_path,
            data_sha256=data_sha256,
            checks=[parse_check(m.group(1)) for m in VERIFIES.finditer(body)],
        ))
    return entries


def run(command: str, timeout: int) -> tuple[str, str, int]:
    """Run one ledger command under bash, which is what the ledger's blocks are written for.

    Executing that command is this tool's whole purpose, and the command comes from the
    repository's own evidence ledger rather than from a caller.  # noqa: S603
    """
    done = subprocess.run(["/bin/bash", "-lc", command],  # noqa: S603
                          capture_output=True, text=True, timeout=timeout)
    return done.stdout or "", done.stderr or "", done.returncode


def missing_environment(entry: Entry) -> str | None:
    """An entry that declares a runtime it cannot find is unrunnable, not failed."""
    for name, binary in ENVIRONMENT_PROBES.items():
        if re.search(rf"\b{name}\b", entry.body, re.IGNORECASE) and shutil.which(binary) is None:
            return f"{name} is not available in this environment"
    return None


def path_tokens(path: str) -> list[str]:
    """Split `a.b[level=f16].c[].WER` into names and bracket selectors.

    Three selector forms, which is all the committed benchmark data in this framework needs:
    `[key=value]` picks the first list element whose field matches, `[]` maps over the rest of the
    path for every element, and a bare integer indexes a list.
    """
    tokens: list[str] = []
    name = ""
    index = 0
    while index < len(path):
        char = path[index]
        if char == "[":
            close = path.index("]", index)
            if name:
                tokens.append(name)
                name = ""
            tokens.append(path[index:close + 1])
            index = close + 1
            continue
        if char == ".":
            if name:
                tokens.append(name)
                name = ""
            index += 1
            continue
        name += char
        index += 1
    if name:
        tokens.append(name)
    return tokens


def matches(value: object, wanted: str) -> bool:
    try:
        return float(value) == float(wanted)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return str(value).lower() == wanted.lower()


def walk(node: object, tokens: list[str]) -> object:
    if not tokens:
        return node
    token, rest = tokens[0], tokens[1:]
    if token.startswith("["):
        body = token[1:-1]
        if not isinstance(node, list):
            raise KeyError(token)
        if body == "":
            values = [walk(item, rest) for item in node]
            return [value for value in values if value is not None]
        key, _, wanted = body.partition("=")
        for item in node:
            if isinstance(item, dict) and matches(item.get(key), wanted):
                return walk(item, rest)
        raise KeyError(token)
    if isinstance(node, dict):
        return walk(node[token], rest)
    if isinstance(node, list):
        return walk(node[int(token)], rest)
    raise KeyError(token)


def aggregate(values: object, kind: str) -> float:
    if not isinstance(values, list):
        raise KeyError(f"agg={kind} needs a list, found {type(values).__name__}")
    numbers = [float(value) for value in values if isinstance(value, (int, float))]
    if not numbers:
        raise KeyError("no numbers to aggregate")
    if kind == "mean":
        return sum(numbers) / len(numbers)
    if kind == "median":
        ordered = sorted(numbers)
        middle = len(ordered) // 2
        return (ordered[middle - 1] + ordered[middle]) / 2 if len(ordered) % 2 == 0 \
            else ordered[middle]
    if kind == "sum":
        return sum(numbers)
    if kind == "min":
        return min(numbers)
    if kind == "max":
        return max(numbers)
    if kind == "count":
        return float(len(numbers))
    raise KeyError(f"unknown agg={kind}")


def check_entry(entry: Entry, root: Path, timeout: int) -> Outcome:
    names = [check.name for check in entry.checks]
    if not entry.checks:
        return Outcome(entry.eid, "unchecked", names,
                       reason="no `Verifies:` line — nothing declares what would prove this")
    unknown = [check.name for check in entry.checks if not check.supported]
    if unknown:
        return Outcome(entry.eid, "unsupported", names,
                       reason=f"check(s) not implemented: {', '.join(sorted(set(unknown)))}")

    block = missing_environment(entry)
    stdout = ""
    stderr = ""
    exit_code = 0
    if any(check.needs_run for check in entry.checks):
        if block:
            return Outcome(entry.eid, "unrunnable", names, reason=block)
        if entry.command is None:
            return Outcome(entry.eid, "unrunnable", names,
                           reason="a runnable check but the entry has no command block")
        try:
            stdout, stderr, exit_code = run(entry.command, timeout)
        except subprocess.TimeoutExpired:
            return Outcome(entry.eid, "unrunnable", names,
                           reason=f"command did not finish within {timeout}s")
        except FileNotFoundError as exc:
            return Outcome(entry.eid, "unrunnable", names, reason=f"command not found: {exc}")
        if exit_code == 127:
            return Outcome(entry.eid, "unrunnable", names,
                           reason=f"command not found: {stderr.strip()[:120]}")

    detail: list[str] = []
    passed = True
    for check in entry.checks:
        ok, message = run_check(check, entry, root, stdout, exit_code, timeout)
        detail.append(f"{check.name}: {'ok' if ok else 'FAILED'}"
                      + (f" — {message}" if message and not ok else ""))
        passed = passed and ok
    if not passed and stderr.strip():
        # A failed run is usually explained by the run's own stderr (a missing credential, a
        # closed port); without it the report blames the entry for an environment problem.
        detail.append(f"stderr: {normalise(stderr)[:200]}")
    return Outcome(entry.eid, "pass" if passed else "fail", names, detail=detail)


def run_check(check: Check, entry: Entry, root: Path, stdout: str, exit_code: int,
              timeout: int) -> tuple[bool, str]:
    output = normalise(stdout)
    if check.name == "exit-zero":
        return exit_code == 0, f"exit {exit_code}"
    if check.name == "output-contains":
        needle = normalise(" ".join(check.args))
        return needle in output, f"output does not contain {needle!r}"
    if check.name == "output-contains-near":
        if not check.args:
            return False, "no value given"
        wanted = float(check.args[0])
        tolerance = float(check.options.get("tolerance", "0"))
        found = [float(m.group(0)) for m in NUMBER.finditer(output)]
        return any(abs(value - wanted) <= tolerance for value in found), (
            f"no number within {tolerance} of {wanted} in the output")
    if check.name == "data-sha256":
        path = Path(check.args[0]) if check.args else (Path(entry.data_path)
                                                      if entry.data_path else None)
        if path is None or entry.data_sha256 is None:
            return False, "no `Data:` line to check"
        if not (root / path).exists():
            return False, f"{path} does not exist"
        actual = sha256_file(root / path)
        return actual == entry.data_sha256.lower(), (
            f"{path} is {actual[:12]}…, the entry records {entry.data_sha256[:12]}…")
    if check.name == "computed-from":
        return check_computed_from(check, root)
    if check.name == "repeat-identical":
        return check_repeat_identical(check, entry, root, timeout)
    return False, "not implemented"


def check_computed_from(check: Check, root: Path) -> tuple[bool, str]:
    if not check.args:
        return False, "no data file given"
    path = root / check.args[0]
    dotted = check.options.get("path")
    if dotted is None or "value" not in check.options:
        return False, "needs path=<dotted.path> and value=<expected>"
    if not path.exists():
        return False, f"{check.args[0]} does not exist"
    data = json.loads(path.read_text(encoding="utf-8"))
    agg = check.options.get("agg")
    try:
        resolved = walk(data, path_tokens(dotted))
        actual = aggregate(resolved, agg) if agg else float(resolved)  # type: ignore[arg-type]
    except (KeyError, IndexError, TypeError, ValueError) as exc:
        return False, f"{dotted} is not a number in {check.args[0]} ({exc})"
    expected = float(check.options["value"])
    tolerance = float(check.options.get("tolerance", "0"))
    if abs(actual - expected) > tolerance:
        return False, (f"{dotted} is {actual}, the entry claims {expected} "
                       f"(tolerance {tolerance})")
    return True, ""


def check_repeat_identical(check: Check, entry: Entry, root: Path,
                           timeout: int) -> tuple[bool, str]:
    runs = int(check.options.get("runs", "2"))
    paths = [Path(arg) for arg in check.args]
    if not paths:
        return False, "no artefact paths given"
    if entry.command is None:
        return False, "no command block"
    digests: list[list[str]] = []
    for _ in range(runs):
        run(entry.command, timeout)
        digests.append([sha256_file(root / path) if (root / path).exists() else "missing"
                        for path in paths])
    first = digests[0]
    for index, other in enumerate(digests[1:], start=2):
        if other != first:
            changed = [str(path) for path, a, b in zip(paths, first, other, strict=True) if a != b]
            return False, f"run {index} differs on {', '.join(changed)}"
    return True, ""


def write_record(root: Path, outcomes: list[Outcome], tool_version: str) -> dict[str, object]:
    today = date.today().isoformat()
    record = {
        "generated": today,
        "tool": tool_version,
        "entries": {
            outcome.eid: {
                "outcome": outcome.outcome,
                "date": today,
                "checks": outcome.checks,
                **({"reason": outcome.reason} if outcome.reason else {}),
            }
            for outcome in outcomes
        },
    }
    (root / RECORD).parent.mkdir(parents=True, exist_ok=True)
    (root / RECORD).write_text(json.dumps(record, indent=2, sort_keys=True) + "\n",
                               encoding="utf-8")
    return record


def render_summary(entries: list[Entry], outcomes: list[Outcome], ledger_text: str,
                   record_text: str) -> str:
    # The digest covers the ledger and the record file as they are on disk, so the gate can
    # recompute it without knowing how either was produced.
    digest = hashlib.sha256((ledger_text + record_text).encode("utf-8")).hexdigest()[:16]
    counts: dict[str, int] = {}
    for outcome in outcomes:
        counts[outcome.outcome] = counts.get(outcome.outcome, 0) + 1
    tally = ", ".join(f"{count} {name}" for name, count in sorted(counts.items()))
    by_id = {entry.eid: entry for entry in entries}
    lines = [
        SUMMARY_START,
        "",
        "# Verification",
        "",
        f"_{tally} · inputs digest {digest} · machine-generated, do not hand-edit._",
        "",
        "Every entry in [docs/05-evidence.md](05-evidence.md) declares how it would be checked; "
        "`python3 tools/verify_evidence.py` executes those declarations. An entry marked "
        "`unrunnable` needs something this machine did not have — the reason is in "
        "`.sota/verification.json`.",
        "",
        "| Entry | Kind | Outcome | Date | Checks |",
        "| :--- | :--- | :--- | :--- | :--- |",
    ]
    record = json.loads(record_text)
    for outcome in outcomes:
        entry = by_id.get(outcome.eid)
        kind = entry.kind if entry and entry.kind else "—"
        recorded = record["entries"].get(outcome.eid, {})
        lines.append(f"| {outcome.eid} | {kind} | {outcome.outcome} | "
                     f"{recorded.get('date', '—')} | {', '.join(outcome.checks) or '—'} |")
    lines += ["", "Reproduce: `python3 tools/verify_evidence.py`", "", SUMMARY_END]
    return "\n".join(lines)


def write_summary(root: Path, block: str) -> None:
    path = root / SUMMARY
    existing = read(path)
    if SUMMARY_START in existing and SUMMARY_END in existing:
        head = existing.split(SUMMARY_START)[0].rstrip()
        tail = existing.split(SUMMARY_END)[1].lstrip("\n")
        path.write_text(f"{head}\n\n{block}\n\n{tail}" if tail else f"{head}\n\n{block}\n",
                        encoding="utf-8")
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(block + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--ledger", type=Path, default=LEDGER)
    parser.add_argument("--only", nargs="+", default=None,
                        help="check only these entries (the record still lists all of them)")
    parser.add_argument("--timeout", type=int, default=900,
                        help="seconds a single entry's command may run")
    args = parser.parse_args(argv)

    root: Path = args.root
    ledger_path = root / args.ledger
    ledger_text = read(ledger_path)
    if not ledger_text:
        print(f"no evidence ledger at {ledger_path}", file=sys.stderr)
        return 1
    entries = parse_ledger(ledger_text)
    if not entries:
        print(f"no E-### entries found in {ledger_path}", file=sys.stderr)
        return 1

    selected = entries if args.only is None else [e for e in entries if e.eid in set(args.only)]
    outcomes = [check_entry(entry, root, args.timeout) for entry in selected]

    write_record(root, outcomes, tool_version="verify_evidence.py")
    write_summary(root, render_summary(selected, outcomes, ledger_text,
                                       read(root / RECORD)))

    width = max(len(outcome.eid) for outcome in outcomes)
    for outcome in outcomes:
        line = f"{outcome.eid:<{width}}  {outcome.outcome}"
        if outcome.reason:
            line += f" — {outcome.reason}"
        print(line)
        for item in outcome.detail:
            if "FAILED" in item:
                print(f"{'':<{width}}    {item}")

    counts: dict[str, int] = {}
    for outcome in outcomes:
        counts[outcome.outcome] = counts.get(outcome.outcome, 0) + 1
    print("\n" + ", ".join(f"{count} {name}" for name, count in sorted(counts.items())))
    print(f"record: {RECORD} · summary: {SUMMARY}")
    return 1 if counts.get("fail") or counts.get("unsupported") or counts.get("unchecked") else 0


if __name__ == "__main__":
    raise SystemExit(main())
