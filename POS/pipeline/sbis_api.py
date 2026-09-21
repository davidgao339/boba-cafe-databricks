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
    from datetime import timedelta
    import concurrent.futures

    headers = {"X-SBISSessionID": sid, "Accept": "application/json"}
    all_items = []
    
    def process_point(p):
        point_id = p["id"]
        default_name = p["name"]
        print(f"  [START] Fetching point {point_id} ({default_name})...")
        
        point_items = []
        intervals = [(start_dt, end_dt)]
        seen_order_keys = set()
        
        while intervals:
            cur_start, cur_end = intervals.pop(0)

            if (cur_end - cur_start).total_seconds() < 1:
                print(f"    WARNING: Interval {cur_start} - {cur_end} too small on point {point_id}, skipping.")
                continue

            params = {
                "pointId": point_id,
                "fromDateTime": _fmt(cur_start),
                "toDateTime": _fmt(cur_end),
                "withDetail": "true",
                "pageSize": 100,
            }

            payload = _request_with_retry(ORDERS_URL, headers, params)
            orders = payload.get("orders") or []
            has_more = (payload.get("outcome") or {}).get("hasMore")

            if has_more and len(orders) >= 100:
                mid_point = cur_start + (cur_end - cur_start) / 2
                intervals.insert(0, (mid_point, cur_end))
                intervals.insert(0, (cur_start, mid_point))
                continue

            if not orders:
                continue

            for o in orders:
                if o.get("Deleted"):
                    continue

                order_key = o.get("Key")
                if order_key in seen_order_keys:
                    continue
                seen_order_keys.add(order_key)

                order_number = o.get("Number")
                raw_cust_name = o.get("CustomerName")
                is_online = "онлайн" in str(raw_cust_name or "").lower()

                payments = o.get("Payments") or []
                pos_rnm = payments[0].get("KKTNumber") or "Non-Fiscal" if payments else "Non-Fiscal"
                store_name = POS_TO_STORE.get(pos_rnm, f"UNKNOWN_{pos_rnm[-4:]}")

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
                else:
                    txn_type = "Non-Fiscal"

                items = o.get("SaleNomenclatures") or []
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
                    point_items.append(base)

                    for pos in item.get("Positions") or []:
                        if pos.get("IsModifier"):
                            t_qty = _nz(pos.get("Quantity"))
                            t_disc = _nz(pos.get("CheckDiscount")) or _nz(pos.get("TotalDiscount"))
                            t_net = (_nz(pos.get("CatalogPrice")) * t_qty) - t_disc

                            point_items.append({
                                **base,
                                "product": pos.get("Name"),
                                "is_topping": True,
                                "qty_raw": t_qty,
                                "revenue_raw": t_net,
                                "discount_amount": t_disc,
                            })
                            
        print(f"  [DONE] Point {point_id} ({default_name}) -> {len(point_items)} items")
        return point_items

    # Fetch points in parallel (10 workers to speed up the time slicing overhead)
    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
        futures = [executor.submit(process_point, p) for p in points]
        for future in concurrent.futures.as_completed(futures):
            all_items.extend(future.result())

    print(f"  Fetched {len(all_items):,} line items total")
    return all_items
