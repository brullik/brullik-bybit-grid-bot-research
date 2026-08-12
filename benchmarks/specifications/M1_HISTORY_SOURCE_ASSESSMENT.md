# M1 Bybit history-source assessment specification

## Purpose

Record the official Bybit Historical Market Data product catalog observed at a specific time and
bound the REST work that remains for linear-contract mark-price 1m candles and funding events.
The assessment is read-only, unauthenticated, and does not download market rows.

## Command

```powershell
grid-data history-source-assessment `
  --instrument-inventory benchmarks/results/m1-bybit-public-inventory.json `
  --output benchmarks/results/m1-bybit-history-source-assessment.json
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
- The observed five-product catalog advertises public trades for contracts, spot, and options;
  mark-price klines for options only; and no product whose ID or name identifies funding.
- The versioned V5 [mark-price kline](https://bybit-exchange.github.io/docs/v5/market/mark-kline)
  and [funding history](https://bybit-exchange.github.io/docs/v5/market/history-fund-rate)
  endpoints therefore remain the implemented sources for those linear-contract datasets.

## Capacity calculation

All page counts are calculated per symbol and then summed. This preserves the endpoint contract
and avoids the optimistic error of combining residual rows from different symbols into one page.

For the planning envelope of 700 instruments over 3,681,644,400 instrument-minutes:

- mark-price 1m needs 3,682,000 requests at the documented 1,000-row page limit;
- funding needs 307,300 requests at a conservative 60-minute interval and 200-event page limit;
- the combined request count is 3,989,300;
- request-only time is at least 33,245 seconds at the documented default IP limit of 120 requests
  per second, or 398,930 seconds at the 10 requests/second planning rate.

The receipt-pinned current inventory estimate is also retained separately. It applies lifecycle
and current funding-interval fields to 1,006 observed USDT linear perpetual records and reports
per-symbol request counts for both current intervals and the conservative observed 60-minute
minimum.

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
