import asyncio

from book_resale_finder.ebay import EbayClient, _Candidate
from book_resale_finder.identifiers import normalize_identifier


class FakeEbayClient(EbayClient):
    def __init__(self, *, candidates, shipping, config=None):
        super().__init__("id", "secret", config or {})
        self._candidates = candidates
        self._shipping = shipping

    async def _search(self, *, gtin=None, query=None, limit=10):
        return self._candidates[:limit]

    async def _shipping_cost(self, candidate):
        return self._shipping.get(candidate.item_id)


def test_selects_lowest_item_price_without_shipping():
    candidates = [
        _Candidate("1", "One", 10.0, "USD", "Good", "https://one"),
        _Candidate("2", "Two", 8.0, "USD", "Very Good", "https://two"),
    ]
    client = FakeEbayClient(candidates=candidates, shipping={})
    result = asyncio.run(
        client.find_best_listing(normalize_identifier("9780306406157"), include_shipping=False)
    )
    assert result.item_id == "2"
    assert result.best_price == 8.0


def test_shipping_can_change_the_best_listing():
    candidates = [
        _Candidate("1", "Cheap item expensive shipping", 5.0, "USD", "Good", "https://one"),
        _Candidate("2", "Higher item free shipping", 8.0, "USD", "Very Good", "https://two"),
    ]
    client = FakeEbayClient(
        candidates=candidates,
        shipping={"1": 6.0, "2": 0.0},
        config={"shipping_item_limit": 3},
    )
    result = asyncio.run(
        client.find_best_listing(normalize_identifier("9780306406157"), include_shipping=True)
    )
    assert result.item_id == "2"
    assert result.best_price == 8.0
    assert result.shipping_price == 0.0


def test_builds_specific_condition_filter():
    client = FakeEbayClient(
        candidates=[],
        shipping={},
        config={
            "conditions": ["NEW", "LIKE_NEW", "VERY_GOOD", "GOOD"],
            "buying_options": ["FIXED_PRICE", "AUCTION"],
        },
    )
    assert client._filter_string() == (
        "conditionIds:{1000|2750|4000|5000},"
        "buyingOptions:{FIXED_PRICE|AUCTION}"
    )
