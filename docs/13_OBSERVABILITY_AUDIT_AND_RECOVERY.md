# Observability, Audit, and Recovery

## Objective

Every important result must be explainable and recoverable: which data, code, configuration, release, operator decision, and exchange response produced it. Restart must resume from committed state rather than silently repeating or skipping actions.

## Three evidence planes

### 1. Research/data lineage

Tracks:

- source archive/object/API interval;
- raw and canonical object hashes;
- dataset ID and parent dataset IDs;
- schema and semantic contract versions;
- manifest, coverage, duplicate, gap, and integrity audits;
- feature/candidate/outcome/experiment lineage;
- software environment and configuration hash.

### 2. Release provenance

Tracks:

- experiment and dataset parents;
- required acceptance evidence;
- immutable member hashes;
- independent verification;
- promotion/revocation records;
- deployment compatibility.

### 3. Live operational audit

Tracks:

- service lifecycle and release identity;
- market-data gaps/repairs/freshness;
- every candidate and rejection reason;
- risk and validate evidence;
- approvals/rejections;
- canonical private API request/response metadata;
- state transitions and reconciliation decisions;
- Telegram control commands;
- incidents and emergency actions.

## Structured event envelope

Every durable audit event includes:

- event ID;
- schema version;
- occurred-at and persisted-at UTC timestamps;
- service/environment/instance ID;
- correlation ID and optional causation ID;
- release/dataset/experiment ID as applicable;
- symbol/instrument ID where applicable;
- event type and state transition;
- actor identity: system, operator, exchange;
- redacted payload or payload hash;
- outcome and reason code;
- previous-event linkage or sequence number;
- integrity checksum.

## Logs, metrics, traces, and audit are different

- **Logs** explain implementation behavior and errors; finite retention.
- **Metrics** support alerting and capacity monitoring.
- **Traces/correlation IDs** join work across components.
- **Audit records** are durable business/control evidence and cannot be replaced by ordinary logs.

## Key metrics

### Data

- source bytes/objects downloaded;
- candles/second and bytes/second;
- API request success, retry, and throttle rates;
- missing/duplicate/conflict/orphan counts;
- partition/file-size distribution;
- compaction amplification;
- committed versus building shards;
- freshness and coverage lag.

### Research

- rows scanned and pruned;
- peak memory and spill bytes;
- feature/candidate throughput;
- candidate density;
- simulation trials/second;
- cache hit ratio;
- experiment failure/retry counts;
- time per fold/regime/symbol group.

### Release

- build/verify duration;
- missing/unexpected member count;
- hash/lineage failures;
- gate failures by reason;
- promoted/revoked release count.

### Live

- market-data age and gap-repair duration;
- closed-candle-to-decision latency;
- candidates, blocked signals, approvals, creates, closes;
- private API latency/error/throttle rate;
- stream disconnect and reconciliation count;
- active/uncertain bot count;
- release verification status;
- state-store/audit durability latency;
- account equity, available balance, and governed risk exposure;
- emergency/paused status.

## Alerts

Immediate alerts:

- unknown or mismatched live exposure;
- create/close uncertain beyond threshold;
- audit/state store write failure;
- release revoked while active;
- clock drift;
- data stale beyond one decision interval;
- repeated private API authentication failure;
- emergency stop action failure;
- unrecognized operator command source.

Non-urgent alerts:

- data freshness lag;
- file-size/partition drift;
- benchmark regression;
- validation or coverage degradation;
- backup age;
- disk/RAM/cpu saturation trends.

## Idempotent restart

Each batch shard and live transition uses an explicit lifecycle:

```text
building → complete | failed
```

`complete` is the only commit marker. Restart logic:

- ignores or quarantines stale building outputs;
- verifies complete receipts before reuse;
- never infers success from file presence alone;
- resumes only missing/failed shards;
- reconciles live exchange state before new actions;
- preserves pause/emergency state.

## Backup policy

### Historical and research data

Canonical datasets are immutable and content-addressed, so backup can be incremental. Required backup targets:

- manifests, receipts, catalogs, and schema registry;
- canonical partitions not cheaply reproducible;
- strategy releases and validation evidence;
- critical experiment summaries.

Raw public archives may be retained according to reproducibility and cost policy.

### Live state

Back up:

- transactional runtime state;
- audit journal;
- release and rollback package;
- deployment configuration excluding secrets;
- promotion/revocation records.

Backups are encrypted, integrity-checked, and restored in drills.

## Recovery objectives

Provisional targets:

| Asset/process | RPO | RTO |
|---|---:|---:|
| immutable historical dataset | last committed shard | hours; rebuild/restore acceptable |
| research experiment | last committed shard | hours |
| release registry | zero committed-record loss target | under 1 hour |
| live state/audit | zero committed transition loss target | under 15 minutes to paused/reconciled state |
| live decision service | bounded rolling window can be rehydrated | under 60 minutes; no entry until reconciled |

Targets are refined after storage and deployment decisions.

## Disaster recovery sequence for live

1. isolate/stop the failed instance;
2. preserve logs and evidence;
3. revoke compromised credentials if applicable;
4. start replacement in `emergency_stopped` or `ready_paused`;
5. restore verified state/audit backup;
6. verify promoted release and configuration;
7. fetch authoritative exchange state;
8. repair rolling market window;
9. reconcile every managed symbol;
10. produce recovery report;
11. resume only through explicit owner authorization.

## Failure-injection programme

Before live scale-up, test:

- process kill before/after each mutating API boundary;
- network timeout with successful remote creation;
- duplicate/late WebSocket messages;
- REST gap-repair failure;
- state-store full/corrupt/read-only;
- audit journal unavailable;
- clock jump/drift;
- revoked/tampered release;
- API rate-limit exhaustion;
- Telegram replay/unauthorized actor;
- host restart during emergency close;
- backup restore and exchange reconciliation.

## Evidence retention

Retention is policy-driven and documented per environment. Live action and release-promotion evidence is retained long enough for full incident reconstruction. Raw debug logs with sensitive metadata have shorter retention and stricter access than immutable audit records.
