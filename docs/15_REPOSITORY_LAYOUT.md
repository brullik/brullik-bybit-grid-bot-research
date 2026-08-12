# Planned Repository Layout

## Purpose

This document plans the monorepo through live readiness. The current documentation baseline deliberately does not create application code.

```text
brullik-bybit-grid-bot-research/
├── README.md
├── README.ru.md
├── AGENTS.md
├── CONTRIBUTING.md
├── SECURITY.md
├── CHANGELOG.md
├── LICENSE_POLICY.md
├── .gitignore
├── .github/
│   ├── CODEOWNERS
│   ├── pull_request_template.md
│   └── ISSUE_TEMPLATE/
├── docs/
│   ├── 00_PROJECT_CHARTER.md ... 20_REFERENCES.md
│   ├── adr/
│   └── ru/
├── governance/
│   ├── DEFINITION_OF_DONE.md
│   ├── ACCEPTANCE_GATES.md
│   ├── CHANGE_CONTROL.md
│   └── REVIEW_CHECKLIST.md
├── planning/
│   ├── ROADMAP.md
│   ├── WORK_BREAKDOWN_STRUCTURE.md
│   ├── SPRINT_00_DOCUMENTATION_BASELINE.md
│   └── BACKLOG.md
├── apps/
│   ├── data/           # future grid-data entrypoint and orchestration
│   ├── research/       # future grid-research entrypoint and orchestration
│   ├── release/        # future grid-release entrypoint and orchestration
│   └── live/           # future grid-live entrypoint and orchestration
├── packages/
│   ├── contracts/      # stable cross-application schemas and identities
│   ├── bybit-public/   # public API/archive adapters
│   ├── bybit-private/  # private API; live-only dependency
│   ├── market-store/   # Parquet manifests, audit, catalog, compaction
│   ├── feature-kernel/ # deterministic batch/live feature semantics
│   ├── strategy-core/  # candidate/ranking/parameter lookup semantics
│   ├── simulator/      # research-only grid/outcome engine
│   ├── risk-core/      # shared exact risk rules; no network side effects
│   └── audit/          # canonical events, receipts, evidence contracts
├── schemas/            # versioned machine-readable contracts
├── configs/
│   ├── examples/       # non-secret examples only
│   └── schemas/
├── tests/
│   ├── unit/
│   ├── contract/
│   ├── integration/
│   ├── acceptance/
│   ├── performance/
│   ├── failure_injection/
│   └── fixtures/
├── benchmarks/
│   ├── datasets/
│   ├── specifications/
│   └── results/        # small reports, never large market data
├── scripts/            # thin developer/CI wrappers only
└── ops/
    ├── runbooks/
    ├── deployment/
    ├── monitoring/
    └── backup_recovery/
```

## Application responsibilities

### `apps/data`

Owns orchestration for acquisition, normalization, validation, incremental updates, repair, and compaction. It does not contain feature or strategy logic and cannot access private trading credentials.

### `apps/research`

Owns orchestration for feature/candidate/outcome builds, experiments, backtests, robustness, and reports. It consumes immutable complete market datasets read-only and cannot execute trades.

### `apps/release`

Owns strategy bundle build, verify, promote, revoke, and rollback metadata. It does not choose parameters; it packages already-reviewed evidence.

### `apps/live`

Owns bounded current market data, signal evaluation from one promoted release, risk, approval, execution, reconciliation, state, and control plane. It does not depend on `apps/data` or `apps/research`.

## Package rules

- A package has one clear owner and contract.
- Cross-application imports go through a small stable package, not another app.
- Network side effects are isolated behind explicit adapters.
- Pure domain logic remains deterministic and testable.
- `bybit-private` is not an allowed dependency of data, research, or release.
- `simulator` is not an allowed dependency of live.
- `market-store` is not an allowed dependency of live.
- `feature-kernel` supports batch/live parity but has no storage or network orchestration.
- Contracts are backward-compatible within a declared support window.

## Test ownership

| Test class | Owner | Purpose |
|---|---|---|
| unit | implementation team | local invariants and edge cases |
| contract | PM/architecture + implementation | schemas and cross-boundary compatibility |
| integration | implementation | real component interactions with controlled fixtures |
| acceptance | PM-owned | prove frozen sprint criteria; implementation PR cannot weaken |
| performance | architecture/PM-owned specs | measured scale and regression thresholds |
| failure injection | live safety owner | restart, uncertainty, emergency, corruption behavior |

## Data excluded from Git

The repository never stores:

- historical candle/funding datasets;
- generated feature/outcome stores;
- API keys or `.env` secrets;
- private Telegram configuration;
- large benchmark inputs;
- runtime state databases;
- logs with account-sensitive payloads;
- mutable promoted release registry.

Only small synthetic fixtures, schemas, manifests, redacted examples, and benchmark reports are committed.

## Branch and PR model

- `main` is protected and always represents accepted architecture/implementation state.
- Work is delivered through small, single-purpose branches and pull requests.
- Every PR states motivation, scope, non-goals, evidence, and rollback.
- Acceptance tests and scope are restored from the base branch during implementation PR validation.
- Binary files require explicit justification and governance.

## Versioning

Separate versions are maintained for:

- repository/application release;
- dataset schema and semantic contracts;
- feature/candidate/outcome contracts;
- strategy release schema;
- live state/audit schema;
- promoted strategy semantic version.

Version numbers are not interchangeable.
