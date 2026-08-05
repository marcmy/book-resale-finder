from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True, slots=True)
class NormalizedIdentifier:
    original: str
    isbn13: str | None = None
    asin: str | None = None
    query: str | None = None

    @property
    def primary_value(self) -> str:
        return self.isbn13 or self.asin or self.query or self.original


@dataclass(slots=True)
class SearchResult:
    asin: str
    title: str = ""
    best_price: float | None = None
    condition: str = ""
    listing_url: str = ""
    item_id: str | None = None
    currency: str = "USD"
    item_price: float | None = None
    shipping_price: float | None = None
    search_method: str = ""
    note: str = ""

    def to_output_row(self) -> list[Any]:
        return [
            self.asin,
            self.title,
            self.best_price,
            self.condition,
            self.listing_url,
        ]


@dataclass(slots=True)
class QuotaInfo:
    limit: int | None = None
    used: int | None = None
    remaining: int | None = None
    reset_at: str | None = None


@dataclass(slots=True)
class ProgressInfo:
    completed: int
    total: int
    current_identifier: str
    api_calls: int
    found: int
    failed: int
    status: str


@dataclass(slots=True)
class RunSummary:
    total_identifiers: int
    unique_identifiers: int
    found: int
    no_match: int
    failed: int
    api_calls: int
    elapsed_seconds: float
    output_file: Path
    quota: QuotaInfo = field(default_factory=QuotaInfo)
    api_call_breakdown: dict[str, int] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
