"""
Section 2: Basket & Attach Intelligence — Average check size, multi-tier attach rates
           (Food/Dessert attach, Topping attach, Multi-Drink %), and Upsell Opportunity Gap.
"""
import re
import numpy as np
import pandas as pd
from modules.utils import fmt_rub, fmt_pct, fmt_diff_rub, pct_arrow, md_table, section

EXCLUDED_PAYMENT_TYPES = {"Non-Fiscal"}

_VARIANT_SUFFIXES = re.compile(
    r"\s*\(шарики не включены\)"
    r"|\s*\(без шариков\)"
    r"|\s*\(no balls\)",
    flags=re.IGNORECASE,
)
_EXCLUDE_PREFIXES = ("списание", "у меня нет тапиоки")
_ZERO_REV_MODIFIERS = {
    "без соуса", "без топпинга", "без шариков", "кетчуп 30гр",
    "менее сладкий", "со льдом", "соус кетчуп", "соус сырный",
    "соус сырный 30гр", "стандартный", "теплый", "холодный меньше льда",
}


def _clean_product_name(name):
    if not isinstance(name, str):
        return name
    cleaned = re.sub(r"\s+", " ", name)
    return _VARIANT_SUFFIXES.sub("", cleaned).strip()


def _should_exclude(name):
    if not isinstance(name, str):
        return False
    low = re.sub(r"\s+", " ", name).lower().strip()
    if any(low.startswith(p) or p in low for p in _EXCLUDE_PREFIXES):
        return True
    if low in _ZERO_REV_MODIFIERS:
        return True
    return False


def _heuristic_category(name):
    low = str(name).lower()
    if any(k in low for k in ["тапиок", "джус болл", "топпинг", "пенк", "желе", "сироп", "молоко", "кусочк"]):
        return "Toppings & Modifiers"
    if any(k in low for k in ["чай", "ти", "лимонад", "коктейль", "кофе", "латте", "раф", "капучино", "бамбл", "фраппучино", "мокка", "американо"]):
        return "Drink"
    if any(k in low for k in ["блинчик", "корн дог", "корн-дог", "сосис", "сыр"]):
        return "Food"
    if any(k in low for k in ["моти", "печень", "чизкейк", "торт"]):
        return "Dessert"
    return "Other"


def _filter_valid_orders(txn):
    """Exclude non-fiscal and online orders."""
    if txn is None or txn.empty:
        return pd.DataFrame()
    df = txn.copy()
    if "online" in df.columns:
        df = df[~df["online"]]
    if "transaction_type" in df.columns:
        df = df[~df["transaction_type"].isin(EXCLUDED_PAYMENT_TYPES)]
    return df


def _basket_stats(txn):
    """Compute net avg basket per store."""
    filtered = _filter_valid_orders(txn)
    if filtered.empty or "order_number" not in filtered.columns:
        return pd.DataFrame()

    store_col = "store_name" if "store_name" in filtered.columns else "store"
    
    non_returns = filtered[filtered["is_return"] == False]
    orders_per_store = non_returns.groupby(store_col)["order_number"].nunique().rename("orders")
    rev_per_store = filtered.groupby(store_col)["revenue"].sum().rename("revenue")
    
    stats = pd.concat([orders_per_store, rev_per_store], axis=1).fillna(0).reset_index().rename(columns={store_col: "store"})
    stats["avg_basket"] = stats.apply(lambda r: r["revenue"] / r["orders"] if r["orders"] > 0 else 0, axis=1)
    return stats


def _overall_avg(txn):
    """Net avg basket across all stores."""
    filtered = _filter_valid_orders(txn)
    if filtered.empty or "order_number" not in filtered.columns:
        return 0
    non_returns = filtered[filtered["is_return"] == False]
    orders = non_returns["order_number"].nunique()
    rev = filtered["revenue"].sum()
    return rev / orders if orders > 0 else 0


def _compute_attach_matrix(txn, hierarchy):
    """Computes Food/Dessert attach, Topping attach, and multi-drink rates per store."""
    df = _filter_valid_orders(txn)
    if df.empty or "order_number" not in df.columns:
        return pd.DataFrame(), 0, 0

    df = df[~df["is_return"]].copy()
    df = df[~df["product"].apply(_should_exclude)]
    df["product_clean"] = df["product"].apply(_clean_product_name)

    if hierarchy is not None and not hierarchy.empty:
        hier_clean = hierarchy.copy()
        hier_clean["product_clean"] = hier_clean["product"].apply(_clean_product_name)
        df = df.merge(
            hier_clean[["product_clean", "category"]],
            on="product_clean", how="left"
        )
        df["category"] = df.apply(
            lambda r: r["category"] if pd.notna(r["category"]) and r["category"] != "Uncategorised"
            else _heuristic_category(r["product_clean"]),
            axis=1
        )
    else:
        df["category"] = df["product_clean"].apply(_heuristic_category)

    store_col = "store_name" if "store_name" in df.columns else "store"

    df["is_drink"] = df["category"] == "Drink"
    df["is_food_dessert"] = df["category"].isin(["Food", "Dessert"])
    df["is_topping"] = df["category"] == "Toppings & Modifiers"
    df["item_qty"] = df["qty"] if "qty" in df.columns else 1
    df["drink_qty"] = np.where(df["is_drink"], df["item_qty"], 0)
    df["food_rev"] = np.where(df["is_food_dessert"], df["revenue"], 0)
    df["food_qty"] = np.where(df["is_food_dessert"], df["item_qty"], 0)

    # Per-order category profile
    order_profile = df.groupby([store_col, "order_number"]).agg(
        has_drink=("is_drink", "max"),
        drink_qty=("drink_qty", "sum"),
        has_food_dessert=("is_food_dessert", "max"),
        has_topping=("is_topping", "max"),
        food_rev=("food_rev", "sum"),
        food_qty=("food_qty", "sum"),
    ).reset_index()

    # Calculate average food item price across network for opportunity gap calculation
    tot_food_rev = order_profile["food_rev"].sum()
    tot_food_qty = order_profile["food_qty"].sum()
    avg_food_price = tot_food_rev / tot_food_qty if tot_food_qty > 0 else 180.0

    drink_orders = order_profile[order_profile["has_drink"] == True].copy()
    if drink_orders.empty:
        return pd.DataFrame(), 0, avg_food_price

    drink_orders["has_food_attach"] = drink_orders["has_drink"] & drink_orders["has_food_dessert"]
    drink_orders["has_topping_attach"] = drink_orders["has_drink"] & drink_orders["has_topping"]
    drink_orders["is_multi_drink"] = drink_orders["drink_qty"] >= 2

    # Store attach aggregation
    store_attach = drink_orders.groupby(store_col).agg(
        drink_orders=("order_number", "count"),
        food_attach_orders=("has_food_attach", "sum"),
        topping_attach_orders=("has_topping_attach", "sum"),
        multi_drink_orders=("is_multi_drink", "sum"),
    ).reset_index().rename(columns={store_col: "store"})

    store_attach["food_attach_pct"] = store_attach.apply(
        lambda r: r["food_attach_orders"] / r["drink_orders"] * 100 if r["drink_orders"] > 0 else 0, axis=1
    )
    store_attach["topping_attach_pct"] = store_attach.apply(
        lambda r: r["topping_attach_orders"] / r["drink_orders"] * 100 if r["drink_orders"] > 0 else 0, axis=1
    )
    store_attach["multi_drink_pct"] = store_attach.apply(
        lambda r: r["multi_drink_orders"] / r["drink_orders"] * 100 if r["drink_orders"] > 0 else 0, axis=1
    )

    # Calculate Top-Quartile Food Attach Benchmark (75th percentile of active stores)
    active_stores = store_attach[store_attach["drink_orders"] >= 30]
    benchmark_food_attach = active_stores["food_attach_pct"].quantile(0.75) if len(active_stores) >= 2 else (
        store_attach["food_attach_pct"].max() if not store_attach.empty else 25.0
    )

    store_attach["food_benchmark"] = benchmark_food_attach
    store_attach["upsell_gap_rub"] = store_attach.apply(
        lambda r: max(0, (benchmark_food_attach - r["food_attach_pct"]) / 100.0 * r["drink_orders"] * avg_food_price),
        axis=1
    )

    return store_attach, benchmark_food_attach, avg_food_price


def build(current_txn, prior_txn, hierarchy=None):
    parts = [section("2. Basket Size & Attach Intelligence", 2)]
    parts.append("_Excludes Non-Fiscal and online orders. Returns net into revenue numerator without inflating order count._\n")

    # ── 2.1 Average Basket by Store ────────────────────────────────
    cur = _basket_stats(current_txn)
    pri = _basket_stats(prior_txn).rename(columns={"avg_basket": "prior_basket", "orders": "prior_orders"})

    merged = cur.merge(pri[["store", "prior_basket", "prior_orders"]], on="store", how="outer").fillna(0)
    merged = merged[
        ~(merged["store"].str.startswith("UNKNOWN_") & (merged["orders"] == 0) & (merged["prior_orders"] == 0))
    ].copy()

    merged["wow"] = merged.apply(lambda r: pct_arrow(r["avg_basket"], r["prior_basket"]), axis=1)
    merged["net_diff"] = merged.apply(lambda r: fmt_diff_rub(r["avg_basket"], r["prior_basket"]), axis=1)
    merged = merged.sort_values("avg_basket", ascending=False)

    cur_overall = _overall_avg(current_txn)
    pri_overall = _overall_avg(prior_txn)
    parts.append(
        f"**Chain-Wide Avg Basket:** {fmt_rub(cur_overall)}  "
        f"**WoW:** {pct_arrow(cur_overall, pri_overall)} ({fmt_diff_rub(cur_overall, pri_overall)})\n"
    )

    parts.append(md_table(
        merged[["store", "avg_basket", "prior_basket", "orders", "wow", "net_diff"]].rename(
            columns={"net_diff": "net_change"}
        ),
        formatters={
            "avg_basket":   fmt_rub,
            "prior_basket": fmt_rub,
            "orders":       lambda x: f"{int(x):,}",
        }
    ))

    # ── 2.2 Multi-Tier Attach Intelligence ─────────────────────────
    cur_att, bench_food, avg_price = _compute_attach_matrix(current_txn, hierarchy)
    pri_att, _, _ = _compute_attach_matrix(prior_txn, hierarchy)

    if not cur_att.empty:
        parts.append(section("Attach Rates & Upsell Opportunity Gap", 3))
        parts.append(
            f"_Measures cross-sell effectiveness on drink orders. **Top-Quartile Food Attach Benchmark: {bench_food:.1f}%** "
            f"(Avg food/dessert ticket: {fmt_rub(avg_price)})._\n"
        )

        pri_cols = pri_att[["store", "food_attach_pct", "topping_attach_pct"]].rename(
            columns={
                "food_attach_pct": "pri_food_attach",
                "topping_attach_pct": "pri_topping_attach",
            }
        )
        att_m = cur_att.merge(pri_cols, on="store", how="left").fillna(0)
        att_m = att_m[
            ~(att_m["store"].str.startswith("UNKNOWN_") & (att_m["drink_orders"] == 0))
        ].copy()

        att_m["food_attach_wow"] = att_m.apply(
            lambda r: pct_arrow(r["food_attach_pct"], r["pri_food_attach"]), axis=1
        )
        att_m["topping_attach_wow"] = att_m.apply(
            lambda r: pct_arrow(r["topping_attach_pct"], r["pri_topping_attach"]), axis=1
        )

        def _format_opportunity(gap_rub):
            if gap_rub <= 500:
                return "✓ Top Tier"
            return f"+{fmt_rub(gap_rub)} / wk"

        att_m["opportunity"] = att_m["upsell_gap_rub"].apply(_format_opportunity)
        att_m = att_m.sort_values("drink_orders", ascending=False)

        parts.append(md_table(
            att_m[[
                "store", "drink_orders", "food_attach_pct", "food_attach_wow",
                "topping_attach_pct", "topping_attach_wow", "multi_drink_pct", "opportunity"
            ]].rename(columns={
                "food_attach_pct": "food_attach",
                "topping_attach_pct": "topping_attach",
                "multi_drink_pct": "multi_drink_pct",
                "opportunity": "upsell_opportunity_₽",
            }),
            formatters={
                "drink_orders":    lambda x: f"{int(x):,}",
                "food_attach":     fmt_pct,
                "topping_attach":  fmt_pct,
                "multi_drink_pct": fmt_pct,
            }
        ))

        total_upsell_opp = att_m["upsell_gap_rub"].sum()
        if total_upsell_opp > 1000:
            parts.append(
                f"\n💡 **Network Upsell Opportunity:** **+{fmt_rub(total_upsell_opp)} / week** left on the table across under-attaching stores if brought to the 75th percentile benchmark.\n"
            )

    return "\n".join(parts)

