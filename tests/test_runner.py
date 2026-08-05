import asyncio
from collections import Counter
from pathlib import Path

from book_resale_finder.ebay import EbayQuotaSafetyError
from book_resale_finder.models import QuotaInfo, SearchResult
from book_resale_finder.runner import run_scan


class FakeClient:
    calls = []

    def __init__(self, client_id, client_secret, config):
        self.api_calls = 0
        self.api_call_breakdown = Counter()
        self.search_calls = 0
        self.item_detail_calls = 0

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return None

    async def fetch_quotas(self):
        return (
            QuotaInfo(limit=5000, used=100, remaining=4900, resource="item_summary"),
            QuotaInfo(limit=5000, used=0, remaining=5000, resource="item"),
        )

    def configure_quota_safety(self, search_quota, item_quota, reserve):
        self.reserve = reserve

    async def find_best_listing(self, identifier, *, include_shipping, retry_unmatched):
        self.api_calls += 1
        self.api_call_breakdown["primary_search"] += 1
        self.search_calls += 1
        self.calls.append((identifier.primary_value, retry_unmatched))
        return SearchResult(
            asin=identifier.original,
            title=f"Title {identifier.primary_value}",
            best_price=10.0,
            condition="Good",
            listing_url="https://www.ebay.com/itm/1",
        )


def test_runner_writes_both_formats_and_preserves_retry_setting(tmp_path: Path, monkeypatch):
    input_file = tmp_path / "masterlist.csv"
    input_file.write_text(
        "ASIN\n9780306406157\n9780306406157\nB000HCWBCG\n",
        encoding="utf-8",
    )
    FakeClient.calls = []
    monkeypatch.setattr("book_resale_finder.runner.EbayClient", FakeClient)

    summary = asyncio.run(
        run_scan(
            input_file=input_file,
            output_dir=tmp_path / "output",
            config={"output_prefix": "results", "max_workers": 2},
            client_id="id",
            client_secret="secret",
            include_shipping=False,
            retry_unmatched=True,
            output_format="both",
            quota_reserve=100,
        )
    )

    assert len(FakeClient.calls) == 2
    assert all(retry for _, retry in FakeClient.calls)
    assert [path.suffix for path in summary.output_files] == [".csv", ".xlsx"]
    assert all(path.exists() for path in summary.output_files)
    assert summary.quota.remaining == 4898
    assert summary.quota.estimated is True


def test_runner_writes_partial_output_when_quota_reserve_is_reached(tmp_path: Path, monkeypatch):
    class StopClient(FakeClient):
        async def find_best_listing(self, identifier, *, include_shipping, retry_unmatched):
            if self.api_calls >= 1:
                raise EbayQuotaSafetyError("search")
            return await super().find_best_listing(
                identifier,
                include_shipping=include_shipping,
                retry_unmatched=retry_unmatched,
            )

    input_file = tmp_path / "masterlist.csv"
    input_file.write_text(
        "ASIN\n9780306406157\nB000HCWBCG\n9780140328721\n",
        encoding="utf-8",
    )
    monkeypatch.setattr("book_resale_finder.runner.EbayClient", StopClient)

    summary = asyncio.run(
        run_scan(
            input_file=input_file,
            output_dir=tmp_path / "output",
            config={"output_prefix": "results", "max_workers": 1},
            client_id="id",
            client_secret="secret",
            include_shipping=False,
            retry_unmatched=True,
            output_format="csv",
            quota_reserve=100,
        )
    )
    assert summary.stopped_for_quota is True
    assert summary.skipped == 2
    assert summary.output_file.exists()
