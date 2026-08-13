# ADR-0040: Sanitized Canonical Campaign Publication Evidence

- Status: accepted
- Date: 2026-08-13
- Implements: GitHub-authoritative Phase 2 canonical campaign publication evidence

## Context

ADR-0039 commits a runtime aggregate only after every Landing child, canonical Parquet file,
audit, manifest, and receipt verifies. Those runtime artifacts contain paths, dataset and
instrument identities, exact market rows, and hundreds of megabytes of data that must remain
outside the public repository. A chat result or local receipt is not sufficient because ADR-0025
makes GitHub the source of truth for measured project progress.

The representative campaign also mixes consecutive candle datasets and sparse funding datasets.
Its public evidence must preserve per-kind totals without publishing symbols, instrument IDs,
dataset IDs, event timestamps, candle values, funding rates, or runtime paths. Publication lineage
must not be misrepresented as accepted historical coverage, catalog selection, Gate 2 completion,
or permission for private/live operations.

## Decision

Freeze `grid.phase2-history-campaign-publication/v1` as the GitHub-safe projection of one fully
verified ADR-0039 publication campaign.

`grid-data history-campaign-publication-evidence` requires the runtime publication root, its
original completed acquisition campaign, an immutable evidence-builder Git identity, and a new
output path. Before constructing evidence it invokes the aggregate verifier, which re-verifies
the source aggregate and child receipts, derives every canonical dataset identity from source,
and verifies every Parquet file, audit, manifest, child receipt, and aggregate receipt.

The projection records only:

- source request/campaign, registry, capacity, publication plan, and publication manifest hashes;
- aggregate and per-kind dataset, row, file, and Parquet-byte totals;
- source scope counts and requested bounds already allowed by ADR-0025;
- the maximum single-child free-space and peak-memory bounds used by the sequential writer;
- immutable publisher and evidence-builder Git identities; and
- explicit receipt/resume and non-Gate-2 limitations.

The schema has an exact field allowlist and constant storage-policy assertions excluding market
values, instrument identities, runtime paths, account data, and runtime market artifacts. The
small canonical JSON evidence is written atomically and its SHA-256 receipt is written last. An
existing evidence file or receipt is never overwritten.

The evidence command contains no exchange client or credential and performs no network request,
order, bot creation, transfer, catalog registration, or live action.

## Consequences

- GitHub can prove which immutable source and canonical publication produced the reported totals
  without distributing market data or local identifiers.
- Substitution of source pages, aggregate artifacts, canonical Parquet, audits, manifests,
  receipts, or publisher identity fails verification or changes a committed binding.
- Per-kind totals keep funding semantics distinct from candles while exposing no funding rates or
  settlement timestamps.
- Hashes do not reconstruct runtime data; retention and backup remain separate operational work.
- Coverage/lifecycle audits and catalog registration remain separate transitions, and Gate 2
  remains closed.

## Rejected alternatives

- Commit runtime plans, manifests, or Parquet: they expose prohibited identities/values or large
  generated data.
- Reuse only the Landing campaign evidence: it proves acquisition, not canonical file/receipt
  lineage.
- Publish individual dataset IDs or source job roots: aggregate bindings already detect
  substitution without leaking runtime topology.
- Treat successful publication as coverage acceptance: exact source/canonical parity can still
  contain historical gaps, cadence blockers, or incomplete lifecycle knowledge.
