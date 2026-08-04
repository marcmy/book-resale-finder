from __future__ import annotations

import asyncio
import base64
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote

import httpx

from .constants import (
    BROWSE_ITEM_URL,
    BROWSE_SEARCH_URL,
    CONDITION_IDS,
    OAUTH_SCOPE,
    OAUTH_URL,
    RATE_LIMIT_URL,
)
from .models import NormalizedIdentifier, QuotaInfo, SearchResult
from .rate_limiter import AsyncRateLimiter


class EbayApiError(RuntimeError):
    pass


@dataclass(slots=True)
class _Candidate:
    item_id: str
    title: str
    item_price: float
    currency: str
    condition: str
    url: str
    summary_shipping: float | None = None


class EbayClient:
    def __init__(
        self,
        client_id: str,
        client_secret: str,
        config: dict[str, Any],
        *,
        on_api_call: Callable[[int], None] | None = None,
    ) -> None:
        self.client_id = client_id
        self.client_secret = client_secret
        self.config = config
        self.marketplace_id = str(config.get("marketplace_id", "EBAY_US"))
        self.max_retries = max(1, int(config.get("max_retries", 3)))
        self.rate_limiter = AsyncRateLimiter(float(config.get("rate_limit_per_second", 5)))
        self.on_api_call = on_api_call
        self.api_calls = 0
        self.token: str | None = None
        self._http: httpx.AsyncClient | None = None

    async def __aenter__(self) -> "EbayClient":
        timeout = float(self.config.get("request_timeout_seconds", 30))
        limits = httpx.Limits(
            max_connections=max(10, int(self.config.get("max_workers", 10)) * 2),
            max_keepalive_connections=max(5, int(self.config.get("max_workers", 10))),
        )
        self._http = httpx.AsyncClient(timeout=timeout, limits=limits, follow_redirects=True)
        self.token = await self._fetch_token()
        return self

    async def __aexit__(self, exc_type, exc, traceback) -> None:
        if self._http is not None:
            await self._http.aclose()
            self._http = None

    @property
    def http(self) -> httpx.AsyncClient:
        if self._http is None:
            raise RuntimeError("EbayClient must be used as an async context manager.")
        return self._http

    def _count_api_call(self) -> None:
        self.api_calls += 1
        if self.on_api_call:
            self.on_api_call(self.api_calls)

    async def _fetch_token(self) -> str:
        credentials = base64.b64encode(f"{self.client_id}:{self.client_secret}".encode()).decode()
        response = await self.http.post(
            OAUTH_URL,
            headers={
                "Authorization": f"Basic {credentials}",
                "Content-Type": "application/x-www-form-urlencoded",
            },
            data={"grant_type": "client_credentials", "scope": OAUTH_SCOPE},
        )
        if response.status_code >= 400:
            detail = self._error_detail(response)
            raise EbayApiError(f"eBay rejected the API credentials ({response.status_code}): {detail}")
        token = response.json().get("access_token")
        if not token:
            raise EbayApiError("eBay did not return an OAuth access token.")
        return str(token)

    def _headers(self) -> dict[str, str]:
        if not self.token:
            raise RuntimeError("OAuth token is unavailable.")
        return {
            "Authorization": f"Bearer {self.token}",
            "X-EBAY-C-MARKETPLACE-ID": self.marketplace_id,
            "Accept": "application/json",
        }

    @staticmethod
    def _error_detail(response: httpx.Response) -> str:
        try:
            data = response.json()
            errors = data.get("errors") or []
            if errors:
                first = errors[0]
                return str(first.get("longMessage") or first.get("message") or first)
            return str(data)
        except Exception:
            return response.text[:500] or response.reason_phrase

    async def _request_json(
        self,
        method: str,
        url: str,
        *,
        params: dict[str, Any] | None = None,
        count_as_api_call: bool = True,
    ) -> dict[str, Any]:
        backoff = 1.0
        for attempt in range(self.max_retries + 1):
            await self.rate_limiter.acquire()
            if count_as_api_call:
                self._count_api_call()
            response = await self.http.request(method, url, headers=self._headers(), params=params)

            if response.status_code == 401 and attempt == 0:
                self.token = await self._fetch_token()
                continue
            if response.status_code == 429 or response.status_code >= 500:
                if attempt >= self.max_retries:
                    raise EbayApiError(
                        f"eBay request failed after retries ({response.status_code}): "
                        f"{self._error_detail(response)}"
                    )
                retry_after = response.headers.get("Retry-After")
                try:
                    delay = float(retry_after) if retry_after else backoff
                except ValueError:
                    delay = backoff
                await asyncio.sleep(min(max(delay, 0.5), 30.0))
                backoff = min(backoff * 2, 30.0)
                continue
            if response.status_code >= 400:
                raise EbayApiError(
                    f"eBay request failed ({response.status_code}): {self._error_detail(response)}"
                )
            try:
                payload = response.json()
            except ValueError as exc:
                raise EbayApiError("eBay returned an invalid JSON response.") from exc
            return payload if isinstance(payload, dict) else {}
        raise EbayApiError("eBay request failed unexpectedly.")

    def _filter_string(self) -> str:
        conditions = [str(value).upper() for value in self.config.get("conditions", [])]
        condition_ids = [CONDITION_IDS[value] for value in conditions if value in CONDITION_IDS]
        buying_options = [str(value).upper() for value in self.config.get("buying_options", [])]
        parts: list[str] = []
        if condition_ids:
            parts.append(f"conditionIds:{{{'|'.join(condition_ids)}}}")
        if buying_options:
            parts.append(f"buyingOptions:{{{'|'.join(buying_options)}}}")
        return ",".join(parts)

    async def _search(self, *, gtin: str | None = None, query: str | None = None, limit: int) -> list[_Candidate]:
        params: dict[str, Any] = {
            "sort": "price",
            "limit": max(1, min(int(limit), 200)),
        }
        filters = self._filter_string()
        if filters:
            params["filter"] = filters
        if gtin:
            params["gtin"] = gtin
        elif query:
            params["q"] = query
        else:
            return []

        payload = await self._request_json("GET", BROWSE_SEARCH_URL, params=params)
        candidates: list[_Candidate] = []
        for item in payload.get("itemSummaries") or []:
            try:
                price = item.get("price") or {}
                item_price = float(price.get("value"))
                item_id = str(item["itemId"])
            except (KeyError, TypeError, ValueError):
                continue

            summary_shipping: float | None = None
            costs: list[float] = []
            for option in item.get("shippingOptions") or []:
                try:
                    costs.append(float((option.get("shippingCost") or {}).get("value")))
                except (TypeError, ValueError):
                    continue
            if costs:
                summary_shipping = min(costs)

            candidates.append(
                _Candidate(
                    item_id=item_id,
                    title=str(item.get("title") or ""),
                    item_price=item_price,
                    currency=str(price.get("currency") or "USD"),
                    condition=str(item.get("condition") or ""),
                    url=str(item.get("itemWebUrl") or item.get("itemHref") or ""),
                    summary_shipping=summary_shipping,
                )
            )
        return sorted(candidates, key=lambda item: item.item_price)

    async def _shipping_cost(self, candidate: _Candidate) -> float | None:
        item_id = quote(candidate.item_id, safe="")
        payload = await self._request_json(
            "GET",
            BROWSE_ITEM_URL.format(item_id=item_id),
            params={"fieldgroups": "COMPACT"},
        )
        costs: list[float] = []
        for option in payload.get("shippingOptions") or []:
            try:
                costs.append(float((option.get("shippingCost") or {}).get("value")))
            except (TypeError, ValueError):
                continue
        if costs:
            return min(costs)
        return candidate.summary_shipping

    async def find_best_listing(
        self,
        identifier: NormalizedIdentifier,
        *,
        include_shipping: bool,
    ) -> SearchResult:
        output_asin = identifier.original
        price_limit = max(1, int(self.config.get("price_item_limit", 10)))
        shipping_limit = max(1, int(self.config.get("shipping_item_limit", 3)))
        search_limit = shipping_limit if include_shipping else price_limit

        candidates: list[_Candidate] = []
        method = ""
        if identifier.isbn13:
            candidates = await self._search(gtin=identifier.isbn13, limit=search_limit)
            method = "GTIN"
            if not candidates and bool(self.config.get("fallback_to_search", True)):
                candidates = await self._search(query=identifier.isbn13, limit=search_limit)
                method = "keyword fallback"
        else:
            search_term = identifier.asin or identifier.query or identifier.original
            candidates = await self._search(query=search_term, limit=search_limit)
            method = "keyword"

        if not candidates:
            return SearchResult(
                asin=output_asin,
                title="No matching listing found",
                condition="No match",
                search_method=method,
                note="No active eBay listing matched this identifier.",
            )

        if not include_shipping:
            chosen = min(candidates, key=lambda item: item.item_price)
            return SearchResult(
                asin=output_asin,
                title=chosen.title,
                best_price=chosen.item_price,
                item_price=chosen.item_price,
                condition=chosen.condition,
                listing_url=chosen.url,
                item_id=chosen.item_id,
                currency=chosen.currency,
                search_method=method,
            )

        semaphore = asyncio.Semaphore(min(shipping_limit, 5))

        async def total_for(candidate: _Candidate) -> tuple[float, _Candidate, float | None]:
            async with semaphore:
                shipping = await self._shipping_cost(candidate)
            return candidate.item_price + (shipping or 0.0), candidate, shipping

        totals = await asyncio.gather(
            *(total_for(candidate) for candidate in candidates[:shipping_limit]),
            return_exceptions=True,
        )
        valid: list[tuple[float, _Candidate, float | None]] = [
            result for result in totals if isinstance(result, tuple)
        ]
        if not valid:
            chosen = candidates[0]
            return SearchResult(
                asin=output_asin,
                title=chosen.title,
                best_price=chosen.item_price,
                item_price=chosen.item_price,
                condition=chosen.condition,
                listing_url=chosen.url,
                item_id=chosen.item_id,
                currency=chosen.currency,
                search_method=method,
                note="Shipping lookup failed; price excludes shipping.",
            )

        total, chosen, shipping = min(valid, key=lambda item: item[0])
        return SearchResult(
            asin=output_asin,
            title=chosen.title,
            best_price=total,
            item_price=chosen.item_price,
            shipping_price=shipping,
            condition=chosen.condition,
            listing_url=chosen.url,
            item_id=chosen.item_id,
            currency=chosen.currency,
            search_method=method,
        )

    async def fetch_quota(self) -> QuotaInfo:
        try:
            payload = await self._request_json(
                "GET",
                RATE_LIMIT_URL,
                params={"api_name": "browse", "api_context": "buy"},
                count_as_api_call=False,
            )
        except Exception:
            return QuotaInfo()

        resources = payload.get("rateLimits") or []
        for group in resources:
            for resource in group.get("resources") or []:
                name = str(resource.get("name") or "").casefold()
                if "search" not in name and "item" not in name:
                    continue
                rates = resource.get("rates") or []
                if not rates:
                    continue
                rate = rates[0]
                try:
                    limit = int(rate.get("limit")) if rate.get("limit") is not None else None
                    remaining = int(rate.get("remaining")) if rate.get("remaining") is not None else None
                    if rate.get("count") is not None:
                        used = int(rate.get("count"))
                    else:
                        used = limit - remaining if limit is not None and remaining is not None else None
                except (TypeError, ValueError):
                    limit = used = remaining = None
                return QuotaInfo(
                    limit=limit,
                    used=used,
                    remaining=remaining,
                    reset_at=str(rate.get("reset") or "") or None,
                )
        return QuotaInfo()
