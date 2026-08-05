import asyncio

import httpx

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


def _quota_payload(search_count: int = 30, item_count: int = 0) -> dict:
    return {
        "rateLimits": [
            {
                "apiContext": "buy",
                "apiName": "browse",
                "resources": [
                    {"name": "search", "rates": _rate(5000, search_count)},
                    {"name": "getItem", "rates": _rate(5000, item_count)},
                ],
            }
        ]
    }


def _run_with_transport(client: EbayClient, handler) -> tuple:
    async def run():
        client._http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        client.token = "test-token"
        try:
            return await client.fetch_quotas()
        finally:
            await client._http.aclose()
            client._http = None

    return asyncio.run(run())


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
    requests_seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests_seen.append(str(request.url))
        if "api_name=browse" in str(request.url):
            return httpx.Response(200, json={"rateLimits": []})
        return httpx.Response(200, json=_quota_payload())

    client = EbayClient("id", "secret", {"max_retries": 1})
    search, item = _run_with_transport(client, handler)

    assert len(requests_seen) == 2
    assert "api_name=browse" in requests_seen[0]
    assert "api_name=" not in requests_seen[1]
    assert search.remaining == 4970
    assert item.remaining == 5000


def test_http_204_is_reported_exactly_in_quota_diagnostics():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(204)

    client = EbayClient("id", "secret", {"max_retries": 1})
    search, item = _run_with_transport(client, handler)

    assert search.remaining is None
    assert item.remaining is None
    assert client.quota_diagnostics == [
        "Quota diagnostic (filtered request): HTTP 204 No Content.",
        "Quota diagnostic (unfiltered request): HTTP 204 No Content.",
    ]


def test_successful_unrecognized_payload_lists_returned_api_resources():
    payload = {
        "rateLimits": [
            {
                "apiContext": "buy",
                "apiName": "browse",
                "resources": [
                    {"name": "searchByImage", "rates": _rate(1000, 4)},
                    {"name": "getItems", "rates": _rate(5000, 2)},
                ],
            }
        ]
    }

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=payload)

    client = EbayClient("id", "secret", {"max_retries": 1})
    search, item = _run_with_transport(client, handler)

    assert search.remaining is None
    assert item.remaining is None
    diagnostic = "\n".join(client.quota_diagnostics)
    assert "HTTP 200" not in diagnostic
    assert "buy/browse: searchByImage, getItems" in diagnostic


def test_diagnostics_redact_credentials_and_authorization_values():
    client = EbayClient("client-id-value", "client-secret-value", {})
    client.token = "oauth-token-value"
    diagnostic = client._sanitize_diagnostic(
        "client-id-value client-secret-value oauth-token-value "
        "Bearer another-sensitive-token"
    )

    assert "client-id-value" not in diagnostic
    assert "client-secret-value" not in diagnostic
    assert "oauth-token-value" not in diagnostic
    assert "another-sensitive-token" not in diagnostic
    assert "[redacted]" in diagnostic
