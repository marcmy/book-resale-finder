import asyncio

from book_resale_finder.ebay_v118 import EbayClient


def _rate(limit: int, count: int) -> list[dict[str, int]]:
    return [
        {
            "limit": limit,
            "count": count,
            "remaining": limit - count,
            "timeWindow": 86400,
        }
    ]


def test_parser_accepts_documented_method_names():
    payload = {
        "rateLimits": [
            {
                "apiContext": "buy",
                "apiName": "browse",
                "resources": [
                    {"name": "search", "rates": _rate(5000, 3054)},
                    {"name": "getItem", "rates": _rate(5000, 10)},
                    {"name": "searchByImage", "rates": _rate(1000, 20)},
                ],
            }
        ]
    }

    search, item = EbayClient._quotas_from_payload(payload)
    assert search.remaining == 1946
    assert search.resource == "search"
    assert item.remaining == 4990
    assert item.resource == "getItem"


def test_parser_remains_compatible_with_resource_style_names():
    payload = {
        "rateLimits": [
            {
                "apiContext": "buy",
                "apiName": "browse",
                "resources": [
                    {"name": "item_summary", "rates": _rate(5000, 30)},
                    {"name": "item", "rates": _rate(5000, 0)},
                ],
            }
        ]
    }

    search, item = EbayClient._quotas_from_payload(payload)
    assert search.remaining == 4970
    assert item.remaining == 5000


def test_fetch_quotas_retries_without_filters_when_filtered_payload_is_empty():
    class FakeClient(EbayClient):
        def __init__(self) -> None:
            super().__init__("id", "secret", {})
            self.params_seen = []

        async def _request_json(self, method, url, *, params=None, **kwargs):
            self.params_seen.append(params)
            if params:
                return {"rateLimits": []}
            return {
                "rateLimits": [
                    {
                        "apiContext": "buy",
                        "apiName": "browse",
                        "resources": [
                            {"name": "search", "rates": _rate(5000, 30)},
                            {"name": "getItem", "rates": _rate(5000, 0)},
                        ],
                    }
                ]
            }

    client = FakeClient()
    search, item = asyncio.run(client.fetch_quotas())
    assert client.params_seen == [
        {"api_name": "browse", "api_context": "buy"},
        None,
    ]
    assert search.remaining == 4970
    assert item.remaining == 5000
