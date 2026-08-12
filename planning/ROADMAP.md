# Project Roadmap

## Objective

Deliver a high-throughput, auditable research-to-live platform while keeping historical data, parameter research, release promotion, and live execution independently runnable.

## Workstreams

1. Governance and contracts.
2. Bybit/data feasibility.
3. Canonical data platform.
4. Feature/candidate platform.
5. Simulator/backtest/portfolio model.
6. Parameter selection and robustness.
7. Strategy release registry.
8. Live shadow/runtime safety.
9. Manual execution and controlled scale.
10. Production operations.

## Milestone sequence

| Milestone | Outcome | Gate |
|---|---|---|
| M0 Architecture baseline | documentation-only repository accepted | G0 |
| M1 Measured feasibility | source/layout/hardware decisions based on benchmarks | G1 |
| M2 Canonical data MVP | complete immutable market datasets and repair | G2 |
| M3 Research datasets | lookahead-safe features/candidates | G3 |
| M4 Honest simulator | path/cost/funding/risk/portfolio evidence | G4 |
| M5 Robust strategy | OOS/out-of-symbol accepted parameters | G5 |
| M6 Promoted release | immutable, independently verified strategy | G6 |
| M7 Shadow live | standalone live signals/reconciliation, no trades | G7 |
| M8 Manual live | one minimal manually approved native grid | G8 |
| M9 Controlled scale | evidence-based concurrency/size increase | G9 |
| M10 Production posture | hardened deployment, DR, optional autonomy decision | explicit |

## Planning rules

- One sprint has one measurable outcome and a narrow acceptance pack.
- Benchmark before full-scale build.
- Scale datasets in controlled stages.
- Store negative results and blockers.
- No implementation sprint may include “and also add live trading” unless that is its approved scope.
- Every sprint ends with a PM acceptance decision: accept, reject, or re-scope through change control.

For detailed requirements see [docs/14_ROADMAP_AND_GATES.md](../docs/14_ROADMAP_AND_GATES.md).
