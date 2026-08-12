# Definition of Done

A task is not complete because code or a document exists. It is complete only when the applicable evidence below is present and accepted.

## Universal criteria

- scope and non-goals match the approved task;
- acceptance criteria are satisfied without modification by the implementation branch;
- contracts, units, timestamp semantics, and failure behavior are explicit;
- tests/evidence cover normal, boundary, malformed, restart, and failure paths;
- no secret or sensitive account data is committed or logged;
- documentation, decision register, and changelog are updated when behavior/contracts change;
- deterministic/reproducible commands and environment identity are recorded;
- artifacts have complete lifecycle status, hashes, lineage, and commit receipt where applicable;
- relevant performance does not regress beyond an accepted threshold;
- review identifies rollback/repair behavior;
- no unresolved critical/high-severity finding remains.

## Documentation/architecture task

- final decision and rationale are stated;
- alternatives and consequences are recorded;
- diagrams and links render/resolve;
- assumptions are distinguished from measured facts;
- open questions and owner decisions are captured;
- no code is smuggled into a documentation-only sprint.

## Data pipeline task

- immutable input/output identities;
- preflight before filesystem mutation;
- duplicate/conflict/gap/orphan/stale-building behavior tested;
- exact coverage and row counts reported;
- restart resumes complete shards and handles partial shards safely;
- source and canonical hashes recorded;
- performance benchmark on representative data;
- no trade credentials available to the process.

## Research task

- no lookahead and explicit decision-time semantics;
- train/validation/test/out-of-symbol boundaries frozen;
- feature/candidate/outcome versions and parent IDs recorded;
- costs/funding/ambiguity cannot be silently disabled;
- experiment is reproducible from immutable parents;
- negative and sensitivity results reported, not hidden;
- concentration and robustness evidence present.

## Release task

- canonical member allowlist;
- complete, verified lifecycle;
- all member hashes and parent lineage valid;
- independent verifier passes;
- promotion/revocation/rollback evidence;
- no secret, mutable path, or unapproved member;
- live compatibility tested.

## Live task

- exact arithmetic and post-rounding risk proven;
- feature parity with research;
- durable state transition before/after side effects as designed;
- no blind retry after uncertain mutating request;
- exchange/local reconciliation tested;
- stale/gapped data and revoked release fail closed;
- restart, emergency, audit failure, and unauthorized command tests pass;
- operator/runbook/rollback evidence accepted;
- owner explicitly approves the live mode and limits.
