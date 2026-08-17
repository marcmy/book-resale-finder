param(
    [string]$Config = "$PSScriptRoot\config.json",
    [int]$Port = 8765
)

$ErrorActionPreference = "Stop"

if (-not (Test-Path -LiteralPath $Config)) {
    Write-Error "Missing config file: $Config`nCopy config.example.json to config.json and fill in your SP-API credentials."
}

$Python = Get-Command py -ErrorAction SilentlyContinue
if ($Python) {
    & py -3.12 "$PSScriptRoot\server.py" --config $Config --port $Port
    exit $LASTEXITCODE
}

& python "$PSScriptRoot\server.py" --config $Config --port $Port
exit $LASTEXITCODE
