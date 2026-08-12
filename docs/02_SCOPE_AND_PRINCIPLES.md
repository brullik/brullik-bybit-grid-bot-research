# Scope and Principles

## In scope

- Bybit public and authenticated APIs required for linear USDT perpetual research and native Futures Grid Bot operation.
- Up to 700 instruments and up to ten years of 1m history capacity.
- Instrument lifecycle and metadata snapshots.
- Trade-price OHLCV, mark-price OHLC, funding history, and required fee/risk metadata.
- High-throughput local-first data lake with a cloud-ready storage abstraction.
- Horizontal range/consolidation detection.
- Neutral + Geometric native futures-grid parameter research.
- Backtesting, walk-forward testing, out-of-symbol testing, stress testing, and Monte Carlo analysis.
- Immutable strategy releases and owner-controlled promotion.
- Live public-market ingestion, signal generation, risk checks, manual approval, execution, monitoring, reconciliation, Telegram operations, and incident handling.

## Out of scope for V1

- Other exchanges.
- Spot grid, DCA, martingale, copy trading, or non-neutral grid modes.
- A custom grid built directly from ordinary orders.
- Tick-level or full-depth order-book backtesting.
- Machine learning before a deterministic rules baseline is proven.
- Trailing up/down.
- Automatic strategy retraining or self-modification in live.
- Autonomous production deployment before explicit owner approval.
- Multi-tenant operation.
- High-frequency trading latency targets.

## Non-negotiable principles

### 1. Separate runtimes

History, research, release, and live are separate applications with separate dependency sets, credentials, and storage permissions.

### 2. Live is small

Live loads a promoted release and only the rolling history needed for current features. It does not query the historical lake.

### 3. Evidence before mutation

Every write or live action performs preflight validation first. A receipt/commit marker is written only after success.

### 4. Immutable committed artifacts

Committed market datasets, experiment inputs, outcome datasets, and strategy releases are immutable. Corrections create new versions.

### 5. Exchange state is authoritative

After restart or ambiguity, live queries/reconciles Bybit state. It never assumes a timed-out create/close call failed.

### 6. No lookahead

Historical decisions use only data, metadata, fees, universe membership, and product status known at the decision time.

### 7. Exact execution math

Research may use high-throughput floating-point analytics where error bounds are acceptable; execution payloads use exact decimal or integer tick/step arithmetic and current instrument constraints.

### 8. Optimize measured bottlenecks

Start with Python orchestration, Polars, DuckDB, Arrow, and Parquet. Add Rust/native kernels only behind stable interfaces after profiling proves a bottleneck.

### 9. Fail closed

Missing evidence, stale data, incompatible release versions, unresolved state, or unavailable risk calculation blocks new entries.

### 10. Acceptance criteria are external to implementation

Implementation cannot redefine its own scope or passing conditions.
