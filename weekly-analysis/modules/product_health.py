"""
Section 3: Product Health — category/subcategory distribution, per-product sales
           grouped by subcategory (featured first), and extra rate per store.
"""
import re
import pandas as pd
from modules.utils import fmt_rub, fmt_pct, wow_arrow, md_table, section

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
_EXCLUDED_PAYMENT_TYPES = {"Non-Fiscal"}


def _clean_product_name(name):
    if not isinstance(name, str):
        return name
    return _VARIANT_SUFFIXES.sub("", name).strip()


def _should_exclude(name):
    if not isinstance(name, str):
        return False
    low = name.lower().strip()
    if any(low.startswith(p) for p in _EXCLUDE_PREFIXES):
        return True
    if low in _ZERO_REV_MODIFIERS:
        return True
    return False


def _enrich(txn, hierarchy):
    df = txn.copy()
    df = df[~df["product"].apply(_should_exclude)]
    df["product_lookup"] = df["product"].apply(_clean_product_name)

    if hierarchy.empty:
        df["category"]    = "Uncategorised"
        df["subcategory"] = "Uncategorised"
        df["product_en"]  = df["product_lookup"]
        df["variant"]     = ""
        df["featured"]    = 0
    else:
        df = df.merge(
            hierarchy[["product", "category", "subcategory", "product_en", "variant", "featured"]],
            left_on="product_lookup", right_on="product",
            how="left", suffixes=("", "_hier")
        )
        df["category"]    = df["category"].fillna("Uncategorised")
        df["subcategory"] = df["subcategory"].fillna("Uncategorised")
        df["product_en"]  = df["product_en"].fillna(df["product_lookup"])
        df["variant"]     = df["variant"].fillna("")
        df["featured"]    = df["featured"].fillna(0).astype(int)

        is_variant = df["product"] != df["product_lookup"]
        df.loc[is_variant & (df["variant"] == ""), "variant"] = "no balls"

    return df


def build(current_txn, prior_txn, hierarchy):
    parts = [section("3. Product Health", 2)]

    cur = _enrich(current_txn[~current_txn["is_return"]], hierarchy)
    pri = _enrich(prior_txn[~prior_txn["is_return"]], hierarchy)

    # ── Category Distribution ─────────────────────────────────────
    parts.append(section("Category Distribution", 3))

    cur_cat = cur.groupby("category").agg(revenue=("revenue", "sum"), qty=("qty", "sum")).reset_index()
    pri_cat = pri.groupby("category")["revenue"].sum().reset_index().rename(columns={"revenue": "prior_revenue"})
    cat = cur_cat.merge(pri_cat, on="category", how="outer").fillna(0)
    cat = cat[(cat["revenue"] > 0) | (cat["prior_revenue"] > 0)]
    cat["share"] = cat["revenue"] / cat["revenue"].sum() * 100
    cat["wow"]   = cat.apply(lambda r: wow_arrow(r["revenue"], r["prior_revenue"]), axis=1)
    cat = cat.sort_values("revenue", ascending=False)

    parts.append(md_table(
        cat[["category", "revenue", "share", "qty", "wow"]],
        formatters={"revenue": fmt_rub, "share": fmt_pct, "qty": lambda x: f"{int(x):,}"}
    ))

    # ── Subcategory Distribution ──────────────────────────────────
    parts.append(section("Subcategory Distribution", 3))
    parts.append("_Featured products (★) shown as a separate group within each subcategory._\n")

    cur_sub = cur.groupby(["category", "subcategory", "featured"]).agg(revenue=("revenue", "sum"), qty=("qty", "sum")).reset_index()
    pri_sub = pri.groupby(["category", "subcategory", "featured"])["revenue"].sum().reset_index().rename(columns={"revenue": "prior_revenue"})
    sub = cur_sub.merge(pri_sub, on=["category", "subcategory", "featured"], how="outer").fillna(0)
    sub["featured"] = sub["featured"].astype(int)
    sub = sub[(sub["revenue"] > 0) | (sub["prior_revenue"] > 0)]
    sub["share"] = sub["revenue"] / sub["revenue"].sum() * 100
    sub["wow"]   = sub.apply(lambda r: wow_arrow(r["revenue"], r["prior_revenue"]), axis=1)
    sub = sub.sort_values(["category", "subcategory", "featured", "revenue"], ascending=[True, True, False, False])
    sub["group"] = sub.apply(lambda r: f"{r['subcategory']} ★" if r["featured"] else r["subcategory"], axis=1)

    parts.append(md_table(
        sub[["category", "group", "revenue", "share", "qty", "wow"]],
        formatters={"revenue": fmt_rub, "share": fmt_pct, "qty": lambda x: f"{int(x):,}"}
    ))

    # ── Per-Product Sales ─────────────────────────────────────────
    parts.append(section("Product Sales", 3))
    parts.append("_Grouped by subcategory; featured products (★) listed first within each group._\n")

    cur_prod = (
        cur.groupby(["category", "subcategory", "featured", "product_en"])
        .agg(revenue=("revenue", "sum"), qty=("qty", "sum"))
        .reset_index()
    )
    pri_prod = (
        pri.groupby("product_en")["revenue"].sum()
        .reset_index().rename(columns={"revenue": "prior_revenue"})
    )
    prod = cur_prod.merge(pri_prod, on="product_en", how="outer")
    prod["prior_revenue"] = prod["prior_revenue"].fillna(0)
    prod["revenue"]       = prod["revenue"].fillna(0)
    prod["qty"]           = prod["qty"].fillna(0)
    prod["category"]      = prod["category"].fillna("Uncategorised")
    prod["subcategory"]   = prod["subcategory"].fillna("Uncategorised")
    prod["featured"]      = prod["featured"].fillna(0).astype(int)

    # Drop products with no sales in either week
    prod = prod[(prod["revenue"] > 0) | (prod["prior_revenue"] > 0)]

    prod["wow"] = prod.apply(lambda r: wow_arrow(r["revenue"], r["prior_revenue"]), axis=1)

    cat_totals = prod.groupby("category")["revenue"].sum().rename("cat_total")
    prod = prod.join(cat_totals, on="category")
    prod["% of cat"] = prod["revenue"] / prod["cat_total"].replace(0, float("nan")) * 100

    # Sort: category → subcategory → featured desc (featured first) → revenue desc
    prod = prod.sort_values(
        ["category", "subcategory", "featured", "revenue"],
        ascending=[True, True, False, False]
    )

    # Build display group label: "Coffee Featured" or "Coffee"
    prod["group"] = prod.apply(
        lambda r: f"{r['subcategory']} ★" if r["featured"] else r["subcategory"], axis=1
    )

    parts.append(md_table(
        prod[["category", "group", "product_en", "qty", "revenue", "% of cat", "wow"]],
        formatters={
            "revenue":   fmt_rub,
            "% of cat":  fmt_pct,
            "qty":       lambda x: f"{int(x):,}",
        }
    ))

    # ── Extra Rate ────────────────────────────────────────────────
    parts.append(section("Add-on Rate", 3))
    parts.append("_Share of in-store orders containing both a drink and a food/dessert item. Excludes online and Non-Fiscal._\n")

    def _compute_extra_rate(txn):
        df = _enrich(txn[~txn["is_return"]], hierarchy)
        df = df[~df["online"] & ~df["transaction_type"].isin(_EXCLUDED_PAYMENT_TYPES)]
        order_cats = (
            df.groupby(["store_name", "order_number"])["category"]
            .agg(set)
            .reset_index()
            .rename(columns={"category": "categories"})
        )
        order_cats["has_drink"] = order_cats["categories"].apply(lambda s: "Drink" in s)
        order_cats["has_extra"] = order_cats["categories"].apply(lambda s: bool(s & {"Food", "Dessert"}))
        order_cats["is_combo"]  = order_cats["has_drink"] & order_cats["has_extra"]
        return (
            order_cats.groupby("store_name")
            .agg(orders=("order_number", "count"), combo_orders=("is_combo", "sum"))
            .reset_index()
            .assign(extra_rate=lambda d: d["combo_orders"] / d["orders"] * 100)
            .rename(columns={"store_name": "store"})
        )

    cur_er = _compute_extra_rate(current_txn)
    pri_er = _compute_extra_rate(prior_txn).rename(columns={
        "extra_rate": "prior_rate", "orders": "prior_orders", "combo_orders": "prior_combo"
    })
    er = cur_er.merge(pri_er[["store", "prior_rate", "prior_orders"]], on="store", how="outer").fillna(0)
    # Show only stores with orders in at least one week
    er = er[(er["orders"] > 0) | (er["prior_orders"] > 0)]
    er["wow"] = er.apply(lambda r: wow_arrow(r["extra_rate"], r["prior_rate"]), axis=1)
    er = er.sort_values("extra_rate", ascending=False)

    parts.append(md_table(
        er[["store", "orders", "combo_orders", "extra_rate", "wow"]],
        formatters={
            "extra_rate":   fmt_pct,
            "orders":       lambda x: f"{int(x):,}",
            "combo_orders": lambda x: f"{int(x):,}",
        }
    ))

    return "\n".join(parts)
