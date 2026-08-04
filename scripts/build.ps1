$ErrorActionPreference = 'Stop'
Set-Location (Split-Path -Parent $PSScriptRoot)

python -m pip install --upgrade pip
python -m pip install -r requirements-build.txt
python -m pytest
python scripts/generate_icon.py
python -m PyInstaller --noconfirm --clean BookResaleFinder.spec

$Executable = Join-Path $PWD 'dist\BookResaleFinder\BookResaleFinder.exe'
$env:BRF_SMOKE_TEST = '1'
$Process = Start-Process -FilePath $Executable -WorkingDirectory (Split-Path $Executable) -PassThru
$Finished = $Process.WaitForExit(30000)
Remove-Item Env:BRF_SMOKE_TEST -ErrorAction SilentlyContinue
if (-not $Finished) {
    Stop-Process -Id $Process.Id -Force -ErrorAction SilentlyContinue
    throw 'Frozen executable did not complete its startup smoke test.'
}
if ($Process.ExitCode -ne 0) {
    throw "Frozen executable exited with code $($Process.ExitCode)."
}

$PackageRoot = Join-Path $PWD 'dist\BookResaleFinder-package\BookResaleFinder'
Remove-Item (Split-Path $PackageRoot) -Recurse -Force -ErrorAction SilentlyContinue
New-Item $PackageRoot -ItemType Directory -Force | Out-Null
Copy-Item 'dist\BookResaleFinder\*' $PackageRoot -Recurse -Force
Copy-Item 'config.yaml' $PackageRoot
Copy-Item 'masterlist.csv' $PackageRoot
Copy-Item 'README.md' $PackageRoot
New-Item (Join-Path $PackageRoot 'output') -ItemType Directory -Force | Out-Null

$Zip = Join-Path $PWD 'dist\BookResaleFinder-Windows.zip'
Remove-Item $Zip -Force -ErrorAction SilentlyContinue
Compress-Archive -Path $PackageRoot -DestinationPath $Zip -Force
Write-Host "Built $Zip"
