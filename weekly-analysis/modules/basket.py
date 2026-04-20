"""
Section 2: Basket Size — avg revenue per order by store, WoW, and add-on rate.
"""
import re
import pandas as pd
from modules.utils import fmt_rub, fmt_pct, wow_arrow, md_table, section


EXCLUDED_PAYMENT_TYPES = {"Non-Fiscal"}

_VARIANT_SUFFIXES = re.compile(
    r"\s*\(шарики не включены\)"
    r"|\s*\(без шариков\)"
    r"|\s*\(no balls\)",
    flags=re.IGNORECASE,
)


def _filter(txn):
    """Exclude Non-Fiscal and online orders. Returns are kept so their negative
    revenue nets against the original sale (fully-returned orders drop to zero)."""
    return txn[
        ~txn["online"]
        & ~txn["transaction_type"].isin(EXCLUDED_PAYMENT_TYPES)
    ]


def _basket_stats(txn):
    """Compute net avg basket per store.

    Returns are separate orders with their own order numbers, so netting by
    order_number is not possible. Instead: net_revenue / sale_order_count gives
    the true average — returns reduce the numerator without inflating the denominator.
    """
    filtered = _filter(txn)
    # Sum revenue per order (returns already carry negative revenue)
    order_revenue = (
        filtered.groupby(["store_name", "order_number", "is_return"])["revenue"]
        .sum()
        .reset_index()
    )
    by_store = order_revenue.groupby("store_name").apply(
        lambda g: pd.Series({
            "avg_basket": g["revenue"].sum() / (g["is_return"] == False).sum()
            if (g["is_return"] == False).sum() > 0 else 0,
            "orders": (g["is_return"] == False).sum(),
        })
    ).reset_index().rename(columns={"store_name": "store"})
    return by_store


def _overall_avg(txn):
    """Net avg basket across all stores."""
    filtered = _filter(txn)
    order_revenue = filtered.groupby(["order_number", "is_return"])["revenue"].sum().reset_index()
    total_revenue = order_revenue["revenue"].sum()
    sale_count = (order_revenue["is_return"] == False).sum()
    return total_revenue / sale_count if sale_count > 0 else 0


def _compute_addon_rate(txn, hierarchy):
    """Per-store share of orders that include a drink AND a food/dessert item."""
    df = txn[
        ~txn["is_return"]
        & ~txn["online"]
        & ~txn["transaction_type"].isin(EXCLUDED_PAYMENT_TYPES)
    ].copy()

    if not hierarchy.empty:
        df["product_lookup"] = df["product"].apply(
            lambda n: _VARIANT_SUFFIXES.sub("", n).strip() if isinstance(n, str) else n
        )
        df = df.merge(
            hierarchy[["product", "category"]],
            left_on="product_lookup", right_on="product",
            how="left", suffixes=("", "_hier")
        )
        df["category"] = df["category"].fillna("Uncategorised")
    else:
        df["category"] = "Uncategorised"

    order_cats = (
        df.groupby(["store_name", "order_number"])["category"]
        .agg(set)
        .reset_index()
        .rename(columns={"category": "categories"})
    )
    order_cats["is_addon"] = order_cats["categories"].apply(
        lambda s: ("Drink" in s) and bool(s & {"Food", "Dessert"})
    )
    return (
        order_cats.groupby("store_name")
        .agg(orders=("order_number", "count"), addon_orders=("is_addon", "sum"))
        .reset_index()
        .assign(addon_rate=lambda d: d["addon_orders"] / d["orders"] * 100)
        .rename(columns={"store_name": "store"})
    )


def build(current_txn, prior_txn, hierarchy=None):
    parts = [section("2. Basket Size", 2)]
    parts.append("_Excludes Non-Fiscal and online orders. Returns (separate orders with negative revenue) are netted into the total; only sale orders count toward the denominator._\n")

    cur = _basket_stats(current_txn)
    pri = _basket_stats(prior_txn).rename(columns={"avg_basket": "prior_basket", "orders": "prior_orders"})

    merged = cur.merge(pri[["store", "prior_basket"]], on="store", how="outer").fillna(0)
    merged["wow"] = merged.apply(lambda r: wow_arrow(r["avg_basket"], r["prior_basket"]), axis=1)
    merged = merged.sort_values("avg_basket", ascending=False)

    cur_overall = _overall_avg(current_txn)
    pri_overall = _overall_avg(prior_txn)
    parts.append(
        f"**Avg basket (all stores):** {fmt_rub(cur_overall)}  "
        f"**WoW:** {wow_arrow(cur_overall, pri_overall)}\n"
    )

    parts.append(md_table(
        merged[["store", "avg_basket", "prior_basket", "orders", "wow"]],
        formatters={
            "avg_basket":   fmt_rub,
            "prior_basket": fmt_rub,
        }
    ))

    # ── Add-on Rate ───────────────────────────────────────────────
    if hierarchy is not None and not hierarchy.empty:
        parts.append(section("Add-on Rate", 3))
        parts.append("_Share of in-store orders that include both a drink and a food/dessert item._\n")

        cur_ar = _compute_addon_rate(current_txn, hierarchy)
        pri_ar = _compute_addon_rate(prior_txn, hierarchy).rename(
            columns={"addon_rate": "prior_rate", "orders": "prior_orders", "addon_orders": "prior_addon"}
        )
        ar = cur_ar.merge(pri_ar[["store", "prior_rate", "prior_orders"]], on="store", how="outer").fillna(0)
        ar = ar[(ar["orders"] > 0) | (ar["prior_orders"] > 0)]
        ar["wow"] = ar.apply(lambda r: wow_arrow(r["addon_rate"], r["prior_rate"]), axis=1)
        ar = ar.sort_values("addon_rate", ascending=False)

        parts.append(md_table(
            ar[["store", "orders", "addon_orders", "addon_rate", "wow"]],
            formatters={
                "addon_rate":   fmt_pct,
                "orders":       lambda x: f"{int(x):,}",
                "addon_orders": lambda x: f"{int(x):,}",
            }
        ))

    return "\n".join(parts)
