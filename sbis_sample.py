import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

import requests
import pandas as pd
from datetime import datetime

# ==========================================
# AUTH
# ==========================================
AUTH_URL = "https://api.sbis.ru/oauth/service/"
APP_CLIENT_ID = "1025293145607151"
LOGIN = "Stefania70"
PASSWORD = "Seaimizs4#"
ORDERS_URL = "https://api.sbis.ru/retail/order/list"

resp = requests.post(AUTH_URL, json={
    "app_client_id": APP_CLIENT_ID, "login": LOGIN, "password": PASSWORD,
}, headers={"Content-Type": "application/json; charset=utf-8"}, timeout=30)
data = resp.json()
SID = data["sid"]
print(f"Auth OK: {SID}\n")

headers = {"X-SBISSessionID": SID, "Accept": "application/json"}

# ==========================================
# FETCH ОЗМОЛЛ March 25 with topping extraction
# ==========================================
pos_to_store = {"7385440900064685": "ОЗМОЛЛ"}

def _nz(value):
    return 0.0 if value is None else float(value)

all_items = []
page = 0
while True:
    params = {
        "pointId": 29449,
        "fromDateTime": "2026-03-25 00:00:00",
        "toDateTime": "2026-03-25 23:59:59",
        "withDetail": "true",
        "page": page,
        "pageSize": 200,
    }
    r = requests.get(ORDERS_URL, headers=headers, params=params, timeout=60)
    r.raise_for_status()
    payload = r.json() or {}
    orders = payload.get("orders", []) or []
    if not orders:
        break

    for o in orders:
        if o.get("Deleted") is True:
            continue

        order_number = o.get("Number")
        raw_cust_name = o.get("CustomerName")
        is_online = "онлайн" in str(raw_cust_name or "").lower()

        payments = o.get("Payments", [])
        if payments:
            pos_rnm = payments[0].get("KKTFiscalNumber") or "Non-Fiscal"
        else:
            pos_rnm = "Non-Fiscal"

        mapped_store = pos_to_store.get(pos_rnm, o.get("CompanyName", "ОЗМОЛЛ"))

        txn_type = "Unknown"
        if payments:
            bank_sum = _nz(payments[0].get("BankSum") or payments[0].get("PayBank"))
            cash_sum = _nz(payments[0].get("CashSum") or payments[0].get("PayCash"))
            is_nonfiscal = payments[0].get("Nonfiscal")
            if bank_sum > 0 and cash_sum > 0: txn_type = "Mixed"
            elif bank_sum > 0: txn_type = "Card"
            elif cash_sum > 0: txn_type = "Cash"
            elif is_nonfiscal: txn_type = "Non-Fiscal"

        items = o.get("SaleNomenclatures", [])
        if not items:
            continue

        for item in items:
            qty = _nz(item.get("Quantity"))
            price = _nz(item.get("CatalogPrice"))
            discount_val = _nz(item.get("CheckDiscount"))
            if discount_val == 0:
                discount_val = _nz(item.get("TotalDiscount"))
            gross = price * qty
            net_revenue = gross - discount_val

            all_items.append({
                "datetime": o.get("DateWTZ"),
                "order_number": order_number,
                "store_name": mapped_store,
                "transaction_type": txn_type,
                "product": item.get("Name"),
                "is_return": bool(o.get("Return")),
                "is_topping": False,
                "qty_raw": qty,
                "revenue_raw": net_revenue,
                "discount_amount": discount_val
            })

            # Extract toppings from nested Positions
            for pos in item.get("Positions", []):
                topping_price = _nz(pos.get("CatalogPrice"))
                if topping_price > 0 and pos.get("IsModifier"):
                    topping_qty = _nz(pos.get("Quantity"))
                    topping_discount = _nz(pos.get("CheckDiscount"))
                    if topping_discount == 0:
                        topping_discount = _nz(pos.get("TotalDiscount"))
                    topping_gross = topping_price * topping_qty
                    topping_net = topping_gross - topping_discount

                    all_items.append({
                        "datetime": o.get("DateWTZ"),
                        "order_number": order_number,
                        "store_name": mapped_store,
                        "transaction_type": txn_type,
                        "product": pos.get("Name"),
                        "is_return": bool(o.get("Return")),
                        "is_topping": True,
                        "qty_raw": topping_qty,
                        "revenue_raw": topping_net,
                        "discount_amount": topping_discount
                    })

    if not (payload.get("outcome") or {}).get("hasMore"):
        break
    page += 1

# ==========================================
# BUILD DATAFRAME
# ==========================================
df = pd.DataFrame(all_items)
df["datetime"] = pd.to_datetime(df["datetime"], format='mixed')
df["sign"] = df["is_return"].apply(lambda x: -1 if x else 1)
df["qty"] = df["qty_raw"] * df["sign"]
df["revenue"] = df["revenue_raw"] * df["sign"]

display_df = df[["datetime", "order_number", "product", "is_topping", "qty", "revenue", "transaction_type", "is_return"]].copy()
display_df = display_df.sort_values(["datetime", "order_number", "is_topping"])

pd.set_option('display.max_rows', None)
pd.set_option('display.max_columns', None)
pd.set_option('display.width', 200)
pd.set_option('display.max_colwidth', 50)

print(f"ОЗМОЛЛ - March 25, 2026 - All Transactions")
print(f"{'='*140}")
print(f"Total rows: {len(display_df)} | Products: {len(display_df[~display_df['is_topping']])} | Toppings: {len(display_df[display_df['is_topping']])}")
print(f"{'='*140}\n")
print(display_df.to_string(index=False))

# Summary
print(f"\n{'='*140}")
print(f"SUMMARY")
print(f"{'='*140}")
total_orders = df[~df["is_return"]]["order_number"].nunique()
orders_with_toppings = df[(df["is_topping"]) & (~df["is_return"])]["order_number"].nunique()
total_topping_qty = df[(df["is_topping"]) & (~df["is_return"])]["qty"].sum()
topping_revenue = df[(df["is_topping"]) & (~df["is_return"])]["revenue"].sum()
total_revenue = df[~df["is_return"]]["revenue"].sum()

print(f"Total orders: {total_orders}")
print(f"Orders with toppings: {orders_with_toppings}")
print(f"Attachment rate: {orders_with_toppings/total_orders*100:.1f}%" if total_orders > 0 else "N/A")
print(f"Total topping qty: {int(total_topping_qty)}")
print(f"Topping revenue: {topping_revenue:.0f} RUB")
print(f"Total revenue: {total_revenue:.0f} RUB")
