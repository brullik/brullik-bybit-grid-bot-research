# Run Modes and Isolation

## Goal

History acquisition, research/parameter selection, strategy release, and live operation are independent commands and deployment units. Starting live must not implicitly start a downloader, scan the historical store, run an optimizer, rebuild features, or require research-only dependencies.

## Planned applications

| Application | Typical command family | Runtime purpose | Network | Secrets | Main storage |
|---|---|---|---|---|---|
| `grid-data` | `grid-data ...` | acquire, normalize, audit, repair, compact history | Bybit public endpoints / archive host | none for public data | historical market store |
| `grid-research` | `grid-research ...` | build features/candidates/outcomes, backtest, search, report | normally disabled | none | read-only history + derived stores |
| `grid-release` | `grid-release ...` | build, verify, promote, revoke strategy bundles | not required | signing/promotion identity only | release registry |
| `grid-live` | `grid-live ...` | current signals, risk, approval, execution, reconciliation | Bybit public/private + Telegram | trade key without withdrawal | small live state store |

The package boundaries are implemented. Phase 2 currently exposes stable-registry publication,
no-mutation history preflight, bounded public 1m acquisition, completed-Landing verification, and
receipt-last canonical publication, fail-closed coverage audit, and no-network gap-repair
planning, receipt-resumable repair execution, immutable replacement lineage, and target-size
immutable compaction plus receipt-verified DuckDB catalog registration and snapshot-bound range
selection. A separate public funding path now includes predecessor-bound, receipt-resumable
acquisition, exact receipt-last canonical publication, fail-closed source-chronology audit, and
single-type registration/selection through the same receipt-verified catalog.
Funding-specific pilot evidence and a fail-closed source-chronology audit remain separate
read-only commands; neither uses current undated interval metadata.
Multi-month public acquisition is now a separate `history-campaign` coordinator over those same
child boundaries. It has no research, catalog, live, credential, or private-endpoint dependency.
On resume, completed immutable Landing children use ADR-0046 receipt/hash integrity verification
once per command and are reused only in-process; partial children and explicit semantic verifiers
retain exact source-row decoding. This changes no request, retry, pacing, or completion contract.
Both candle and funding child executors apply the ADR-0043 shared decrease-only response-header
pacer and receipt its sanitized observations; HTTP 403 aborts the resumable child rather than
retrying through the documented IP-ban interval.
Canonical campaign publication is a second `grid-data` coordinator: it consumes only a completed
campaign, runs the existing receipt-last writers sequentially, and has no Bybit network client.

## Separate startup examples

Planned operator intent:

```text
# Stable identities and bounded historical download only
grid-data instrument-registry --instrument-inventory <inventory.json> --output <registry.json>
grid-data instrument-timeline --instrument-registry <registry-1.json> \
  [--instrument-registry <registry-2.json> ...] --output <timeline.json>
grid-data verify-instrument-timeline <timeline.json>
grid-data instrument-timeline-summary --timeline <timeline.json> \
  --software-identity git:<full-commit-sha> --output <sanitized-summary.json>
grid-data announcement-archive-depth --instrument-registry <registry.json> \
  --instrument-id <id> [--instrument-id <id> ...] \
  --software-identity git:<full-commit-sha> --output <sanitized-depth-evidence.json>
# This makes at most 16 public responses, persists no announcement body, and never closes Gate 2.
grid-data history-1m --request <request.json> --instrument-registry <registry.json> \
  --capacity-evidence <capacity.json> --staging-root <local-path>
# Repeat with --execute only after the printed no-mutation preflight is accepted.
grid-data verify-history-1m <completed-job-root>
grid-data history-campaign --request <campaign-request.json> \
  --instrument-registry <registry.json> --capacity-evidence <capacity.json> \
  --staging-root <local-path>
# Repeat with --execute only after aggregate no-mutation preflight; children run sequentially.
grid-data verify-history-campaign <completed-campaign-root>
grid-data publish-history-campaign --campaign-root <completed-campaign-root> \
  --instrument-registry <registry.json> --capacity-evidence <capacity.json> \
  --store-root <local-path> --software-identity git:<full-commit-sha> --prepare-plan
# Review the prepared summary, then execute/resume from the printed receipt-bound root.
grid-data publish-history-campaign --campaign-root <completed-campaign-root> \
  --instrument-registry <registry.json> --capacity-evidence <capacity.json> \
  --store-root <local-path> --software-identity git:<full-commit-sha> --execute \
  --publication-root <store>/.publication-campaigns/<prepared-root>
# Pending children are serial and each is semantically preflighted immediately before mutation.
grid-data verify-history-campaign-publication \
  <store>/.publication-campaigns/<publication-campaign-root> \
  --campaign-root <completed-campaign-root>
grid-data publish-history-1m --job-root <completed-job-root> \
  --instrument-registry <registry.json> --capacity-evidence <capacity.json> \
  --store-root <local-path> --software-identity git:<full-commit-sha>
# Repeat with --execute only after the printed no-mutation preflight is accepted.
grid-data verify-canonical-candle <committed-dataset-root>
grid-data funding-history --request <funding-request.json> \
  --instrument-registry <registry.json> --capacity-evidence <capacity.json> \
  --staging-root <local-path>
# Repeat with --execute only after the printed no-mutation preflight is accepted.
grid-data verify-funding-history <completed-funding-job-root>
grid-data publish-funding-history --job-root <completed-funding-job-root> \
  --instrument-registry <registry.json> --capacity-evidence <capacity.json> \
  --store-root <local-path> --software-identity git:<full-commit-sha>
# Repeat with --execute only after the printed no-mutation preflight is accepted.
grid-data verify-canonical-funding <committed-funding-dataset-root>
grid-data audit-funding-history --job-root <completed-funding-job-root> \
  --instrument-registry <registry.json> --capacity-evidence <capacity.json> \
  --store-root <local-path> --publisher-software-identity git:<publisher-commit-sha> \
  --audit-software-identity git:<auditor-commit-sha> --output <funding-audit-evidence.json>
grid-data history-pilot-evidence --job-root <completed-job-root> \
  --instrument-registry <registry.json> --capacity-evidence <capacity.json> \
  --store-root <local-path> --software-identity git:<full-commit-sha> \
  --output benchmarks/results/<sanitized-pilot-evidence>.json
grid-data audit-history-1m --job-root <completed-job-root> \
  --instrument-registry <registry.json> --capacity-evidence <capacity.json> \
  --store-root <local-path> --publisher-software-identity git:<publisher-commit-sha> \
  --audit-software-identity git:<auditor-commit-sha> --output <audit-evidence.json>
grid-data plan-history-repair --coverage-audit <blocked-audit.json> \
  --job-root <completed-job-root> --instrument-registry <registry.json> \
  --capacity-evidence <capacity.json> --store-root <local-path> \
  --planner-software-identity git:<planner-commit-sha> --output <repair-plan.json>
grid-data execute-history-repair --repair-plan <repair-plan.json> \
  --coverage-audit <blocked-audit.json> --job-root <completed-job-root> \
  --instrument-registry <registry.json> --capacity-evidence <capacity.json> \
  --store-root <local-path> --repair-staging-root <local-path> \
  --executor-software-identity git:<executor-commit-sha> --output <execution.json>
# Repeat with --execute only after the printed whole-plan preflight is accepted.
grid-data publish-history-repair --repair-execution <passed-execution.json> \
  --repair-plan <repair-plan.json> --coverage-audit <blocked-audit.json> \
  --job-root <completed-job-root> --instrument-registry <registry.json> \
  --capacity-evidence <capacity.json> --store-root <local-path> \
  --repair-staging-root <local-path> --software-identity git:<replacement-commit-sha> \
  --output <replacement-evidence.json>
# Repeat with --execute only after the printed no-mutation publication preflight is accepted.

# Funding chronology repair starts as private discovery-only planning.
grid-data plan-funding-repair --coverage-audit <blocked-funding-audit.json> \
  --job-root <completed-funding-job-root> --instrument-registry <registry.json> \
  --capacity-evidence <capacity.json> --store-root <local-path> \
  --planner-software-identity git:<planner-commit-sha> \
  --output <private-funding-repair-plan.json>
# This executes no market request and does not accept cadence or mutate canonical data.
grid-data execute-funding-repair --repair-plan <private-funding-repair-plan.json> \
  --coverage-audit <blocked-funding-audit.json> \
  --job-root <completed-funding-job-root> --instrument-registry <registry.json> \
  --capacity-evidence <capacity.json> --store-root <local-path> \
  --repair-staging-root <local-path> --executor-software-identity git:<executor-commit-sha> \
  --output <private-funding-repair-execution.json>
# Repeat with --execute only after the printed whole-plan preflight is accepted.
grid-data publish-funding-repair --repair-execution <passed-execution.json> \
  --repair-plan <private-funding-repair-plan.json> --coverage-audit <blocked-audit.json> \
  --job-root <completed-funding-job-root> --instrument-registry <registry.json> \
  --capacity-evidence <capacity.json> --store-root <local-path> \
  --repair-staging-root <local-path> --software-identity git:<publisher-commit-sha> \
  --output <replacement-evidence.json>
# Repeat with --execute only after the printed no-mutation publication preflight is accepted.
grid-data audit-funding-repair --repair-execution <passed-execution.json> \
  --repair-plan <private-funding-repair-plan.json> \
  --original-coverage-audit <blocked-audit.json> --job-root <completed-funding-job-root> \
  --instrument-registry <registry.json> --capacity-evidence <capacity.json> \
  --store-root <local-path> --repair-staging-root <local-path> \
  --replacement-evidence <replacement-evidence.json> \
  --publisher-software-identity git:<publisher-commit-sha> \
  --audit-software-identity git:<auditor-commit-sha> \
  --output <private-repair-coverage-audit.json>
# Existing output is receipt-verified and rebuilt; the detailed audit remains private.

# Immutable canonical maintenance (trade/mark compaction)
grid-data compact --dataset <dataset-id> [--dataset <dataset-id> ...] \
  --capacity-evidence <capacity.json> --store-root <local-path> \
  --software-identity git:<full-commit-sha> --output <compaction-evidence.json>
# Repeat with --execute only after the printed no-mutation preflight is accepted.
grid-data compact-funding --dataset <funding-id> [--dataset <funding-id> ...] \
  --capacity-evidence <capacity.json> --store-root <local-path> \
  --software-identity git:<full-commit-sha> --output <funding-compaction-evidence.json>
# Repeat with --execute only after the printed no-mutation preflight is accepted.
grid-data catalog-registration-request --publication-root <completed-publication-root> \
  --campaign-root <completed-source-campaign-root> \
  --software-identity git:<full-commit-sha> --output <private-request.json>
grid-data catalog-register --request <private-request.json> \
  --store-root <local-path> --catalog <local-path>/catalog/canonical.duckdb \
  --output <registration-evidence.json>
# Repeat with --execute only after the printed no-mutation preflight is accepted.
grid-data catalog-select --request <snapshot-bound-selection-request.json> \
  --store-root <local-path> --catalog <local-path>/catalog/canonical.duckdb \
  --output <selection-evidence.json>

# Research/parameter selection only
grid-research build-features --market-dataset <dataset-id>
grid-research build-candidates --feature-dataset <dataset-id>
grid-research run-experiment --experiment-spec <spec-id>
grid-research validate --experiment <experiment-id>

# Promotion only
grid-release build --experiment <experiment-id>
grid-release verify --release <release-id>
grid-release promote --release <release-id> --mode shadow

# Live only
grid-live start --release <promoted-release-id> --mode shadow
grid-live start --release <promoted-release-id> --mode manual-mainnet
```

None of the live commands calls a research command as a side effect.

## Dependency isolation

The planned packaging uses separate dependency groups or independently built artifacts:

- `data`: HTTP/archive readers, Arrow/Parquet, Polars, DuckDB, checksums;
- `research`: data plus simulation, statistics, reporting, experiment orchestration;
- `release`: contracts, canonical serialization, hashing, signing/verification;
- `live`: small feature kernel, contracts, current market client, state store, risk, Telegram, private Bybit adapter;
- `dev`: tests, linting, static analysis, documentation tooling.

`grid-live` must install successfully without DuckDB, notebook tooling, parameter-search frameworks, or bulk archive clients unless a measured runtime requirement justifies an exception.

## Import/dependency direction

```text
contracts ← data
contracts ← research
contracts ← release
contracts ← live

strategy-core ← research
strategy-core ← live
risk-core ← research/backtest
risk-core ← live

research ✗ live
market-store ✗ live
notebooks ✗ production packages
live ✗ research outputs except promoted release contract
```

Automated architecture tests will reject forbidden imports.

## Storage isolation

### Data application

Read/write:

- raw landing zone;
- canonical market datasets;
- audit and compaction staging;
- dataset catalog/receipts.

No access:

- trade credentials;
- live state;
- live approvals.

### Research application

Read-only:

- complete canonical market datasets;
- immutable instrument/funding metadata.

Read/write:

- feature, candidate, outcome, experiment, and report stores.

No access:

- trade credentials;
- live state;
- promoted-release mutation.

### Release application

Read-only:

- completed research evidence;
- acceptance results.

Read/write:

- building registry area;
- append-only promotion and revocation records.

No access:

- trade credentials;
- historical market mutation.

### Live application

Read-only:

- promoted release registry or deployed release package;
- rollback release.

Read/write:

- bounded runtime state and journal.

No mount/access:

- raw or canonical historical lake;
- feature/candidate/outcome stores;
- optimizer workspace.

## Credentials and operating-system identities

Preferred deployment identities:

- `grid-data`: no private exchange credentials;
- `grid-research`: no network and no credentials;
- `grid-release`: promotion/signing identity, no trade permission;
- `grid-live`: dedicated trade key, no withdrawal permission, restricted filesystem and network.

Local development may run under one user initially, but directory permissions and configuration still model these boundaries so later deployment does not require architectural changes.

## Process isolation

The applications are separate operating-system processes. A process supervisor may manage them independently, but there is no mandatory all-in-one daemon.

Allowed production combinations:

- data workstation: `grid-data` and scheduled maintenance;
- research workstation: `grid-research` and optional local `grid-release build/verify`;
- live host: `grid-live` only;
- operator workstation: promotion/revocation utility only.

## Failure isolation

- A failed historical download must not affect an already-running live instance.
- A research out-of-memory event must not affect live latency.
- A revoked release must block future live entries according to policy, even if research is offline.
- A live incident must not modify historical/research evidence.
- A live host rebuild must require only configuration, secrets, a promoted release, state backup, and exchange reconciliation—not the historical corpus.

## Configuration isolation

Each application has its own schema and refuses unknown keys. Configuration is not a shared mutable “everything YAML.” Common identifiers are explicit contracts:

- environment ID;
- dataset/release IDs;
- instrument identity version;
- feature version;
- risk policy version;
- audit schema version.

Live configuration cannot override a release with looser values. Research configuration cannot promote itself.

## Build and deployment artifacts

Planned artifacts:

- `grid-data` wheel/container;
- `grid-research` wheel/container;
- `grid-release` wheel/container;
- slim `grid-live` wheel/container;
- immutable strategy release archive;
- schema/contract package;
- SBOM and dependency lock for each deployable.

An all-in-one developer installation may exist for convenience, but it is never the production reference deployment.

## Isolation acceptance tests

Before live readiness, CI must prove:

- live builds without research dependency group;
- live starts with no historical-data path configured;
- history/research processes are absent and live still reaches shadow-ready state;
- live fails if only an experiment directory—not a promoted release—is supplied;
- research cannot load private trade credentials through its schema;
- data cannot write live state;
- architecture import rules pass;
- revocation is honored while research and data are offline.
