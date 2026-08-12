[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [ValidatePattern('^[A-Z0-9]+$')]
    [string]$Symbol,

    [Parameter(Mandatory = $true)]
    [ValidateRange(2, 400)]
    [int]$CellNumber,

    [Parameter(Mandatory = $true)]
    [ValidatePattern('^[0-9]+(?:\.[0-9]+)?$')]
    [string]$MinPrice,

    [Parameter(Mandatory = $true)]
    [ValidatePattern('^[0-9]+(?:\.[0-9]+)?$')]
    [string]$MaxPrice,

    [Parameter(Mandatory = $true)]
    [ValidatePattern('^[0-9]+(?:\.[0-9]+)?$')]
    [string]$Leverage,

    [Parameter(Mandatory = $true)]
    [ValidatePattern('^[0-9]+(?:\.[0-9]+)?$')]
    [string]$StopLossPrice,

    [Parameter(Mandatory = $true)]
    [ValidatePattern('^[0-9]+(?:\.[0-9]+)?$')]
    [string]$TakeProfitPrice,

    [Parameter(Mandatory = $true)]
    [string]$Output
)

$ErrorActionPreference = 'Stop'
$repoRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
$cli = Join-Path $repoRoot '.venv\Scripts\grid-bybit-validate.exe'
if (-not (Test-Path -LiteralPath $cli -PathType Leaf)) {
    throw "validate-only CLI is not installed at $cli"
}

$resolvedOutput = [IO.Path]::GetFullPath((Join-Path $repoRoot $Output))
$privateRoot = [IO.Path]::GetFullPath((Join-Path $repoRoot 'reports\private'))
if (-not $resolvedOutput.StartsWith($privateRoot + [IO.Path]::DirectorySeparatorChar)) {
    throw 'Output must be below reports/private.'
}
if ((Test-Path -LiteralPath $resolvedOutput) -or (Test-Path -LiteralPath "$resolvedOutput.receipt.json")) {
    throw "Private output already exists: $resolvedOutput"
}

$keySecure = $null
$secretSecure = $null
$keyPtr = [IntPtr]::Zero
$secretPtr = [IntPtr]::Zero
try {
    Write-Host 'Bybit Demo validate-only: no bot or order will be created.' -ForegroundColor Cyan
    Write-Host "Parameters: $Symbol, $MinPrice-$MaxPrice, $CellNumber cells, leverage $Leverage, SL $StopLossPrice, TP $TakeProfitPrice"
    $keySecure = Read-Host 'BYBIT_DEMO_API_KEY' -AsSecureString
    $secretSecure = Read-Host 'BYBIT_DEMO_API_SECRET' -AsSecureString
    $keyPtr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($keySecure)
    $secretPtr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secretSecure)
    $env:BYBIT_DEMO_API_KEY = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($keyPtr)
    $env:BYBIT_DEMO_API_SECRET = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($secretPtr)

    & $cli doctor
    if ($LASTEXITCODE -ne 0) { throw "doctor failed with exit code $LASTEXITCODE" }

    & $cli probe `
        --environment demo `
        --symbol $Symbol `
        --cell-number $CellNumber `
        --min-price $MinPrice `
        --max-price $MaxPrice `
        --leverage $Leverage `
        --stop-loss-price $StopLossPrice `
        --take-profit-price $TakeProfitPrice `
        --output $resolvedOutput
    $probeExitCode = $LASTEXITCODE

    if (Test-Path -LiteralPath $resolvedOutput -PathType Leaf) {
        & $cli verify $resolvedOutput
        if ($LASTEXITCODE -ne 0) { throw "private receipt verification failed" }
        & git -C $repoRoot check-ignore $resolvedOutput
        if ($LASTEXITCODE -ne 0) { throw "private report is not ignored by Git" }
    }
    if ($probeExitCode -ne 0) {
        throw "Demo validate returned a non-success result (exit code $probeExitCode)"
    }
    Write-Host 'Demo validate succeeded; receipt verified and report is Git-ignored.' -ForegroundColor Green
}
catch {
    Write-Host $_.Exception.Message -ForegroundColor Red
    Write-Host 'The key was not retried against Testnet or Mainnet.' -ForegroundColor Yellow
}
finally {
    Remove-Item Env:BYBIT_DEMO_API_KEY -ErrorAction SilentlyContinue
    Remove-Item Env:BYBIT_DEMO_API_SECRET -ErrorAction SilentlyContinue
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
