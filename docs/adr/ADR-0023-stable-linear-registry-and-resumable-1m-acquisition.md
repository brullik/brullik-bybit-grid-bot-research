# ADR-0023: Stable Linear Registry and Resumable Public 1m Acquisition

- Status: accepted
- Date: 2026-08-12
- Implements: Phase 2 instrument snapshot and one-minute REST acquisition boundary

## Context

ADR-0021 requires a stable positive UInt32 `instrument_id` before candle publication. A history
request cannot safely accept an operator-invented number or renumber symbols whenever the current
inventory changes. The qualified M1 Bybit linear inventory contains 1,752 unique positive
`symbolId` values (5 through 2,853) and no duplicate symbol. Bybit exposes those values with the
instrument metadata response, independently of list order.

The qualified M1 public benchmark also demonstrated a finite 24-worker/10-RPS run, while the
documented IP ceiling was much higher. It did not implement a durable downloader, authorize the
96-RPS benchmark ceiling as an operating rate, or bound the bytes retained by failed/restarted
runs. Phase 2 therefore needs an explicit request contract, fixed page ownership, receipt-based
resume, and a fresh ADR-0019 host/capacity check before Landing mutation.

## Decision

Freeze `grid.instrument-registry/v1` with identity algorithm
`bybit-linear-source-symbol-id-v1`: for the Bybit `linear` category only,
`instrument_id = source_symbol_id`. Registry creation verifies a receipted
`grid.bybit-public-inventory/v1`, positive UInt32 range, unique IDs and symbols, exact decimal
metadata, source payload hashes, and deterministic ID ordering. Bybit's zero delivery-time
sentinel for perpetuals and zero funding-interval sentinel for non-funding products become
canonical null. The registry remains a dated snapshot; research
must join metadata by effective time and may not treat today's status as historical truth.

Freeze `grid.bybit-1m-history-request/v1`. Operator requests contain symbols and inclusive,
minute-aligned ranges but cannot contain `instrument_id`. Resolution accepts only USDT-settled
`LinearPerpetual` records from a verified registry and derives the identity. One job owns exactly
one dataset type, UTC calendar month, and `instrument_id mod 8` bucket.

Acquire trade and mark candles only from unauthenticated mainnet public endpoints:

- `GET /v5/market/kline`, interval `1`; and
- `GET /v5/market/mark-price-kline`, interval `1`.

The planner divides each range into deterministic, non-overlapping inclusive pages of at most
1,000 minutes. Default operation uses 24 workers, a global 10-RPS pacer, one transport attempt,
and up to three explicit application attempts. Hard ceilings are 32 workers, 96 requested RPS,
five attempts per page, and 100,000 HTTP attempts per run. The operational default is not raised
automatically from successful short runs.

No-mutation preflight verifies the registry and selected Gate 1 capacity artifacts, derives the
active-plus-building requirement, reserves 8 GiB for the operating system, and bounds Landing as
64 MiB plus 512 KiB for every planned page. It requires a fresh memory, local SSD/NVMe identity,
same-volume, and current-free-space observation. Execution repeats those checks before mutation
and before completion.

Each successful page is canonical JSON plus a SHA-256 receipt. Failed runs retain verified pages;
resume fetches only missing page identities. Partial pairs, stale locks, altered plans, oversized
pages, escaped timestamps, malformed decimals/OHLC, duplicate response timestamps, symlinks, and
orphan files fail closed. The manifest records per-page hashes, ranges, row/attempt counts,
evidence bindings, resource facts, and that tick rows were not requested. A separate completion
receipt is written last. Empty pages remain explicit source evidence and do not fabricate candles.

This boundary produces a verified Landing batch compatible with the ADR-0021 exact Arrow
contract. It does not yet declare lifecycle coverage complete, commit the batch into a canonical
dataset, ingest funding, repair gaps, compact files, or update the catalog. Gate 2 remains closed.

## Consequences

- Reordering or expanding a current Bybit linear inventory cannot renumber existing identities.
- Adding another exchange/category or exceeding UInt32 requires a new identity policy and
  migration; silent namespace reuse is forbidden.
- Current partial inventory can bootstrap known instruments but cannot prove all historical
  instruments or exact listing/delisting coverage.
- Fixed page ownership permits bounded parallelism and deterministic resume without cursor races.
- Landing storage is intentionally larger than typical payloads so admission is conservative and
  independent of decimal-string width.
- No API key, account identifier, tick archive, private endpoint, order, bot, or transfer is used.

## Rejected alternatives

- Assign IDs by sorted symbol: insertion of a new symbol would renumber history.
- Accept `instrument_id` in the operator request: it permits undetectable symbol/ID corruption.
- Use Python `hash(symbol)`: it is neither stable nor the benchmarked bucket identity.
- Start one backward cursor per instrument: sequential ownership reduces safe parallelism and
  makes page-level resume dependent on mutable cursor state.
- Run at the documented IP ceiling: the evidence supports a conservative operational baseline,
  not edge-of-limit production behavior.
- Delete failed Landing output automatically: it discards useful verified work and interruption
  evidence.
