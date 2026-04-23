import asyncio
from bot.database.pool import init_pool
from bot.database.base import fetch, execute
from bot.services.logo_service import get_logo


async def main():
    await init_pool()

    sellers = await fetch("""
        SELECT id, website
        FROM sellers
        WHERE website IS NOT NULL
          AND (logo_url IS NULL OR logo_url = '')
    """)

    seen = set()

    for s in sellers:
        website = s["website"]

        if not website or website in seen:
            continue

        seen.add(website)

        print("Processing:", website)

        logo = await get_logo(website)

        await execute(
            "UPDATE sellers SET logo_url = $1 WHERE website = $2",
            logo,
            website
        )

        # невелика пауза
        await asyncio.sleep(0.5)

    print("DONE")


if __name__ == "__main__":
    asyncio.run(main())
