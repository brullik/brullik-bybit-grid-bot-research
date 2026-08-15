# Backtest and Validation Architecture

## Purpose

The backtest must estimate how the complete decision, selection, risk, and execution policy would have behaved using only information available at each historical timestamp.

ADR-0100 freezes the design-only Phase 4 boundary while Gate 3 remains closed. Outcome builds bind
explicit immutable candidate/future-path/policy sources, admit no simulated action before declared
activation, share exact grid/risk primitives with later live payload preparation, and expose rather
than guess one-minute event-order ambiguity. See the
[M4 implementation plan](../planning/M4_OUTCOME_SIMULATOR_IMPLEMENTATION_PLAN.md). P-007 and P-008
remain owner-controlled and no primary Gate 4 qualification is permitted until they are resolved.

## Validation hierarchy

1. Unit and synthetic invariants.
2. Single-candidate path tests.
3. Symbol-period integration tests.
4. Train/validation parameter selection.
5. Walk-forward test.
6. Out-of-symbol test.
7. Stress and adversarial periods.
8. Portfolio and capital constraints.
9. Monte Carlo/order-resampling analysis.
10. Shadow-live comparison.

## Required splits

ADR-0101 requires split compilation to bind both decision time and the complete future-information
interval used by each outcome. Boundary-crossing labels are purged rather than assigned by decision
time alone; out-of-symbol stable IDs and the logical final-test lifecycle are frozen before
selection. P-007/P-008 and all qualifying thresholds remain owner-controlled.

### Time split

Use chronological train, validation, and final test periods. No random row split for time-dependent strategy selection.

### Walk-forward

For each fold:

- build/select using only prior data;
- freeze parameters and universe rules;
- evaluate the next unseen interval;
- roll forward and repeat.

### Out-of-symbol

Hold out a group of instruments from all parameter selection. Evaluate whether the rule generalizes beyond symbols used for discovery.

### Instrument lifecycle

At each historical date, include only instruments that were then eligible, listed, and sufficiently warmed up. Future survivorship and delisting knowledge are prohibited.

## Cost and execution model

Required inputs:

- maker/taker fee assumptions and effective schedule;
- funding timestamps and rates;
- trade-price and mark-price path;
- tick size, quantity step, min/max investment and leverage;
- native grid validation constraints;
- signal-to-create latency assumptions;
- rejected/timeout/create failure scenarios;
- close behavior and fees;
- SL and liquidation-distance checks;
- capital reserved/locked while a grid is active.

## Intrabar ambiguity

A 1m OHLC candle may touch multiple levels without revealing the order. The simulator must expose ambiguity. Allowed policies:

- conservative worst-case ordering;
- interval/bounds result showing best and worst possible PnL;
- exclude from primary result with a reported exclusion rate;
- use higher-resolution evidence for the affected subset if available.

Selecting a favorable sequence is forbidden.

## Primary metrics

- net PnL after fees/funding;
- PnL in `R`, where current baseline 1R = 5 USDT maximum planned loss;
- expected value per accepted signal;
- profit factor;
- max portfolio drawdown;
- worst 1% and expected shortfall;
- consecutive losses;
- capital utilization and capital-locked minutes;
- duration distribution;
- signal and accepted-trade frequency;
- max simultaneous eligible signals;
- Bybit validate pass rate;
- rejection/failure rate;
- contribution concentration by symbol/time/regime;
- rolling-period consistency;
- recovery time.

Win rate and gross ROI are secondary and cannot independently qualify a strategy.

## Hard rejection examples

A candidate release is rejected if any mandatory gate is violated, including:

- non-positive out-of-sample expectancy;
- unresolved lookahead or data lineage issue;
- gross-positive but net-negative result after costs;
- unacceptable profit concentration;
- materially different behavior on held-out symbols;
- unacceptable drawdown/risk-of-ruin;
- excessive capital lock under the available 500 USDT assumption;
- low validation feasibility;
- unstable result under small parameter perturbations;
- failure under documented restart/rejection/latency assumptions;
- incomplete or unverified evidence.

Numeric thresholds are owned by the acceptance-gate document and may be revised only through change control before the final test is inspected.

## Selection-bias controls

- Register parameter search space before final evaluation.
- Preserve every tested configuration and run status.
- Use nested selection where practical.
- Limit adaptive manual retuning after seeing holdout results.
- Measure sensitivity around selected parameters.
- Report number of trials and effective degrees of freedom.
- Use deflated/adjusted performance measures where appropriate.

## Portfolio simulation

A single-signal backtest is insufficient. Portfolio simulation must reproduce:

- one active grid per symbol;
- rank ordering when capital is insufficient;
- active-bot limit;
- reserved cash and exact risk budget;
- cooldown and duplicate-signal policy;
- manual approval delay/rejection in early live stages;
- failed or uncertain Bybit actions;
- emergency-stop periods;
- no new entries during stale data or incomplete reconciliation.

## Required reports

- dataset and methodology summary;
- split/fold definition;
- parameter-selection trace;
- aggregate and per-fold metrics;
- per-symbol/time/regime concentration;
- tail and drawdown analysis;
- duration/capital lock;
- fee/funding attribution;
- ambiguity analysis;
- validate feasibility;
- stress results;
- Monte Carlo results;
- known limitations;
- pass/reject conclusion against frozen gates.
