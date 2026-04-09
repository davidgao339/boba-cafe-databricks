"""
Shared configuration for the SBIS pipeline.
Credentials loaded from Databricks secrets, with env var fallback for local dev.
"""
import os

# --- API Endpoints ---
AUTH_URL = "https://api.sbis.ru/oauth/service/"
POINTS_URL = "https://api.sbis.ru/retail/point/list"
ORDERS_URL = "https://api.sbis.ru/retail/order/list"

# --- Credentials ---
try:
    # Databricks environment
    APP_CLIENT_ID = dbutils.secrets.get("boba-cafe", "SBIS_APP_CLIENT_ID")  # noqa: F821
    LOGIN = dbutils.secrets.get("boba-cafe", "SBIS_LOGIN")  # noqa: F821
    PASSWORD = dbutils.secrets.get("boba-cafe", "SBIS_PASSWORD")  # noqa: F821
except Exception:
    # Local fallback
    APP_CLIENT_ID = os.getenv("SBIS_APP_CLIENT_ID", "")
    LOGIN = os.getenv("SBIS_LOGIN", "")
    PASSWORD = os.getenv("SBIS_PASSWORD", "")

# --- POS Terminal → Store Name Mapping ---
POS_TO_STORE = {
    "7385440900109131": "ВОЛОДЯ",
    "7381440800707469": "ГАЛЕРЕЯ",
    "7385440800017777": "КПК",
    "7385440900064685": "ОЗМОЛЛ",
    "7385440800017708": "ЧЕРНОМОРСКИЙ",
    "7385440900076636": "БОН ПАССАЖ",
    "7385440900087819": "СОВЕТОВ",
    "7385440900108974": "ГРИН ПАРК",
    "7385440900083511": "НОВО КП",
}

# --- Delta Table Names ---
TRANSACTIONS_TABLE = "workspace.default.transactions"
DAILY_SALES_TABLE = "workspace.default.daily_sales"
PRODUCT_SALES_TABLE = "workspace.default.product_sales"
