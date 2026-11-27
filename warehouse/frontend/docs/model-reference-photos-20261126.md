# Model reference photographs — 2026-11-26

Draft, no live deployment. Base 761573af6b6b698d65c28dca6ebaa370ce6d8814. The existing vehicle image registry contains only generic generated cars. Cards shared by Vehicles and Inventory now use only reviewed real model references, or a neutral unavailable label. Other detail/gallery views retain the existing fallback behavior. Unknown-year references are explicitly marked and never matched to a different model or claimed to identify generation. Existing donor upload flow unchanged. No new runtime API, paid provider, database or stock writes.

## Candidate photo sources (not imported or approved for display yet)

| Model / explicit catalogue alias | Source | Author | License |
|---|---|---|---|
| Alfa Romeo 147 / 147 (937_) | https://commons.wikimedia.org/wiki/File:Alfa_Romeo_147_front.JPG | Tokumeigakarinoaoshima | CC0 1.0 |
| Audi Q5 (8R photo; unknown year model-only) | https://commons.wikimedia.org/wiki/File:Audi_Q5_8R.jpg | Bene Riobó | CC BY-SA 4.0 |
| DAF XF 105 / XF105 | https://commons.wikimedia.org/wiki/File:DAF_XF_front.jpg | MarkusHagenlocher | CC BY-SA 3.0 |
| Volvo XC90 (second generation, 2016 photo) | https://commons.wikimedia.org/wiki/File:Volvo_XC90_-_2016.jpg | Staticvent | CC BY-SA 4.0 |

Photo download blocked by environment network restrictions; no binary asset is bundled, and the generated manifest is intentionally empty. The candidate list is not a claim of visual acceptance for all four. Run the importer in a network-enabled maintainer environment, visually verify each image against its identity and verify source/license/attribution, then commit the generated manifest and WebP assets. Prefer reviewed generation/year bounds; register exact aliases rather than fuzzy matching. Keep CC BY-SA derivatives under their respective licenses, identify resizing, and preserve linked author/source/license credits. No client-side hotlinks.

## Acceptance still required
- Run existing resolver unit tests and frontend build; update and run browser coverage for the new reference-only card behavior (legacy image browser test assumes generic images on all cards, and must be revised).
- Verify all four actual image bytes and credits, cards in all four themes and mobile sizes, no wrong-brand/model images, bounded error handling, and no external requests.
- Add actual donor image preference only using an existing safe summary field or a batched authorized endpoint; do not add one photo API call per card.
- Expand reviewed library to current 36 donors and future models. No automatic open-web scraping or universal coverage claim.
