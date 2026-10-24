# Vehicle cards (UX 5.4)

Both Vehicles and Inventory's donor picker use `VehicleCard`. It reuses existing
vehicle records, stock position counts and PowertrainEditor. Vehicle IDs, API
contracts, quantity calculations and inventory/order operations are unchanged.
The whole card is not clickable: title/parts, data and powertrain are separate
keyboard-accessible controls. Inventory’s data link opens the existing vehicle
view with its data section expanded (`info=1`, frontend routing only). Missing engine/transmission values show “Не вказано”
on compact cards; the existing editor remains available.

## Artwork and fallback

`VehicleSilhouette` contains two independently authored inline SVG drawings:
**generic SUV** and **generic neutral car**. They are decorative body profiles,
not verified drawings of a named model or generation. No model-specific images
or brand emblems are bundled. No external art, fonts, paid APIs, image endpoints,
network requests or additional dependencies are used for the silhouette.

The normalized manufacturer/model lookup currently identifies only unambiguous
SUV profiles: Volvo XC60, Volvo XC90, BMW X3. It does not infer engines, trim or
parts compatibility. Other models use the neutral fallback, including Chevrolet
Lacetti: its name alone does not identify sedan/hatchback/estate bodywork.
Unknown and empty lookup keys also use that fallback.

The inline fallback is synchronous: there is no image URL to fail or fetch,
so lazy loading is unnecessary for these small SVG paths. The element is
aria-hidden, unfocusable, pointer-events:none and has low opacity. Text and
controls occupy separate space; the SVG cannot intercept clicks or cover them.
Future exact-model artwork must have verified identity/generation and usage
rights before adding a separately documented asset registry; do not relabel a
generic drawing as model-accurate or use remote hotlinks.

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
