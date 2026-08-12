# Contributing

This repository follows a documentation-first, evidence-driven delivery model.

## Work item types

Every change should be classified as one of:

- architecture/governance;
- data ingestion or data quality;
- research methodology;
- backtest/validation;
- strategy release and promotion;
- live market data;
- risk/execution/reconciliation;
- observability/operations;
- performance benchmark.

## Branch and pull-request policy

- One coherent task per branch.
- Keep generated datasets and binary artifacts out of Git.
- State the exact acceptance criteria in the issue before implementation begins.
- Link any affected ADR or create one when required.
- Explain data-contract and backward-compatibility impact.
- Include validation commands and evidence.
- Default to draft PRs until checks and PM-owned acceptance tests pass.

## Acceptance criteria ownership

Acceptance criteria, live-readiness gates, risk limits, and project scope are owned by the project owner/PM. Implementation PRs cannot weaken, replace, or remove them to make a change pass.

## Research changes

A research change must declare:

- hypothesis;
- data version and coverage;
- candidate and outcome definitions;
- fee/funding assumptions;
- train/validation/test and out-of-symbol splits;
- multiple-testing controls;
- expected artifacts;
- rejection conditions.

## Performance claims

A performance claim must include:

- hardware and operating system;
- software versions;
- dataset row count, file count, schema, and compression;
- cold-cache or warm-cache status;
- exact benchmark command;
- wall-clock time, CPU utilization, peak memory, and bytes read/written;
- comparison baseline.

## Security

Never post API keys, secrets, account exports, Telegram tokens, private strategy releases, runtime databases, or identifiable account data in issues, PRs, logs, screenshots, or test fixtures.
