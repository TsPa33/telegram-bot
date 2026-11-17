# CarPot Global CRM — концепція 01

**Лише для погодження. Робоча CRM та Railway UI не змінені.**

## Відкрити

- **preview.html** — самодостатній інтерактивний файл. Відкрити у браузері; сервер,
  інсталяція чи доступ до інтернету не потрібні. Тема і demo-роль у верхній панелі.
- **review.html** — галерея п'яти пов'язаних макетів із screenshots; потребує решти
  файлів поряд. Відкривається локально або через простий HTTP server.
- **mobile.html** — мобільна версія в рамці 390 px; це той самий адаптивний інтерфейс.
- Локальний HTTP preview: `http://127.0.0.1:5284/review.html` у середовищі розробки.
  Ця loopback-адреса не є опублікованим сайтом і не обов'язково доступна на комп'ютері
  власника. Для перегляду на своєму пристрої використати preview.html або розпакувати архів.

Запуск сервера з кореня репозиторію:

```sh
python -m http.server 5284 --bind 127.0.0.1 --directory docs/control-center/concept-2026-11-17
```

## П'ять екранів

| Екран | Маршрут | Статичний макет |
| --- | --- | --- |
| Головний огляд | index.html#/overview | screenshots/01-overview.png |
| Клієнти | index.html#/clients | screenshots/02-clients.png |
| Повний профіль | index.html#/company/1 | screenshots/03-company.png |
| Робоча черга | index.html#/queue | screenshots/04-queue.png |
| Mobile | mobile.html | screenshots/05-mobile.png |

Додатково: Forest Slate screenshot, 4 теми, Settings, пошук/порожній результат,
фільтри, 2 сторінки, вкладки, створення demo-завдання, зміна demo-status,
ізольовані нотатки компанії. Дані нотаток/завдань лише в пам'яті поточної сторінки;
після reload початкові fixtures відновлюються. Немає fetch/API/авторизації/оплат.
Роль у макеті демонструє очікуваний UX, а не реалізує реальний access control.

## Документи

- DATA_AUDIT.md: доказове походження лімітів і статусів, актуальні агрегати staging,
  що підтверджено й що неможливо перевірити без окремого read-only доступу.
- UX_AND_PLAN.md: аудит чинного UI, інформаційна архітектура, компоненти, data gaps
  та план одного reviewable пакета після погодження.
- ../Checkpoint_010_Data_Audit_UX_Concept.md: provenance, перевірки та межі роботи.

## Валідація нового preview

- Chromium + WebKit × 4 теми × 320/390/768/1440 × 5 екранів: 32 конфігурації,
  160 screen checks, без document overflow, JS errors чи зовнішніх HTTP-запитів.
- 4 interaction cases: пошук/empty/filter/pagination, profile sections, demo-role,
  ізоляція нотаток/escaping, створення задачі, submenu та mobile menu/ESC.
- Самодостатній file:// preview перевірено в обох engines без зовнішніх запитів.
- Фінальні screenshots переглянуті візуально; payloads та реальні дані не використовуються.
- JSON receipts: verification/. Це перевірка концепції, не повторна сертифікація
  робочого frontend чи Warehouse regression. Зовнішнього live usability study немає.

Не реалізовувати ці макети у робочому UI до погодження власником.
