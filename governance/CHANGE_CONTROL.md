# Change Control

## Controlled baselines

The following require explicit review and recorded change:

- final goal and system scope;
- runtime separation and dependency boundaries;
- canonical data semantics and primary keys;
- lookahead/decision-time and intrabar policies;
- risk and live authorization limits;
- strategy release member/compatibility contract;
- acceptance gates and PM-owned tests;
- emergency and reconciliation behavior;
- security/credential policy.

## Change classes

### Class A — editorial

Spelling, formatting, clarification with no semantic effect. Normal PR review.

### Class B — compatible implementation/design

Adds behavior within accepted contracts. Requires tests/evidence and affected-owner review.

### Class C — contract/architecture

Changes schema semantics, service boundaries, source of truth, lifecycle, performance target, or compatibility. Requires ADR and migration/rollback plan.

### Class D — risk/live authorization

Changes leverage, intended loss, concurrency, approval, emergency, credentials, promotion mode, or fail-closed behavior. Requires owner approval and new/revalidated strategy/live evidence.

## Required change record

- motivation and observed problem;
- current and proposed behavior;
- alternatives considered;
- impacted contracts, datasets, releases, deployments, and users;
- compatibility/migration plan;
- safety and performance impact;
- acceptance evidence;
- rollback/revocation plan;
- approvers.

## Prohibited shortcuts

- editing an acceptance test to match a failing implementation without PM approval;
- mutating an accepted dataset or promoted release in place;
- silently changing a default that alters trading behavior;
- weakening validation because an exchange symbol fails it;
- labeling a semantic change as refactoring;
- using a live hotfix without incident evidence and follow-up review.
