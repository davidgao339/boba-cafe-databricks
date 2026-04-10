"""
Shared configuration for the SBIS pipeline.
Credentials imported from secrets.py (gitignored).
"""

# --- SBIS API Endpoints ---
AUTH_URL = "https://api.sbis.ru/oauth/service/"
POINTS_URL = "https://api.sbis.ru/retail/point/list"
ORDERS_URL = "https://api.sbis.ru/retail/order/list"

# --- SBIS Credentials (from secrets.py) ---
from pipeline.secrets import APP_CLIENT_ID, LOGIN, PASSWORD

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
