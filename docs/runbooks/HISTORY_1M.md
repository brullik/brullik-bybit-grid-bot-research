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

## 14. Register datasets and select a reproducible range

Catalog registration is a separate transition after canonical publication, repair, or compaction.
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

## 15. Acquire and publish canonical funding

Funding is a separate request and Landing contract because every first requested event needs the
authoritative settlement immediately before the range. Do not add `instrument_id`, launch time, or
funding interval to the request. Example `data\requests\btc-funding-2026-07.json`:

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
repair/compaction/catalog registration, or close Gate 2.
