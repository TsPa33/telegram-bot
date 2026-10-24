# Warehouse visual system (UX 5.3)

Frontend-only presentation update. Inventory calculations, API contracts,
request keys, authorization, navigation destinations and tree state are unchanged.

## Audit and structure

The existing stylesheet mixed successive UX layouts with many similar literal
colours. `primary` also styled donor navigation and every stock-row sale.
Focus, disabled states and motion preferences varied between components.

- `src/tokens.css`: palette, spacing, radii, control height, timing and aliases.
- `src/style.css`: existing responsive layouts, with neutral colours normalized.
- `src/design-system.css`: shared component roles and interactive states.
- Import in that order from `main.tsx`; put future palette values in tokens,
  visual roles in design-system, and geometry in the existing layout stylesheet.

## Roles

- Default / `secondary`: light outlined navigation and ordinary actions.
- `primary`: compact solid accent for submission and explicit confirmation.
- `ghost`, `text-button`: low-emphasis contextual actions.
- `icon-button`: named icon action; use an accessible label.
- `destructive`: outlined red confirmation, never colour as the only indication.
  The existing Confirm component accepts `destructive`; callbacks are unchanged.

Donor cards reuse PowertrainEditor and existing vehicle-detail navigation. They
show name, year, number, stock positions, engine and transmission; no new API or
inferred fitment data is introduced. Category and subcategory expansion/search
behaviour remains unchanged.

## Accessibility and interaction

Secondary text is #606D7C rather than the suggested lighter #768191:
5.28:1 against white and 4.71:1 against the subtle surface. Solid accent #42675E
has 6.30:1 contrast with white. #668B82 remains a restrained decorative accent.
Small text targets 4.5:1, large text 3:1. Disabled controls are excluded from the
text-contrast test, but use readable secondary text rather than low opacity.

Keyboard focus has a 2px outline plus halo. Solid primary foreground/fill switch
together rather than interpolating through low-contrast intermediate colours;
its border and focus halo still transition. Controls have 150ms transitions;
reduced-motion disables transitions/animations. Mobile controls and icon actions
have 44px minimum targets; checkboxes retain their larger associated label rows.
Hover never gates access to information or actions. Loading text remains visible
when the spinner animation is disabled.

## Checks

`npm run build`; existing browser suites unchanged. With a disposable local test
API and production preview at 127.0.0.1:5173 (never staging/production):

```
WAREHOUSE_E2E=1 WAREHOUSE_CHROMIUM_PATH=/usr/bin/chromium node tests/design-system-browser.mjs
```

Run this suite with a fresh test API process/database, separately from the other
suites: their combined registrations reach the real 20-per-IP rate limit. Do not
disable authentication throttling to run visual tests.

The new suite checks populated screens, forms, modal dialogs, the nested tree,
neutral donor actions, focus/hover/disabled states, reduced motion, computed text
contrast and page overflow at 1440x1000, 768x1024 and 390x844. Screenshots go to
ignored test-results/. This is a Chromium viewport check, not a physical Safari
or assistive-technology certification.
