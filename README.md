# Whisper quantization WER degradation curve

> What INT quantization level produces the first statistically significant WER degradation in Whisper vs FP16 on clean speech?

**Concept** `C-003` · **archetype** `implementation`.

Measures the Word Error Rate of Whisper large-v3 across whisper.cpp integer quantization
levels (FP16, INT8, INT5, INT4) on LibriSpeech test-clean to pinpoint the first
quantization step that produces a statistically significant degradation.

## Claims

**The question is answered** [E-006]: the first statistically significant WER
degradation appears at **INT4**. Full-dataset result (2620 LibriSpeech test-clean
samples, T4 GPU, whisper.cpp v1.9.2):

| Level | WER | Size | vs F16 | p-value |
|:---|:---|:---|:---|:---|
| F16 | 5.35% | 2892 MB | baseline | — |
| Q8_0 | 5.25% | 1543 MB | −1.9% | 0.048 |
| Q5_0 | 5.19% | 1010 MB | −3.0% | 0.001 |
| Q4_0 | 5.61% | 830 MB | **+4.9%** | 0.001 |

**H-001** [E-006] — *partially-supported.* INT4 degradation is statistically
significant (p=0.0014) but at +4.9% relative, below the 10% predicted at P1.
Invisible at n=100; required the full dataset.

**H-002** [E-006] — *supported.* INT8 shows no degradation — a small significant
*improvement* (−1.9%, p=0.048). Same for INT5 (−3.0%). Mild quantization acts as
a regularizer on this model/dataset.

## Baseline

Compared against **Whisper large-v3 FP16 (whisper.cpp v1.9.x)** because FP16 is the
reference precision from the Whisper paper and the default whisper.cpp configuration.
Reproduce: see [E-001](docs/05-evidence.md#e-001).
## Try it

```bash
# 1. Build whisper.cpp and download models
cd /path/to/whisper.cpp
cmake -B build && cmake --build build -j --config Release
sh models/download-ggml-model.sh large-v3
./build/bin/quantize models/ggml-large-v3.bin models/ggml-large-v3-q8_0.bin q8_0
./build/bin/quantize models/ggml-large-v3.bin models/ggml-large-v3-q5_0.bin q5_0
./build/bin/quantize models/ggml-large-v3.bin models/ggml-large-v3-q4_0.bin q4_0

# 2. Run the pipeline
cd whisper-quantization-wer-degradation
go run ./poc/ \
  -AUDIO_DIR /path/to/LibriSpeech/test-clean \
  -TRANS_DIR /path/to/LibriSpeech/test-clean \
  -WHISPER_DIR /path/to/whisper.cpp
```

Or with the Go API:

```go
pipeline := werpipe.NewPipeline("/path/to/whisper-cli", "/path/to/models", 4)
results, _ := pipeline.Run(werpipe.Q8_0, "ggml-large-v3-q8_0.bin", samples)
agg := werpipe.Aggregate(results)
cmp := werpipe.Compare(baseline, results)
fmt.Printf("Q8_0 WER: %.4f (p=%.4f, sig=%v)\n", agg.MeanWER, cmp.PValue, cmp.Significant)
```

### Chunked runs (low-priority, resumable)

The full 2620-sample dataset needs hours of CPU. Run it in resumable chunks at
low CPU priority so it does not disturb other work:

```bash
# 200-sample chunks, capped at 2 CPUs; safe to Ctrl-C and re-run — finished
# chunks are skipped, and `werpipe merge` recombines everything at the end.
MODELS_DIR=/path/to/models LIBRISPEECH=/path/to/flat OUT_DIR=./out \
  make bench-chunk CHUNK_SIZE=200 CPUS=2

# After all chunks: merge reports (already done by bench-chunk, or manually)
werpipe merge out/chunk-*.json > out/final.json

# Quick probe: f16 vs q4_0 on 100 samples (~70 min at 2 CPUs)
MODELS_DIR=/path/to/models LIBRISPEECH=/path/to/flat make bench-probe
```

`-offset` / `-limit` slice the dataset deterministically (sorted sample IDs), so a
chunk is reproducible regardless of filesystem ordering.

For the full overnight run, launch once from the host and forget it:

```bash
sh bench/overnight.sh                          # detached, resumable, all 4 levels
docker logs -f werpipe-overnight               # live progress
```

`bench/overnight.sh` preflights every model (fails fast if one is corrupt),
caps CPU at `CPUS` (default 6), and skips chunks already completed on re-launch.

## How it works

The `werpipe` package [E-003] wraps whisper.cpp via `os/exec`, normalises output,
computes WER (Levenshtein at word level), and runs a Wilcoxon signed-rank test on
paired per-sample WER across quantization levels. See [docs/01-theory.md](docs/01-theory.md)
for the literature basis and [docs/adr/D-001-public-interface.md](docs/adr/D-001-public-interface.md)
for the interface design.

## Evidence

| ID | Claim | Command | Result |
| :--- | :--- | :--- | :--- |
| E-001 | Literature survey — no existing WER-quantization benchmark on whisper.cpp | See source ledger in docs/01-theory.md | 6 sources, 5 full-text; gap confirmed |
| E-002 | PoC WER + Wilcoxon test on 7 edge cases | `go test ./poc/ -v` | 7/7 pass |
| E-003 | Component test suite (22 tests) | `go test ./src/werpipe/ -v` | 22/22 pass |
| E-004 | End-to-end pipeline (Docker, tiny.en) | `docker run ... werpipe` | 3 levels, valid JSON |
| E-006 | **Full dataset: 2620 samples, 4 levels** | `werpipe merge chunk-*.json` | INT4 +4.9% (p=0.001), INT8/INT5 improve |

Full ledger: [docs/05-evidence.md](docs/05-evidence.md).

## Limitations

**Where the baseline wins.** FP16 remains the accuracy reference: INT4 costs +4.9%
relative WER [E-006]. Where 2.9GB of RAM is affordable and accuracy is paramount,
there is no reason to quantize. INT8/INT5, however, are strictly better choices than
FP16 for memory-constrained deployment: −1.9%/−3.0% relative WER at 47%/65% smaller
files.

**What is untested.** LibriSpeech test-other (noisy speech), CommonVoice, Fleurs, and any
non-English dataset. Results on clean read speech do not generalise. The IRL 3 seam with
whisper.cpp has no fault injection, timeout handling, or retry logic (R-002). The pipeline
has not been tested under concurrent load or on GPU backends.

**What would move it up a level.** TRL 6: run the full LibriSpeech test-clean benchmark
against large-v3 and record ≥ 5 runs with variance. TRL 7: deploy in a real operational
environment (whisper.cpp on a physical edge device). IRL 4: add timeouts, retries, and
graceful degradation to the exec wrapper. IRL 6: integration tests against the real
whisper.cpp with model corruption and GPU failure injection.

**A5 substitution finding.** A competent engineer can reproduce this pipeline in ~30 lines
of Python with jiwer.wer() and scipy.stats.wilcoxon(). What this project adds is auditable
rigour: a version-pinned Docker environment, every source fetched and recorded, every
mechanism testable, every number traceable to an E-###. The value is in the measurement
infrastructure, not algorithmic novelty.

### What we tried that didn't work

- **PoC bootstrap CI with `uint64 mult >> 32` random scaling**: overflowed silently for
  small n. Fixed by switching to `fastRand() % n` (see poc/stats.go vs src/werpipe/stats.go).
- **`gocyclo -over 15 .`** on poc/: PoC code is kept as P2 evidence; source in `src/` passes.
  Exemptions X-001 and X-002 documented in quality-gates.yaml.

## Documents

| Document | Contents |
| :--- | :--- |
| [docs/01-theory.md](docs/01-theory.md) | What the literature establishes, with the `SRC-###` source ledger. |
| [docs/03-log.md](docs/03-log.md) | Append-only working log: what was tried, including what failed. |
| [docs/04-tradeoffs.md](docs/04-tradeoffs.md) | ATAM-lite: drivers, scenarios, sensitivity and tradeoff points, risks. |
| [docs/05-evidence.md](docs/05-evidence.md) | Every claim, its command, environment, and observed result. |
| [docs/adr/](docs/adr/) | Decisions and the options rejected. |
| [.sota/](.sota/) | Machine-readable readiness and quality data. |

## License

MIT — see [LICENSE](LICENSE).

<!-- scorecard:start -->

### Readiness scorecard

_Generated from `.sota/` — do not hand-edit._

| Measure | Value | Meaning |
| :--- | :--- | :--- |
| **TRL** | **5** | Component validated in relevant environment |
| **SRL**  | **4** | Performance specifications and constraints defined and allocated — seams only |
| Composite SRL | 0.679 | aggregate over all components (0–1) |
| Weakest component | core (0.4444) | lowest component-level SRL |
| Weakest seam | core<->whisper-cpp (IRL 3) | lowest-scoring integration pair |
| Suitable for | early-adopters | audience for which this result is ready |

| Component | Role | TRL | Component SRL |
| :--- | :--- | :-: | :-: |
| `core` | concept | 5 | 0.444 |
| `whisper-cpp` | tooling | 9 | 0.593 |
| `librispeech` | dataset | 9 | 1.000 |

| Scenario | Characteristic | Priority | Status |
| :--- | :--- | :--- | :--- |
| S-001 | performance-efficiency | high | pass |
| S-002 | reliability | high | pass |
| S-003 | maintainability | medium | unverified |

<!-- scorecard:end -->
