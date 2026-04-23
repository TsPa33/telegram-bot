import os

# ================= BASIC =================

BOT_TOKEN = os.getenv("BOT_TOKEN")

ADMIN_IDS = [6206952389]

# Backward compatibility
ADMINS = ADMIN_IDS


# ================= DATABASE =================

DATABASE_URL = os.getenv("DATABASE_URL")


# ================= LIQPAY =================

LIQPAY_PUBLIC_KEY = os.getenv("LIQPAY_PUBLIC_KEY")
LIQPAY_PRIVATE_KEY = os.getenv("LIQPAY_PRIVATE_KEY")
LIQPAY_CALLBACK_URL = os.getenv("LIQPAY_CALLBACK_URL")


# ================= UI / DEFAULTS =================

# 🔥 Заглушка логотипа (використовується якщо сайт не має лого)
DEFAULT_LOGO = "https://i.ibb.co/6yJ0p9C/carpot.png"
