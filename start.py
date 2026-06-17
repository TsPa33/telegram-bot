import asyncio
import logging
import os

from bot.main import main

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger(__name__)

logger.info("Railway entrypoint start.py loaded")
logger.info("BOT_TOKEN present: %s", "yes" if os.getenv("BOT_TOKEN") else "no")
logger.info("DATABASE_URL present: %s", "yes" if os.getenv("DATABASE_URL") else "no")

if __name__ == "__main__":
    asyncio.run(main())
