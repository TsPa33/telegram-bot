# CarPot normalization v1.0 — semantic review of 73 R13 proposals

Date: 2026-11-01. Review-only, **no approval issued, no SQL writes**.
Source: `warehouse/docs/catalogue-ua-proposals-r13.csv` (58 translation, 15 hierarchy candidates).
This is an editorial/semantic review of the proposal list, **not** verification against all 15,444 staging rows.

## Translation candidates — screening for ambiguous or risky source meaning

**Relatively straightforward translation candidates** (still pending owner approval and row-context checks):
- `Электрика → Електрика`, `Освещение → Освітлення`, `Безопасность → Безпека`, `Двери → Двері`.
- `Передний бампер` / `Бампер передний → Передній бампер`; `Бампер задний` / `Задний бампер → Задній бампер`.
- `Тормозной диск → Гальмівний диск`, `Тормозной суппорт → Гальмівний супорт`, `Поворотный кулак → Поворотний кулак`.
- `Рулевая рейка → Кермова рейка`, `Стеклоподъемник → Склопідіймач`, `Подушка безопасности → Подушка безпеки`.

**Must check category, technical meaning, or part-vs-tool scope before approval:**
- `Внутренняя отделка → Оздоблення салону`: confirm whether source means trim, upholstery, or general interior decoration.
- `Дополнительные удобства → Додаткове обладнання`: source may be a broad functional class rather than a part.
- `Подвеска оси / система подвески / колеса → Підвіска осі / колеса`: the proposed target drops a concept; avoid conflating suspension with wheels.
- `Система сцепления / навесные части → Система зчеплення / навісне обладнання`: scope of “навісні частини” is ambiguous.
- `Монтажный инструмент, сайлентблок → Монтажний інструмент для сайлентблока`: tool rather than automotive dismantling part; review product domain.
- `Монтажный комплект, компрессор → Монтажний комплект компресора`: compressor system must be identified.
- `Расширение, крыло → Розширювач крила`: distinguish fender flare from a wing extension.
- `Гильза, подвески поперечного рычага → Гільза поперечного важеля підвіски`: may mean a bushing/sleeve, confirm.
- `Зеркало заднего вида → Дзеркало заднього виду`: does not determine interior vs external, side, or equipment.
- `Генератор → Генератор`, `Стартер → Стартер`: unchanged spelling; record as Ukrainian-valid terms, not proof of a translation change.
- `Тормозная колодка → Гальмівна колодка`: inspect disc/drum and axle differences; name alone cannot establish one SKU or fitment.

## Hierarchy candidates: block automatic structural moves pending tree review

| Source | Proposed target | Preliminary assessment |
| --- | --- | --- |
| Двигатель / Двигун | Силовий агрегат | **BLOCK automatic merge**: engine is narrower than powertrain |
| Трансмиссия / Трансмісія | Силовий агрегат / Трансмісія | **BLOCK**: drivetrain placement needs a clearly approved taxonomy |
| Подвеска и рулевое / Підвіска та кермове управління | Ходова частина | **REVIEW**: broad source may cover multiple second-level systems |
| Колёса / шины / Колеса та шини / Колеса | Ходова частина / Колеса та шини or Колеса | **REVIEW**: wheel assembly, rim and tire are not the same part type |
| Оливи та рідини | Витратні матеріали / Оливи та рідини | **REVIEW**: parts catalog vs consumables policy |
| Двері | Кузов / Двері | **REVIEW**: ensure level=category/subcategory/part not mixed; 36 namesake part nodes |
| Интерьер / салон / Інтер’єр / салон / Салон | Салон | **REVIEW**: root classification and source-specific hierarchy |
| Тормозная система | Гальмівна система | Naming may be straightforward but a root-level move needs parent review |

## Preliminary duplicate decisions (not approved)

- 590 exact-name duplicate groups: **review_required** pending all member IDs, parent context, provenance, and stock/FK exposure.
- Same-name `Двері` (36), `Гальмівний супорт` (20), `Фара` (20): **do not merge by label**; check left/right, front/rear, model/generation, and intended classification level.
- Roots `Силовий агрегат`, `Кузов`, `Ходова частина`, `Салон`, `Охолодження`, `Освітлення`: prioritize because R13 shows high stock-link exposure and multiple source systems.

## Required next data input for actual per-ID decisions

Export from the existing owner-only staging endpoints after an authenticated login:
- `/api/v1/catalogue/admin/audit/duplicate-review.csv`
- `/api/v1/catalogue/admin/audit/catalogue-mapping.csv`

Without these exports (or a read-only PostgreSQL connection), this review cannot claim to have classified all 590 groups / 15,444 rows.

## Guardrails

- Synonyms are for **search only**; user-facing canonical names stay Ukrainian.
- Target hierarchy is exactly **category → subcategory → part type**, with variants as attributes.
- Preserve historical IDs, original labels, stock links, OEM, quantities, prices, and financial records.
- No staged migration or production change in this review.
