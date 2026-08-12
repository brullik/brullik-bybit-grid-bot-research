# Data and State Contracts

## Contract principles

Every persisted dataset or runtime record has:

- explicit schema and semantic version;
- stable identity and primary key;
- UTC timestamp semantics;
- numeric units and null policy;
- parent/provenance identity;
- canonical serialization or column representation;
- validation rules;
- lifecycle status and commit marker where applicable;
- migration/compatibility policy.

A matching column name is not sufficient: units, boundary rules, source category, and meaning are part of the contract.

## Instrument snapshot

Primary identity:

```text
(snapshot_time, category, instrument_id)
```

Required concepts:

- stable internal `instrument_id`;
- exchange symbol;
- category, base, quote, settle coin;
- contract type and status;
- launch/delivery/delisting times;
- tick size and price scale;
- quantity step and min/max order quantity;
- min/max leverage;
- funding interval when applicable;
- pre-listing/innovation flags where available;
- source payload hash and snapshot metadata.

Symbol strings are attributes, not the only durable identity.

## Canonical trade-price 1m candle

Primary key:

```text
(category, instrument_id, open_time_ms)
```

Required fields:

- open time and fixed 60-second interval;
- open/high/low/close;
- volume and turnover;
- source identity;
- ingestion/batch identity;
- quality flags;
- source archive/object or API range evidence.

Invariants:

- timestamps exactly minute-aligned;
- `low <= open, close <= high` and `low <= high`;
- one canonical row per key;
- no candle before instrument launch;
- numeric values finite, non-negative where required;
- conflicting duplicate source rows are not silently resolved.

## Canonical mark-price 1m candle

Same time/instrument key pattern, distinct dataset/source contract. Fields include OHLC and quality/provenance. It must never be joined to trade candles by row order; join uses explicit category, instrument ID, and timestamp.

## Funding event

Primary key:

```text
(category, instrument_id, funding_time_ms)
```

Fields:

- funding rate;
- applicable funding interval/version;
- source and ingestion identity;
- quality flags.

Backtests join funding by the exact economic application interval, not nearest-row convenience.

## Dataset manifest

Required fields:

- dataset ID;
- dataset type;
- schema and semantic contract version;
- status: `building`, `failed`, or `complete`;
- parent dataset IDs;
- coverage bounds and instrument count;
- partition inventory;
- row counts and key statistics;
- file/object hashes;
- source evidence hashes;
- build configuration hash;
- software/environment identity;
- audit report IDs and hashes;
- commit timestamp.

Only `complete` datasets are consumable.

## Feature row

Primary key:

```text
(feature_dataset_id, category, instrument_id, decision_time_ns)
```

Required concepts:

- feature version;
- decision/availability timestamp;
- warmup completeness;
- data-quality status;
- normalized ATR/volatility/range position;
- boundary touches/crossings;
- amplitude/compression/volume/regime fields declared by version;
- parent market dataset ID.

Every feature must document its exact lookback and whether the current closed candle is included.

## Range candidate

Primary key:

```text
(candidate_dataset_id, candidate_id)
```

`candidate_id` is deterministic from instrument, decision time, candidate-rule identity, and feature version.

Fields include:

- category/instrument/symbol;
- decision time;
- lookback/window identity;
- lower/upper/mid range;
- range height in price, percent, and ATR units;
- touch/crossing/amplitude measurements;
- current position in range;
- hard-filter results and reason codes;
- ranking inputs;
- parent feature dataset and configuration hash.

## Grid outcome

Primary key:

```text
(outcome_dataset_id, candidate_id, parameter_id, ambiguity_case)
```

Fields include:

- exact grid geometry and constraints;
- entry/activation semantics;
- stop-loss and exit policy;
- leverage/investment/risk values;
- fees/funding/slippage assumptions;
- fill/event counts;
- gross/net PnL and PnL in risk units;
- max adverse/favorable excursion;
- liquidation/SL/exit results;
- duration and capital-locked time;
- intrabar ambiguity classification;
- validate-feasibility or constraint status;
- simulator version and parent candidate/market IDs.

## Experiment record

Fields include:

- experiment ID and lifecycle status;
- immutable specification hash;
- dataset/feature/candidate/outcome parent IDs;
- split/fold and embargo definitions;
- parameter search space and algorithm;
- selected candidates and rationale;
- per-fold/time/symbol/regime metrics;
- concentration, stress, ambiguity, and cost evidence;
- environment/software identity;
- report and artifact hashes.

## Strategy release

Defined in [Strategy Release Contract](09_STRATEGY_RELEASE_CONTRACT.md). It is immutable and is the only research-to-live interface.

## Live signal

Primary identity:

```text
signal_id = deterministic(release_id, category, instrument_id, decision_time, rule_id)
```

Fields include:

- release/strategy/feature version;
- complete feature snapshot or its canonical hash;
- selected parameter row and hash;
- hard-filter and risk results;
- Bybit validate evidence;
- projected exposure/loss;
- status and state-transition sequence;
- approval identity/expiry/payload hash where applicable.

## Live bot state

Required concepts:

- local bot workflow ID;
- exchange bot ID(s);
- signal/release identity;
- canonical request identity;
- exact requested and observed parameters;
- current exchange/local state;
- creation/close uncertainty flags;
- last reconciliation evidence/time;
- position, PnL, fees, funding, liquidation/SL fields where available;
- state transition version.

## Audit event

Defined by the structured envelope in [Observability, Audit, and Recovery](13_OBSERVABILITY_AUDIT_AND_RECOVERY.md). Audit records are append-only.

## Numeric policy

- Canonical market timestamps use signed integer Unix milliseconds; candle open times are exact
  multiples of 60,000. A new unit requires a new semantic/physical contract version.
- Prices/quantities/rates use Decimal/scaled integer at exact boundaries.
- Binary floats may be used only in explicitly documented analytics where round-off cannot change execution semantics.
- No implicit coercion from strings, booleans, floats, or nulls to exact contract fields.
- Every rounding direction is named and tested.

## Schema evolution

- Additive compatible changes require explicit version policy.
- Semantic changes always bump the semantic contract version even if physical columns look compatible.
- Consumers declare supported versions and fail clearly on unsupported versions.
- Migrations produce new immutable datasets; they do not rewrite an accepted dataset in place.
