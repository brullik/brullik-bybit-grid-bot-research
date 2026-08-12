# AGENTS.md

Instructions for Codex and any other implementation agent working in this repository.

## Read first

Before proposing or changing implementation, read in this order:

1. `docs/00_PROJECT_CHARTER.md`
2. `docs/01_FINAL_GOAL_AND_SUCCESS_CRITERIA.md`
3. `docs/02_SCOPE_AND_PRINCIPLES.md`
4. `docs/04_TARGET_ARCHITECTURE.md`
5. `docs/11_RUN_MODES_AND_ISOLATION.md`
6. relevant ADRs under `docs/adr/`
7. the PM-owned acceptance criteria for the assigned milestone

## Non-negotiable constraints

- History download, research/parameter selection, release promotion, and live execution are separate applications.
- `grid-live` must run without the historical corpus, DuckDB research catalog, notebooks, optimizer, or research orchestration.
- Live may consume only a promoted, complete, hash-verified strategy release.
- No module may silently bypass risk validation or manual-approval gates.
- No production order/grid payload may use binary floating-point arithmetic for tick/quantity rounding; exact decimal/integer-step arithmetic is required at the execution boundary.
- Market-history datasets are immutable after their commit receipt.
- No future candle, future instrument metadata, future delisting knowledge, or future fee schedule may leak into a historical decision.
- Secrets, account identifiers, private exports, runtime databases, logs, and market datasets must never be committed.
- Public implementation PRs must not contain binary research artifacts or large generated datasets.

## Governance rule

Implementation PRs must not modify their own acceptance criteria, PM-owned tests, scope documents, risk policy, or promotion requirements unless the task explicitly authorizes a governance change. Any necessary change must be proposed separately and reviewed before implementation is accepted.

## Architecture-change rule

A change that affects a component boundary, dependency direction, storage layout, data contract, strategy-release contract, risk model, or live safety behavior requires an ADR or an update to an existing ADR.

## Expected engineering behavior

- Prefer small, reviewable tasks and deterministic outputs.
- Add explicit schemas and version compatibility checks.
- Make write workflows preflight first, then mutate atomically.
- Use receipts/manifests as commit markers.
- Fail closed on missing, stale, conflicting, or unverified evidence.
- Design every long-running job for resume, idempotency, bounded concurrency, and auditability.
- Benchmark before optimizing and record reference hardware, dataset size, and exact command.
- Preserve a strict separation between exact canonical/runtime contracts and exploratory notebooks.

## Definition of done

A task is not complete merely because code runs once. It must satisfy the milestone acceptance checklist, tests, lint/static checks, documentation update requirements, reproducibility, and no-live-safety constraints.
