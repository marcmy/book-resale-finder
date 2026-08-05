# Changelog

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
