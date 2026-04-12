"""
Section 3: Product Health — category distribution, per-product sales, WoW.
Uses products_mapped.csv for hierarchy. Strips variant suffixes before joining.
"""
import re
import pandas as pd
from modules.utils import fmt_rub, fmt_pct, wow_arrow, md_table, section

# Suffixes that mark a variant of the base product (strip before lookup)
_VARIANT_SUFFIXES = re.compile(
    r"\s*\(шарики не включены\)"
    r"|\s*\(без шариков\)"
    r"|\s*\(no balls\)",
    flags=re.IGNORECASE,
)

# Products to exclude from health reporting entirely
_EXCLUDE_PREFIXES = ("списание", "у меня нет тапиоки")
_ZERO_REV_MODIFIERS = {
    "без соуса", "без топпинга", "без шариков", "кетчуп 30гр",
    "менее сладкий", "со льдом", "соус кетчуп", "соус сырный",
    "соус сырный 30гр", "стандартный", "теплый", "холодный меньше льда",
}


def _clean_product_name(name):
    """Strip variant suffixes to get the canonical lookup name."""
    if not isinstance(name, str):
        return name
    return _VARIANT_SUFFIXES.sub("", name).strip()


def _should_exclude(name):
    """Return True for write-offs and zero-revenue modifiers."""
    if not isinstance(name, str):
        return False
    low = name.lower().strip()
    if any(low.startswith(p) for p in _EXCLUDE_PREFIXES):
        return True
    if low in _ZERO_REV_MODIFIERS:
        return True
    return False


def _enrich(txn, hierarchy):
    """Join transactions with product hierarchy, stripping variant suffixes."""
    df = txn.copy()
    df = df[~df["product"].apply(_should_exclude)]

    # Create a lookup key by stripping suffixes
    df["product_lookup"] = df["product"].apply(_clean_product_name)

    if hierarchy.empty:
        df["category"]    = "Uncategorised"
        df["subcategory"] = "Uncategorised"
        df["product_en"]  = df["product_lookup"]
        df["variant"]     = ""
    else:
        df = df.merge(
            hierarchy[["product", "category", "subcategory", "product_en", "variant"]],
            left_on="product_lookup", right_on="product",
            how="left", suffixes=("", "_hier")
        )
        df["category"]    = df["category"].fillna("Uncategorised")
        df["subcategory"] = df["subcategory"].fillna("Uncategorised")
        df["product_en"]  = df["product_en"].fillna(df["product_lookup"])
        df["variant"]     = df["variant"].fillna("")

        # Mark variant rows (original name ≠ lookup name)
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
    total_revenue = prod["revenue"].sum()
    prod["share"] = prod["revenue"] / total_revenue * 100 if total_revenue > 0 else 0
    prod = prod.sort_values(["category", "share"], ascending=[True, False])

    parts.append(md_table(
        prod[["category", "subcategory", "product_en", "qty", "revenue", "share", "wow"]],
        formatters={
            "revenue": fmt_rub,
            "share":   fmt_pct,
            "qty":     lambda x: f"{int(x):,}",
        }
    ))

    return "\n".join(parts)
