# Glossary

**Acceptance gate** — Required, evidenced conditions before the next delivery or risk phase is allowed.

**Ambiguity case** — One conservative interpretation of price movement when 1m OHLC does not reveal intrabar order.

**Audit journal** — Append-only durable record of business/control events, separate from ordinary logs.

**Canonical dataset** — Validated, normalized, immutable dataset with a complete manifest and commit marker.

**Candidate** — A lookahead-safe range/consolidation event eligible for more expensive outcome simulation.

**Capacity target** — The scale the architecture must handle without redesign: 700 instruments × 10 years × 1m.

**Commit marker** — Explicit receipt/status proving a shard or dataset completed successfully; file presence alone is not completion.

**Compaction** — Rewriting validated small source fragments into efficient immutable analytical files without changing semantics.

**Content identity** — Hash/ID derived from exact parents, contract versions, configuration, and content.

**Cooldown** — Period/condition preventing immediate reuse of a symbol after a grid closes.

**Data lake/store** — Historical immutable Parquet datasets and their manifests; not accessible to live.

**Dataset ID** — Stable identifier for one immutable dataset version.

**Decision time** — Timestamp at which a signal could have been known using only available, closed inputs.

**Fail closed** — Refuse new exposure when evidence or state is missing, stale, incompatible, or uncertain.

**Feature kernel** — Deterministic computation of strategy inputs shared by batch research and live rolling evaluation.

**Feature parity** — Proof that batch and live compute the same feature outputs under the same contract.

**Gap repair** — Deterministic recovery of missing historical/current intervals with provenance and re-audit.

**Halo** — Read-only overlap around a shard, used for rolling warmup while writing only the core interval.

**Instrument ID** — Stable internal integer identity; symbol text remains an attribute.

**Lookahead** — Use of information not available at the historical decision time; prohibited.

**Mark price** — Exchange-derived reference price used in derivatives risk/liquidation contexts, stored separately from trade price.

**Native grid** — Bybit’s own Futures Grid Bot API/product rather than a locally emulated set of limit orders.

**Neutral + Geometric** — Baseline native grid direction/mode and geometric spacing policy for V1.

**Outcome** — Simulated future behavior and PnL/risk evidence for one candidate and parameter set.

**Parameter ID** — Stable identity for one exact parameter tuple and applicability policy.

**PM-owned acceptance** — Scope/tests controlled outside an implementation PR so the implementer cannot redefine success.

**Promoted release** — Immutable, verified strategy bundle explicitly authorized for a given live mode.

**Provenance** — Trace from an artifact to parent data, configuration, software, and decisions.

**Receipt** — Machine-readable evidence for a completed operation/shard, including hashes and counts.

**Reconciliation** — Comparison of local expected state with authoritative exchange state, resolving mismatches before new actions.

**Release bundle** — Versioned package containing strategy, features, parameters, risk/execution policy, compatibility, and validation evidence.

**Research store** — Feature, candidate, outcome, experiment, and report datasets; read by research/release, never live.

**Risk unit (R)** — Project-defined per-trade loss unit; current baseline models 1R as 5 USDT.

**Rolling window** — Bounded recent market data maintained by live for current feature computation.

**Shadow mode** — Live market processing and signals with no mutating exchange action.

**Source evidence** — Archive/API identity, hash, request range, and retrieval metadata proving input origin.

**Strategy release registry** — Append-only store of building/verified/promoted/revoked immutable releases.

**Uncertain state** — A mutating request may or may not have succeeded remotely; blind retry is prohibited.

**Universe snapshot** — Instrument set and metadata valid at a specific historical/current time.
