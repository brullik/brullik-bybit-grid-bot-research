# M1 Bybit history-source assessment specification

## Purpose

Record the official Bybit Historical Market Data product catalog observed at a specific time and
bound the REST work required by the owner-approved one-minute-only source policy.
The assessment is read-only, unauthenticated, and does not download market rows.

## Command

```powershell
grid-data history-source-assessment `
  --instrument-inventory benchmarks/results/m1-bybit-public-inventory.json `
  --output benchmarks/results/m1-bybit-history-source-assessment.json
```

The immutable v1 command above records the original catalog classification. The append-only v2
policy evidence is produced with:

```powershell
grid-data history-source-assessment-1m `
  --instrument-inventory benchmarks/results/m1-owner-storage-review-inventory-20260812.json `
  --output benchmarks/results/m1-bybit-one-minute-source-assessment-20260812.json
```

The command preflights the output and verifies both the completion receipt and embedded content
hash of the inventory before making one GET request to the exact allowlisted catalog endpoint. It
then publishes the assessment atomically and writes its SHA-256 receipt last.

## Sources and classification

- The official [Historical Market Data page](https://www.bybit.com/en/derivative-activity/history-data)
  is backed by the public
  [product catalog](https://api2.bybit.com/quote/public/support/download/list-products).
- The catalog client accepts only the exact HTTPS origin and path, rejects redirects outside that
  endpoint, and fails closed on malformed or duplicate products.
- The observed five-product catalog advertises tick-level public trades for contracts, spot, and
  options; mark-price klines for options only; and no product whose ID or name identifies funding.
- ADR-0016 classifies the tick-level trade product as incompatible with V1. The versioned V5
  [trade-price kline](https://bybit-exchange.github.io/docs/v5/market/kline),
  [mark-price kline](https://bybit-exchange.github.io/docs/v5/market/mark-kline), and
  [funding history](https://bybit-exchange.github.io/docs/v5/market/history-fund-rate) endpoints
  are the current sources.

## Capacity calculation

All page counts are calculated per symbol and then summed. This preserves the endpoint contract
and avoids the optimistic error of combining residual rows from different symbols into one page.

The immutable v1 numbers below cover mark-price and funding only. V2 adds trade-price 1m because
tick aggregation is excluded. For the planning envelope of 700 instruments over 3,681,644,400
instrument-minutes per candle dataset:

- trade-price 1m needs 3,682,000 requests at the 1,000-row page limit;
- mark-price 1m needs 3,682,000 requests at the documented 1,000-row page limit;
- funding needs 307,300 requests at a conservative 60-minute interval and 200-event page limit;
- the v2 combined request count is 7,671,300;
- v2 request-only time is at least 63,928 seconds at the documented default IP limit of 120
  requests per second, or 767,130 seconds at the 10 requests/second planning rate.

The immutable v1 estimate applies lifecycle and current funding-interval fields to 1,006 observed
USDT linear perpetual records. The v2 artifact binds the later 1,010-record owner inventory. It
estimates 885,570 REST pages for each candle dataset and 1,785,544 total requests with current
funding intervals, or 1,845,401 with a conservative 60-minute funding interval.

The append-only
[current-universe capacity report](M1_CURRENT_UNIVERSE_CAPACITY.md) can combine a fresh assessment
with the v3 real-market calibration and a fresh workstation snapshot. It separates one-time
canonical bootstrap/rebuild headroom from bounded daily/monthly incremental updates without
claiming that lifecycle minutes are downloaded coverage.

## Interpretation limits

- The frontend catalog endpoint is official and public but is not a versioned V5 API contract.
- Product absence means `not advertised at observation time`; it does not prove permanent
  nonexistence.
- The inventory is partial and omits historical symbols absent from the current snapshot.
- Current lifecycle and funding-interval metadata cannot be treated as dated historical metadata.
- Request-only timing excludes latency, retry, validation, throttling headroom, and publication.
- This evidence resolves source classification and bounds REST capacity. It does not select a
  physical layout, accept reference hardware, or close Gate 1.
- V2 explicitly records `tick_data_downloaded=false` and `tick_data_retained=false`; the command
  itself makes only one catalog request and downloads no market rows.
