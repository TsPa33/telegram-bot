import asyncio
from bot.database.pool import init_pool
from bot.database.base import fetch, execute
from bot.services.logo_service import get_logo


async def main():
    await init_pool()

    # 🔥 беремо унікальні сайти
    websites = await fetch("""
        SELECT DISTINCT website
        FROM sellers
        WHERE website IS NOT NULL
    """)

    for row in websites:
        website = row["website"]

        if not website:
            continue

        print("Processing:", website)

        logo = await get_logo(website)

        if not logo:
            print("❌ No logo:", website)
            continue

        # 🔥 ОНОВЛЮЄМО ВСІ записи з цим сайтом
        await execute(
            """
            UPDATE sellers
            SET logo_url = $1
            WHERE website = $2
            """,
            logo,
            website
        )

        await asyncio.sleep(0.5)

    print("DONE")


if __name__ == "__main__":
    asyncio.run(main())
