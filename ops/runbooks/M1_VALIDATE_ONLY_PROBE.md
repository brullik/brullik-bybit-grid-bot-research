# M1 owner-controlled Futures Grid validate-only probe

## Safety boundary

This probe can call only `POST /v5/fgridbot/validate`. The package contains no create, close,
transfer, or order endpoint. It never retries and rejects redirects before following them. API
credentials are read from process environment variables and are never written to the report.

Testnet is the default and should be used first. Mainnet validation is read/validate-only but still
requires the explicit `--environment mainnet --acknowledge-mainnet-validate-only` pair. No command
in this runbook authorizes grid creation.

## Prerequisites

- System-generated HMAC API key. RSA keys are not supported by this M1 probe.
- Testnet key first; enable only the minimum Trading Bot permission required by Bybit.
- Withdrawal permission must be disabled.
- Synchronized Windows clock.
- Parameters reviewed by the owner: Neutral, Geometric, explicit stop loss, and exact decimals.

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

## Authoritative references

- [Bybit V5 authentication and signing](https://bybit-exchange.github.io/docs/v5/guide)
- [Official Trading MCP validate schema](https://github.com/bybit-exchange/trading-mcp/blob/main/src/tools/bot/validateFGridInput.ts)
- [Official Trading Bot module](https://github.com/bybit-exchange/skills/blob/main/modules/trading-bot.md)
