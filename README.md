# Book Resale Finder

A desktop eBay price finder for Keepa-style book lists. It reads a CSV containing an `ASIN` column, finds the lowest eligible active offer for each identifier, and writes a formatted XLSX workbook.

## Features

- The input filename defaults to `masterlist.csv`, but the GUI can browse to any CSV. A relative name such as `list.csv` is resolved beside `BookResaleFinder.exe`.
- The input column is `ASIN` (case-insensitive).
- Output columns are `ASIN`, `Title`, `Best Price`, `Condition`, and `Listing URL`.
- Output is XLSX, with approximate physical widths of 1.5, 5.0, 1.5, 1.5, and 8.0 inches.
- ASIN cells link to a general eBay search so competing offers can be reviewed; Listing URL cells link to the selected offer.
- The GUI shows progress, elapsed time, matches, an exact per-run eBay lookup-request count, and a request breakdown.
- Optional shipping-aware comparison checks individual candidate listings and therefore uses additional eBay requests.
- Light, dark, and automatic themes use the same visual language as Book Resale Calculator.
- eBay credentials are stored through the operating-system keyring (Windows Credential Manager on Windows) and are not displayed on the main screen.

## Input

Extract the complete release folder and keep the `_internal` directory beside `BookResaleFinder.exe`. Place a CSV beside the executable or choose one with **Browse**. The file must contain an `ASIN` column.

```csv
ASIN
9780306406157
0306406152
B000HCWBCG
```

ISBN-10 values are converted to ISBN-13. Amazon product URLs and raw ten-character ASINs are also accepted. Non-book ASINs use eBay keyword search because eBay's GTIN search does not accept Amazon-specific identifiers.

## eBay credentials

Create production application keys in the eBay Developer Program. When credentials are missing, the application asks for the Client ID (App ID) and Client Secret (Cert ID) and stores them in Windows Credential Manager. They can later be replaced from the system-tray menu.

Credentials can also be supplied using `EBAY_CLIENT_ID` and `EBAY_CLIENT_SECRET`, or as `client_id` and `client_secret` entries in `config.yaml` (not recommended for a shared computer).

## Request accounting

The completion panel separates primary searches, fallback searches, and shipping-detail requests. A book normally uses one primary search. An ISBN that returns no GTIN result can use one additional fallback keyword search. Enabling shipping can add one listing-detail request for each candidate checked.

The daily quota value comes from eBay's separate quota-reporting service and can lag behind the live per-run count. When that happens, the GUI marks the quota value and explains that the run counter is the accurate count for the completed scan.

## Build on Windows

```powershell
pwsh ./scripts/build.ps1
```

The portable package is created at `dist/BookResaleFinder-Windows.zip`. Extract the complete folder before running the executable.

## Development

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -e ".[test]"
python -m pytest
python -m book_resale_finder
```

## Startup diagnostics

If the application cannot open, it displays an error and writes `startup.log` under `%LOCALAPPDATA%\Book Resale Finder`.
