# M1 owner-controlled Futures Grid validate-only probe

## Safety boundary

This probe can call only `POST /v5/fgridbot/validate`. The package contains no create, close,
transfer, or order endpoint. It never retries and rejects redirects before following them. API
credentials are read from process environment variables and are never written to the report.

Testnet is the default and should be used first. If the Testnet website is unavailable, Bybit Demo
Trading is the isolated fallback and uses `https://api-demo.bybit.com`; Bybit's published Demo API
list does not include this endpoint, so an unsupported response is valid feasibility evidence and
must never trigger automatic mainnet fallback. Mainnet validation still requires the explicit
`--environment mainnet --acknowledge-mainnet-validate-only` pair. No command in this runbook
authorizes grid creation.

## Prerequisites

- System-generated HMAC API key. RSA keys are not supported by this M1 probe.
- Testnet key first, or a key created while the main-site account visibly shows `Demo Trading`;
  enable only the minimum Trading Bot/Contract Order permission required by Bybit.
- Withdrawal permission must be disabled.
- Synchronized Windows clock.
- Parameters reviewed by the owner: Neutral, Geometric, explicit stop loss, and exact decimals.
- Before mainnet validation, the UI must visibly confirm that migration to the Unified Trading
  Account is complete. Do not validate while an account upgrade is processing.

## Load credentials without placing them in shell history

Use unique process-local variables. Enter values only into the secure prompts:

```powershell
$probeKeySecure = Read-Host 'BYBIT_TESTNET_API_KEY' -AsSecureString
$probeSecretSecure = Read-Host 'BYBIT_TESTNET_API_SECRET' -AsSecureString
$probeKeyPtr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($probeKeySecure)
$probeSecretPtr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($probeSecretSecure)
try {
  $env:BYBIT_TESTNET_API_KEY = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($probeKeyPtr)
  $env:BYBIT_TESTNET_API_SECRET = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($probeSecretPtr)
} finally {
  [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($probeKeyPtr)
  [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($probeSecretPtr)
}
```

## Preflight and probe

First prove the installed endpoint boundary:

```powershell
grid-bybit-validate doctor
```

Then substitute owner-reviewed current prices. The output path must remain under the Git-ignored
`reports/private/` directory and must not already exist:

```powershell
grid-bybit-validate probe `
  --symbol BTCUSDT `
  --cell-number 20 `
  --min-price <LOWER_PRICE> `
  --max-price <UPPER_PRICE> `
  --leverage 2 `
  --stop-loss-price <STOP_BELOW_LOWER> `
  --take-profit-price <TAKE_PROFIT_ABOVE_UPPER> `
  --output reports/private/m1-fgrid-validate-testnet.json
```

Success requires both `retCode=0` and
`check_code=FGRID_CHECK_CODE_UNSPECIFIED`. A successful validation is feasibility evidence only;
it is not permission to create a bot and does not close Gate 1 by itself.

Verify the receipt:

```powershell
grid-bybit-validate verify reports/private/m1-fgrid-validate-testnet.json
git check-ignore reports/private/m1-fgrid-validate-testnet.json
```

## Cleanup

Remove process credentials immediately after the probe:

```powershell
Remove-Item Env:BYBIT_TESTNET_API_KEY
Remove-Item Env:BYBIT_TESTNET_API_SECRET
```

Keep the private report outside Git. Record only a redacted owner/PM conclusion in public evidence.

## Demo Trading fallback

Create the key only after the Bybit header visibly shows `Demo Trading`. Demo, Testnet, and
mainnet keys are deliberately isolated by variable name. Load the Demo values through hidden
prompts:

```powershell
$probeKeySecure = Read-Host 'BYBIT_DEMO_API_KEY' -AsSecureString
$probeSecretSecure = Read-Host 'BYBIT_DEMO_API_SECRET' -AsSecureString
$probeKeyPtr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($probeKeySecure)
$probeSecretPtr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($probeSecretSecure)
try {
  $env:BYBIT_DEMO_API_KEY = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($probeKeyPtr)
  $env:BYBIT_DEMO_API_SECRET = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($probeSecretPtr)
} finally {
  [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($probeKeyPtr)
  [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($probeSecretPtr)
}
```

Use the same owner-reviewed exact-decimal parameters, but select Demo explicitly:

```powershell
grid-bybit-validate probe `
  --environment demo `
  --symbol BTCUSDT `
  --cell-number 20 `
  --min-price <LOWER_PRICE> `
  --max-price <UPPER_PRICE> `
  --leverage 2 `
  --stop-loss-price <STOP_BELOW_LOWER> `
  --take-profit-price <TAKE_PROFIT_ABOVE_UPPER> `
  --output reports/private/m1-fgrid-validate-demo.json

grid-bybit-validate verify reports/private/m1-fgrid-validate-demo.json
git check-ignore reports/private/m1-fgrid-validate-demo.json
```

Remove the Demo credentials immediately afterward:

```powershell
Remove-Item Env:BYBIT_DEMO_API_KEY
Remove-Item Env:BYBIT_DEMO_API_SECRET
```

## Mainnet minimum-investment discovery

Use this only after Testnet and Demo are unavailable or unsupported, the owner has separately
acknowledged validate-only mainnet access, and the Bybit UI visibly confirms a completed Unified
Trading Account migration. The script has no create/order/transfer endpoint. It validates three
distinct high-liquidity, 5-USDT-minimum-notional candidates once each, with two cells and leverage
1, then displays only the returned minimum investment fields:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass `
  -File scripts/discover_mainnet_validate_minimum.ps1 `
  -AcknowledgeUnifiedAccount
```

The three private reports stay under `reports/private/`. No failure may automatically retry or
fall back to a different environment. Delete the temporary key immediately after the run.

The owner completed this discovery on 2026-08-12. All three receipts verified and Bybit returned
successful validation for XRPUSDT, DOGEUSDT, and LINKUSDT. The returned minimum investment values
were respectively 0.1389, 0.0989, and 1.1887 USDT. These are observed `validate` lower bounds, not
an assurance that `create` will accept the same amount and not permission to trade. The private
response bodies remain ignored; the redacted public result is
`benchmarks/results/m1-bybit-mainnet-validate-conclusion.json`.

## Create capability boundary

Bybit's official rate-limit table lists `POST /v5/fgridbot/create`. The official Trading MCP
contract at commit `562291168e9fd3d679275bf28c16056d562cefce` requires the validated fields plus
`total_investment` and describes `bot_id` as the successful response identifier. This proves that
the exchange exposes a create capability; M1 does not call it.

A `create` request may place real orders. It remains blocked until the manual-mainnet phase has a
promoted strategy release, current instrument constraints, exact-decimal quantization, balance and
worst-loss evidence, durable audit/state storage, exact-payload approval, detail/reconciliation,
and close/emergency handling. Adding a raw create script to this M1 runbook would bypass those
project gates.

## Authoritative references

- [Bybit V5 authentication and signing](https://bybit-exchange.github.io/docs/v5/guide)
- [Bybit Demo Trading service and isolated API domain](https://bybit-exchange.github.io/docs/v5/demo)
- [Bybit Standard-to-UTA migration precautions](https://www.bybit.com/ru-RU/help-center/article/How-to-Upgrade-Standard-Account-to-UTA)
- [Official Trading MCP validate schema](https://github.com/bybit-exchange/trading-mcp/blob/main/src/tools/bot/validateFGridInput.ts)
- [Official Trading MCP create schema](https://github.com/bybit-exchange/trading-mcp/blob/562291168e9fd3d679275bf28c16056d562cefce/src/tools/bot/createFGridBot.ts)
- [Official Bybit rate limits including Futures Grid validate/create](https://bybit-exchange.github.io/docs/v5/rate-limit)
- [Official Trading Bot module](https://github.com/bybit-exchange/skills/blob/main/modules/trading-bot.md)
