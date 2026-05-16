from bot.database.base import fetch, fetchrow


DEFAULT_LIMIT = 12
MAX_LIMIT = 48


def _safe_limit(limit: int) -> int:
    return max(1, min(int(limit or DEFAULT_LIMIT), MAX_LIMIT))


def _safe_offset(offset: int) -> int:
    return max(0, int(offset or 0))


async def get_marketplace_summary() -> dict:
    """Return public marketplace counters for isolated buyer pages."""
    row = await fetchrow(
        """
        SELECT
            (SELECT COUNT(*)::int FROM seller_cars sc WHERE sc.status::text IN ('active', '1')) AS cars_count,
            (SELECT COUNT(*)::int FROM services) AS services_count,
            (SELECT COUNT(*)::int FROM sellers) AS sellers_count,
            (
                SELECT COUNT(DISTINCT city)::int
                FROM (
                    SELECT city FROM sellers WHERE city IS NOT NULL AND trim(city) <> ''
                    UNION
                    SELECT city FROM services WHERE city IS NOT NULL AND trim(city) <> ''
                ) cities
            ) AS cities_count
        """
    )

    if not row:
        return {
            "cars_count": 0,
            "services_count": 0,
            "sellers_count": 0,
            "cities_count": 0,
        }

    return dict(row)


async def get_latest_cars(limit: int = DEFAULT_LIMIT, offset: int = 0):
    return await fetch(
        """
        SELECT
            sc.id,
            sc.seller_id,
            sc.photo_id,
            sc.description,
            sc.views,
            sc.phone_clicks,
            sc.site_clicks,
            sc.created_at,
            m.name AS model,
            b.name AS brand,
            sel.username,
            sel.telegram_id,
            sel.phone,
            sel.name,
            sel.city,
            sel.shop_name,
            sel.website,
            sel.is_verified
        FROM seller_cars sc
        JOIN sellers sel ON sel.id = sc.seller_id
        JOIN models m ON m.id = sc.model_id
        JOIN brands b ON b.id = m.brand_id
        WHERE sc.status::text IN ('active', '1')
        ORDER BY sc.id DESC
        LIMIT $1 OFFSET $2
        """,
        _safe_limit(limit),
        _safe_offset(offset),
    )


async def get_latest_services(limit: int = DEFAULT_LIMIT, offset: int = 0):
    return await fetch(
        """
        SELECT
            srv.id,
            srv.seller_id,
            srv.category,
            srv.title,
            srv.city,
            srv.address,
            srv.description,
            srv.website,
            srv.photo_id,
            srv.price,
            srv.created_at,
            sel.username,
            sel.telegram_id,
            sel.phone,
            sel.name,
            sel.shop_name,
            sel.is_verified,
            COALESCE(st.views, 0) AS views,
            COALESCE(st.calls, 0) AS calls,
            COALESCE(st.clicks, 0) AS clicks
        FROM services srv
        LEFT JOIN sellers sel ON sel.id = srv.seller_id
        LEFT JOIN service_stats st ON st.service_id = srv.id
        ORDER BY srv.id DESC
        LIMIT $1 OFFSET $2
        """,
        _safe_limit(limit),
        _safe_offset(offset),
    )


async def get_featured_sellers(limit: int = 8, offset: int = 0):
    return await fetch(
        """
        SELECT
            sel.id,
            sel.telegram_id,
            sel.username,
            sel.phone,
            sel.name,
            sel.city,
            sel.shop_name,
            sel.website,
            sel.is_verified,
            sel.description,
            sel.photo_id,
            COUNT(DISTINCT sc.id)::int AS cars_count,
            COUNT(DISTINCT srv.id)::int AS services_count
        FROM sellers sel
        LEFT JOIN seller_cars sc
            ON sc.seller_id = sel.id
           AND sc.status::text IN ('active', '1')
        LEFT JOIN services srv ON srv.seller_id = sel.id
        GROUP BY sel.id
        HAVING COUNT(DISTINCT sc.id) > 0 OR COUNT(DISTINCT srv.id) > 0 OR sel.is_verified = TRUE
        ORDER BY sel.is_verified DESC, (COUNT(DISTINCT sc.id) + COUNT(DISTINCT srv.id)) DESC, sel.id DESC
        LIMIT $1 OFFSET $2
        """,
        _safe_limit(limit),
        _safe_offset(offset),
    )


async def search_marketplace(
    q: str | None = None,
    city: str | None = None,
    item_type: str = "all",
    limit: int = DEFAULT_LIMIT,
    offset: int = 0,
    category: str | None = None,
    service_type: str | None = None,
    brand: str | None = None,
    condition: str | None = None,
    verified: str | None = None,
    sort: str | None = "new",
) -> dict:
    normalized_type = item_type if item_type in {"all", "cars", "services"} else "all"
    normalized_query = (q or "").strip()
    normalized_city = (city or "").strip()
    normalized_category = (category or "").strip()
    normalized_service_type = (service_type or "").strip()
    normalized_brand = (brand or "").strip()
    normalized_condition = (condition or "").strip()
    normalized_verified = "true" if str(verified or "").lower() == "true" else ""
    normalized_sort = sort if sort in {"new", "popular", "trusted"} else "new"

    query_pattern = f"%{normalized_query}%" if normalized_query else None
    city_pattern = f"%{normalized_city}%" if normalized_city else None
    category_pattern = f"%{normalized_category}%" if normalized_category else None
    service_type_pattern = f"%{normalized_service_type}%" if normalized_service_type else None
    brand_pattern = f"%{normalized_brand}%" if normalized_brand else None
    condition_pattern = f"%{normalized_condition}%" if normalized_condition else None
    verified_filter = True if normalized_verified == "true" else None

    car_category_allows = not normalized_category or any(
        marker in normalized_category.lower()
        for marker in ("авто", "зап", "дет", "car", "part")
    )

    car_order = {
        "new": "sc.id DESC",
        "popular": "COALESCE(sc.views, 0) DESC, sc.id DESC",
        "trusted": "sel.is_verified DESC, sc.id DESC",
    }[normalized_sort]
    service_order = {
        "new": "srv.id DESC",
        "popular": "COALESCE(st.views, 0) DESC, srv.id DESC",
        "trusted": "sel.is_verified DESC, srv.id DESC",
    }[normalized_sort]

    cars = []
    services = []
    sellers = []

    if normalized_type in {"all", "cars"} and car_category_allows:
        cars = await fetch(
            f"""
            SELECT
                sc.id,
                sc.seller_id,
                sc.photo_id,
                sc.description,
                sc.views,
                sc.created_at,
                m.name AS model,
                b.name AS brand,
                sel.username,
                sel.telegram_id,
                sel.phone,
                sel.name,
                sel.city,
                sel.shop_name,
                sel.website,
                sel.is_verified
            FROM seller_cars sc
            JOIN sellers sel ON sel.id = sc.seller_id
            JOIN models m ON m.id = sc.model_id
            JOIN brands b ON b.id = m.brand_id
            WHERE sc.status::text IN ('active', '1')
              AND ($1::text IS NULL OR b.name ILIKE $1 OR m.name ILIKE $1 OR sc.description ILIKE $1 OR sel.shop_name ILIKE $1 OR sel.name ILIKE $1)
              AND ($2::text IS NULL OR sel.city ILIKE $2)
              AND ($3::text IS NULL OR b.name ILIKE $3)
              AND ($4::text IS NULL OR sc.description ILIKE $4)
              AND ($5::boolean IS NULL OR sel.is_verified = $5)
            ORDER BY {car_order}
            LIMIT $6 OFFSET $7
            """,
            query_pattern,
            city_pattern,
            brand_pattern,
            condition_pattern,
            verified_filter,
            _safe_limit(limit),
            _safe_offset(offset),
        )

    if normalized_type in {"all", "services"}:
        services = await fetch(
            f"""
            SELECT
                srv.id,
                srv.seller_id,
                srv.category,
                srv.title,
                srv.city,
                srv.address,
                srv.description,
                srv.website,
                srv.price,
                srv.created_at,
                sel.username,
                sel.telegram_id,
                sel.phone,
                sel.name,
                sel.shop_name,
                sel.is_verified,
                COALESCE(st.views, 0) AS views
            FROM services srv
            LEFT JOIN sellers sel ON sel.id = srv.seller_id
            LEFT JOIN service_stats st ON st.service_id = srv.id
            WHERE ($1::text IS NULL OR srv.category ILIKE $1 OR srv.title ILIKE $1 OR srv.description ILIKE $1 OR sel.shop_name ILIKE $1 OR sel.name ILIKE $1)
              AND ($2::text IS NULL OR srv.city ILIKE $2 OR sel.city ILIKE $2)
              AND ($3::text IS NULL OR srv.category ILIKE $3 OR srv.title ILIKE $3)
              AND ($4::text IS NULL OR srv.category ILIKE $4 OR srv.title ILIKE $4 OR srv.description ILIKE $4)
              AND ($5::boolean IS NULL OR sel.is_verified = $5)
            ORDER BY {service_order}
            LIMIT $6 OFFSET $7
            """,
            query_pattern,
            city_pattern,
            category_pattern,
            service_type_pattern,
            verified_filter,
            _safe_limit(limit),
            _safe_offset(offset),
        )

    if normalized_type == "all":
        sellers = await fetch(
            """
            SELECT
                sel.id,
                sel.telegram_id,
                sel.username,
                sel.phone,
                sel.name,
                sel.city,
                sel.shop_name,
                sel.website,
                sel.is_verified,
                sel.description,
                COUNT(DISTINCT sc.id)::int AS cars_count,
                COUNT(DISTINCT srv.id)::int AS services_count
            FROM sellers sel
            LEFT JOIN seller_cars sc
                ON sc.seller_id = sel.id
               AND sc.status::text IN ('active', '1')
            LEFT JOIN services srv ON srv.seller_id = sel.id
            WHERE ($1::text IS NULL OR sel.shop_name ILIKE $1 OR sel.name ILIKE $1 OR sel.description ILIKE $1)
              AND ($2::text IS NULL OR sel.city ILIKE $2)
              AND ($3::boolean IS NULL OR sel.is_verified = $3)
            GROUP BY sel.id
            HAVING COUNT(DISTINCT sc.id) > 0 OR COUNT(DISTINCT srv.id) > 0 OR sel.is_verified = TRUE
            ORDER BY sel.is_verified DESC, sel.id DESC
            LIMIT $4 OFFSET $5
            """,
            query_pattern,
            city_pattern,
            verified_filter,
            8,
            0,
        )

    return {
        "cars": cars,
        "services": services,
        "sellers": sellers,
        "query": normalized_query,
        "city": normalized_city,
        "type": normalized_type,
        "category": normalized_category,
        "service_type": normalized_service_type,
        "brand": normalized_brand,
        "condition": normalized_condition,
        "verified": normalized_verified,
        "sort": normalized_sort,
    }

def _text_or_none(value: str | None) -> str | None:
    value = (value or "").strip()
    return value or None


def _pattern(value: str | None) -> str | None:
    value = _text_or_none(value)
    return f"%{value}%" if value else None


def _vehicle_search_values(interpretation: dict) -> tuple[str | None, str | None, str | None, str | None, str | None, str | None, str | None]:
    brand = _text_or_none(interpretation.get("brand"))
    model = _text_or_none(interpretation.get("model") or interpretation.get("generation"))
    generation = _text_or_none(interpretation.get("generation"))
    engine = _text_or_none(interpretation.get("engine"))
    fuel = _text_or_none(interpretation.get("fuel"))
    transmission = _text_or_none(interpretation.get("transmission"))
    city = _text_or_none(interpretation.get("city"))
    return brand, model, generation, engine, fuel, transmission, city


async def search_exact_part_matches(*, interpretation: dict, query: str | None, limit: int = DEFAULT_LIMIT):
    """Search explicit inventory/description matches for the requested part.

    This is the highest-priority marketplace layer and represents potential exact
    part inventory. It is intentionally separate from donor vehicles so the UI can
    avoid misleading buyers.
    """
    brand, model, generation, engine, fuel, transmission, city = _vehicle_search_values(interpretation)
    part_name = _text_or_none(interpretation.get("part_name"))
    normalized_query = _text_or_none(query)
    part_pattern = _pattern(part_name)
    query_pattern = None if part_name else _pattern(normalized_query)
    brand_pattern = _pattern(brand)
    model_pattern = _pattern(model)
    generation_pattern = _pattern(generation)
    engine_pattern = _pattern(engine)
    fuel_pattern = _pattern(fuel)
    transmission_pattern = _pattern(transmission)
    city_pattern = _pattern(city)

    return await fetch(
        """
        SELECT
            sc.id,
            sc.seller_id,
            sc.photo_id,
            sc.description,
            sc.views,
            sc.phone_clicks,
            sc.site_clicks,
            sc.created_at,
            sc.inventory_kind,
            sc.donor_generation,
            sc.engine_code,
            sc.engine_family,
            sc.fuel_type,
            sc.transmission_type,
            sc.compatibility_notes,
            m.name AS model,
            b.name AS brand,
            sel.username,
            sel.telegram_id,
            sel.phone,
            sel.name,
            sel.city,
            sel.shop_name,
            sel.website,
            sel.is_verified,
            'exact_part_match' AS result_type,
            'Точний збіг по опису запчастини' AS match_label,
            'Знайдено явну згадку запчастини у пропозиції продавця. Наявність і стан підтвердіть напряму.' AS match_explanation,
            'Це не donor vehicle — це потенційний точний інвентар.' AS trust_message,
            'Відкрити пропозицію' AS primary_cta,
            'Створити заявку' AS secondary_cta,
            (
                CASE WHEN $3::text IS NOT NULL AND b.name ILIKE $3 THEN 30 ELSE 0 END +
                CASE WHEN $4::text IS NOT NULL AND m.name ILIKE $4 THEN 25 ELSE 0 END +
                CASE WHEN $1::text IS NOT NULL AND sc.description ILIKE $1 THEN 35 ELSE 0 END +
                CASE WHEN $5::text IS NOT NULL AND (sc.description ILIKE $5 OR sc.donor_generation ILIKE $5) THEN 10 ELSE 0 END +
                CASE WHEN $6::text IS NOT NULL AND (sc.description ILIKE $6 OR sc.engine_code ILIKE $6 OR sc.engine_family ILIKE $6) THEN 10 ELSE 0 END +
                CASE WHEN sel.is_verified THEN 5 ELSE 0 END
            )::int AS match_score
        FROM seller_cars sc
        JOIN sellers sel ON sel.id = sc.seller_id
        JOIN models m ON m.id = sc.model_id
        JOIN brands b ON b.id = m.brand_id
        WHERE sc.status::text IN ('active', '1')
          AND ($9::text IS NULL OR sel.city ILIKE $9)
          AND ($3::text IS NULL OR b.name ILIKE $3)
          AND ($4::text IS NULL OR m.name ILIKE $4 OR sc.description ILIKE $4)
          AND ($1::text IS NULL OR sc.description ILIKE $1 OR $2::text IS NOT NULL AND sc.description ILIKE $2)
          AND ($5::text IS NULL OR sc.description ILIKE $5 OR sc.donor_generation ILIKE $5)
          AND ($6::text IS NULL OR sc.description ILIKE $6 OR sc.engine_code ILIKE $6 OR sc.engine_family ILIKE $6)
          AND ($7::text IS NULL OR sc.description ILIKE $7 OR sc.fuel_type ILIKE $7)
          AND ($8::text IS NULL OR sc.description ILIKE $8 OR sc.transmission_type ILIKE $8)
        ORDER BY match_score DESC, sel.is_verified DESC, sc.id DESC
        LIMIT $10
        """,
        part_pattern,
        query_pattern,
        brand_pattern,
        model_pattern,
        generation_pattern,
        engine_pattern,
        fuel_pattern,
        transmission_pattern,
        city_pattern,
        _safe_limit(limit),
    )


async def search_donor_vehicle_matches(*, interpretation: dict, query: str | None, limit: int = DEFAULT_LIMIT):
    """Search donor vehicles compatible with interpreted vehicle signals."""
    brand, model, generation, engine, fuel, transmission, city = _vehicle_search_values(interpretation)
    normalized_query = _text_or_none(query)
    query_pattern = _pattern(normalized_query)
    brand_pattern = _pattern(brand)
    model_pattern = _pattern(model)
    generation_pattern = _pattern(generation)
    engine_pattern = _pattern(engine)
    fuel_pattern = _pattern(fuel)
    transmission_pattern = _pattern(transmission)
    city_pattern = _pattern(city)

    return await fetch(
        """
        SELECT
            sc.id,
            sc.seller_id,
            sc.photo_id,
            sc.description,
            sc.views,
            sc.phone_clicks,
            sc.site_clicks,
            sc.created_at,
            sc.inventory_kind,
            sc.donor_generation,
            sc.engine_code,
            sc.engine_family,
            sc.fuel_type,
            sc.transmission_type,
            sc.compatibility_notes,
            m.name AS model,
            b.name AS brand,
            sel.username,
            sel.telegram_id,
            sel.phone,
            sel.name,
            sel.city,
            sel.shop_name,
            sel.website,
            sel.is_verified,
            'donor_vehicle_match' AS result_type,
            'Potential donor vehicle' AS match_label,
            'Точної запчастини не підтверджено, але авто-донор відповідає бренду/моделі/двигуну або трансмісії.' AS match_explanation,
            'Donor vehicle не гарантує наявність конкретної деталі — запитайте продавця про демонтаж, стан і сумісність.' AS trust_message,
            'Запитати про деталь' AS primary_cta,
            'Створити заявку' AS secondary_cta,
            (
                CASE WHEN $1::text IS NOT NULL AND (
                    b.name ILIKE $1::text
                    OR m.name ILIKE $1::text
                    OR sc.description ILIKE $1::text
                    OR sc.donor_generation ILIKE $1::text
                    OR sc.engine_code ILIKE $1::text
                    OR sc.engine_family ILIKE $1::text
                    OR sc.fuel_type ILIKE $1::text
                    OR sc.transmission_type ILIKE $1::text
                    OR sc.compatibility_notes ILIKE $1::text
                ) THEN 10 ELSE 0 END +
                CASE WHEN $2::text IS NOT NULL AND b.name ILIKE $2::text THEN 35 ELSE 0 END +
                CASE WHEN $3::text IS NOT NULL AND (m.name ILIKE $3::text OR sc.description ILIKE $3::text) THEN 25 ELSE 0 END +
                CASE WHEN $4::text IS NOT NULL AND (sc.description ILIKE $4::text OR sc.donor_generation ILIKE $4::text) THEN 15 ELSE 0 END +
                CASE WHEN $5::text IS NOT NULL AND (sc.description ILIKE $5::text OR sc.engine_code ILIKE $5::text OR sc.engine_family ILIKE $5::text) THEN 15 ELSE 0 END +
                CASE WHEN $6::text IS NOT NULL AND (sc.description ILIKE $6::text OR sc.fuel_type ILIKE $6::text) THEN 10 ELSE 0 END +
                CASE WHEN $7::text IS NOT NULL AND (sc.description ILIKE $7::text OR sc.transmission_type ILIKE $7::text OR sc.compatibility_notes ILIKE $7::text) THEN 10 ELSE 0 END +
                CASE WHEN sel.is_verified THEN 5 ELSE 0 END
            )::int AS match_score
        FROM seller_cars sc
        JOIN sellers sel ON sel.id = sc.seller_id
        JOIN models m ON m.id = sc.model_id
        JOIN brands b ON b.id = m.brand_id
        WHERE sc.status::text IN ('active', '1')
          AND (
              $1::text IS NULL
              OR b.name ILIKE $1::text
              OR m.name ILIKE $1::text
              OR sc.description ILIKE $1::text
              OR sc.donor_generation ILIKE $1::text
              OR sc.engine_code ILIKE $1::text
              OR sc.engine_family ILIKE $1::text
              OR sc.fuel_type ILIKE $1::text
              OR sc.transmission_type ILIKE $1::text
              OR sc.compatibility_notes ILIKE $1::text
          )
          AND ($2::text IS NULL OR b.name ILIKE $2::text)
          AND ($3::text IS NULL OR m.name ILIKE $3::text OR sc.description ILIKE $3::text)
          AND ($4::text IS NULL OR sc.description ILIKE $4::text OR sc.donor_generation ILIKE $4::text)
          AND ($5::text IS NULL OR sc.description ILIKE $5::text OR sc.engine_code ILIKE $5::text OR sc.engine_family ILIKE $5::text)
          AND ($6::text IS NULL OR sc.description ILIKE $6::text OR sc.fuel_type ILIKE $6::text)
          AND ($7::text IS NULL OR sc.description ILIKE $7::text OR sc.transmission_type ILIKE $7::text OR sc.compatibility_notes ILIKE $7::text)
          AND ($8::text IS NULL OR sel.city ILIKE $8::text)
        ORDER BY match_score DESC, sel.is_verified DESC, sc.id DESC
        LIMIT $9::int
        """,
        query_pattern,
        brand_pattern,
        model_pattern,
        generation_pattern,
        engine_pattern,
        fuel_pattern,
        transmission_pattern,
        city_pattern,
        _safe_limit(limit),
    )


async def search_seller_specialization_matches(*, interpretation: dict, query: str | None, limit: int = 8):
    """Find sellers whose profile, donor vehicles or services match the buyer need."""
    brand, model, generation, engine, fuel, transmission, city = _vehicle_search_values(interpretation)
    part_name = _text_or_none(interpretation.get("part_name"))
    category = _text_or_none(interpretation.get("category"))
    service_type = _text_or_none(interpretation.get("service_type"))
    normalized_query = _text_or_none(query)
    query_pattern = None if any((brand, model, generation, engine, fuel, transmission, part_name, category, service_type)) else _pattern(normalized_query)
    brand_pattern = _pattern(brand)
    model_pattern = _pattern(model)
    generation_pattern = _pattern(generation)
    engine_pattern = _pattern(engine)
    fuel_pattern = _pattern(fuel)
    transmission_pattern = _pattern(transmission)
    part_pattern = _pattern(part_name)
    category_pattern = _pattern(category)
    service_type_pattern = _pattern(service_type)
    city_pattern = _pattern(city)

    return await fetch(
        """
        SELECT
            sel.id,
            sel.telegram_id,
            sel.username,
            sel.phone,
            sel.name,
            sel.city,
            sel.shop_name,
            sel.website,
            sel.is_verified,
            sel.description,
            sel.photo_id,
            COUNT(DISTINCT sc.id)::int AS cars_count,
            COUNT(DISTINCT srv.id)::int AS services_count,
            'seller_specialization_match' AS result_type,
            'Спеціалізований продавець' AS match_label,
            'Профіль продавця, donor vehicles або послуги збігаються з брендом/моделлю/категорією запиту.' AS match_explanation,
            'Це спеціалізація продавця, а не підтверджений точний складський залишок.' AS trust_message,
            'Зв’язатися з продавцем' AS primary_cta,
            'Створити заявку' AS secondary_cta,
            MAX(
                CASE WHEN $3::text IS NOT NULL AND b.name ILIKE $3 THEN 35 ELSE 0 END +
                CASE WHEN $4::text IS NOT NULL AND m.name ILIKE $4 THEN 20 ELSE 0 END +
                CASE WHEN $8::text IS NOT NULL AND (srv.category ILIKE $8 OR srv.title ILIKE $8 OR srv.description ILIKE $8 OR sel.description ILIKE $8 OR sc.description ILIKE $8) THEN 25 ELSE 0 END +
                CASE WHEN $9::text IS NOT NULL AND (srv.category ILIKE $9 OR srv.title ILIKE $9 OR srv.description ILIKE $9) THEN 20 ELSE 0 END +
                CASE WHEN $10::text IS NOT NULL AND (srv.category ILIKE $10 OR srv.title ILIKE $10 OR srv.description ILIKE $10) THEN 15 ELSE 0 END +
                CASE WHEN $5::text IS NOT NULL AND (sc.description ILIKE $5 OR sc.donor_generation ILIKE $5) THEN 10 ELSE 0 END +
                CASE WHEN $6::text IS NOT NULL AND (sc.description ILIKE $6 OR sc.engine_code ILIKE $6 OR sc.engine_family ILIKE $6) THEN 10 ELSE 0 END +
                CASE WHEN $7::text IS NOT NULL AND (sc.description ILIKE $7 OR sc.fuel_type ILIKE $7 OR sc.transmission_type ILIKE $7) THEN 10 ELSE 0 END +
                CASE WHEN sel.is_verified THEN 5 ELSE 0 END
            )::int AS match_score
        FROM sellers sel
        LEFT JOIN seller_cars sc
            ON sc.seller_id = sel.id
           AND sc.status::text IN ('active', '1')
        LEFT JOIN models m ON m.id = sc.model_id
        LEFT JOIN brands b ON b.id = m.brand_id
        LEFT JOIN services srv ON srv.seller_id = sel.id
        WHERE ($11::text IS NULL OR sel.city ILIKE $11 OR srv.city ILIKE $11)
          AND (
            $1::text IS NULL
            OR sel.shop_name ILIKE $1
            OR sel.name ILIKE $1
            OR sel.description ILIKE $1
            OR srv.category ILIKE $1
            OR srv.title ILIKE $1
            OR srv.description ILIKE $1
            OR b.name ILIKE $1
            OR m.name ILIKE $1
            OR sc.description ILIKE $1
          )
          AND (
            $3::text IS NULL
            OR b.name ILIKE $3
            OR sel.description ILIKE $3
            OR srv.description ILIKE $3
            OR sc.description ILIKE $3
          )
        GROUP BY sel.id
        HAVING COUNT(DISTINCT sc.id) > 0 OR COUNT(DISTINCT srv.id) > 0 OR sel.is_verified = TRUE
        ORDER BY match_score DESC, sel.is_verified DESC, (COUNT(DISTINCT sc.id) + COUNT(DISTINCT srv.id)) DESC, sel.id DESC
        LIMIT $12
        """,
        query_pattern,
        normalized_query,
        brand_pattern,
        model_pattern,
        generation_pattern,
        engine_pattern,
        fuel_pattern or transmission_pattern,
        part_pattern,
        category_pattern,
        service_type_pattern,
        city_pattern,
        _safe_limit(limit),
    )


async def search_service_provider_matches(*, interpretation: dict, query: str | None, limit: int = DEFAULT_LIMIT):
    """Search automotive services with city as an optional refinement, never a blocker."""
    _, _, _, _, _, _, city = _vehicle_search_values(interpretation)
    service_type = _text_or_none(interpretation.get("service_type"))
    category = _text_or_none(interpretation.get("category"))
    normalized_query = _text_or_none(query)
    service_pattern = _pattern(service_type or normalized_query)
    category_pattern = _pattern(category if category not in {"unknown", "services"} else None)
    query_pattern = None if service_type or category_pattern else _pattern(normalized_query)
    city_pattern = _pattern(city)

    return await fetch(
        """
        SELECT
            srv.id,
            srv.seller_id,
            srv.category,
            srv.title,
            srv.city,
            srv.address,
            srv.description,
            srv.website,
            srv.price,
            srv.created_at,
            sel.username,
            sel.telegram_id,
            sel.phone,
            sel.name,
            sel.shop_name,
            sel.is_verified,
            COALESCE(st.views, 0) AS views,
            'service_provider_match' AS result_type,
            'Релевантний сервіс або провайдер' AS match_label,
            'Послуга або профіль виконавця збігається з типом сервісу; місто використовується тільки як уточнення.' AS match_explanation,
            'Місто не блокує пошук — уточніть локацію для точнішого результату.' AS trust_message,
            'Зв’язатися з сервісом' AS primary_cta,
            'Створити заявку' AS secondary_cta,
            (
                CASE WHEN $1::text IS NOT NULL AND (srv.category ILIKE $1 OR srv.title ILIKE $1 OR srv.description ILIKE $1) THEN 45 ELSE 0 END +
                CASE WHEN $2::text IS NOT NULL AND (srv.category ILIKE $2 OR srv.title ILIKE $2 OR srv.description ILIKE $2) THEN 20 ELSE 0 END +
                CASE WHEN $3::text IS NOT NULL AND (srv.category ILIKE $3 OR srv.title ILIKE $3 OR srv.description ILIKE $3 OR sel.shop_name ILIKE $3 OR sel.name ILIKE $3 OR sel.description ILIKE $3) THEN 15 ELSE 0 END +
                CASE WHEN $4::text IS NOT NULL AND (srv.city ILIKE $4 OR sel.city ILIKE $4) THEN 10 ELSE 0 END +
                CASE WHEN sel.is_verified THEN 5 ELSE 0 END
            )::int AS match_score
        FROM services srv
        LEFT JOIN sellers sel ON sel.id = srv.seller_id
        LEFT JOIN service_stats st ON st.service_id = srv.id
        WHERE (
            $1::text IS NULL
            OR srv.category ILIKE $1
            OR srv.title ILIKE $1
            OR srv.description ILIKE $1
            OR sel.shop_name ILIKE $1
            OR sel.name ILIKE $1
            OR sel.description ILIKE $1
        )
          AND ($2::text IS NULL OR srv.category ILIKE $2 OR srv.title ILIKE $2 OR srv.description ILIKE $2)
          AND (
            $3::text IS NULL
            OR srv.category ILIKE $3
            OR srv.title ILIKE $3
            OR srv.description ILIKE $3
            OR sel.shop_name ILIKE $3
            OR sel.name ILIKE $3
            OR sel.description ILIKE $3
          )
        ORDER BY match_score DESC, sel.is_verified DESC, COALESCE(st.views, 0) DESC, srv.id DESC
        LIMIT $5
        """,
        service_pattern,
        category_pattern,
        query_pattern,
        city_pattern,
        _safe_limit(limit),
    )
