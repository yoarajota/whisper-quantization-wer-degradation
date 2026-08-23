# Design system — Concept artifact

The visual and content system for this directory's artifact: `index.html` +
`data.json`. `index.html` and `styles.css` are generated files — do not hand-edit;
all content comes from `data.json`, and the page files are produced by regeneration
tooling outside this repository.

## Design read

*The artifact is the concept's own document — a blogpost, not a report — for a
cold reader deciding "is this worth using or learning from?", written the way
the author would explain it out loud, in a dark-by-default midnight palette with
ice-blue accent and semantic verdict colors.*

## Binding rules

1. **The artifact is the concept's own document.** It carries no assessment-
   methodology branding, no external tool credits, no generator names — the
   concept speaks for itself. The concept's own IDs (`E-###`, `H-###`, `S-###`)
   are links into the repository, not decoration; they appear only where the
   legend and the data tables give them meaning.
2. **Never hand-edit `index.html` or `styles.css`.** They are generated. All
   content comes from `data.json`, and the page embeds a copy of it at
   generation time — `data.json` remains the canonical validated file.
3. **No CDN, no third-party script, ever, and no network at all.** Fonts are
   bundled; the chart is inline SVG; the content is embedded in the page.
   Nothing loads at read time, so the page opens by double-clicking it
   (`file://`), from Pages, or from any static host.
4. **Verdicts are never communicated by color alone.** Every chip carries its
   text label; color is redundant reinforcement (WCAG 1.4.1).

## Structure — blogpost arc, not report sections

Hook (question + one-line answer + verdict chip) → opening paragraph (drop
cap) → **legend** ("How to read this page" — the shared vocabulary, once) →
the numbers (claims, chart, reproduce-it-yourself) → what we claimed and what
happened → how ready this is → the story (and what didn't work) → what we
learned → where this falls short → should you use it → the evidence → dig
deeper (links, not a path table) → colophon (repository link only).

## Writing rules (grounded in the research doc)

- **Blogpost, not report.** Section headers are sentences-worth of signal,
  numbered nothing: "Where this falls short", never "§ 8 — Limitations".
- **No process chrome.** No concept IDs, phases, readiness numbers, or
  generation dates in the masthead, hero, or footer. The footer carries the
  repository link and nothing else.
- **The legend carries the jargon.** Identifiers (`E-###`, `H-###`, `S-###`,
  TRL, SRL, IRL, baseline, suitable-for) are explained once, in the legend
  table directly after the opening. Narrative prose glosses domain terms
  inline in plain language and never names internal machinery (ADR numbers,
  gate names, instrument names).
- **Write for one reader** — the competent engineer deciding whether to adopt
  — and the way you'd talk: conversational, short sentences, no process-speak.
- **Every claim points at its `E-###`.** Unmapped adjectives are deleted.
- **Dead ends and falsifications are loud**, never buried.
- **Internal artefacts become links.** The "dig deeper" list names human
  destinations (theory, evidence, tradeoffs, decisions) — a cold reader
  follows links; a maintainer reads the repository.

## Palette — "Midnight"

Dark by default; the `PAPER/INK` toggle switches to the light palette (persisted
in `localStorage` under `artifact-ink`, respected by `prefers-reduced-motion`).

| Token | Dark (default) | Light (toggle) | Use |
| :--- | :--- | :--- | :--- |
| `--paper` | `#171a20` | `#f6f8fb` | page background |
| `--panel` | `#22272f` | `#e9edf4` | chart, reproduce, limitation panels, legend |
| `--ink` | `#e9edf3` | `#21262f` | body text |
| `--muted` | `#99a2af` | `#5f6676` | captions, meta |
| `--line` | `#343a45` | `#dce1ec` | hairlines, table rules |
| `--accent` | `#7ca7dd` | `#3d5f9e` | links, gauges, chart series, drop cap, claim numerals |
| `--ok` / `--ok-soft` | `#7cc29b` / `#22332a` | `#2f6e4e` / `#dce9e2` | verdict `supported`, scenario `pass`, diffusion `strong` |
| `--warn` / `--warn-soft` | `#d9a05c` / `#382f1e` | `#a16207` / `#f4e8d0` | verdict `partially-supported`, diffusion `partial` |
| `--bad` / `--bad-soft` | `#d97a6e` / `#3b2724` | `#a63a3a` / `#f4dcdc` | verdict `falsified`, dead-ends panel, diffusion `weak` |
| `--idle` | `#8e97a4` | `#7e8295` | verdict `untested`, scenario `unverified`, baseline chart series |

Contrast: body ink on paper exceeds 7:1 in both modes; semantic colors are paired
with their soft backgrounds above 4.5:1, and each is always accompanied by its text.

## Typography

- **Display** (title, question, section titles, dig-deeper links): Source Serif, 600–700.
- **Body**: IBM Plex Sans, 400–600.
- **Mono** (legend terms, IDs, commands, tables, kickers, captions): IBM Plex Mono, 400–600.
- All three families are bundled OFL fonts in `fonts/` (woff2, latin) with their
  license files. No network font fetch.

## Components

Hero (kicker = domain tags, serif title, italic serif question, verdict chip +
one-line answer) · opening paragraph with drop cap · legend table · claims list
with `E-###` refs · SVG chart (optional) · reproduce panel · hypothesis
blockquotes with per-hypothesis verdict chips · TRL/SRL gauges · weakest-link
line · scenario table with status chips · diffusion chips + chasm sentence ·
journey steps · red-tinted dead-ends panel · lessons · limitations grid ·
audience · evidence table · dig-deeper links · colophon with repository link.

## States

- **Verdict chips**: `supported` filled green, `falsified` filled red,
  `partially-supported` amber outline, `untested` dashed neutral. All caps,
  letter-spaced, sans 700.
- **Scenario chips**: `pass` green soft, `fail` red soft, `unverified` dashed neutral.
- **Diffusion chips**: `strong`/`partial`/`weak` green/amber/red soft.
- **Toggle**: switches `body.ink`; the CSS palette blocks in `:root` (dark) and
  `body.ink` (light) are the only place colors are defined.

## Chart

Inline SVG, no library. `data.json` provides `chart`: title, evidence ref, caption,
`x_ticks` (log scale), `y_ticks`, `ymax`, `crossover`, `series` (one `baseline` in
dashed idle, one `concept` in accent with point dots). The renderer lives in
`index.html`; it uses CSS classes so the toggle re-colors it automatically.
The x-axis is numeric (log-scaled) only — categorical comparisons belong in the
claims list, not the chart. A chart is optional.

## Accessibility & robustness

- Responsive single column; tables scroll horizontally under 720px.
- `:focus-visible` outlines in accent; semantic landmarks; `lang="en"`;
  heading order 1→2→3.
- `@media print` forces the light palette, hides the toggle, avoids page-breaks
  inside panels.
- No console errors (favicon suppressed with `<link rel="icon" href="data:,">`).
- The page is self-contained: opening `index.html` directly in a browser works,
  no server required.
