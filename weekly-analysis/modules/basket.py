"""
Section 2: Basket Size — avg revenue per order by store, WoW.
"""
import pandas as pd
from modules.utils import fmt_rub, wow_arrow, md_table, section


EXCLUDED_PAYMENT_TYPES = {"Non-Fiscal"}


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


def build(current_txn, prior_txn):
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

    return "\n".join(parts)
