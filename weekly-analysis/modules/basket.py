"""
Section 2: Basket Size — avg revenue per order by store, WoW.
"""
import pandas as pd
from modules.utils import fmt_rub, wow_arrow, md_table, section


def _basket_stats(txn):
    """Compute avg basket size per store from transaction rows."""
    return (
        txn[~txn["is_return"]]
        .groupby(["store_name", "order_number"])["revenue"]
        .sum()
        .reset_index()
        .groupby("store_name")
        .agg(avg_basket=("revenue", "mean"), orders=("order_number", "count"))
        .reset_index()
        .rename(columns={"store_name": "store"})
    )


def build(current_txn, prior_txn):
    parts = [section("2. Basket Size", 2)]

    cur = _basket_stats(current_txn)
    pri = _basket_stats(prior_txn).rename(columns={"avg_basket": "prior_basket", "orders": "prior_orders"})

    merged = cur.merge(pri[["store", "prior_basket"]], on="store", how="outer").fillna(0)
    merged["wow"] = merged.apply(lambda r: wow_arrow(r["avg_basket"], r["prior_basket"]), axis=1)
    merged = merged.sort_values("avg_basket", ascending=False)

    # Overall
    cur_overall  = current_txn[~current_txn["is_return"]].groupby("order_number")["revenue"].sum().mean()
    pri_overall  = prior_txn[~prior_txn["is_return"]].groupby("order_number")["revenue"].sum().mean()
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
