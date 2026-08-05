from __future__ import annotations

import re
from typing import Any

from .constants import RATE_LIMIT_URL
from .ebay import EbayClient as _BaseEbayClient
from .models import QuotaInfo


class EbayClient(_BaseEbayClient):
    """Quota-reporting compatibility layer for eBay Analytics responses.

    eBay documents Analytics resource names as API methods. Depending on the
    response/version, Browse entries can therefore be named ``search`` and
    ``getItem`` rather than ``item_summary`` and ``item``.
    """

    @staticmethod
    def _normalized_method_name(raw_name: object) -> str:
        text = str(raw_name or "").strip()
        text = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "_", text)
        return re.sub(r"[^a-z0-9]+", "_", text.casefold()).strip("_")

    @classmethod
    def _quotas_from_payload(cls, payload: dict[str, Any]) -> tuple[QuotaInfo, QuotaInfo]:
        search_resource: dict[str, Any] | None = None
        item_resource: dict[str, Any] | None = None
        search_name = "search"
        item_name = "getItem"
        search_score = item_score = -1

        search_priorities = {
            "search": 100,
            "item_summary_search": 90,
            "itemsummary_search": 90,
            "item_summary": 80,
        }
        item_priorities = {
            "get_item": 100,
            "getitem": 100,
            "item": 80,
        }

        for group in payload.get("rateLimits") or []:
            api_name = str(group.get("apiName") or "").casefold()
            api_context = str(group.get("apiContext") or "").casefold()
            if api_name and api_name != "browse":
                continue
            if api_context and api_context != "buy":
                continue

            for resource in group.get("resources") or []:
                raw_name = str(resource.get("name") or "")
                normalized = cls._normalized_method_name(raw_name)

                candidate_search_score = search_priorities.get(normalized, -1)
                if (
                    candidate_search_score < 0
                    and normalized.startswith("search")
                    and "image" not in normalized
                ):
                    candidate_search_score = 70
                if candidate_search_score > search_score:
                    search_resource = resource
                    search_name = raw_name or "search"
                    search_score = candidate_search_score

                candidate_item_score = item_priorities.get(normalized, -1)
                if candidate_item_score > item_score:
                    item_resource = resource
                    item_name = raw_name or "getItem"
                    item_score = candidate_item_score

        search = (
            cls._quota_for_resource(search_resource, search_name)
            if search_resource is not None and search_score >= 0
            else QuotaInfo(resource="search")
        )
        item = (
            cls._quota_for_resource(item_resource, item_name)
            if item_resource is not None and item_score >= 0
            else QuotaInfo(resource="getItem")
        )
        return search, item

    @classmethod
    def _quota_from_payload(cls, payload: dict[str, Any]) -> QuotaInfo:
        return cls._quotas_from_payload(payload)[0]

    async def fetch_quotas(self) -> tuple[QuotaInfo, QuotaInfo]:
        try:
            filtered_payload = await self._request_json(
                "GET",
                RATE_LIMIT_URL,
                params={"api_name": "browse", "api_context": "buy"},
                count_as_api_call=False,
            )
        except Exception:
            filtered_payload = {}

        search, item = self._quotas_from_payload(filtered_payload)
        if search.remaining is not None and item.remaining is not None:
            return search, item

        # Some Analytics deployments ignore or reject the optional filters.
        # Retry once without them, then fill only entries that were missing.
        try:
            full_payload = await self._request_json(
                "GET",
                RATE_LIMIT_URL,
                count_as_api_call=False,
            )
        except Exception:
            return search, item

        full_search, full_item = self._quotas_from_payload(full_payload)
        if search.remaining is None and full_search.remaining is not None:
            search = full_search
        if item.remaining is None and full_item.remaining is not None:
            item = full_item
        return search, item


__all__ = ["EbayClient"]
