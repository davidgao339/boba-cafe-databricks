"""
SBIS API client with authentication and retry logic.
"""
import requests
import time
from datetime import datetime
from pipeline.config import AUTH_URL, POINTS_URL, ORDERS_URL, APP_CLIENT_ID, LOGIN, PASSWORD


def authenticate(app_client_id=None, login=None, password=None):
    """Authenticate with SBIS and return session ID."""
    resp = requests.post(
        AUTH_URL,
        json={
            "app_client_id": app_client_id or APP_CLIENT_ID,
            "login": login or LOGIN,
            "password": password or PASSWORD,
        },
        headers={"Content-Type": "application/json; charset=utf-8"},
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()

    sid = data.get("sid") or data.get("access_token") or data.get("token")
    if not sid:
        raise ValueError(f"Auth failed — no session token in response: {data}")

    print(f"Authenticated (sid: {sid[:16]}...)")
    return sid


def get_sales_points(sid):
    """Fetch all sales points."""
    headers = {"X-SBISSessionID": sid, "Accept": "application/json"}
    resp = requests.get(POINTS_URL, headers=headers, timeout=30)
    resp.raise_for_status()
    points = resp.json().get("salesPoints", [])
    print(f"Found {len(points)} sales points")
    return points


def _request_with_retry(url, headers, params, max_retries=3):
    """GET request with exponential backoff retry."""
    for attempt in range(max_retries):
        try:
            r = requests.get(url, headers=headers, params=params, timeout=60)
            r.raise_for_status()
            return r.json() or {}
        except requests.exceptions.RequestException as e:
            if attempt == max_retries - 1:
                raise
            wait = 2 ** attempt
            print(f"  Retry {attempt + 1}/{max_retries} after {wait}s — {e}")
            time.sleep(wait)


def _fmt(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%d %H:%M:%S")


def _nz(value):
    return 0.0 if value is None else float(value)


def fetch_orders(sid, points, start_dt, end_dt):
    """
    Fetch raw order data from SBIS for the given date range.
    Returns a list of dicts (one per line item / topping).
    """
    from pipeline.config import POS_TO_STORE

    headers = {"X-SBISSessionID": sid, "Accept": "application/json"}
    all_items = []

    for p in points:
        point_id = p["id"]
        default_name = p["name"]
        print(f"  Fetching point {point_id} ({default_name})...")

        page = 0
        while True:
            params = {
                "pointId": point_id,
                "fromDateTime": _fmt(start_dt),
                "toDateTime": _fmt(end_dt),
                "withDetail": "true",
                "page": page,
                "pageSize": 200,
            }

            payload = _request_with_retry(ORDERS_URL, headers, params)
            orders = payload.get("orders") or []
            if not orders:
                break

            for o in orders:
                if o.get("Deleted"):
                    continue

                order_number = o.get("Number")
                raw_cust_name = o.get("CustomerName")
                is_online = "онлайн" in str(raw_cust_name or "").lower()

                payments = o.get("Payments") or []
                if payments:
                    pos_rnm = payments[0].get("KKTNumber") or "Non-Fiscal"
                else:
                    pos_rnm = "Non-Fiscal"

                if pos_rnm in POS_TO_STORE:
                    store_name = POS_TO_STORE[pos_rnm]
                else:
                    store_name = f"UNKNOWN_{pos_rnm[-4:]}"

                # Determine transaction type
                txn_type = "Unknown"
                if payments:
                    p0 = payments[0]
                    bank = _nz(p0.get("BankSum") or p0.get("PayBank"))
                    cash = _nz(p0.get("CashSum") or p0.get("PayCash"))
                    if is_online:
                        txn_type = "Online"
                    elif bank > 0 and cash > 0:
                        txn_type = "Mixed"
                    elif bank > 0:
                        txn_type = "Card"
                    elif cash > 0:
                        txn_type = "Cash"
                    elif p0.get("Nonfiscal"):
                        txn_type = "Non-Fiscal"
                elif is_online:
                    txn_type = "Online"

                items = o.get("SaleNomenclatures") or []
                if not items:
                    continue

                for item in items:
                    qty = _nz(item.get("Quantity"))
                    price = _nz(item.get("CatalogPrice"))
                    discount = _nz(item.get("CheckDiscount")) or _nz(item.get("TotalDiscount"))
                    gross = price * qty
                    net_revenue = gross - discount

                    base = {
                        "datetime": o.get("DateWTZ"),
                        "order_number": order_number,
                        "store_name": store_name,
                        "rnm": pos_rnm,
                        "transaction_type": txn_type,
                        "customer_name": raw_cust_name,
                        "online": is_online,
                        "product": item.get("Name"),
                        "is_return": bool(o.get("Return")),
                        "is_topping": False,
                        "qty_raw": qty,
                        "revenue_raw": net_revenue,
                        "discount_amount": discount,
                    }
                    all_items.append(base)

                    # Toppings (modifiers with price > 0)
                    for pos in item.get("Positions") or []:
                        if _nz(pos.get("CatalogPrice")) > 0 and pos.get("IsModifier"):
                            t_qty = _nz(pos.get("Quantity"))
                            t_disc = _nz(pos.get("CheckDiscount")) or _nz(pos.get("TotalDiscount"))
                            t_net = (_nz(pos.get("CatalogPrice")) * t_qty) - t_disc

                            all_items.append({
                                **base,
                                "product": pos.get("Name"),
                                "is_topping": True,
                                "qty_raw": t_qty,
                                "revenue_raw": t_net,
                                "discount_amount": t_disc,
                            })

            if not (payload.get("outcome") or {}).get("hasMore"):
                break
            page += 1

    print(f"  Fetched {len(all_items):,} line items total")
    return all_items
