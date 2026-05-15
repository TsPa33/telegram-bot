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


# ================= SELLER CRM =================

SELLER_CRM_BASE_URL = os.getenv("SELLER_CRM_BASE_URL", "https://crm.carpot.com.ua")
SELLER_CRM_MONTHLY_PRICE_UAH = int(os.getenv("SELLER_CRM_MONTHLY_PRICE_UAH", "99"))
