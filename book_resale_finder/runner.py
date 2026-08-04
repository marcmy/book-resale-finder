from __future__ import annotations

import asyncio
import time
from dataclasses import replace
from collections import defaultdict
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Any

from .csv_input import read_asins
from .ebay import EbayClient
from .identifiers import normalize_identifier
from .models import ProgressInfo, RunSummary, SearchResult
from .workbook import write_results_xlsx


class ScanCancelled(RuntimeError):
    pass


async def run_scan(
    *,
    input_file: Path,
    output_dir: Path,
    config: dict[str, Any],
    client_id: str,
    client_secret: str,
    include_shipping: bool,
    progress_callback: Callable[[ProgressInfo], None] | None = None,
    cancel_requested: Callable[[], bool] | None = None,
) -> RunSummary:
    started = time.monotonic()
    raw_identifiers = read_asins(input_file)
    normalized = [normalize_identifier(value) for value in raw_identifiers]

    # Process each unique normalized value once, then reuse the result for duplicates.
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

    def is_cancelled() -> bool:
        return bool(cancel_requested and cancel_requested())

    async with EbayClient(client_id, client_secret, config) as ebay:
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
                    )
                    matched = result.best_price is not None
                except ScanCancelled:
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

        if is_cancelled():
            raise ScanCancelled()

        quota = await ebay.fetch_quota()
        api_calls = ebay.api_calls

    final_results = [result for result in results if result is not None]
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    prefix = str(config.get("output_prefix", "book_resale_results"))
    output_file = output_dir / f"{prefix}_{timestamp}.xlsx"
    write_results_xlsx(final_results, output_file)

    no_match = sum(1 for result in final_results if result.condition == "No match")
    row_failures = sum(1 for result in final_results if result.condition == "Error")
    return RunSummary(
        total_identifiers=len(raw_identifiers),
        unique_identifiers=len(unique_keys),
        found=sum(1 for result in final_results if result.best_price is not None),
        no_match=no_match,
        failed=row_failures,
        api_calls=api_calls,
        elapsed_seconds=time.monotonic() - started,
        output_file=output_file,
        quota=quota,
    )
