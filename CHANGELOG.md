# Changelog

## 1.1.12

- Fixed the scan dashboard at four stable metrics: identifiers processed, matches found, search API calls, and Browse quota remaining.
- Removed the shipping-only item-detail call counter from the prominent card grid.
- Keep item-detail usage in the completion text only when shipping was enabled or an item-detail call actually occurred.
- Moved the Browse quota card into the fourth grid position so the dashboard no longer leaves an empty slot.
- Added unit and frozen-executable checks for the four-card layout.

## 1.1.11

- Fixed quota parsing for eBay's production resource names: `buy.browse` and `buy.browse.item.bulk`.
- Treat search and item-detail shipping requests as consumers of one shared `buy.browse` daily quota.
- Ignore the separate `buy.browse.item.bulk` quota because the app does not call the bulk `getItems` method.
- Enforce the configured reserve against the combined total of search and item-detail calls.
- Replace the separate search/item-detail quota cards with one **Browse quota remaining** card.
- Reconcile locally adjusted remaining quota against every Browse call made during the run.

## 1.1.10

- Added sanitized diagnostics for eBay Developer Analytics quota requests.
- Report exact HTTP failures, including 204 No Content, 4xx/5xx responses, empty bodies, invalid JSON, and network/client errors.
- When eBay returns a successful but unrecognized quota payload, list only the API/context/resource names that were returned.
- Redact the Client ID, Client Secret, OAuth token, and authorization values from all displayed diagnostics.
- Keep scan results and API-call behavior unchanged; this release is intended to identify why the live quota value is missing.

## 1.1.9

- Keep quota cards dedicated to quota data instead of relabeling them with unrelated scan statistics.
- Hide an individual quota card when eBay provides no value for that quota.
- Keep no-match, failed, and not-scanned counts in the completion summary where they belong.
- Show one direct warning when a configured safety buffer could not be enforced because eBay returned no quota data.

## 1.1.8

- Fixed quota parsing for eBay Analytics responses that name Browse limits by API method (`search` and `getItem`) instead of endpoint resource (`item_summary` and `item`).
- Retry quota retrieval once without API filters when the filtered response omits the needed limits.
- Removed useless `quota remaining: unavailable` lines from the completion summary.
- When quota data is genuinely absent, reuse the two quota cards for useful no-match, failed, and not-scanned counts.
- Clearly warn when a configured quota safety buffer could not be enforced because eBay supplied no quota data.

## 1.1.7

- Fixed the six scan-stat cards hiding their values when the window was vertically compressed.
- Replaced the two-line cards with compact one-line label/value rows that remain visible at supported window sizes.
- Added a frozen-executable smoke test that fails if any scan-stat value is clipped or invisible.
- Renamed `Keep unused quota` to `Stop with at least … calls remaining` and clarified that setting it to zero disables the safety buffer.

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
