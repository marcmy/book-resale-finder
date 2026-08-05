from __future__ import annotations

from pathlib import Path

from .csv_input import read_asins
from .identifiers import normalize_identifier
from .models import CallEstimate


def estimate_calls(
    input_file: Path,
    *,
    retry_unmatched: bool,
    include_shipping: bool,
    shipping_item_limit: int,
) -> CallEstimate:
    raw_identifiers = read_asins(input_file)
    unique: dict[str, object] = {}
    for raw in raw_identifiers:
        normalized = normalize_identifier(raw)
        unique.setdefault(normalized.primary_value.casefold(), normalized)

    isbn_count = sum(1 for value in unique.values() if getattr(value, "isbn13", None))
    unique_count = len(unique)
    search_min = unique_count
    search_max = unique_count + (isbn_count if retry_unmatched else 0)
    item_detail_max = unique_count * max(1, shipping_item_limit) if include_shipping else 0
    return CallEstimate(
        total_identifiers=len(raw_identifiers),
        unique_identifiers=unique_count,
        isbn_identifiers=isbn_count,
        search_min=search_min,
        search_max=search_max,
        item_detail_max=item_detail_max,
    )
