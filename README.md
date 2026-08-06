# Book Resale Finder

A desktop eBay price finder for Keepa-style book lists. It reads a CSV containing an `ASIN` column, finds the lowest eligible active offer for each identifier, and writes CSV, XLSX, or both.

## Features

- The input filename defaults to `masterlist.csv`, but the GUI can browse to any CSV. A relative name such as `list.csv` is resolved beside `BookResaleFinder.exe`.
- The input column is `ASIN` (case-insensitive).
- Output columns are exactly `ASIN`, `TITLE`, `LOWEST`, `CONDITION`, and `LISTING` for compatibility with existing spreadsheet formulas.
- CSV is the default output and contains plain values for compatibility with existing spreadsheet formulas.
- When no usable listing is returned, the ASIN remains in column A and all result cells remain blank. No status phrases are inserted into CSV or XLSX cells.
- XLSX remains available with requested column widths, currency formatting, and clickable ASIN/listing links. Both formats can be created in one scan.
- The recommended search mode performs a structured ISBN search and retries unmatched ISBNs with a broader keyword search. The retry can be disabled to reproduce the original tool's one-search-per-book behavior.
- The GUI estimates minimum and maximum API calls before a scan starts.
- Search and item-detail calls are counted separately for transparency, but both consume one shared daily eBay Browse quota.
- A configurable quota reserve stops the scan safely and writes partial results before the shared Browse quota is exhausted.
- Shipping already present in eBay search results is reused; item-detail calls are made only for candidates whose search result omitted shipping.
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

## Search behavior and API calls

The broader retry is enabled by default because it recovered 1,253 additional matches in the reported 1,706-book scan. That run used 1,706 first searches plus 1,348 broader retries, for 3,054 Browse API calls.

Disabling **Retry unmatched ISBNs with a broader search** restores the original tool's one-pass behavior and reduces calls, but can miss listings where a seller placed the ISBN in searchable text without filling eBay's structured ISBN field.

Shipping is not a simple doubling of calls. It adds between zero and the configured candidate limit per matched identifier. Search-result shipping is reused without another call; only missing shipping values require item-detail requests.

The Developer Analytics response identifies the normal shared quota as `buy.browse`. Searches and individual `getItem` shipping lookups both consume that pool. The separate `buy.browse.item.bulk` quota applies to the bulk `getItems` method, which this application does not call.

The app displays one **Browse quota remaining** value and enforces the safety reserve against the combined total of search and item-detail calls. If eBay's analytics response has not caught up yet, the app subtracts its own exact call total from the starting value and labels the result as locally adjusted.

## Output formats

- **CSV:** plain values with no currency styling or embedded hyperlinks; best for existing formulas and workflows.
- **XLSX:** formatted columns, currency display, and clickable links.
- **Both:** produces matching CSV and XLSX files from the same results.

Both formats use the exact header row `ASIN,TITLE,LOWEST,CONDITION,LISTING`. Unavailable results preserve row alignment by retaining the ASIN while leaving TITLE, LOWEST, CONDITION, and LISTING empty. The GUI completion summary still reports no-match, failed, skipped, and quota-stop counts separately.

## eBay credentials

Create production application keys in the eBay Developer Program. When credentials are missing, the application asks for the Client ID (App ID) and Client Secret (Cert ID) and stores them in Windows Credential Manager. They can later be replaced from the system-tray menu.

Credentials can also be supplied using `EBAY_CLIENT_ID` and `EBAY_CLIENT_SECRET`, or as `client_id` and `client_secret` entries in `config.yaml` (not recommended for a shared computer).

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
