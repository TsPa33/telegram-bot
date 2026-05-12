import asyncio
import os
import sys
from pathlib import Path

from passlib.context import CryptContext

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from bot.database import pool as pool_module
from bot.database.pool import init_pool
from bot.database.repositories.crm_admin_repo import (
    get_admin_user_by_telegram_id,
    set_admin_password,
    set_admin_username,
)

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def _required_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"{name} is required")
    return value


async def main() -> None:
    telegram_id_raw = _required_env("CRM_ADMIN_TELEGRAM_ID")
    username = _required_env("CRM_ADMIN_USERNAME").strip()
    password = _required_env("CRM_ADMIN_PASSWORD")

    if not username:
        raise RuntimeError("CRM_ADMIN_USERNAME must not be empty")

    try:
        telegram_id = int(telegram_id_raw)
    except ValueError as exc:
        raise RuntimeError("CRM_ADMIN_TELEGRAM_ID must be an integer") from exc

    await init_pool()
    try:
        admin = await get_admin_user_by_telegram_id(telegram_id)
        if not admin:
            raise RuntimeError(
                "Admin user not found. Run database bootstrap first or create the admin in CRM."
            )

        password_hash = pwd_context.hash(password)
        await set_admin_username(admin["id"], username)
        await set_admin_password(admin["id"], password_hash)
        print(f"CRM password configured for admin id={admin['id']} username={username}")
    finally:
        if pool_module.pool:
            await pool_module.pool.close()


if __name__ == "__main__":
    asyncio.run(main())
