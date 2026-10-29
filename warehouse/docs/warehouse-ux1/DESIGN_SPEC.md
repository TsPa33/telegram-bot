# CarPot Warehouse UX-1 — Visual design reference

**Authoritative visual reference:** `00_full_reference.png` (1536×1024). The crops below are annotations of THAT SAME approved reference, not independent designs. They are UX references, not real product/market data. Do not hardcode any example vehicle, photo, number or price.

## Reference mapping (in priority order)

| File | Required visual element |
|---|---|
| `01_vehicle_header.png` | Compact vehicle summary, title, subtle tabs, tight spacing |
| `02_stats_cards.png` | Four concise statistics, with counts and filtering on click |
| `03_search_and_filters.png` | One compact horizontal filter bar |
| `04_compact_parts_table.png` | Grouped dense desktop parts table; alignment and price prominence |
| `05_part_detail_drawer.png` | Desktop right drawer is UX-2 target; UX-1 must not break its ability to open existing detail editor |
| `06_mobile_cards.png` | 390px mobile compact cards without horizontal overflow |
| `07_single_part_card.png` | One card layout, visual density and pricing hierarchy |
| `08_price_sources_detail.png` | UX-2 expanded pricing view; no provider names in UI |
| `09_bulk_price_form.png` | UX-3 visual reference only; do not implement bulk workflow in UX-1 |

## Palette — reference-informed approximate CSS tokens (not necessarily pixel-exact)

```css
--cp-sidebar: #151D28;
--cp-page: #F7F8FA;
--cp-card: #FFFFFF;
--cp-surface-muted: #F3F5F8;
--cp-border: #DEE5EF;
--cp-text: #172235;
--cp-muted: #66758C;
--cp-primary: #2563EB;
--cp-primary-hover: #1D4ED8;
--cp-success-bg: #E4F8EA;
--cp-success-text: #166534;
--cp-reserved-bg: #DBEAFE;
--cp-reserved-text: #1D4ED8;
--cp-warning-bg: #FEF3C7;
--cp-warning-text: #92400E;
```

## UI rules

- Maintain existing app-wide design tokens/nav where compatible; scope necessary changes to Warehouse UX, do not globally recolor unrelated pages.
- Clean professional desktop table and mobile cards, flat white backgrounds with 1px soft gray borders, subtle radii 8–12px, little/no shadow, and only primary actions blue.
- Main readable font: existing system font (Inter if already present, otherwise system sans-serif); normal text 13–14px, metadata 11–12px, prices 15–18px semibold, section titles 16–20px.
- Desktop list rows aim for ~60–76px in typical cases; compact status and clear right-aligned prices. Not a fixed height if content is genuinely needed. Use responsive column layout and existing sidebar dimensions.
- The **user-facing UI must not show any provider/source brand names**, despite such words being present in older reference image examples. Show only `Рекомендована ціна`, `Схожі ціни`, `Моя ціна`, `Переглянути ціни` and actual amount/currency/condition in expanded examples.
- Never display `engine_code`, `options`, raw OEM matching reasons, ingestion timestamps or source IDs by default. Preserve audit/matching evidence in backend.
- The reference image contains illustrative values, images and clickable actions; don't invent data, don't show a fake product photo, and don't add non-working actions.
- Display source prices in their original currency (UAH or USD). Never silently convert. Verified recommendation may be acted on only under existing save-confirmation semantics; unverified examples require explicit user choice, not an automatic recommendation.
- UX-1 is **presentation + read-only stats + existing safe manual price editing only**. UX-2 and UX-3 shown as future references, not implementation scope. Don't add migrations or new pricing algorithms.
- Verify 1440px desktop and 390px phone screenshots against these references, then provide screenshots and concise differences.
