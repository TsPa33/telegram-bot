# Корпоративна ієрархія Day / Night

- Чинні ThemeProvider, bootstrap, localStorage, системний fallback і cross-tab sync повторно використані без змін.
- Нічна палітра наближена до затвердженого макета: фон #0D211D, sidebar #091C19, картки #142F29, таблиці #112A25, основний текст #E2E9E5. Акцент кнопок трохи затемнений для AA без чисто білого тексту.
- У наявній системі токенів додані ролі `--color-table`, `--color-text-muted`, `--color-link`, `--color-price`, `--color-number`, `--color-on-accent`, `--part-row-base`, `--part-row-selected-border`. Нічні row tokens явно відрізняють base / zebra / hover / active / selected / success. Checkbox залишається окремою ознакою вибору; combined active+selected має обидві межі.
- Синій використовується для клікабельного донора, теплий колір — лише для встановленої власної ціни. Відсутні OEM, артикули та ціна приглушені. Числа 0/0.00 залишаються встановленою ціною. Атрибути презентації отримують дані з чинних моделей, без нових API-запитів.
- Виправлено нічний foreground primary-кнопок: раніше він використовував колір поверхні. Нейтральні controls, межі, focus, QuickPreview та меню споживають ті самі токени. Звичайні ролі працівників не використовують danger-акцент; архівування має destructive-стиль.
- Денне компонування й робочі обробники залишені; нових меню, сповіщень, OEM, сум або фотографій із макета не додано.

## Перевірки

- `node --test tests/night-hierarchy-unit.mjs tests/theme-unit.mjs tests/theme-day-night-unit.mjs`: **18 PASS**. AA перевірено для фактичних нічних text/muted/link/price/number токенів на surface/table/active/selected; контрольні межі ≥3:1; primary та hover text ≥4.5:1.
- `npm --ignore-scripts run build`: **PASS**. Незмінний загальний prebuild не повторювався; залишається стандартне попередження Vite про chunk size.
- `WAREHOUSE_E2E=1 node tests/night-hierarchy-browser.mjs`: **PASS**, 1440/390px. Перевірено computed colors п’яти row states, присутню/відсутню ціну, донора, відсутні номери, Day/Night, reload, cross-tab sync, основні маршрути, налаштування деталей, popover і modal drawer. JS errors / business writes: **0**. Read-only POST `/pricing/guidance` читає імпортовані дані; платних запитів немає.

[Ніч desktop](screenshots/inventory-dark-1440.png) · [Ніч mobile](screenshots/inventory-dark-390.png) · [День desktop](screenshots/inventory-light-1440.png) · [День mobile](screenshots/inventory-light-390.png) · [Night drawer](screenshots/drawer-dark.png)

Backend, API contracts, PostgreSQL, migrations, кількості, ціни, резерви, OEM/артикули, переклади та permissions не змінені. Дані на скриншотах — наявний локальний synthetic fixture, не числа з макета. Повний owner-only каталог та заповнені фінансові графіки не приймалися через відсутність відповідних локальних даних/доступу. Railway deployment і staging QA — UNVERIFIED; очікується Web Auto Deploy після звичайного push.
