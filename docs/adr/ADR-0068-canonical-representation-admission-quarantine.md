# ADR-0068: Receipt-bound canonical representation admission quarantine

- Status: accepted
- Date: 2026-08-14
- Extends: ADR-0020, ADR-0021, ADR-0024, ADR-0039, ADR-0053, and ADR-0067
- Preserves: P-001 exact hybrid representation and unchanged Gate 2 ownership

## Context

The completed full-history public candle campaign contains 30,832,408 Landing-admitted rows. A
read-only semantic scan found 74 trade candles whose exact volume has more than four fractional
digits. OHLC values fit the accepted Int64 `1e-8` units, turnover fits Decimal128(38, 12), and no
non-plain decimal was observed. The exact source values are valid Bybit response evidence but
cannot be represented by the owner-accepted Decimal128(38, 4) canonical volume field without
rounding.

ADR-0020 explicitly forbids silent rounding. The completed Landing pages and receipts are
immutable, so rewriting them or retroactively changing their earlier source-semantic admission is
also forbidden. Failing the entire aggregate preflight hides otherwise independently publishable
children and prevents the coverage auditor from reporting the exact blocker.

## Decision

Add a second, canonical-representation admission step after complete semantic Landing
verification and before Arrow construction. It applies only to trade candles. A row whose exact
volume cannot be represented at scale 4 is retained unchanged in immutable Landing and excluded
from the canonical table with reason `volume_exceeds_canonical_scale`. No value is rounded,
truncated, normalized, or rewritten. Mark candles and funding rows are unchanged.

For every candle child, semantic verification produces an in-process admission result containing
source, admitted, and excluded counts, exact excluded keys, one complete reason counter, and a
SHA-256 binding over each excluded row's key, reason, and canonical source-row hash. Exact keys and
values remain private runtime data. When exclusions exist, the aggregate publication plan and
manifest contain only the counts, policy, reason counters, and exclusion hash; that same payload
enters the child build-configuration hash, and the exclusion hash enters source evidence. Existing
children without exclusions keep their byte-compatible v1 build identity and artifact shape.

The canonical dataset contains only admitted rows. If every Landing-admitted row is excluded, the
ADR-0067 schema-only publication path is used. Aggregate row totals are canonical admitted totals;
the optional `source_row_count` and admission summary preserve exact source-to-canonical
accounting. Completed-publication verification recomputes the expected lineage from the immutable
source campaign and rejects missing, malformed, funding-attached, or inconsistent admission
claims.

Extend the coverage audit backward-compatibly with the unaccepted reason
`canonical_representation_overflow`. Excluded keys are removed from
`rest_returned_no_data` accounting, must belong to exactly one requested series, and remain
ineligible for ordinary same-endpoint gap repair. Aggregate GitHub evidence may expose only the
reason and count. A reviewed physical-contract migration or separate source-policy decision is
required before those minutes can be accepted.

## Consequences

- P-001 remains Decimal128(38, 4), and all canonical values remain exact.
- The immutable Landing campaign is neither rewritten nor relabelled.
- Independent children can be published with complete receipt-bound exclusion lineage.
- The 74 observed exclusions remain explicit blockers; canonical coverage and Gate 2 stay closed.
- Existing v1 publication, coverage, and evidence artifacts remain valid without migration.

## Rejected alternatives

- Round or truncate volume to four digits: this violates the explicit owner decision and loses
  source truth.
- Widen the canonical volume scale in place: this changes P-001 and requires owner-approved
  migration evidence, not an implementation shortcut.
- Rewrite completed Landing admission: immutable source receipts cannot be edited after commit.
- Classify the minute as `rest_returned_no_data`: a receipt-bound source row exists.
- Retry the same endpoint through ordinary repair: the stable exact value is expected to recur.
- Publish exact rows or keys to GitHub: sanitized evidence must not disclose market values or
  instrument/time identities.
