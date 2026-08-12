# GitHub Repository Settings

## Repository identity

- Owner: `brullik`
- Name: `brullik-bybit-grid-bot-research`
- Visibility: public
- Default branch: `main`
- Description: `Documentation-first architecture for a high-throughput Bybit Futures Grid Bot research-to-live platform.`
- Website: none initially

Suggested topics:

- `bybit`
- `grid-bot`
- `algorithmic-trading`
- `quant-research`
- `backtesting`
- `parquet`
- `duckdb`
- `polars`
- `python`
- `risk-management`

## Initial feature settings

- Issues: enabled.
- Discussions: optional; keep disabled until external collaboration is intended.
- Wiki: disabled; architecture belongs in version-controlled docs.
- Projects: optional after the first implementation sprint.
- Sponsorships: disabled.
- Merge queue: optional after CI exists.

## Default branch protection target

After the first push, configure `main` to:

- require a pull request before merging;
- require at least one approving review when another trusted reviewer is available;
- dismiss stale approvals after new commits;
- require conversation resolution;
- require status checks once CI exists;
- block force pushes and branch deletion;
- require linear history or squash merges;
- include administrators when operationally acceptable;
- restrict direct changes to governance/acceptance paths through CODEOWNERS review.

## Sensitive paths

Treat these as owner/PM-controlled:

```text
AGENTS.md
SECURITY.md
docs/00_PROJECT_CHARTER.md
docs/01_FINAL_GOAL_AND_SUCCESS_CRITERIA.md
docs/02_SCOPE_AND_PRINCIPLES.md
docs/09_STRATEGY_RELEASE_CONTRACT.md
docs/11_RUN_MODES_AND_ISOLATION.md
docs/12_SECURITY_RISK_AND_SAFETY.md
governance/**
planning/**
tests/acceptance/**
tests/performance/specifications/**
```

CODEOWNERS can be refined when additional maintainers exist.

## Merge policy

- Documentation baseline: direct initial commit to empty `main` is acceptable.
- Subsequent work: pull request required.
- Default merge method: squash merge with meaningful title/body.
- Never merge a PR that changes its own PM-owned acceptance criteria unless the PR is explicitly a governance change.
- Draft PR is the default for implementation work until evidence is complete.

## Public-repository safety

Before every push:

- run secret scanning locally/CI;
- verify no `.env`, account IDs, Telegram IDs/tokens, private logs, runtime DB, market data, or release evidence containing account details;
- reject binary and generated research artifacts unless explicitly approved;
- review Git history, not only the current working tree, after accidental secret exposure;
- rotate a secret immediately if it ever enters a commit.

## License status

No open-source license is selected in version 0.1.0. The repository can be public, but external reuse/contribution remains unlicensed until the owner chooses and adds a license.
