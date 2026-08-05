from __future__ import annotations

APP_NAME = "Book Resale Finder"
APP_ID = "com.marcmy.bookresalefinder"
VERSION = "1.1.9"
KEYRING_SERVICE = "Book Resale Finder eBay API"

DEFAULT_CONFIG = {
    "input_csv": "masterlist.csv",
    "output_dir": "output",
    "output_prefix": "book_resale_results",
    "marketplace_id": "EBAY_US",
    "conditions": ["NEW", "LIKE_NEW", "VERY_GOOD", "GOOD"],
    "buying_options": ["FIXED_PRICE", "AUCTION"],
    "max_workers": 10,
    "rate_limit_per_second": 5,
    "include_shipping": False,
    "shipping_item_limit": 3,
    "price_item_limit": 10,
    "fallback_to_search": True,
    "output_format": "csv",
    "quota_reserve": 100,
    "request_timeout_seconds": 30,
    "max_retries": 3,
}

CONDITION_IDS = {
    "NEW": "1000",
    "LIKE_NEW": "2750",
    "VERY_GOOD": "4000",
    "GOOD": "5000",
    "ACCEPTABLE": "6000",
}

OAUTH_URL = "https://api.ebay.com/identity/v1/oauth2/token"
BROWSE_SEARCH_URL = "https://api.ebay.com/buy/browse/v1/item_summary/search"
BROWSE_ITEM_URL = "https://api.ebay.com/buy/browse/v1/item/{item_id}"
RATE_LIMIT_URL = "https://api.ebay.com/developer/analytics/v1_beta/rate_limit/"
OAUTH_SCOPE = "https://api.ebay.com/oauth/api_scope"
