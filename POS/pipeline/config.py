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
    "0008929167049570": "ЧЕРНОМОРСКИЙ",
    "0009764481004270": "БОН ПАССАЖ",
    "0009737172035798": "ГРИН ПАРК",
    "0009768658041311": "СОВЕТОВ",
    "0009737141024036": "НОВО КП",
    "0008929272022685": "КПК",
    "0009703367016085": "КИОСК",
    "0009096403062988": "ГАЛЕРЕЯ",
    "0009336001027180": "ОЗМОЛЛ",
}

# --- Delta Table Names ---
TRANSACTIONS_TABLE = "workspace.default.transactions"
DAILY_SALES_TABLE = "workspace.default.daily_sales"
PRODUCT_SALES_TABLE = "workspace.default.product_sales"
