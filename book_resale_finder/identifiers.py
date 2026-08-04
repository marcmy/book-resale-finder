from __future__ import annotations

import re

from .models import NormalizedIdentifier

_AMAZON_URL_RE = re.compile(
    r"/(?:dp|gp/product|gp/aw/d|gp/offer-listing)/([A-Z0-9]{10})(?:[/?]|$)",
    re.IGNORECASE,
)
_ASIN_RE = re.compile(r"^[A-Z0-9]{10}$", re.IGNORECASE)
_ISBN10_RE = re.compile(r"^[0-9]{9}[0-9Xx]$")
_ISBN13_RE = re.compile(r"^[0-9]{13}$")


def _compact(raw: str) -> str:
    return re.sub(r"[\s\-]", "", raw.strip())


def is_valid_isbn10(value: str) -> bool:
    value = _compact(value)
    if not _ISBN10_RE.fullmatch(value):
        return False
    total = 0
    for index, char in enumerate(value):
        digit = 10 if char.upper() == "X" else int(char)
        total += (10 - index) * digit
    return total % 11 == 0


def is_valid_isbn13(value: str) -> bool:
    value = _compact(value)
    if not _ISBN13_RE.fullmatch(value):
        return False
    total = sum(int(ch) * (1 if index % 2 == 0 else 3) for index, ch in enumerate(value[:12]))
    check = (10 - (total % 10)) % 10
    return check == int(value[-1])


def isbn10_to_isbn13(value: str) -> str | None:
    value = _compact(value)
    if not is_valid_isbn10(value):
        return None
    body = "978" + value[:9]
    total = sum(int(ch) * (1 if index % 2 == 0 else 3) for index, ch in enumerate(body))
    return body + str((10 - total % 10) % 10)


def normalize_identifier(raw: object) -> NormalizedIdentifier:
    original = "" if raw is None else str(raw).strip()
    if not original:
        return NormalizedIdentifier(original="")

    url_match = _AMAZON_URL_RE.search(original)
    candidate = url_match.group(1).upper() if url_match else _compact(original).upper()

    if _ISBN13_RE.fullmatch(candidate):
        # Keep digit-only values usable even when a source exported a bad check digit;
        # eBay will simply return no result. Valid values are still preferred.
        return NormalizedIdentifier(original=original, isbn13=candidate)

    if _ISBN10_RE.fullmatch(candidate):
        converted = isbn10_to_isbn13(candidate)
        if converted:
            return NormalizedIdentifier(original=original, isbn13=converted)
        return NormalizedIdentifier(original=original, query=candidate)

    if _ASIN_RE.fullmatch(candidate):
        return NormalizedIdentifier(original=original, asin=candidate)

    return NormalizedIdentifier(original=original, query=original)
