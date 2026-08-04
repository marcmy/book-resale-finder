$ErrorActionPreference = 'Stop'
Set-Location (Split-Path -Parent $PSScriptRoot)

python -m pip install --upgrade pip
python -m pip install -r requirements-build.txt
python -m pytest
python scripts/generate_icon.py
python -m PyInstaller --noconfirm --clean BookResaleFinder.spec

$Package = Join-Path $PWD 'dist\BookResaleFinder-package'
Remove-Item $Package -Recurse -Force -ErrorAction SilentlyContinue
New-Item $Package -ItemType Directory | Out-Null
Copy-Item 'dist\BookResaleFinder.exe' $Package
Copy-Item 'config.yaml' $Package
Copy-Item 'masterlist.csv' $Package
New-Item (Join-Path $Package 'output') -ItemType Directory | Out-Null
Compress-Archive -Path "$Package\*" -DestinationPath 'dist\BookResaleFinder-Windows.zip' -Force
Write-Host "Built dist\BookResaleFinder-Windows.zip"
