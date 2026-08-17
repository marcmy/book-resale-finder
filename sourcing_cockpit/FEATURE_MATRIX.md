# Feature matrix

This is a clean-room workflow recreation based on public product descriptions and official APIs.
It does not contain SourceLens code, assets, or proprietary scoring logic.

| SourceLens-advertised area | Sourcing Cockpit status | Notes |
|---|---|---|
| Keepa row eligibility | Implemented | Official SP-API Listings Restrictions via localhost bridge |
| Green/yellow/red gating | Implemented | Seller-specific; approval URL shown when available |
| Eligibility cache / clear | Implemented | Configurable TTL |
| Brand/category gating DB | Implemented | Learns from rows observed locally |
| Bookmarks / Watch Later | Implemented | Local storage |
| Product notes | Implemented | Amazon page panel + sync payload |
| Sourcing history / CSV | Implemented | Up to 2,000 latest observations |
| Bulk cost file | Implemented | CSV import/export, per-ASIN cost storage |
| Deal Score | Partial | Transparent local heuristic; not SourceLens' proprietary score |
| Competition trend | Partial | Local observed seller-count trend, not Keepa historical-series decoding |
| Meltable / hazmat flags | Partial | Keyword warnings only; deliberately labeled heuristic |
| Similar Product finder | Implemented | Keepa title-keyword search helper |
| Rabbit Trail finder | Implemented | Amazon narrow search helper |
| Amazon product page tools | Implemented | Eligibility, bookmark, note, Keepa jump, fees |
| Product fee estimate | Implemented | Official SP-API Product Fees endpoint |
| Pomodoro timer | Implemented | 25-minute in-page timer |
| Gist team sync | Implemented | Optional private Gist; no application backend |
| Regional Buy Box map / 8-region sweep | Not implemented | Would require reliable location-specific offer capture; not faked |
| Exact Keepa chart break-even line | Not implemented | Chart internals need targeted DOM/chart adapter |
| Competitor storefront -> Product Finder | Scaffold candidate | Seller IDs can be detected, but exact Product Finder mapping should be verified against live Keepa |
| AI supplier research | Not implemented | Requires an AI service/API and supplier-research design |
| 90+ built-in sourcing guides | Not implemented | Documentation content is proprietary; project README covers our own workflow |

## Next high-value targets

1. Verify Keepa's live DOM selectors and replace heuristic row parsing with explicit adapters.
2. Add a chart adapter for a true cost / break-even horizontal overlay.
3. Add storefront seller-ID extraction and a verified Product Finder handoff.
4. Add an optional AI supplier-research provider interface.
5. Explore location-specific Buy Box capture using documented/allowed APIs where possible.
