from bot.database.base import fetch, fetchrow


ALLOWED_STATUSES = {"new", "in_progress", "done", "rejected"}


def validate_lead_status(status: str) -> str:
    if status not in ALLOWED_STATUSES:
        raise ValueError("Invalid lead status")
    return status


async def create_site_lead(
    seller_id: int,
    site_id: int | None,
    subdomain: str,
    name: str | None,
    phone: str,
    message: str | None,
    session_id: str | None = None,
    utm_source: str | None = None,
    utm_medium: str | None = None,
    utm_campaign: str | None = None,
    referrer: str | None = None,
):
    return await fetchrow(
        """
        INSERT INTO site_leads (
            seller_id,
            site_id,
            subdomain,
            name,
            phone,
            message,
            session_id,
            utm_source,
            utm_medium,
            utm_campaign,
            referrer
        )
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
        RETURNING *
        """,
        seller_id,
        site_id,
        subdomain,
        name,
        phone,
        message,
        session_id,
        utm_source,
        utm_medium,
        utm_campaign,
        referrer,
    )


async def list_site_leads(status: str | None = None, limit: int = 100):
    if status is not None:
        validate_lead_status(status)
        return await fetch(
            """
            SELECT *
            FROM site_leads
            WHERE status = $1
            ORDER BY created_at DESC, id DESC
            LIMIT $2
            """,
            status,
            limit,
        )

    return await fetch(
        """
        SELECT *
        FROM site_leads
        ORDER BY created_at DESC, id DESC
        LIMIT $1
        """,
        limit,
    )


async def get_site_lead_by_id(lead_id: int):
    return await fetchrow(
        """
        SELECT *
        FROM site_leads
        WHERE id = $1
        LIMIT 1
        """,
        lead_id,
    )


async def update_site_lead_status(
    lead_id: int,
    status: str,
    manager_admin_id: int | None = None,
):
    validate_lead_status(status)

    return await fetchrow(
        """
        UPDATE site_leads
        SET status = $2,
            manager_admin_id = $3,
            updated_at = NOW()
        WHERE id = $1
        RETURNING *
        """,
        lead_id,
        status,
        manager_admin_id,
    )
