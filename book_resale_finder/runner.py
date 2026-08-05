from __future__ import annotations

import asyncio
import time
from collections import defaultdict
from collections.abc import Callable
from dataclasses import replace
from datetime import datetime
from pathlib import Path
from typing import Any

from .csv_input import read_asins
from .ebay import EbayClient, EbayQuotaSafetyError
from .identifiers import normalize_identifier
from .models import ProgressInfo, QuotaInfo, RunSummary, SearchResult
from .workbook import write_results_csv, write_results_xlsx


class ScanCancelled(RuntimeError):
    pass


def _reconcile_quota(start: QuotaInfo, end: QuotaInfo, calls: int) -> QuotaInfo:
    if start.remaining is None:
        return end
    locally_expected = max(0, start.remaining - max(0, calls))
    if end.remaining is None or end.remaining > locally_expected:
        used = (start.used + calls) if start.used is not None else None
        return QuotaInfo(
            limit=start.limit or end.limit,
            used=used,
            remaining=locally_expected,
            reset_at=end.reset_at or start.reset_at,
            resource=end.resource or start.resource,
            estimated=True,
        )
    return end


async def run_scan(
    *,
    input_file: Path,
    output_dir: Path,
    config: dict[str, Any],
    client_id: str,
    client_secret: str,
    include_shipping: bool,
    retry_unmatched: bool = True,
    output_format: str = "csv",
    quota_reserve: int = 100,
    progress_callback: Callable[[ProgressInfo], None] | None = None,
    cancel_requested: Callable[[], bool] | None = None,
) -> RunSummary:
    started = time.monotonic()
    raw_identifiers = read_asins(input_file)
    normalized = [normalize_identifier(value) for value in raw_identifiers]

    grouped_indices: dict[str, list[int]] = defaultdict(list)
    for index, identifier in enumerate(normalized):
        key = identifier.primary_value.casefold()
        grouped_indices[key].append(index)
    unique_keys = list(grouped_indices)

    results: list[SearchResult | None] = [None] * len(raw_identifiers)
    completed_rows = found_rows = failed_rows = 0
    max_workers = max(1, int(config.get("max_workers", 10)))
    semaphore = asyncio.Semaphore(max_workers)
    completion_lock = asyncio.Lock()
    quota_stop: EbayQuotaSafetyError | None = None

    def is_cancelled() -> bool:
        return bool(cancel_requested and cancel_requested())

    async with EbayClient(client_id, client_secret, config) as ebay:
        starting_search_quota, starting_item_quota = await ebay.fetch_quotas()
        ebay.configure_quota_safety(
            starting_search_quota,
            starting_item_quota,
            max(0, int(quota_reserve)),
        )

        async def process_key(key: str) -> None:
            nonlocal completed_rows, found_rows, failed_rows
            if is_cancelled():
                raise ScanCancelled()
            first_index = grouped_indices[key][0]
            identifier = normalized[first_index]
            async with semaphore:
                if is_cancelled():
                    raise ScanCancelled()
                try:
                    result = await ebay.find_best_listing(
                        identifier,
                        include_shipping=include_shipping,
                        retry_unmatched=retry_unmatched,
                    )
                    matched = result.best_price is not None
                except (ScanCancelled, EbayQuotaSafetyError):
                    raise
                except Exception as exc:
                    result = SearchResult(
                        asin=identifier.original,
                        title="Lookup failed",
                        condition="Error",
                        note=str(exc),
                    )
                    matched = False
                    failure = True
                else:
                    failure = False

            for index in grouped_indices[key]:
                results[index] = replace(result, asin=raw_identifiers[index])

            async with completion_lock:
                row_count = len(grouped_indices[key])
                completed_rows += row_count
                if matched:
                    found_rows += row_count
                elif failure:
                    failed_rows += row_count
                if progress_callback:
                    progress_callback(
                        ProgressInfo(
                            completed=completed_rows,
                            total=len(raw_identifiers),
                            current_identifier=identifier.original,
                            api_calls=ebay.api_calls,
                            found=found_rows,
                            failed=failed_rows,
                            status=("Found listing" if matched else "Lookup failed" if failure else "No match"),
                            search_calls=ebay.search_calls,
                            item_detail_calls=ebay.item_detail_calls,
                        )
                    )

        tasks = [asyncio.create_task(process_key(key)) for key in unique_keys]
        try:
            await asyncio.gather(*tasks)
        except ScanCancelled:
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            raise
        except EbayQuotaSafetyError as exc:
            quota_stop = exc
            for task in tasks:
                if not task.done():
                    task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)

        if is_cancelled():
            raise ScanCancelled()

        ending_search_quota, ending_item_quota = await ebay.fetch_quotas()
        api_calls = ebay.api_calls
        api_call_breakdown = dict(ebay.api_call_breakdown)
        search_calls = ebay.search_calls
        item_detail_calls = ebay.item_detail_calls

    skipped = 0
    if quota_stop:
        for index, result in enumerate(results):
            if result is None:
                results[index] = SearchResult(
                    asin=raw_identifiers[index],
                    title="Not scanned — quota safety reserve reached",
                    condition="Not scanned",
                    note=str(quota_stop),
                )
                skipped += 1

    final_results = [result for result in results if result is not None]
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    prefix = str(config.get("output_prefix", "book_resale_results"))
    output_dir.mkdir(parents=True, exist_ok=True)
    output_format = str(output_format).strip().casefold()
    if output_format not in {"csv", "xlsx", "both"}:
        output_format = "csv"

    output_files: list[Path] = []
    if output_format in {"csv", "both"}:
        csv_file = output_dir / f"{prefix}_{timestamp}.csv"
        write_results_csv(final_results, csv_file)
        output_files.append(csv_file)
    if output_format in {"xlsx", "both"}:
        xlsx_file = output_dir / f"{prefix}_{timestamp}.xlsx"
        write_results_xlsx(final_results, xlsx_file)
        output_files.append(xlsx_file)

    search_quota = _reconcile_quota(starting_search_quota, ending_search_quota, search_calls)
    item_quota = _reconcile_quota(starting_item_quota, ending_item_quota, item_detail_calls)
    no_match = sum(1 for result in final_results if result.condition == "No match")
    row_failures = sum(1 for result in final_results if result.condition == "Error")
    warnings: list[str] = []
    if search_quota.estimated or item_quota.estimated:
        warnings.append("eBay quota reporting had not caught up; remaining values were adjusted locally.")
    if quota_stop:
        warnings.append(str(quota_stop))

    return RunSummary(
        total_identifiers=len(raw_identifiers),
        unique_identifiers=len(unique_keys),
        found=sum(1 for result in final_results if result.best_price is not None),
        no_match=no_match,
        failed=row_failures,
        skipped=skipped,
        api_calls=api_calls,
        api_call_breakdown=api_call_breakdown,
        elapsed_seconds=time.monotonic() - started,
        output_file=output_files[0],
        output_files=output_files,
        quota=search_quota,
        item_quota=item_quota,
        stopped_for_quota=quota_stop is not None,
        stop_reason=str(quota_stop or ""),
        warnings=warnings,
    )
