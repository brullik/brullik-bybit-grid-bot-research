# Open Questions and Required Evidence

These questions do not block the documentation baseline. They block specific implementation or live gates and must be resolved through authoritative documentation, measured experiments, or explicit owner decisions.

## Bybit and data coverage

1. Which official historical archive products provide trade-price 1m, mark-price 1m, and funding coverage for each relevant linear instrument and date?
2. How far back can REST recover data not present in archives, and are there instrument-specific discontinuities?
3. How are renamed, migrated, pre-listing, dated futures, and delisted contracts represented across archive/API history?
4. Which source is authoritative when archive and REST values conflict?
5. What are the exact regional/account requirements for native Futures Grid endpoints on the owner account?
6. Does validate-only behavior fully reflect create constraints for minimum investment and all target symbols?
7. Which private streams/events are sufficient to reconcile native grid creation, fills, positions, close reasons, funding, and PnL?
8. What are the current maker/taker/funding fee schedules applicable to the actual account tier?

## Capacity and performance

9. What effective stored bytes/row result from representative trade and mark schemas under candidate encodings?
10. Which month/bucket/file layout gives the best mix of all-universe time scans and single-symbol ten-year scans?
11. What hardware budget and disk capacity are available for the full research workstation?
12. Is a 250 GB historical-data target still a hard constraint once mark-price, derived stores, compaction headroom, and backup are included?
13. Should raw archives be retained permanently, content-addressed remotely, or deleted after verified canonical import?
14. Is local NVMe the source of truth or a cache over object storage?
15. At what measured point, if any, is a Rust/native kernel justified?

## Research and simulation

16. What exact baseline defines a “touch,” false breakout, middle zone, and horizontal slope tolerance?
17. How are simultaneous candidate windows deduplicated or represented?
18. Which features are shared/materialized versus experiment-specific?
19. What conservative intrabar ambiguity policy is accepted for 1m OHLC simulation?
20. How are native grid fills, fees, funding, liquidation, and close semantics validated against observed minimal-mainnet behavior?
21. Is SL-only acceptable after capital-lock analysis, or must a time/condition exit be added?
22. Which market regimes and stress periods are mandatory acceptance segments?
23. What exact OOS/embargo/out-of-symbol split is frozen before parameter search?
24. What minimum event count is required per fold/group before trusting a metric?

## Live and operations

25. Will production use a dedicated Bybit subaccount from the first mutating test?
26. What host/region/network and clock-synchronization setup will run live?
27. Who is authorized for Telegram approve/close/emergency/resume commands?
28. Is a second control channel required for emergency or high-impact approval?
29. What is the maximum allowed market-data age and private-stream outage before pausing entries?
30. How long may create/close remain uncertain before mandatory owner intervention?
31. Should an emergency close all managed grids immediately or apply symbol-specific policy?
32. What backup destination and retention satisfy live audit requirements?
33. What exact number of manual real executions is required before semi-automation? Current baseline: 100.
34. Which legal/jurisdiction/account restrictions must be verified before live operation?

## Governance

35. Which license should the public repository use? Until selected, `LICENSE_POLICY.md` intentionally grants no open-source license.
36. Which branch-protection and required-check settings will be enabled?
37. Who owns final promotion, risk-policy changes, and incident restart approval?
38. Which documentation and acceptance files are PM-owned/protected?
