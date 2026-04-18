import os

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_IDS = [6206952389]


def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS


# Backward compatibility for old imports.
ADMINS = ADMIN_IDS
