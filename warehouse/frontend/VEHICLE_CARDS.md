# Vehicle cards (UX 5.4)

Both Vehicles and Inventory's donor picker use `VehicleCard`. It reuses existing
vehicle records, stock position counts and PowertrainEditor. Vehicle IDs, API
contracts, quantity calculations and inventory/order operations are unchanged.
The whole card is not clickable: title/parts, data and powertrain are separate
keyboard-accessible controls. Inventory’s data link opens the existing vehicle
view with its data section expanded (`info=1`, frontend routing only). Missing engine/transmission values show “Не вказано”
on compact cards; the existing editor remains available.

## Artwork and fallback (updated in UX 5.4.1)

The original primitive inline SVGs have been replaced by VehicleImage and a
reviewed, extensible manifest/resolver. Two detailed generated local WebP
fallbacks (SUV and neutral car) are supplied; no exact model image is claimed.
See [VEHICLE_IMAGES.md](VEHICLE_IMAGES.md) for selection, years/generations,
licensing, all supported body types, native lazy loading and bounded failures.

## Layout and local checks

Two columns above 900px; one column below. Titles wrap without ellipsis; counts
use tabular figures. The compact footer preserves “Дані автомобіля” and
“Запчастини →”; touch controls are at least 44px at tablet/phone widths.
UX 5.3 colours, focus, motion preferences and semantic action variants remain.

`npm run build`. Run all existing browser suites, plus
`tests/vehicle-cards-browser.mjs`, against disposable local test PostgreSQL/API
and the production preview at 127.0.0.1:5173. Never use staging for these tests.
The design-system suite and the vehicle-card suite need separate fresh local
API processes/databases after the existing suite batch to respect the existing
20-registration-per-IP limiter; do not disable it.

The card suite covers 1440x1000, 768x1024 and 390x844; long names, blank powertrain,
zero counts, a large count read-only fixture, generic fallback, layout, focus,
powertrain editing and parts/data navigation. Screenshots are local, ignored:
`test-results/vehicle-cards-vehicles-{width}.png` and
`test-results/vehicle-cards-inventory-{width}.png`.
