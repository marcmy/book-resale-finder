# Sourcing Cockpit

A local-first Chrome/Edge Manifest V3 extension for Amazon/Keepa book and OA sourcing.

This project deliberately does **not** copy SourceLens code or use undocumented Amazon Seller Central endpoints.
It recreates the useful workflow with public page integration, local storage, and Amazon's official Selling Partner API (SP-API).

## Implemented

- Keepa row ASIN discovery with inline eligibility badges
- Live seller-specific eligibility via SP-API Listings Restrictions
- Approval-required links when Amazon supplies them
- Eligibility cache with manual clear and configurable TTL
- Local gating database generated from observed products
- Bookmarks / Watch Later
- Per-ASIN notes
- Sourcing history + CSV export
- Bulk ASIN cost CSV import/export
- Local deal score heuristic
- Competition trend from locally observed seller-count changes
- Heuristic meltable / hazmat flags
- Similar-product / rabbit-trail search helpers
- Amazon product-page panel
- Optional SP-API fee estimate lookup
- Pomodoro sourcing timer
- Optional team sync through a GitHub Gist
- Zero application backend: Amazon credentials stay in the localhost bridge; browser state stays in Chrome storage

## Layout

- `extension/` – unpacked Manifest V3 extension
- `bridge/` – localhost SP-API bridge; contains the LWA client secret/refresh token, never the extension

## Quick start

1. Create/self-authorize an Amazon SP-API private app with the **Product Listing** role.
2. Copy `bridge/config.example.json` to `bridge/config.json` and fill in the values.
3. Run:
   ```powershell
   py -3.12 .\sourcing_cockpit\bridge\server.py --config .\sourcing_cockpit\bridge\config.json
   ```
4. In Chrome/Edge open Extensions -> Developer mode -> Load unpacked -> choose `sourcing_cockpit/extension`.
5. Open the extension Options page and verify the bridge says healthy.
6. Browse Keepa. Rows with discoverable ASINs will get sourcing badges.

## Security model

The browser extension never stores the Amazon LWA client secret or refresh token. Those stay in
`bridge/config.json` on localhost. The bridge binds to `127.0.0.1` only.

If Gist sync is enabled, the GitHub token is stored in `chrome.storage.local`; use a fine-grained token
with only the minimum Gist permission you need. Gist sync is optional and off by default.

## Known limits

SourceLens also advertises features that depend on proprietary logic, undocumented page integrations,
or data we cannot faithfully derive from the public page alone (notably its regional Buy Box sweeps and
its exact Keepa chart break-even overlay). Those are intentionally not faked here.

DOM extraction is defensive rather than coupled to one Keepa build, but Keepa can still change its markup.
The extension surfaces extraction quality in tooltips rather than pretending inferred values are exact.
