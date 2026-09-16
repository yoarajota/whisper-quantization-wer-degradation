<!-- scorecard:start -->

# Readiness scorecard

_Machine-generated from this repository's readiness data — do not hand-edit._

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
