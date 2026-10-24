# Universal vehicle images — UX 5.4.1

## Current scope and real data

VehicleCard retains the UX 5.4 HTML/data/actions and UX 5.3 palette. VehicleImage
replaces the primitive SVG component. Existing backend fields used: manufacturer,
model, year and generation. **The backend has no body-type field.** No backend,
API, order, stock-operation, schema or Railway change is required.

No verified exact-model image is bundled. Two original generated generic
fallback images are supplied, with 960px and 480px transparent WebP variants:
generic SUV and universal neutral car. These are not donor photos and do not
identify a generation. Provenance, terms, dimensions and hashes are recorded in
`src/assets/vehicles/PROVENANCE.md` and `metadata.json`.

The type system supports sedan, hatchback, wagon, suv/crossover, coupe,
convertible, minivan/MPV, pickup, van and unknown. Only SUV and unknown currently
have supplied artwork. Missing body artwork falls through to the quality unknown
resource; the system does not pretend to contain ten distinct images.

## Architecture and selection

- `vehicleImageTypes.ts`: manifest/identity/body-type contracts, frontend only.
- `vehicleImageManifest.ts`: reviewed data, URL index, body-only rules, fallbacks.
- `vehicleImageResolver.ts`: indexed lookup compiled once; no network or React.
- `VehicleImage.tsx`: native lazy image, responsive selection, bounded error chain.

Canonical names use Unicode NFKC, case and whitespace normalization. No fuzzy,
substring, numeric-generation or guessed brand aliases are used. Add explicit
reviewed aliases as additional manifest entries/rules if actually needed.

Selection, with at most one resource per tier (maximum four attempts per card):

1. Exact canonical brand/model/generation AND verified year coverage.
2. Exact brand/model with verified year coverage. Missing generation may use this
   tier, but the stored generation is never inferred or written. An explicitly
   conflicting generation is rejected. Ambiguous overlapping generation coverage
   without a confirmed generation falls back rather than guessing.
3. Reviewed body-specific fallback. The current explicit body rules classify only
   XC60, XC90 and X3 as generic SUVs; this is not generation/fitment inference.
   Multiple conflicting rules produce unknown. Optional trusted bodyType input is
   supported by the pure resolver for future callers, not added to the backend.
4. Universal unknown image. If even that fails, a stable neutral text placeholder
   appears; no broken-image icon, loop, stock change or new API request occurs.

Both gen/model assets need finite inclusive yearFrom/yearTo values. Matching
uses only current vehicle data plus reviewed local metadata. Missing/invalid
resource paths, unavailable file entries, pending rights, unverified images,
duplicate IDs, external/data URLs and unsupported file types are excluded before
rendering. Loading errors advance through the already resolved safe chain.

## Manifest example (schema example, not a claim of a supplied image)

```ts
{
 id: 'reviewed-model-generation-v1', kind: 'generation',
 manufacturer: '<canonical brand>', model: '<canonical model>',
 generation: '<verified generation>', yearFrom: 2018, yearTo: 2020,
 bodyType: 'suv', file: 'reviewed-model-generation.webp',
 width: 960, height: 400, verified: true, priority: 10,
 variants: [{file: 'reviewed-model-generation-480.webp', width: 480}],
 source: {type: 'licensed', description: '<source/verification>', reference: '<source/license record>'},
 usage: {status: 'approved', license: '<actual terms>', commercialUse: true, attribution: '<if required>'}
}
```

Add a model/generation by placing reviewed, optimized artwork in
`src/assets/vehicles/`, then adding its metadata entry. React card code stays
unchanged. WebP, PNG and audited SVG files are already indexed by the build-time glob;
adding a reviewed resource does not require editing the card component. Only same-origin build
asset URLs are accepted. Do not put query tokens, hotlinks, private credentials
or API-returned URLs in this registry. Keep generic resources kind body/unknown;
never register them as a verified model. Rights must allow the intended product
use. A nonempty usage.attribution is rendered as a visible credit outside the
decorative aria-hidden image, without changing card height. Review any additional
link/credit requirements before approving a resource; text credit alone must not
be assumed to satisfy every license. Current generated assets have no third-party
attribution requirement.

To add artwork for an already supported body type, add a kind body entry and
map that type in fallbacks. To add another body type beyond the ten, extend the
type list and fallback schema and add tests; no vehicle-table change is needed.
Body rules may constrain generation/years when a model name alone is ambiguous.
For unknown body data, use unknown; never guess from a partial model name.

## Performance, caching and failure behaviour

Vite emits separate content-hashed /assets/ files; only URL/metadata strings enter
JS, not the image bytes. Production Nginx already caches /assets/ for one year;
no Nginx/Railway configuration change is made. Native loading=lazy, decoding=async,
responsive 480/960 sources and shared URLs avoid provider calls and per-card
resource copies. Model indexes are built once; selection does not scan the entire
image library for each card. Keep resources ideally below 100KB, width <=1600px,
correct declared dimensions, and alpha transparency. The current four files total
about 174KB; typical selected files are 22–67KB. No graphics dependency is added.

The image region has a fixed responsive height before/during/after loading. Error
state is reset synchronously when vehicle identity changes, preventing a stale
model image on another donor. No API image cache, permanent supplier-data cache,
background synchronization or paid provider integration is introduced.

## Local validation

```
npm run build
node tests/vehicle-images-unit.mjs
```

Browser suites require a disposable local test PostgreSQL/API and production
preview at 127.0.0.1:5173 with WAREHOUSE_E2E=1. Run the existing batch, design suite,
card suite and images suite with fresh local API processes as documented for UX
5.3/5.4, respecting the 20-registration-per-IP limit rather than disabling it.
`vehicle-images-browser.mjs` covers the six requested demo identities, unknown
body, native lazy/shared resources, blocked/broken images, stable loading layout,
long names and a 1000-card read-only response fixture at 1440x1000, 768x1024 and
390x844. Resolver unit tests use synthetic metadata for exact-model/generation
cases; no real model image is falsely claimed by those fixtures.

Screenshots: ignored `test-results/vehicle-images-{width}.png`. Chromium viewports
are tested; physical iPhone/Safari and an actual licensed model-asset library are
outside the current local verification.
