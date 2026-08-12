[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [switch]$AcknowledgeUnifiedAccount
)

$ErrorActionPreference = 'Stop'
$repoRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
$cli = Join-Path $repoRoot '.venv\Scripts\grid-bybit-validate.exe'
if (-not (Test-Path -LiteralPath $cli -PathType Leaf)) {
    throw "validate-only CLI is not installed at $cli"
}
if (-not $AcknowledgeUnifiedAccount) {
    throw 'Mainnet discovery requires visible confirmation that the UTA migration is complete.'
}

# 2026-08-12 public shortlist: each instrument advertised a 5 USDT minimum order value,
# at least 50 million USDT 24h turnover, and a tight top-of-book spread. CYSUSDT met the
# mechanical filter but was excluded because its observed 24h range was unusually wide.
$candidates = @(
    [pscustomobject]@{
        Symbol = 'XRPUSDT'; MinPrice = '0.99'; MaxPrice = '1.04'
        StopLossPrice = '0.98'; TakeProfitPrice = '1.05'
    },
    [pscustomobject]@{
        Symbol = 'DOGEUSDT'; MinPrice = '0.069'; MaxPrice = '0.074'
        StopLossPrice = '0.068'; TakeProfitPrice = '0.075'
    },
    [pscustomobject]@{
        Symbol = 'LINKUSDT'; MinPrice = '8.4'; MaxPrice = '8.9'
        StopLossPrice = '8.3'; TakeProfitPrice = '9.0'
    }
)

$outputs = @{}
foreach ($candidate in $candidates) {
    $name = $candidate.Symbol.ToLowerInvariant()
    $output = Join-Path $repoRoot "reports\private\m1-fgrid-validate-mainnet-$name.json"
    $receipt = "$output.receipt.json"
    if ((Test-Path -LiteralPath $output) -or (Test-Path -LiteralPath $receipt)) {
        throw "Private output already exists: $output"
    }
    & git -C $repoRoot check-ignore $output | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "private report is not ignored by Git: $output" }
    $outputs[$candidate.Symbol] = $output
}

$keySecure = $null
$secretSecure = $null
$keyPtr = [IntPtr]::Zero
$secretPtr = [IntPtr]::Zero
$exitCode = 0
try {
    Write-Host 'Bybit Mainnet validate-only discovery: no bot, order, or transfer will be created.' -ForegroundColor Cyan
    Write-Host 'Three distinct candidates will each be validated once; there are no retries.'
    Write-Host 'Candidates use 2 cells and leverage 1 to measure a low-capital, lower-leverage baseline.'
    $keySecure = Read-Host 'BYBIT_MAINNET_API_KEY' -AsSecureString
    $secretSecure = Read-Host 'BYBIT_MAINNET_API_SECRET' -AsSecureString
    $keyPtr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($keySecure)
    $secretPtr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secretSecure)
    $env:BYBIT_MAINNET_API_KEY = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($keyPtr)
    $env:BYBIT_MAINNET_API_SECRET = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($secretPtr)

    & $cli doctor
    if ($LASTEXITCODE -ne 0) { throw "doctor failed with exit code $LASTEXITCODE" }

    foreach ($candidate in $candidates) {
        $output = $outputs[$candidate.Symbol]
        Write-Host "Validating $($candidate.Symbol) once..." -ForegroundColor Cyan
        & $cli probe `
            --environment mainnet `
            --acknowledge-mainnet-validate-only `
            --symbol $candidate.Symbol `
            --cell-number 2 `
            --min-price $candidate.MinPrice `
            --max-price $candidate.MaxPrice `
            --leverage 1 `
            --stop-loss-price $candidate.StopLossPrice `
            --take-profit-price $candidate.TakeProfitPrice `
            --output $output

        if (-not (Test-Path -LiteralPath $output -PathType Leaf)) {
            throw "validate did not publish a private report for $($candidate.Symbol)"
        }
        & $cli verify $output
        if ($LASTEXITCODE -ne 0) {
            throw "private receipt verification failed for $($candidate.Symbol)"
        }
    }

    Write-Host 'Redacted results (private response bodies are not printed):' -ForegroundColor Cyan
    foreach ($candidate in $candidates) {
        $payload = Get-Content -LiteralPath $outputs[$candidate.Symbol] -Raw | ConvertFrom-Json
        $investmentFrom = $payload.response.result.investment.from
        [pscustomobject]@{
            Symbol = $candidate.Symbol
            RetCode = $payload.result.ret_code
            CheckCode = $payload.result.check_code
            Successful = $payload.result.successful
            MinimumInvestment = $investmentFrom
        } | Format-Table -AutoSize
    }
}
catch {
    $exitCode = 1
    Write-Host $_.Exception.Message -ForegroundColor Red
    Write-Host 'No call was retried and no create/order/transfer endpoint exists in this CLI.' -ForegroundColor Yellow
}
finally {
    Remove-Item Env:BYBIT_MAINNET_API_KEY -ErrorAction SilentlyContinue
    Remove-Item Env:BYBIT_MAINNET_API_SECRET -ErrorAction SilentlyContinue
    if ($keyPtr -ne [IntPtr]::Zero) {
        [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($keyPtr)
    }
    if ($secretPtr -ne [IntPtr]::Zero) {
        [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($secretPtr)
    }
    if ($null -ne $keySecure) { $keySecure.Dispose() }
    if ($null -ne $secretSecure) { $secretSecure.Dispose() }
}

Write-Host 'Credentials were removed from this process. Press Enter to close.' -ForegroundColor Cyan
[void](Read-Host)
exit $exitCode
