# Work Breakdown Structure

## 0. Project governance

- 0.1 final goal/scope;
- 0.2 ADR process and decision register;
- 0.3 PM-owned acceptance framework;
- 0.4 repository/branch/security controls;
- 0.5 release/change/incident governance.

## 1. Feasibility and benchmarks

- 1.1 Bybit instrument/universe/API inventory;
- 1.2 bulk archive coverage inventory;
- 1.3 representative raw sample acquisition;
- 1.4 canonical schema/encoding candidates;
- 1.5 partition/file/compression benchmark;
- 1.6 feature throughput/memory benchmark;
- 1.7 storage/hardware plan;
- 1.8 native grid validate/account feasibility.

## 2. Historical data platform

- 2.1 source registry and downloader;
- 2.2 instrument snapshots and stable identity;
- 2.3 raw landing/evidence;
- 2.4 trade 1m canonicalization;
- 2.5 mark-price 1m canonicalization;
- 2.6 funding canonicalization;
- 2.7 manifests/receipts/atomic commit;
- 2.8 audits: coverage/gap/duplicate/conflict/orphan/hash;
- 2.9 incremental sync and gap repair;
- 2.10 compaction/catalog/retention;
- 2.11 full available universe build.

## 3. Research data platform

- 3.1 decision-time contract;
- 3.2 shared rolling feature kernel;
- 3.3 deterministic shard/halo execution;
- 3.4 range candidate detector;
- 3.5 amplitude/narrow-range classification;
- 3.6 candidate deduplication/ranking inputs;
- 3.7 feature/candidate manifests and audits.

## 4. Simulator and backtest

- 4.1 geometric grid math;
- 4.2 exchange precision/constraint model;
- 4.3 fill/event state machine;
- 4.4 fees/funding/slippage;
- 4.5 SL/liquidation/close behavior;
- 4.6 intrabar ambiguity bounds;
- 4.7 portfolio capital/concurrency allocator;
- 4.8 metrics, drawdown, concentration, risk-of-ruin;
- 4.9 golden/adversarial fixtures;
- 4.10 performance optimization.

## 5. Parameter selection

- 5.1 frozen splits/embargo/universe history;
- 5.2 experiment specification/registry;
- 5.3 efficient candidate/parameter evaluation;
- 5.4 stability and perturbation analysis;
- 5.5 regime/time/symbol robustness;
- 5.6 stress and Monte Carlo;
- 5.7 independent review pack;
- 5.8 select/reject decision.

## 6. Strategy release

- 6.1 release schema and allowlist;
- 6.2 deterministic builder;
- 6.3 independent verifier;
- 6.4 promotion/revocation/rollback registry;
- 6.5 compatibility and expiry;
- 6.6 tamper/failure acceptance pack.

## 7. Live shadow

- 7.1 slim runtime/build isolation;
- 7.2 current WebSocket/REST market gateway;
- 7.3 rolling feature parity;
- 7.4 signal and risk manager;
- 7.5 transactional state/audit;
- 7.6 exchange/local reconciliation;
- 7.7 Telegram read/control plane;
- 7.8 restart/failure injection;
- 7.9 30-day/100-signal shadow evidence.

## 8. Manual live execution

- 8.1 dedicated restricted credentials/subaccount;
- 8.2 validate and exact risk payload;
- 8.3 approval binding;
- 8.4 native create/detail/close adapter;
- 8.5 uncertain request protocol;
- 8.6 one-bot minimal-mainnet drill;
- 8.7 emergency and recovery drill;
- 8.8 owner acceptance.

## 9. Scale and operations

- 9.1 live/backtest drift monitoring;
- 9.2 staged concurrency/size limits;
- 9.3 backup/restore/DR;
- 9.4 secret rotation/IP allowlist;
- 9.5 host hardening and monitoring;
- 9.6 incident management;
- 9.7 autonomy decision, if justified.

ADR-0106 and the M10 production-hardening plan govern 9.3 through 9.7 after Gate 9. Production
readiness does not require autonomy; the autonomous capability remains absent unless a separate
owner governance decision is later justified by evidence.
