from bot.database.base import fetchrow


async def create_buyer_lead(
    name: str | None,
    phone: str | None,
    query: str | None,
    city: str | None,
    source: str | None = "web",
):
    return await fetchrow(
        """
        INSERT INTO buyer_leads (name, phone, query, city, source)
        VALUES ($1, $2, $3, $4, $5)
        RETURNING id, created_at
        """,
        name,
        phone,
        query,
        city,
        source,
    )
