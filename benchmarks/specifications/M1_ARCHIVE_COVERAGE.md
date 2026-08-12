# M1 official archive coverage specification

## Purpose

Compare the verified current Bybit USDT LinearPerpetual inventory with the observed
`public.bybit.com` indexes without downloading raw trade files or treating a directory listing as
a complete historical registry.

## Command

```powershell
grid-data archive-coverage `
  --instrument-inventory benchmarks/results/m1-bybit-public-inventory.json `
  --sample-size 20 `
  --output benchmarks/results/m1-bybit-archive-coverage.json --force
```

The command preflights the output and verifies both the completion receipt and embedded content
hash of the instrument inventory before any network request.

## Bounded coverage method

- Compare every current USDT LinearPerpetual symbol with the observed `/trading/` index.
- Directly probe every current symbol missing from that index.
- Directly probe every current `PreLaunch` symbol because status semantics are material to
  historical eligibility.
- Fill the remaining 20-symbol budget with a deterministic launch-time-stratified sample.
- Inspect every advertised top-level archive product, retaining only child counts and at most 20
  link names per product.
- Retain only gap counts and at most 20 missing-date examples per detailed symbol.
- Distinguish a path containing files, an existing path containing no daily files, and HTTP 404.
  Other HTTP or network failures abort the whole report.

## Interpretation limits

- The separate receipt-pinned
  [history-source assessment](M1_HISTORY_SOURCE_ASSESSMENT.md) records the product semantics
  advertised by the official Historical Market Data catalog. This archive report does not infer
  mark-price or funding semantics from directory names.
- A symbol absent from the `/trading/` listing may still have an accessible direct archive path.
- A product name absent from the root index is `not advertised in the observed index`; it is not
  proof that no unlisted path exists.
- Current `launchTime` and status fields are undated-current metadata. They cannot be substituted
  for historical metadata snapshots.
- The report inventories daily raw trade archives. It does not relabel premium-index or other
  products as canonical mark-price/funding data.
- The dedicated V5 mark-kline and funding-history REST endpoints remain the implemented paths for
  linear-contract mark-price 1m and funding datasets.
- Raw trade files and directory HTML are not committed; only bounded JSON evidence and its
  SHA-256 receipt enter Git.
