# Changelog

## 1.1.6

- Restored the original tool's spreadsheet-compatible behavior for unavailable results.
- No-match, failed, skipped, and quota-stopped rows retain the ASIN in column A while leaving Title, Best Price, Condition, and Listing URL blank.
- Applied the same clean blank-cell behavior to both CSV and XLSX output so status text cannot break filters or formulas.
- Added regression tests covering no-match, API-error, and quota-skipped rows in both formats.

## 1.1.5

- Kept the broader unmatched-ISBN retry enabled by default because it recovered most matches in the 1,706-book test.
- Added a clearly labeled option to disable that retry and reproduce the original tool's one-search-per-book behavior.
- Added pre-scan minimum/maximum API call estimates.
- Separated search API calls/quota from item-detail API calls/quota.
- Added a configurable quota reserve that stops safely and writes partial results before the reported quota is exhausted.
- Reused shipping already present in eBay search results, avoiding item-detail calls unless shipping is missing.
- Added CSV, XLSX, and dual-output options; CSV is now the default for formula compatibility.
- Locally adjusts remaining quota when eBay's analytics response has not caught up yet.

## 1.1.4

- Fixed the quota display to select eBay's `item_summary` search quota instead of the unused item-detail quota.
- Renamed the quota output to make clear that it applies to Browse searches.
- Added a compact per-run breakdown such as `1,706 first searches + 1,348 second searches`.

## 1.1.3

- Convert eBay's UTC quota-reset timestamp to the user's local system time.
- Display the reset as `MM-DD-YYYY h:mm AM/PM` instead of raw ISO 8601.

## 1.1.2

- Removed the repeated API-request tutorial from every completed scan.
- Kept the useful run results: processed, matches, no matches, failures, requests used, elapsed time, daily quota, reset time, and output path.
- Retained only a short note when eBay's separate quota report appears delayed.

## 1.1.1

- Fixed a double theme guard that prevented every stylesheet from being applied in v1.1.0.
- Extended executable smoke tests to fail when light and dark themes are missing or identical.
- Applied the selected theme to credential dialogs, message boxes, and tray menus.
- Reworded the eBay request breakdown as simple addition: first searches + second searches + shipping checks = total requests.
- Simplified the separate daily-quota explanation.

## 1.1.0

- Removed the always-visible eBay credential fields from the main window; missing credentials are requested in a dedicated dialog and stored in Windows Credential Manager.
- Fixed clipped statistic labels and values by giving the cards reliable minimum sizing.
- Removed the explanatory subtitle and redundant input/output footer text.
- Added clickable ASIN cells that open general eBay searches for competing offers.
- Added an exact request breakdown for primary searches, fallback searches, and shipping-detail requests.
- Clarified that eBay's separately reported daily quota can lag behind the live per-run request count.
- Made relative input filenames such as `list.csv` resolve beside the executable.
- Added the Trivy and Syft supply-chain audit workflow used by Book Resale Calculator.

## 1.0.1

- Changed the Windows package from PyInstaller one-file to the more reliable onedir layout.
- Pinned the desktop runtime to Python 3.12, PySide6 6.8.3, and PyInstaller 6.21.0.
- Added startup crash logging and a native error dialog instead of silent exits.
- Added explicit frozen Qt plugin-path setup.
- Added CI smoke tests that launch both the built and packaged executables.

## 1.0.0

- Rewritten from scratch as **Book Resale Finder**.
- Added a responsive desktop GUI with progress, elapsed time, cancellation, live counters, and integrated completion details.
- Changed the default input to `masterlist.csv` and the required header to `ASIN`.
- Added optional shipping-aware comparisons.
- Added styled XLSX output with requested column names and widths.
- Added light, dark, and automatic themes matching Book Resale Calculator.
- Added secure credential storage, migration from the old tool's keyring entry, and a magnifying-glass/dollar-bill tray icon.
