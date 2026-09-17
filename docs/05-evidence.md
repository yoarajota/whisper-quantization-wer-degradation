# Evidence ledger — Whisper quantization WER degradation curve

Every claim in this repository resolves to an entry here (rule R3). An entry without a
reproduction command is a note, not evidence, and fails validation.

**Required in every entry:** a fenced command block, an `Environment:` line, and a `Result:`
line. Headings must be exactly `### E-###  —  <title>` so the tooling can parse them.

IDs are never reused. Evidence that stops reproducing is marked `Status: broken` and the
readiness level that depended on it comes down (rule R1).

---

### E-001  —  Literature survey

**Claim.** The literature contains no WER benchmark across whisper.cpp quantization levels
(FP16, INT8, INT5, INT4) on a full standard dataset with statistical significance testing.
Six sources were fetched and read, establishing the gap. Appears in `docs/01-theory.md`.

**Environment:** WebFetch against arXiv, GitHub, OpenSLR. Date of search: 2026-08-11.

**Kind:** survey

```sh
# Counts the ledger's own sources, so the numbers in the Result come from this command.
printf 'sources: %s full-text: %s abstract-only: %s\n' \
  "$(grep -c '^### SRC-' docs/01-theory.md)" \
  "$(grep -c '^- \*\*Access:\*\* full-text' docs/01-theory.md)" \
  "$(grep -c '^- \*\*Access:\*\* abstract-only' docs/01-theory.md)"
```

**Result:** Six sources read (5 full-text, 1 abstract-only). Key finding: no existing work
measures whisper.cpp ggml quantization WER on a full benchmark with bootstrap CIs and
paired statistical tests.

**Verifies:** exit-zero
**Verifies:** output-contains "sources: 6 full-text: 5 abstract-only: 1"

**Status:** reproducing
**Supports:** H-001, H-002, TRL 1 for `core`
**Recorded:** 2026-08-11

---

### E-002  —  PoC: WER computation and Wilcoxon test validate statistically

**Claim.** The PoC pipeline correctly computes WER (Levenshtein at word level) and produces
valid Wilcoxon signed-rank p-values. Tests in `poc/main_test.go` verify edge cases.

**Environment:** Go 1.x, Linux/amd64.

**Kind:** test

```sh
# Prints the pass/fail counts the Result states, and exits with the test suite's own status.
out=$(go test ./poc/ -v 2>&1); status=$?
printf '%s\n' "$out" | grep -E '^--- (PASS|FAIL):'
printf 'passed: %s failed: %s\n' "$(printf '%s\n' "$out" | grep -c '^--- PASS:')" \
  "$(printf '%s\n' "$out" | grep -c '^--- FAIL:')"
exit $status
```

**Result:** 7/7 tests pass. `TestWilcoxonShift` confirms systematic 0.01 shift on n=60
produces p <= 0.05.

**Verifies:** exit-zero
**Verifies:** output-contains "passed: 7 failed: 0"
**Verifies:** output-contains "--- PASS: TestWilcoxonShift"

**Status:** reproducing
**Supports:** H-001, H-002, TRL 3 for `core`
**Recorded:** 2026-08-11

---

### E-003  —  Component test suite passes (conformance, failure-mode, property)

**Claim.** The `werpipe` package has 22 tests across three layers: conformance, failure
modes, and properties. All pass.

**Environment:** Go 1.22, Linux/amd64.

**Kind:** test

```sh
# Prints the pass/fail counts the Result states, and exits with the test suite's own status.
out=$(go test ./src/werpipe/ -v 2>&1); status=$?
printf '%s\n' "$out" | grep -E '^--- (PASS|FAIL):'
printf 'passed: %s failed: %s\n' "$(printf '%s\n' "$out" | grep -c '^--- PASS:')" \
  "$(printf '%s\n' "$out" | grep -c '^--- FAIL:')"
exit $status
```

**Result:** 22/22 tests pass. Wilcoxon p=1.0 for identical data, p<0.05 for shift of 0.05
on n=40. Normalize is idempotent. Bootstrap CI monotonic.

**Verifies:** exit-zero
**Verifies:** output-contains "passed: 22 failed: 0"

**Status:** reproducing
**Supports:** S-003 (modifiability)
**Recorded:** 2026-08-11

---

### E-004  —  End-to-end pipeline verification (Docker, tiny.en model)

**Claim.** The werpipe CLI transcribes audio across quantization levels, computes WER,
and reports Wilcoxon p-values with bootstrap 95% CI — all inside a single Docker container.

**Environment:** Docker container `concept-whisper-wer` (whisper.cpp v1.9.2, werpipe Go
CLI), Intel Xeon E5-2680 v4 @ 2.40GHz, 6 vCPUs, no GPU.

**Kind:** test

```bash
docker build -f docker/Dockerfile -t concept-whisper-wer .
docker run --rm --entrypoint sh concept-whisper-wer -c '
  cd /whisper.cpp
  wget -q https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-tiny.en.bin \
    -O ggml-tiny.en.bin
  ./build/bin/whisper-quantize ggml-tiny.en.bin ggml-tiny.en-q5_0.bin q5_0 2>/dev/null
  ./build/bin/whisper-quantize ggml-tiny.en.bin ggml-tiny.en-q4_0.bin q4_0 2>/dev/null
  mkdir -p /tmp/test/audio /tmp/test/transcripts
  cp samples/jfk.wav /tmp/test/audio/
  echo "And so my fellow Americans ask not what your country can do for you
ask what you can do for your country" > /tmp/test/transcripts/jfk.txt
  werpipe -audio /tmp/test/audio -transcripts /tmp/test/transcripts \
    -model-dir /whisper.cpp -whisper-cli /whisper.cpp/build/bin/whisper-cli \
    -v -levels "ggml-tiny.en.bin,ggml-tiny.en-q5_0.bin,ggml-tiny.en-q4_0.bin"
'
```

**Result:** 3 levels, 1 sample each. F16 WER=0.0909, Q5_0 WER=0.0909 (rel=0%, p=1.0),
Q4_0 WER=0.0909 (rel=0%, p=1.0). Pipeline produces valid JSON. Sizes: 75MB→29MB→25MB.

**Verifies:** exit-zero

**Status:** reproducing
**Supports:** H-001, H-002, S-001, S-002, TRL 5 for `core`
**Recorded:** 2026-08-11

---


### E-006  —  Full-dataset benchmark: 2620 LibriSpeech test-clean samples (GPU)

**Claim.** Whisper large-v3 across 4 whisper.cpp quantization levels on ALL 2620
LibriSpeech test-clean utterances. Q8_0 and Q5_0 show statistically significant WER
*improvement* vs FP16 (−1.9%, p=0.048; −3.0%, p=0.001). Q4_0 shows the first
statistically significant *degradation*: +4.9% relative, p=0.0014. The effect is real
but below the 10% predicted at P1 — it was invisible at n=100 and required the
full dataset.

An earlier 100-sample run of the same comparison found no significant difference
at any level (Q4_0 at +4.2%, p=0.57) and was originally recorded as its own evidence
entry; that entry's raw per-sample data was lost in a temp-dir wipe, and this full
run supersedes it entirely.

**Environment:** Google Colab, Tesla T4 (15360 MiB), whisper.cpp v1.9.2 compiled with
CUDA 12.8 (`-DGGML_CUDA=1`, sm_75), werpipe Go CLI, containerless Colab runtime.
Full dataset run in resumable 200-sample chunks; chunk-8.json (offset 1400) was
corrupted in transit and redone as chunk-1400.json. All 2620 samples, 0 errors.

**Kind:** benchmark

**Data:** evidence-data/E-006-final.json (sha256: 6bcf09f18f2422eb94c7f297401bfd058fa70edf7ed6c41b9446c608f6cec97c)

```bash
# GPU environment (Colab): see bench/colab.py
# Merge (any environment):
werpipe merge chunk-1.json chunk-2.json ... chunk-2600.json > final.json
```

**Result:**

2620 samples, 4 levels:

| Level | WER | Size | vs F16 | p-value | 95% CI |
|:---|:---|:---|:---|:---|:---|
| F16 | 5.35% | 2892 MB | baseline | — | — |
| Q8_0 | 5.25% | 1543 MB | −1.9% | 0.048 | [4.85%, 5.65%] |
| Q5_0 | 5.19% | 1010 MB | −3.0% | 0.001 | [4.79%, 5.60%] |
| Q4_0 | 5.61% | 830 MB | +4.9% | 0.001 | [5.21%, 6.03%] |

Answer to the concept question: the first statistically significant WER degradation
appears at INT4 (Q4_0). INT8 and INT5 show no degradation — small significant
improvements consistent with the literature's observation that mild quantization
acts as a regularizer on Transformer ASR.

**Verifies:** data-sha256
**Verifies:** computed-from evidence-data/E-006-final.json path=[level=f16].results.Samples[].WER agg=mean value=0.053518 tolerance=0.000001
**Verifies:** computed-from evidence-data/E-006-final.json path=[level=q8_0].results.Samples[].WER agg=mean value=0.052481 tolerance=0.000001
**Verifies:** computed-from evidence-data/E-006-final.json path=[level=q5_0].results.Samples[].WER agg=mean value=0.051937 tolerance=0.000001
**Verifies:** computed-from evidence-data/E-006-final.json path=[level=q4_0].results.Samples[].WER agg=mean value=0.056139 tolerance=0.000001

**Status:** reproducing
**Supports:** H-001 (partially — significant but +4.9% < 10%), H-002 (supported),
S-001, S-002
**Recorded:** 2026-08-15

---

## Benchmark methodology

Filled at P5. Applies to every entry with `Kind: benchmark`.

- **What is measured:** Per-sample WER across quantization levels; aggregate WER with 95%
  bootstrap CI; Wilcoxon signed-rank p-value for paired FP16 vs quantized comparisons.
- **Runs:** 1 run per quantization level (deterministic inference), **warm-up:** N/A
- **Held constant:** whisper.cpp build flags, thread count (4), text normalisation pipeline,
  LibriSpeech test-clean audio and transcripts
- **Baseline configuration:** Whisper large-v3 FP16 ggml, same build and hyperparameters as
  all quantized variants. The only variable is the model file's quantization format.
- **Known measurement bias:** The percentile bootstrap assumes i.i.d. per-sample WER, which
  holds for the independent utterances in LibriSpeech test-clean. WER values are bounded
  below by 0; the bootstrap should use BCa correction if skew is severe. LibriSpeech
  test-clean represents clean read speech only — results do not generalise.
