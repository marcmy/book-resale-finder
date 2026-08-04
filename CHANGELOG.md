# Changelog

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
