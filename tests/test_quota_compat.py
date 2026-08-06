import asyncio

import httpx
import pytest

from book_resale_finder.ebay import EbayQuotaSafetyError
from book_resale_finder.ebay_v118 import EbayClient
from book_resale_finder.models import QuotaInfo


def _rate(limit: int, count: int) -> list[dict[str, int]]:
    return [
        {
            "limit": limit,
            "count": count,
            "remaining": limit - count,
            "timeWindow": 86400,
        }
    ]


def _quota_payload(count: int = 30, bulk_count: int = 0) -> dict:
    return {
        "rateLimits": [
            {
                "apiContext": "buy",
                "apiName": "Browse",
                "resources": [
                    {"name": "buy.browse", "rates": _rate(5000, count)},
                    {"name": "buy.browse.item.bulk", "rates": _rate(5000, bulk_count)},
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


def test_parser_accepts_production_shared_browse_resource_names():
    browse, bulk = EbayClient._quotas_from_payload(_quota_payload(count=3054, bulk_count=10))

    assert browse.remaining == 1946
    assert browse.resource == "buy.browse"
    assert bulk.remaining == 4990
    assert bulk.resource == "buy.browse.item.bulk"


def test_bulk_quota_is_never_selected_as_the_normal_browse_pool():
    payload = {
        "rateLimits": [
            {
                "apiContext": "buy",
                "apiName": "Browse",
                "resources": [
                    {"name": "buy.browse.item.bulk", "rates": _rate(5000, 2)},
                ],
            }
        ]
    }

    browse, bulk = EbayClient._quotas_from_payload(payload)
    assert browse.remaining is None
    assert bulk.remaining == 4998


def test_parser_remains_compatible_with_legacy_search_resource_name():
    payload = {
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

    browse, bulk = EbayClient._quotas_from_payload(payload)
    assert browse.remaining == 4970
    assert browse.resource == "search"
    assert bulk.remaining is None


def test_fetch_quotas_retries_without_filters_when_filtered_payload_is_empty():
    requests_seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests_seen.append(str(request.url))
        if "api_name=browse" in str(request.url):
            return httpx.Response(200, json={"rateLimits": []})
        return httpx.Response(200, json=_quota_payload())

    client = EbayClient("id", "secret", {"max_retries": 1})
    browse, bulk = _run_with_transport(client, handler)

    assert len(requests_seen) == 2
    assert "api_name=browse" in requests_seen[0]
    assert "api_name=" not in requests_seen[1]
    assert browse.remaining == 4970
    assert bulk.remaining == 5000


def test_search_and_item_detail_calls_share_one_safety_budget():
    async def run() -> None:
        client = EbayClient("id", "secret", {})
        client.configure_quota_safety(
            QuotaInfo(remaining=3, resource="buy.browse"),
            QuotaInfo(),
            reserve=1,
        )
        await client._claim_api_call("primary_search")
        await client._claim_api_call("shipping_detail")
        with pytest.raises(EbayQuotaSafetyError, match="Browse API quota"):
            await client._claim_api_call("fallback_search")
        assert client.api_calls == 2
        assert client.search_calls == 1
        assert client.item_detail_calls == 1

    asyncio.run(run())


def test_http_204_is_reported_exactly_in_quota_diagnostics():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(204)

    client = EbayClient("id", "secret", {"max_retries": 1})
    browse, bulk = _run_with_transport(client, handler)

    assert browse.remaining is None
    assert bulk.remaining is None
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
                    {"name": "buy.browse.item.bulk", "rates": _rate(5000, 2)},
                ],
            }
        ]
    }

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=payload)

    client = EbayClient("id", "secret", {"max_retries": 1})
    browse, bulk = _run_with_transport(client, handler)

    assert browse.remaining is None
    assert bulk.remaining == 4998
    diagnostic = "\n".join(client.quota_diagnostics)
    assert "HTTP 200" not in diagnostic
    assert "buy/browse: searchByImage, buy.browse.item.bulk" in diagnostic
    assert "shared Browse quota" in diagnostic


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
