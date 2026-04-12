"""
Section 3: Product Health — category distribution, per-product sales, WoW.
Uses product_hierarchy.csv if available, falls back to raw product names.
"""
import pandas as pd
from modules.utils import fmt_rub, fmt_pct, wow_arrow, md_table, section


def _enrich(txn, hierarchy):
    """Join transactions with product hierarchy."""
    df = txn.copy()
    if hierarchy.empty:
        df["category"]   = "Uncategorised"
        df["subcategory"] = "Uncategorised"
        df["product_en"] = df["product"]
        df["variant"]    = ""
    else:
        df = df.merge(
            hierarchy[["product", "category", "subcategory", "product_en", "variant"]],
            on="product", how="left"
        )
        df["category"]    = df["category"].fillna("Uncategorised")
        df["subcategory"] = df["subcategory"].fillna("Uncategorised")
        df["product_en"]  = df["product_en"].fillna(df["product"])  # fallback to Russian name
        df["variant"]     = df["variant"].fillna("")
    return df


def build(current_txn, prior_txn, hierarchy):
    parts = [section("3. Product Health", 2)]

    cur = _enrich(current_txn[~current_txn["is_return"]], hierarchy)
    pri = _enrich(prior_txn[~prior_txn["is_return"]], hierarchy)

    # ── Category Distribution ─────────────────────────────────────
    parts.append(section("Category Distribution", 3))

    cur_cat = cur.groupby("category").agg(revenue=("revenue", "sum"), qty=("qty", "sum")).reset_index()
    pri_cat = pri.groupby("category").agg(revenue=("revenue", "sum")).reset_index().rename(columns={"revenue": "prior_revenue"})
    cat = cur_cat.merge(pri_cat, on="category", how="outer").fillna(0)
    cat["share"] = cat["revenue"] / cat["revenue"].sum() * 100
    cat["wow"]   = cat.apply(lambda r: wow_arrow(r["revenue"], r["prior_revenue"]), axis=1)
    cat = cat.sort_values("revenue", ascending=False)

    parts.append(md_table(
        cat[["category", "revenue", "share", "qty", "wow"]],
        formatters={"revenue": fmt_rub, "share": fmt_pct, "qty": lambda x: f"{int(x):,}"}
    ))

    # ── Per-Product Sales ─────────────────────────────────────────
    parts.append(section("Product Sales", 3))

    cur_prod = (
        cur.groupby(["category", "subcategory", "product_en"])
        .agg(revenue=("revenue", "sum"), qty=("qty", "sum"))
        .reset_index()
    )
    pri_prod = (
        pri.groupby("product_en")["revenue"].sum()
        .reset_index().rename(columns={"revenue": "prior_revenue"})
    )
    prod = cur_prod.merge(pri_prod, on="product_en", how="outer").fillna(0)
    prod["wow"] = prod.apply(lambda r: wow_arrow(r["revenue"], r["prior_revenue"]), axis=1)
    prod = prod.sort_values(["category", "subcategory", "revenue"], ascending=[True, True, False])

    parts.append(md_table(
        prod[["category", "subcategory", "product_en", "qty", "revenue", "wow"]],
        formatters={
            "revenue": fmt_rub,
            "qty":     lambda x: f"{int(x):,}",
        }
    ))

    return "\n".join(parts)
