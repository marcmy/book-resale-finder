# Book Resale Finder

A from-scratch desktop rewrite of the former `isbn_lookup.exe` utility. It reads a Keepa-style `masterlist.csv`, searches active eBay listings, and writes a readable XLSX workbook.

## What changed

- Input filename defaults to `masterlist.csv`.
- Input column is `ASIN` (case-insensitive).
- Output columns are `ASIN`, `Title`, `Best Price`, `Condition`, and `Listing URL`.
- Output is XLSX, with approximate physical widths of 1.5, 5.0, 1.5, 1.5, and 8.0 inches.
- Full GUI with Start, progress, live counters, elapsed time, cancellation, shipping-cost toggle, and an integrated completion summary.
- Light, dark, and automatic themes use the same visual language as Book Resale Calculator.
- eBay credentials are stored through the operating system keyring (Windows Credential Manager on Windows).
- Window, taskbar, and system-tray icon use a magnifying glass plus dollar bill design.

## Input

Place `masterlist.csv` beside `BookResaleFinder.exe`, or choose another CSV from the GUI. The file must contain an `ASIN` column.

```csv
ASIN
9780306406157
0306406152
B000HCWBCG
```

ISBN-10 values are converted to ISBN-13. Amazon product URLs and raw ten-character ASINs are also accepted. Non-book ASINs use eBay keyword search because eBay's GTIN search does not accept Amazon-specific identifiers.

## eBay credentials

Create production application keys in the eBay Developer Program. On first launch, enter the Client ID (App ID) and Client Secret (Cert ID), then select **Save credentials**.

Credentials can also be supplied using `EBAY_CLIENT_ID` and `EBAY_CLIENT_SECRET`, or as `client_id` and `client_secret` entries in `config.yaml` (not recommended for a shared computer).

## Build on Windows

```powershell
pwsh ./scripts/build.ps1
```

The portable package is created at `dist/BookResaleFinder-Windows.zip`.

## Development

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -e ".[test]"
python -m pytest
python -m book_resale_finder
```
