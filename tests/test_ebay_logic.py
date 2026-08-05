import asyncio

import pytest

from book_resale_finder.ebay import EbayClient, EbayQuotaSafetyError, _Candidate
from book_resale_finder.identifiers import normalize_identifier
from book_resale_finder.models import QuotaInfo


class FakeEbayClient(EbayClient):
    def __init__(self, *, candidates, shipping=None, config=None):
        super().__init__("id", "secret", config or {})
        self._candidates = candidates
        self._shipping = shipping or {}
        self.search_kinds = []
        self.shipping_lookups = []

    async def _search(self, *, gtin=None, query=None, limit=10, call_kind="primary_search"):
        self.search_kinds.append(call_kind)
        return self._candidates[:limit]

    async def _shipping_cost(self, candidate):
        self.shipping_lookups.append(candidate.item_id)
        return self._shipping.get(candidate.item_id)


def test_selects_lowest_item_price_without_shipping():
    candidates = [
        _Candidate("1", "One", 10.0, "USD", "Good", "https://one"),
        _Candidate("2", "Two", 8.0, "USD", "Very Good", "https://two"),
    ]
    client = FakeEbayClient(candidates=candidates)
    result = asyncio.run(
        client.find_best_listing(normalize_identifier("9780306406157"), include_shipping=False)
    )
    assert result.item_id == "2"
    assert result.best_price == 8.0
    assert client.search_kinds == ["primary_search"]


class FallbackClient(FakeEbayClient):
    async def _search(self, *, gtin=None, query=None, limit=10, call_kind="primary_search"):
        self.search_kinds.append(call_kind)
        if gtin:
            return []
        return [_Candidate("2", "Fallback", 9.0, "USD", "Good", "https://two")]


def test_retry_is_enabled_by_default_but_can_be_disabled():
    default_client = FallbackClient(candidates=[], config={"fallback_to_search": True})
    result = asyncio.run(
        default_client.find_best_listing(normalize_identifier("9780306406157"), include_shipping=False)
    )
    assert result.item_id == "2"
    assert default_client.search_kinds == ["primary_search", "fallback_search"]

    one_pass_client = FallbackClient(candidates=[], config={"fallback_to_search": True})
    result = asyncio.run(
        one_pass_client.find_best_listing(
            normalize_identifier("9780306406157"),
            include_shipping=False,
            retry_unmatched=False,
        )
    )
    assert result.best_price is None
    assert one_pass_client.search_kinds == ["primary_search"]


def test_shipping_reuses_search_result_shipping_without_detail_call():
    client = FakeEbayClient(
        candidates=[
            _Candidate("1", "One", 5.0, "USD", "Good", "https://one", summary_shipping=6.0),
            _Candidate("2", "Two", 8.0, "USD", "Very Good", "https://two", summary_shipping=0.0),
        ],
        config={"shipping_item_limit": 3},
    )
    result = asyncio.run(
        client.find_best_listing(normalize_identifier("9780306406157"), include_shipping=True)
    )
    assert result.item_id == "2"
    assert result.best_price == 8.0
    assert client.shipping_lookups == []


def test_shipping_calls_item_detail_only_when_summary_is_missing():
    client = FakeEbayClient(
        candidates=[_Candidate("1", "One", 5.0, "USD", "Good", "https://one")],
        shipping={"1": 2.0},
        config={"shipping_item_limit": 3},
    )
    result = asyncio.run(
        client.find_best_listing(normalize_identifier("9780306406157"), include_shipping=True)
    )
    assert result.best_price == 7.0
    assert client.shipping_lookups == ["1"]


def test_builds_specific_condition_filter():
    client = FakeEbayClient(
        candidates=[],
        config={
            "conditions": ["NEW", "LIKE_NEW", "VERY_GOOD", "GOOD"],
            "buying_options": ["FIXED_PRICE", "AUCTION"],
        },
    )
    assert client._filter_string() == (
        "conditionIds:{1000|2750|4000|5000},"
        "buyingOptions:{FIXED_PRICE|AUCTION}"
    )


def test_quota_parser_returns_search_and_item_detail_separately():
    payload = {
        "rateLimits": [
            {
                "apiContext": "buy",
                "apiName": "browse",
                "resources": [
                    {
                        "name": "item",
                        "rates": [{"limit": 5000, "count": 10, "remaining": 4990, "timeWindow": 86400}],
                    },
                    {
                        "name": "item_summary",
                        "rates": [{"limit": 5000, "count": 3054, "remaining": 1946, "timeWindow": 86400}],
                    },
                ],
            }
        ]
    }
    search, item = EbayClient._quotas_from_payload(payload)
    assert search.remaining == 1946
    assert search.resource == "item_summary"
    assert item.remaining == 4990
    assert item.resource == "item"
    assert EbayClient._quota_from_payload(payload).remaining == 1946


def test_quota_safety_budget_stops_before_reserve():
    async def exercise() -> None:
        client = EbayClient("id", "secret", {})
        client.configure_quota_safety(
            QuotaInfo(remaining=3),
            QuotaInfo(remaining=5),
            reserve=1,
        )
        await client._claim_api_call("primary_search")
        await client._claim_api_call("fallback_search")
        with pytest.raises(EbayQuotaSafetyError):
            await client._claim_api_call("primary_search")

    asyncio.run(exercise())
