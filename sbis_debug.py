import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

import requests
import json
from datetime import datetime

# ==========================================
# AUTH
# ==========================================
AUTH_URL = "https://api.sbis.ru/oauth/service/"
APP_CLIENT_ID = "1025293145607151"
LOGIN = "Stefania70"
PASSWORD = "Seaimizs4#"

POINTS_URL = "https://api.sbis.ru/retail/point/list"
ORDERS_URL = "https://api.sbis.ru/retail/order/list"

resp = requests.post(
    AUTH_URL,
    json={
        "app_client_id": APP_CLIENT_ID,
        "login": LOGIN,
        "password": PASSWORD,
    },
    headers={"Content-Type": "application/json; charset=utf-8"},
    timeout=30
)
print("HTTP status:", resp.status_code)
data = resp.json()

if "sid" in data:
    SID = data["sid"]
    print("Auth successful - got sid:", SID)
else:
    print("Auth failed:", data)
    exit(1)

# ==========================================
# FETCH POINTS
# ==========================================
headers = {
    "X-SBISSessionID": SID,
    "Accept": "application/json"
}

resp = requests.get(POINTS_URL, headers=headers, timeout=30)
resp.raise_for_status()
points = resp.json().get("salesPoints", [])
print(f"\nFound {len(points)} sales points")

# ==========================================
# DEBUG: Inspect raw order structure from OZMOLL
# ==========================================
# OZMOLL point ID = 29449
debug_params = {
    "pointId": 29449,
    "fromDateTime": "2026-03-20 00:00:00",
    "toDateTime": "2026-03-26 23:59:59",
    "withDetail": "true",
    "page": 0,
    "pageSize": 50,
}

r = requests.get(ORDERS_URL, headers=headers, params=debug_params, timeout=60)
r.raise_for_status()
debug_payload = r.json()

debug_orders = debug_payload.get("orders", [])
print(f"\nFetched {len(debug_orders)} orders from OZMOLL\n")

if debug_orders:
    o = debug_orders[0]
    print("=== ORDER TOP-LEVEL KEYS ===")
    for k, v in o.items():
        if k not in ("SaleNomenclatures", "Payments"):
            print(f"  {k}: {v}")

    print("\n=== PAYMENTS[0] KEYS ===")
    if o.get("Payments"):
        for k, v in o["Payments"][0].items():
            print(f"  {k}: {v}")

    print("\n=== SaleNomenclatures (all items in first order) ===")
    for i, item in enumerate(o.get("SaleNomenclatures", [])):
        print(f"\n  --- Item {i} ---")
        for k, v in item.items():
            print(f"    {k}: {v}")

    # Skip first 50 detail

# ==========================================
# COLLECT ALL UNIQUE MODIFIER NAMES & PRICES
# ==========================================
print("\n=== COLLECTING ALL UNIQUE MODIFIERS FROM POSITIONS ===")

modifier_set = {}  # name -> set of prices seen

for page in range(0, 10):
    params = {
        "pointId": 29449,
        "fromDateTime": "2026-03-01 00:00:00",
        "toDateTime": "2026-03-26 23:59:59",
        "withDetail": "true",
        "page": page,
        "pageSize": 200,
    }
    r = requests.get(ORDERS_URL, headers=headers, params=params, timeout=60)
    r.raise_for_status()
    orders = r.json().get("orders", []) or []
    if not orders:
        break

    for order in orders:
        if order.get("Deleted"):
            continue
        for item in order.get("SaleNomenclatures", []):
            for pos in item.get("Positions", []):
                name = pos.get("Name", "")
                price = pos.get("CatalogPrice")
                if name not in modifier_set:
                    modifier_set[name] = set()
                modifier_set[name].add(price)

print(f"\nFound {len(modifier_set)} unique modifier names:\n")
print("--- PRICED MODIFIERS (toppings) ---")
for name, prices in sorted(modifier_set.items()):
    non_none = [p for p in prices if p is not None and p > 0]
    if non_none:
        print(f"  {name} | Prices: {non_none}")

print("\n--- FREE MODIFIERS (customizations) ---")
for name, prices in sorted(modifier_set.items()):
    non_none = [p for p in prices if p is not None and p > 0]
    if not non_none:
        print(f"  {name}")
