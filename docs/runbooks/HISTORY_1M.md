# Public Bybit 1m History Runbook

This runbook operates only the unauthenticated public data application. It does not read API
keys, place orders, create bots, transfer funds, or download tick trades. Run one bounded pilot
before increasing symbols or time coverage.

## 1. Build the stable instrument registry

Use a receipt-verified inventory. The command derives `instrument_id`; never enter it in a
history request.

```powershell
.venv\Scripts\grid-data.exe instrument-registry `
  --instrument-inventory benchmarks\results\m1-owner-storage-review-inventory-20260812.json `
  --output data\evidence\instrument-registry-20260812.json
```

The output is local runtime evidence under the ignored `data/` tree. Keep the JSON and its
`.receipt.json` together.

## 2. Create one partition-scoped request

`data\requests\btc-trade-2026-07.json`:

```json
{
  "contract": "grid.bybit-1m-history-request/v1",
  "job_id": "trade-2026-07-b05-btc-pilot",
  "kind": "trade",
  "series": [
    {
      "symbol": "BTCUSDT",
      "start_ms": 1782864000000,
      "end_ms": 1783468740000
    }
  ],
  "page_limit": 1000,
  "workers": 24,
  "target_rps": 10,
  "max_attempts": 3,
  "max_http_requests": 100000
}
```

The example is seven days of closed July 2026 BTC trade candles. A request must contain only one
kind, UTC month, and stable bucket. Every bound is inclusive and divisible by 60,000. The resolver
checks launch/delivery metadata and rejects future or currently open candles during preflight.

## 3. Run the mandatory no-mutation preflight

```powershell
.venv\Scripts\grid-data.exe history-1m `
  --request data\requests\btc-trade-2026-07.json `
  --instrument-registry data\evidence\instrument-registry-20260812.json `
  --capacity-evidence benchmarks\results\m1-owner-storage-review-capacity-20260812.json `
  --staging-root data\history
```

Without `--execute`, this command makes no directory and sends no HTTP request. Review the printed
plan hash, page count, pending count, current required-free-space result, memory bound, and job
root. Failure means stop; do not bypass the evidence or storage check.

## 4. Execute exactly that request

Repeat the command with `--execute`. Execution re-probes memory, NVMe/SSD identity, and free space,
then calls only Bybit public trade/mark 1m endpoints.

```powershell
.venv\Scripts\grid-data.exe history-1m `
  --request data\requests\btc-trade-2026-07.json `
  --instrument-registry data\evidence\instrument-registry-20260812.json `
  --capacity-evidence benchmarks\results\m1-owner-storage-review-capacity-20260812.json `
  --staging-root data\history `
  --execute
```

An ordinary failed run keeps verified pages. Re-running the same command fetches only missing
pages. A machine/process crash can leave `.run-lock`; that is deliberately treated as stale
evidence and requires explicit repair work rather than automatic deletion.

## 5. Verify the completed Landing batch

Use the exact `job_root` printed by preflight/execution:

```powershell
.venv\Scripts\grid-data.exe verify-history-1m `
  data\history\.landing\trade-2026-07-b05-btc-pilot--<plan-prefix>
```

Verification checks the plan, every page and receipt, actual attempt/row totals, completion
receipt, source policy, hashes, and exact file allowlist. This proves a Landing batch only.

## 6. Preflight canonical publication

Use the mandatory immutable code identity: `git:` followed by the 40-character lowercase Git
commit SHA that contains the publisher:

```powershell
.venv\Scripts\grid-data.exe publish-history-1m `
  --job-root data\history\.landing\trade-2026-07-b05-btc-pilot--<plan-prefix> `
  --instrument-registry data\evidence\instrument-registry-20260812.json `
  --capacity-evidence benchmarks\results\m1-owner-storage-review-capacity-20260812.json `
  --store-root data\market-store `
  --software-identity git:<full-commit-sha>
```

Without `--execute`, no canonical directory is created. The command re-verifies every Landing,
registry, and capacity receipt; checks their hash bindings and lifecycle bounds; takes a fresh
host snapshot; and prints the deterministic dataset ID, row count, memory bound, and required
free space. Preserve the exact software identity for the execution and all idempotent reruns.

## 7. Publish and verify the canonical dataset

After reviewing the preflight, repeat the exact command with `--execute`, then verify the printed
dataset root:

```powershell
.venv\Scripts\grid-data.exe verify-canonical-candle `
  data\market-store\datasets\trade-1m-<landing-manifest-prefix>
```

Publication repeats the current memory, storage, and free-space checks before its first write and
writes the completion receipt last. Repeating an identical publication returns the existing
verified commit. A conflicting identity or incomplete directory fails closed and is not deleted.

Canonical publication does not accept missing lifecycle ranges. Gap/lifecycle classification,
repair, immutable compaction, and catalog registration are separate Phase 2 transitions; Gate 2
remains closed.

## 8. Publish a sanitized pilot evidence summary to GitHub

For a deliberately bounded pilot, build the small public artifact only after canonical verification
and an idempotent existing-commit preflight:

```powershell
.venv\Scripts\grid-data.exe history-pilot-evidence `
  --job-root data\history\.landing\trade-2026-07-b05-btc-pilot--<plan-prefix> `
  --instrument-registry data\evidence\instrument-registry-20260812.json `
  --capacity-evidence benchmarks\results\m1-owner-storage-review-capacity-20260812.json `
  --store-root data\market-store `
  --software-identity git:<full-commit-sha> `
  --output benchmarks\results\m2-public-1m-canonical-pilot-<date>.json
```

Commit the JSON, its `.receipt.json`, schema, status documentation, and generator in one reviewed
PR. The summary contains hashes, ranges, counts, source policy, layout, and limitations. It rejects
an incomplete range and never contains candle values, local paths, host/device identity, account
data, or credentials. Runtime Landing and Parquet artifacts remain ignored; GitHub is authoritative
through their cryptographic bindings, not by storing the market lake. Existing evidence and its
receipt cannot be overwritten; a later run uses a new output identity.

## 9. Audit exact requested coverage

After the auditor implementation has a merged full Git SHA, run the read-only audit. The publisher
identity is the SHA already bound into the canonical manifest; the auditor identity is the SHA that
contains `audit-history-1m`:

```powershell
.venv\Scripts\grid-data.exe audit-history-1m `
  --job-root data\history\.landing\trade-2026-07-b05-btc-pilot--<plan-prefix> `
  --instrument-registry data\evidence\instrument-registry-20260812.json `
  --capacity-evidence benchmarks\results\m1-owner-storage-review-capacity-20260812.json `
  --store-root data\market-store `
  --publisher-software-identity git:<publisher-commit-sha> `
  --audit-software-identity git:<auditor-commit-sha> `
  --output benchmarks\results\m2-canonical-coverage-audit-<date>.json
```

The command always preserves a valid audit plus receipt. Exit code 0 means exact source parity and
zero missing, duplicate, unexpected, unrequested, or lifecycle-invalid rows inside the requested
ranges. Exit code 2 means blocked evidence was written. In v1, even a fully verified REST page with
no candle is `rest_returned_no_data` and remains unaccepted; do not edit the audit or classify it as
no-trade manually. Repair and reason-policy changes require their own contract and review.

A receipt-bound row excluded by the narrow ADR-0050 OHLC quarantine is reported as
`quarantined_source_row`, not `rest_returned_no_data`. It remains blocked and is not eligible for
ordinary same-endpoint gap repair. Preserve the local Landing job and escalate to a separate
source-reconciliation decision; do not disclose the exact row, key, symbol, or timestamp in
GitHub evidence.

The audit evidence accepts the same bounded 1 through 700 series as the acquisition request. This
does not enlarge the pilot-evidence contract: `history-pilot-evidence` remains limited to 16 series
and 1,000,000 rows. Use the complete coverage audit, not a relabelled pilot, for larger controlled
scale steps.

## 10. Plan a blocked missing-minute repair

Run this only for an immutable blocked v1 audit. The command performs no Bybit request and no
canonical write. It re-verifies the audit receipt, recomputes the complete gap list from the
original runtime inputs, and refuses every blocker except missing requested minutes observed as
`rest_returned_no_data`:

```powershell
.venv\Scripts\grid-data.exe plan-history-repair `
  --coverage-audit benchmarks\results\m2-canonical-coverage-audit-<date>.json `
  --job-root data\history\.landing\<completed-job> `
  --instrument-registry data\evidence\instrument-registry-<date>.json `
  --capacity-evidence benchmarks\results\m1-owner-storage-review-capacity-<date>.json `
  --store-root data\market-store `
  --planner-software-identity git:<planner-commit-sha> `
  --output data\evidence\m2-gap-repair-plan-<date>.json
```

The receipt-last result embeds one standard, hash-bound history request per contiguous gap and
accounts for every missing minute. Do not run it for a passing audit, edit an embedded request, or
treat the plan as permission to download or replace canonical data. The successful bounded pilot
has no gaps, so it correctly produces no repair plan.

## 11. Execute a verified repair plan

First run the command without `--execute`. It recomputes the plan from all original inputs,
resolves embedded requests without temporary files, verifies existing task receipts, and admits
the aggregate Landing/free-space/memory bound before any public request:

```powershell
.venv\Scripts\grid-data.exe execute-history-repair `
  --repair-plan data\evidence\m2-gap-repair-plan-<date>.json `
  --coverage-audit benchmarks\results\m2-canonical-coverage-audit-<date>.json `
  --job-root data\history\.landing\<completed-original-job> `
  --instrument-registry data\evidence\instrument-registry-<date>.json `
  --capacity-evidence benchmarks\results\m1-owner-storage-review-capacity-<date>.json `
  --store-root data\market-store `
  --repair-staging-root data\history-repair `
  --executor-software-identity git:<executor-commit-sha> `
  --output data\evidence\m2-gap-repair-execution-<date>.json
```

Inspect `task_count`, `planned_max_http_requests`, `required_free_bytes`, and
`planned_peak_memory_bytes`. Then repeat the identical command with `--execute`. Tasks run
sequentially but retain their standard bounded worker pool, page receipts, retries, and resume.
Exit code 0 writes `status=passed`; exit code 2 writes immutable `status=blocked` evidence when a
minute is still absent. Never delete a blocked execution to disguise a repeated empty response.

## 12. Publish the immutable repaired child

Only a receipt-verified `passed` execution is eligible. Run without `--execute` first:

```powershell
.venv\Scripts\grid-data.exe publish-history-repair `
  --repair-execution data\evidence\m2-gap-repair-execution-<date>.json `
  --repair-plan data\evidence\m2-gap-repair-plan-<date>.json `
  --coverage-audit benchmarks\results\m2-canonical-coverage-audit-<date>.json `
  --job-root data\history\.landing\<completed-original-job> `
  --instrument-registry data\evidence\instrument-registry-<date>.json `
  --capacity-evidence benchmarks\results\m1-owner-storage-review-capacity-<date>.json `
  --store-root data\market-store `
  --repair-staging-root data\history-repair `
  --software-identity git:<replacement-commit-sha> `
  --output data\evidence\m2-gap-replacement-<date>.json
```

The preflight re-verifies the entire chain, checks that the exact repair key union closes every
original requested minute, and prints the deterministic child ID and parent ID. Repeat with
`--execute` to atomically publish the new dataset and write the value-free lineage proof. Verify
that the new manifest has exactly the printed parent, and retain the old dataset unchanged. This
does not compact files, register the child in a catalog, change the accepted gap-reason policy, or
close Gate 2.

## 13. Compact immutable same-partition fragments

Use compaction only when two or more receipt-verified files collectively describe one candle kind,
schema, UTC month, and stable bucket. Repeat `--dataset` for each immutable fragment. Parent order
on the command line does not affect identity; the command sorts and binds every parent ID and
manifest hash.

Run without `--execute` first:

```powershell
.venv\Scripts\grid-data.exe compact `
  --dataset trade-1m-<fragment-a> `
  --dataset trade-1m-<fragment-b> `
  --capacity-evidence benchmarks\results\m1-owner-storage-review-capacity-<date>.json `
  --store-root data\market-store `
  --software-identity git:<compactor-commit-sha> `
  --output data\evidence\m2-canonical-compaction-<date>.json
```

Review the input/output file counts, rows-per-file target, planned peak memory, and required free
space. Preflight verifies each parent, estimates the uncompressed parent footprint before loading
the bounded month/bucket union, rejects duplicate/conflicting keys, and refuses a rewrite that does
not reduce file count. It performs no filesystem mutation.

Repeat the exact command with `--execute`. Publication takes a new host snapshot, re-verifies every
parent, writes ordered hash-named ZSTD-3 files in a same-volume building directory, atomically
publishes the child, and writes its completion receipt last. Only the final output may be a tail;
the audit records actual bytes and target classification for every file. The public evidence binds
equal logical input/output hashes and `parent_datasets_mutated=false` without containing candle
values or local paths.

Do not delete the parents after compaction. Parent retention/garbage collection requires a future
catalog reachability policy. Compaction does not register the child, accept a missing-minute
reason, or close Gate 2.

### Compact funding fragments

Funding uses a separate exact schema and settlement chronology. Run no-mutation preflight first
with at least two receipt-verified funding parents from exactly one month/bucket:

```powershell
.venv\Scripts\grid-data.exe compact-funding `
  --dataset funding-<parent-a> `
  --dataset funding-<parent-b> `
  --capacity-evidence benchmarks\results\m1-owner-storage-review-capacity-<date>.json `
  --store-root data\market-store `
  --software-identity git:<compactor-commit-sha> `
  --output data\evidence\m2-canonical-funding-compaction-<date>.json
```

Inspect the input/output file counts, parent IDs, memory bound, and free-space bound. Repeat the
identical command with `--execute` only after preflight passes. The command rejects duplicate keys,
mixed partitions, and settlement-interval mismatches across parent boundaries. It creates one new
receipt-last funding child and a sanitized proof; it never changes or deletes a parent and does
not accept a previously blocked funding chronology reason.

## 14. Register datasets and select a reproducible range

Catalog registration is a separate transition after canonical publication, repair, or compaction.
It accepts receipt-verified canonical trade/mark 1m and funding datasets. Every registration is
dataset-type aware, while each selection request must name exactly one dataset type.
The catalog must live inside the market-store root. Include every unregistered parent together
with a child so lineage is complete. First run without `--execute`:

```powershell
.venv\Scripts\grid-data.exe catalog-register `
  --dataset trade-1m-<parent-or-current-dataset> `
  --dataset trade-1m-<compacted-child> `
  --store-root data\market-store `
  --catalog data\market-store\catalog\canonical.duckdb `
  --software-identity git:<catalog-implementation-sha> `
  --output data\evidence\m2-catalog-registration-<date>.json
```

Preflight verifies every dataset receipt, Parquet hash/footer/key order, exact partition layout,
catalog digest/revision, and lineage while creating no catalog/evidence file. Review requested/new
dataset IDs and the current catalog hash, then repeat the identical command with `--execute`.
Registration uses a same-directory building database and exclusive lock; do not delete a leftover
lock/building file until an operator has confirmed no writer is running and inspected the catalog.
An identical rerun verifies the existing registration and evidence without changing the revision.

Build a closed `grid.canonical-dataset-selection-request/v1` JSON from the printed final
`catalog_revision` and `catalog_content_sha256`. Dataset IDs and include-mode instrument IDs must
be sorted and unique; never substitute a `latest` alias:

```json
{
  "catalog_content_sha256": "<64 lowercase hex>",
  "catalog_revision": 1,
  "consumer_software_identity": "git:<full-consumer-commit-sha>",
  "dataset_ids": ["trade-1m-<exact-id>"],
  "dataset_type": "trade_kline_1m",
  "end_time_ms": 1767229140000,
  "instrument_filter": {"instrument_ids": [9], "mode": "include"},
  "request_schema": "grid.canonical-dataset-selection-request/v1",
  "start_time_ms": 1767225600000
}
```

Run the read-only selection and publish its receipt-bound object manifest:

```powershell
.venv\Scripts\grid-data.exe catalog-select `
  --request data\requests\catalog-selection-<id>.json `
  --store-root data\market-store `
  --catalog data\market-store\catalog\canonical.duckdb `
  --output data\evidence\catalog-selection-<id>.json
```

The output contains only canonical store-relative object keys and hashes, never absolute paths or
market values. A changed catalog snapshot, missing month/bucket, parent plus child, overlapping key
range, or substituted dataset/file fails closed. Selection is not a coverage audit: research must
still require the applicable PM-owned gap/lifecycle evidence before treating the range as complete.

For funding, register `funding-<exact-id>` with the same command and build the request with
`"dataset_type": "funding_event"`, exact funding dataset IDs, and funding settlement time bounds.
The selected files use `funding_time_ms` internally, but the request fields remain
`start_time_ms`/`end_time_ms`. Never combine funding and candle dataset IDs in one request. A
successful funding selection proves only receipt-bound pruning; bind the separate funding
chronology/lifecycle evidence before research consumption.

## 15. Acquire and publish canonical funding

Funding is a separate request and Landing contract because every first requested event needs the
authoritative settlement immediately before the range. Do not add `instrument_id`, launch time, or
funding interval to the request. Example `data\requests\btc-funding-2026-07.json`:

### Discover a missing full-history predecessor boundary

If a registry-bounded predecessor query returns no settlement, do not move the request boundary by
guessing and do not use the current `fundingInterval`. Create a new local request such as
`data\requests\funding-source-boundary.json` (runtime requests and results remain outside Git):

```json
{
  "contract": "grid.bybit-funding-source-boundary-request/v1",
  "discovery_id": "funding-source-boundary",
  "start_ms": 1514764800000,
  "end_ms": 1785542340000,
  "symbols": ["BTCUSDT"],
  "page_limit": 200,
  "workers": 24,
  "target_rps": 15,
  "max_attempts": 3,
  "max_pages_per_symbol": 512
}
```

Run no-mutation preflight with the full merged Git SHA containing the discovery implementation:

```powershell
.venv\Scripts\grid-data.exe funding-source-boundary `
  --request data\requests\funding-source-boundary.json `
  --instrument-registry data\evidence\instrument-registry-<date>.json `
  --output-root data\funding-boundary `
  --software-identity git:<full-commit-sha>
```

Review the plan hash, symbol/request ceiling, fresh resource admission, and job root. Repeat with
`--execute` to call only public `GET /v5/market/funding/history`. Execution validates exact rates
but stores only minute timestamps, resumes from verified page receipts, and completes only after
finding at least two settlements per symbol. The oldest is predecessor-only; use the second-oldest
as the earliest possible canonical start in a separately resolved funding request. Source absence
and cadence still require the normal audit. A stale `.run-lock`, partial receipt, invalid row,
exhausted 512-page ceiling, or missing second settlement fails closed and requires explicit review.

Independently verify the completed root printed by execution before consuming its boundaries:

```powershell
.venv\Scripts\grid-data.exe verify-funding-source-boundary `
  data\funding-boundary\funding-source-boundary--<plan-prefix>
```

After the evidence builder is merged, publish a new GitHub-safe result with that merge identity:

```powershell
.venv\Scripts\grid-data.exe funding-source-boundary-evidence `
  --job-root data\funding-boundary\funding-source-boundary--<plan-prefix> `
  --software-identity git:<full-evidence-builder-merge-sha> `
  --output benchmarks\results\m2-funding-source-boundary-<date>.json
```

The builder re-verifies every private receipt but publishes only aggregate counts, requested scan
bounds, hashes, immutable Git identities, and strict response accounting. Inspect the schema and
receipt before commit. The artifact must contain no symbol, instrument ID, per-series boundary,
funding rate, observed settlement timestamp, runtime path, host/account datum, or credential.

### Acquire one canonical funding partition

Example `data\requests\btc-funding-2026-07.json`:

```json
{
  "contract": "grid.bybit-funding-history-request/v1",
  "job_id": "funding-2026-07-b05-btc-pilot",
  "series": [
    {
      "symbol": "BTCUSDT",
      "start_ms": 1782864000000,
      "end_ms": 1785542340000
    }
  ],
  "page_span_minutes": 10080,
  "page_limit": 200,
  "workers": 24,
  "target_rps": 10,
  "max_attempts": 3,
  "max_http_requests": 100000
}
```

The range is inclusive, closed, minute-aligned, and limited to one UTC month/bucket. Preflight
makes no request and creates no directory:

```powershell
.venv\Scripts\grid-data.exe funding-history `
  --request data\requests\btc-funding-2026-07.json `
  --instrument-registry data\evidence\instrument-registry-20260812.json `
  --capacity-evidence benchmarks\results\m1-owner-storage-review-capacity-20260812.json `
  --staging-root data\history
```

Review the predecessor/range page count, pending pages, retry bound, host identity hash, memory,
and free-space requirement. Repeat with `--execute` to call only public
`GET /v5/market/funding/history`. A range page returning its full limit is rejected as potentially
truncated. Create a new request with a smaller `page_span_minutes`; never edit or delete the failed
Landing identity. Repeating the identical command resumes only missing receipted pages.

Verify the printed funding job root:

```powershell
.venv\Scripts\grid-data.exe verify-funding-history `
  data\history\.funding-landing\funding-2026-07-b05-btc-pilot--<plan-prefix>
```

Verification requires exactly one predecessor per series and checks every normalized exact rate,
settlement timestamp, page/receipt, attempt bound, boundary aggregate, completion receipt, and
file allowlist. It never uses today's `fundingInterval` as historical evidence.

Preflight canonical funding publication with the full Git SHA that contains the adapter:

```powershell
.venv\Scripts\grid-data.exe publish-funding-history `
  --job-root data\history\.funding-landing\funding-2026-07-b05-btc-pilot--<plan-prefix> `
  --instrument-registry data\evidence\instrument-registry-20260812.json `
  --capacity-evidence benchmarks\results\m1-owner-storage-review-capacity-20260812.json `
  --store-root data\market-store `
  --software-identity git:<full-commit-sha>
```

The adapter derives each event's interval from the preceding settlement, beginning with the
boundary page, then re-verifies registry lifecycle, capacity, exact Arrow values, and current host
admission. Repeat with `--execute` only after review, then independently verify:

```powershell
.venv\Scripts\grid-data.exe verify-canonical-funding `
  data\market-store\datasets\funding-<landing-manifest-prefix>
```

An empty entire requested series, missing predecessor, non-minute settlement, duplicate key,
saturated response, altered page, stale lock/building output, or conflicting dataset identity
fails closed. Successful publication does not yet prove full funding coverage, perform funding
repair/compaction/catalog registration, or close Gate 2. Section 14 describes the now-supported
funding registration/selection transition after publication.

## 16. Publish sanitized funding pilot evidence to GitHub

After canonical publication is committed, repeat its preflight through the evidence command using
the same full publisher Git SHA. The output target must be new:

```powershell
.venv\Scripts\grid-data.exe funding-pilot-evidence `
  --job-root data\history\.funding-landing\funding-2026-07-b05-btc-pilot--<plan-prefix> `
  --instrument-registry data\evidence\instrument-registry-20260812.json `
  --capacity-evidence benchmarks\results\m1-owner-storage-review-capacity-20260812.json `
  --store-root data\market-store `
  --software-identity git:<full-publisher-commit-sha> `
  --output benchmarks\results\m2-public-funding-canonical-pilot-<date>.json
```

The command requires `existing_commit=true`, re-verifies Landing and canonical receipts, compares
the reconstructed and committed exact Arrow tables, and privately recomputes the first interval
from each predecessor plus every later interval from adjacent settlements. It writes canonical
JSON and its receipt last without overwriting an existing artifact.

Only requested bounds, event/window/page counts, process/layout facts, immutable software identity,
and transitive hashes are safe to commit. The schema forbids rates, observed settlement timestamps,
local paths, device/account data, credentials, and runtime market artifacts. This bounded proof is
not a funding chronology/lifecycle audit, repair, compaction, catalog registration, scale result,
or Gate 2 acceptance.

## 17. Audit funding source chronology

Run the read-only audit only after canonical publication. The publisher identity must be the SHA
already bound into the canonical manifest; the auditor identity is the full Git SHA containing the
audit implementation:

```powershell
.venv\Scripts\grid-data.exe audit-funding-history `
  --job-root data\history\.funding-landing\funding-2026-07-b05-btc-pilot--<plan-prefix> `
  --instrument-registry data\evidence\instrument-registry-20260812.json `
  --capacity-evidence benchmarks\results\m1-owner-storage-review-capacity-20260812.json `
  --store-root data\market-store `
  --publisher-software-identity git:<full-publisher-commit-sha> `
  --audit-software-identity git:<full-auditor-commit-sha> `
  --output benchmarks\results\m2-canonical-funding-coverage-audit-<date>.json
```

The command makes no network call and does not mutate Landing or canonical storage. It
re-verifies all receipts and identities, exact Landing/Parquet equality, one predecessor per
series, complete range-page tiling, registry lifecycle bounds, and every derived interval. It
writes the audit and receipt even when blocked, then exits `2` for a blocked result.

V1 accepts no absence or schedule-change reason. An empty range page, predecessor/internal
interval mismatch, or change in observed cadence is hash-bound and blocks. Do not use current
`fundingInterval` to override the result; a legitimate historical cadence change needs separately
dated evidence or an explicit governance decision. A passing bounded audit still does not prove an
independent venue ledger, full lifecycle/history, repair, compaction, catalog readiness, scale, or
Gate 2.

### Plan private funding repair discovery

Only a receipt-verified blocked audit whose sole reason is `unexplained_interval_change` can be
considered. Run the planner with the merge commit that contains ADR-0055:

```powershell
.venv\Scripts\grid-data.exe plan-funding-repair `
  --coverage-audit reports\private\funding-coverage-audit.json `
  --job-root data\history\.funding-landing\funding-<job>--<plan-prefix> `
  --instrument-registry data\evidence\instrument-registry-20260812.json `
  --capacity-evidence benchmarks\results\m1-owner-storage-review-capacity-20260812.json `
  --store-root data\market-store `
  --planner-software-identity git:<full-planner-merge-commit-sha> `
  --output reports\private\funding-repair-plan.json
```

The command re-verifies and recomputes the complete audit, executes no market request, and does
not alter Landing or canonical data. It succeeds only when every changed interval edge belongs to
an isolated integer-multiple `C, N*C, C` pattern and no empty window or other quality blocker
exists. Embedded requests identify candidate settlements for later exact public-source
confirmation; the original audit remains blocked and no schedule is accepted.

Keep the generated plan and receipt private because they contain exact instrument and settlement
identities. Commit only the implementation, schema, ADR, tests, and a later sanitized aggregate
proof. Funding repair execution and immutable child publication are separate transitions and are
not yet authorized by a successful plan.

## 18. Run a resumable multi-month campaign

Use a campaign only after the single-job path and the preceding controlled-scale step verify. The
request names symbols and a common inclusive range; it never contains `instrument_id`. Example:

```json
{
  "contract": "grid.public-history-campaign-request/v1",
  "campaign_id": "m2-representative-5x24",
  "kinds": ["trade", "mark", "funding"],
  "symbols": ["BTCUSDT", "UNIUSDT", "FILUSDT", "CHZUSDT", "SUIUSDT"],
  "start_ms": 1704067200000,
  "end_ms": 1767225540000,
  "lifecycle_policy": "registry-lifecycle-intersection-v1",
  "history_page_limit": 1000,
  "funding_page_limit": 200,
  "funding_page_span_minutes": 10080,
  "workers": 24,
  "target_rps": 15,
  "max_attempts": 3
}
```

The 15-RPS value is an explicit measured controlled-scale setting, not a new default or venue
limit. First run aggregate no-mutation preflight:

```powershell
.venv\Scripts\grid-data.exe history-campaign `
  --request benchmarks\specifications\m2-representative-5x24-history-campaign-request-20260813.json `
  --instrument-registry data\evidence\instrument-registry-20260813.json `
  --capacity-evidence benchmarks\results\m1-owner-storage-review-capacity-20260812.json `
  --staging-root data\history
```

For a campaign containing `funding`, first complete ADR-0048 discovery for the exact registry and
symbol/range scope, then bind it in both preflight and execute/resume commands:

```powershell
  --funding-source-boundary-root data\funding-boundary\<discovery>--<plan-prefix>
```

This removes pre-source empty funding months and makes the first child request the exact proven
predecessor. Do not use registry `launchTime` alone as a historical funding-source boundary.

Review the deterministic plan hash, job/page counts, fresh host identity, aggregate required free
space, peak memory, and `preflight_elapsed_ms`. ADR-0047 verifies the registry/capacity files once
per command and derives all child plans from that exact snapshot; every execute/resume command
reloads them. Repeat with `--execute` only if all pass. Children run sequentially and
emit progress JSON; interruption preserves their verified pages. Repeating the identical command
downloads only missing pages, while a completed campaign performs no public request.

Verify the printed root independently:

```powershell
.venv\Scripts\grid-data.exe verify-history-campaign `
  data\history\.campaigns\m2-representative-5x24--<plan-prefix>
```

The campaign clips each series to the verified current registry launch/delivery interval. This is
only ex-post acquisition scoping: do not expose present-day lifecycle/status/tick metadata to a
historical decision. Campaign completion is Landing evidence only. Publish and audit each child
through the existing canonical boundaries before claiming coverage; partial inventory, missing
candles, funding cadence changes, and Gate 2 remain fail-closed.

After independent verification, publish the bounded summary using the full Git SHA that contains
the evidence builder:

```powershell
.venv\Scripts\grid-data.exe history-campaign-evidence `
  --campaign-root data\history\.campaigns\m2-representative-5x24--<plan-prefix> `
  --software-identity git:<full-commit-sha> `
  --output benchmarks\results\m2-public-history-campaign-<date>.json
```

The command re-verifies every child again and can take minutes. It writes only hashes, scope and
aggregate counts, measured bytes, public endpoint policy, process facts, and limitations. Never
commit the campaign plan/manifests or Landing pages: they contain runtime relative paths, symbols,
instrument identities, and market values.

Use `--require-complete-throttling-evidence` for every long-run qualification. It fails if a child
lacks receipt-bound execution timing, mixes legacy/current summaries, or has fewer sanitized
response observations than completed pages. Transport attempts that fail before an HTTP response
are counted separately and do not masquerade as missing headers. Ordinary projection without this
flag remains available only to reproduce immutable legacy campaigns.

For a campaign executed entirely by an ADR-0044 implementation, qualify it explicitly:

```powershell
.venv\Scripts\grid-data.exe history-campaign-evidence `
  --campaign-root data\history\.campaigns\<long-run-campaign> `
  --software-identity git:<full-commit-sha> `
  --require-complete-throttling-evidence `
  --output benchmarks\results\m2-public-history-long-run-<date>.json
```

## 19. Publish a completed campaign as canonical datasets

Use the exact publisher merge commit containing ADR-0039. First run the aggregate no-mutation
preflight; it verifies the acquisition campaign and every child Landing input while retaining only
one Arrow batch at a time:

```powershell
.venv\Scripts\grid-data.exe publish-history-campaign `
  --campaign-root data\history\.campaigns\m2-representative-5x24--<plan-prefix> `
  --instrument-registry data\evidence\instrument-registry-20260813.json `
  --capacity-evidence benchmarks\results\m1-owner-storage-review-capacity-20260812.json `
  --store-root data\market-store `
  --software-identity git:<full-merge-commit-sha>
```

Review the source manifest hash, dataset/pending counts, maximum single-writer free-space and
memory bounds, and deterministic publication root. Repeat the exact command with `--execute` only
after preflight passes. Writers run sequentially; each emits progress JSON only after its own
canonical completion receipt verifies. If interrupted, rerun the same command: already committed
datasets are hash-verified and reused, never rewritten.

Aggregate preflight decodes each verified Landing page once through the typed child handoff and
releases that child's Arrow batch before moving to the next child. It is still intentionally a
full exact verification and can take several minutes for multi-million-row campaigns. A long
runtime with active CPU is not permission to skip the preflight or lower its digest/receipt checks.

Verify the aggregate receipt and every source/canonical relationship independently:

```powershell
.venv\Scripts\grid-data.exe verify-history-campaign-publication `
  data\market-store\.publication-campaigns\m2-representative-5x24--<plan-prefix> `
  --campaign-root data\history\.campaigns\m2-representative-5x24--<plan-prefix>
```

This command performs no exchange request. For an already committed aggregate publication it
uses ADR-0046 receipt-integrity reverification: every Landing page byte, receipt, exact manifest
fact, child/aggregate chain, and canonical dataset is verified, but source market rows are not
decoded again. A successful result proves immutable publication and lineage only. Run the
separate candle and funding coverage audits before claiming requested-range quality; those audits
retain full source-row semantics. Register only explicitly selected verified datasets in the
catalog. Do not commit runtime campaign plans, Landing data, Parquet, or local catalog files.

After the evidence-builder implementation is merged, use that exact merge commit identity to
publish the GitHub-safe projection. The builder fully re-verifies source integrity and canonical
lineage using the completed-publication mode and records its monotonic elapsed milliseconds:

```powershell
.venv\Scripts\grid-data.exe history-campaign-publication-evidence `
  --publication-root data\market-store\.publication-campaigns\m2-representative-5x24--<plan-prefix> `
  --campaign-root data\history\.campaigns\m2-representative-5x24--<source-plan-prefix> `
  --software-identity git:<full-evidence-builder-merge-commit-sha> `
  --output benchmarks\results\m2-canonical-history-campaign-<date>.json
```

Commit only the resulting evidence JSON and receipt. The exact schema excludes runtime paths,
symbols, instrument/dataset identities, market values, account data, and credentials. Do not use
publication evidence as a substitute for the subsequent candle/funding coverage audits. A first
or pending publication must still run the semantic preflight above; never use the completed-only
integrity verifier to admit new source rows.

After the aggregate audit implementation is merged, use that exact merge SHA as the auditor
identity. The command is read-only for Landing/canonical storage and writes only the sanitized
evidence/receipt target:

```powershell
.venv\Scripts\grid-data.exe audit-history-campaign `
  --publication-root data\market-store\.publication-campaigns\m2-representative-5x24--<plan-prefix> `
  --campaign-root data\history\.campaigns\m2-representative-5x24--<source-plan-prefix> `
  --instrument-registry data\evidence\instrument-registry-20260813.json `
  --capacity-evidence benchmarks\results\m1-owner-storage-review-capacity-20260812.json `
  --store-root data\market-store `
  --publisher-software-identity git:<publication-merge-commit-sha> `
  --audit-software-identity git:<aggregate-auditor-merge-commit-sha> `
  --output benchmarks\results\m2-history-campaign-coverage-audit-<date>.json
```

Exit code 2 means the receipt-bound negative evidence was written successfully but one or more
children remain blocked. Inspect aggregate reason counts, then reproduce only the corresponding
private child audits when detailed repair or dated cadence evidence is needed. Never convert a
blocked aggregate to passed by editing the output or weakening ADR-0026/ADR-0034.

## 20. Adaptive public REST pacing

Adaptive public REST pacing follows ADR-0043. The configured request RPS remains a ceiling, never
an automatically tuned target. New Landing manifests record complete/absent/invalid Bybit header
observations and every decrease. HTTP 429 or retCode 10006 slows the whole child job; HTTP 403
aborts the run and must not be resumed for at least the reported ten-minute boundary. Verified
page receipts remain reusable after that stop.
