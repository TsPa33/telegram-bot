from bot.database.base import fetchrow


async def create_buyer_lead(
    what_needed: str,
    phone: str,
    city: str | None = None,
    telegram: str | None = None,
    vin: str | None = None,
    description: str | None = None,
    photos: str | None = None,
    source_path: str | None = None,
):
    return await fetchrow(
        """
        INSERT INTO buyer_leads (
            what_needed,
            phone,
            city,
            telegram,
            vin,
            description,
            photos,
            source_path
        )
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
        RETURNING *
        """,
        what_needed,
        phone,
        city,
        telegram,
        vin,
        description,
        photos,
        source_path,
    )
