# Security, Risk, and Safety

## Security objective

Protect exchange funds, API credentials, strategy integrity, research evidence, and operator control while making the safest behavior the default. Any uncertainty that can change exposure results in paused entries or no trade.

## Threat model

The design addresses:

- leaked or overprivileged API keys;
- unauthorized operator/Telegram commands;
- dependency or artifact tampering;
- a modified strategy after validation;
- replayed approval or API requests;
- duplicate creation after network timeout;
- stale or manipulated market data;
- compromised research workstation reaching live credentials;
- accidental main-account/manual trading conflicts;
- corrupted local state or backup;
- rate-limit exhaustion and clock drift;
- malicious/unreviewed implementation changes;
- secret leakage through logs, crash reports, artifacts, or prompts.

## Credential policy

- Withdrawal permission is forbidden.
- A dedicated subaccount and dedicated live API key are the target deployment.
- If an owner explicitly accepts a main-account test, it remains manual-only and uses the smallest feasible exposure until migration to a subaccount.
- Private keys live outside Git, documentation, issue bodies, pull requests, chat prompts, and strategy releases.
- Secrets are injected at runtime through an operating-system secret store or equivalent protected mechanism.
- Public data and research applications do not receive private exchange credentials.
- Key rotation, revocation, and incident procedures are documented and rehearsed.
- IP allowlisting is enabled when the stable live host is known.
- A future Phase 7 shadow credential, if separately authorized, is read-only/least-privileged with
  no withdrawal permission; the shadow executable has no exchange-mutation method even when a key
  is misconfigured with broader permissions.
- A future Phase 8 mainnet key/account is admitted only after Gate 7, P-009 resolution, and a
  separate owner decision. Withdrawal/transfer permission remains forbidden; each create/close is
  exact, manually approved, one-attempt, and blocked globally by any active or uncertain bot.
- Phase 9 scale uses the same restricted capability boundary and gains no new key permission.
  Concurrency, universe, size/risk, and automation remain one-axis, evidence-bound owner decisions;
  account-wide atomic reservations and strictest-wins aggregate/concentration risk fail closed.

## Least privilege and network policy

| Runtime | Bybit access | Other outbound access | Filesystem |
|---|---|---|---|
| data | public only | archive host | raw/canonical market store |
| research | none by default | none | historical read-only; derived write |
| release | none by default | registry/signing as needed | evidence read; registry write |
| live | required public/private endpoints | Telegram/monitoring allowlist | release read; live state write |

## Artifact trust

A strategy release is trusted only if:

- its lifecycle status is `promoted`;
- member allowlist is exact;
- every required member hash matches;
- provenance and validation evidence are complete;
- promotion and verifier records are valid;
- compatibility checks pass;
- it is not expired or revoked;
- the live binary/dependency versions satisfy the compatibility contract.

Live never accepts a mutable research folder or manually edited parameter file.

## Baseline trading-risk controls

Current controlled assumptions:

- initial capital model: 500 USDT;
- maximum intended loss per grid: 5 USDT;
- one active or uncertain grid per symbol;
- Neutral + Geometric only in V1;
- trailing up/down disabled in V1;
- every live grid requires an explicit stop-loss policy;
- first real executions require manual approval;
- emergency stop persists until explicit, authorized resume.

These values are not financial promises. They are versioned constraints subject to evidence-based change control.

## Risk hierarchy

The system applies limits from broadest to narrowest:

1. exchange/account hard constraints;
2. owner governance limits;
3. promoted release risk limits;
4. deployment/operator limits;
5. per-signal and per-symbol constraints;
6. current account/exposure state;
7. data-quality and operational health.

The most restrictive result wins.

## Required risk calculations

Before create approval, the risk evidence includes:

- exact proposed investment and leverage;
- lower/upper range and grid count;
- stop-loss price and side behavior;
- estimated liquidation prices returned or inferred from authoritative data;
- worst intended loss under the strategy model;
- fees and funding assumptions;
- existing account exposure and correlated positions;
- free balance after reserves;
- validate response and all exchange min/max constraints;
- rounding/quantization transformations.

If the system cannot prove the intended loss cap after exchange rounding, it skips the trade.

## Fail-closed conditions

New entries are blocked on:

- unavailable or non-durable audit/state storage;
- stale, partial, gapped, conflicting, or future-dated market data;
- clock drift beyond policy;
- API authentication degradation;
- private-stream loss without successful reconciliation;
- local/exchange state mismatch;
- unresolved create/close uncertainty;
- unknown external grid/position on a managed symbol;
- release verification failure or revocation;
- rate-limit or error budget breach;
- balance/risk calculation failure;
- repeated unexpected exceptions;
- operator pause/emergency state.

Monitoring of existing exposure continues whenever safely possible even when entries are blocked.

## Approval security

- Approver identities are allowlisted.
- Approval tokens are cryptographically random, short-lived, and single-use.
- Approval binds to exact payload and release hash.
- Telegram chat/user ID is verified; display names are not identities.
- Commands include replay and duplicate protection.
- High-impact commands can require a second confirmation or separate control channel.
- Approval and rejection are written durably before execution.

## Emergency behavior

`/emergency_stop` must:

1. durably enter emergency state;
2. stop all new entries immediately;
3. enumerate managed and unexpected exchange exposure;
4. close/cancel according to the versioned emergency policy;
5. reconcile every outcome, including uncertainty;
6. alert the owner with an incident ID;
7. remain stopped across process/host restart;
8. require explicit authorized resume after a clean reconciliation.

Emergency behavior is tested in shadow/sandbox and through controlled minimal-mainnet drills before scaling.

## Software-supply-chain controls

Planned controls:

- pinned/locked dependencies per deployable;
- dependency and secret scanning;
- SBOM for release artifacts;
- signed commits/tags or equivalent provenance where practical;
- protected default branch and pull-request review;
- PM-owned acceptance tests that implementation PRs cannot weaken;
- reproducible build metadata;
- no binary artifacts committed unless explicitly governed;
- release hashes and independent verifier.

## Logging and privacy

Never log:

- API secret/private key;
- raw authorization headers;
- complete approval token;
- private Telegram bot token;
- secret environment values.

Sensitive payload fields are redacted before persistence. Public repositories contain examples and schemas only.

## Incident classes

- **SEV-0:** confirmed unauthorized exposure/credential compromise;
- **SEV-1:** uncertain or mismatched live exposure, emergency close failure;
- **SEV-2:** live unavailable or entries paused with no unmanaged exposure;
- **SEV-3:** data/research/release pipeline degradation with live unaffected.

Each incident receives an immutable timeline, impact statement, containment actions, root cause, corrective controls, and owner decision on restart.
