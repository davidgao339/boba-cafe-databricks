"""
Section 3: Product Health — category/subcategory distribution, per-product sales
           grouped by subcategory (featured first), and add-on / topping dynamics.
"""
import re
import pandas as pd
from modules.utils import fmt_rub, fmt_pct, fmt_diff_rub, pct_arrow, md_table, section

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
    # Normalize multiple spaces into single space and strip variant suffixes
    cleaned = re.sub(r"\s+", " ", name)
    cleaned = _VARIANT_SUFFIXES.sub("", cleaned).strip()
    return cleaned


def _should_exclude(name):
    if not isinstance(name, str):
        return False
    low = re.sub(r"\s+", " ", name).lower().strip()
    if any(low.startswith(p) or p in low for p in _EXCLUDE_PREFIXES):
        return True
    if low in _ZERO_REV_MODIFIERS:
        return True
    return False


def _heuristic_fallback(product_name):
    """Fallback classification for products missing in hierarchy Google Sheet."""
    low = product_name.lower()

    # Toppings & Add-ons
    if any(k in low for k in ["тапиок", "джус болл", "топпинг", "пенк", "желе", "сироп", "молоко", "кусочк", "добавк"]):
        return "Toppings & Modifiers", "Add-ons", product_name

    # Drinks
    if any(k in low for k in ["чай", "ти", "лимонад", "коктейль", "кофе", "латте", "раф", "капучино", "бамбл", "фраппучино", "мокка", "американо"]):
        return "Drink", "Other Drinks", product_name

    # Food
    if any(k in low for k in ["блинчик", "корн дог", "корн-дог", "сосис", "сыр", "сендвич"]):
        return "Food", "Snacks", product_name

    # Dessert
    if any(k in low for k in ["моти", "печень", "чизкейк", "торт", "макарон"]):
        return "Dessert", "Sweets", product_name

    return "Other", "Miscellaneous", product_name


def _enrich(txn, hierarchy):
    df = txn.copy()
    df = df[~df["product"].apply(_should_exclude)]
    df["product_lookup"] = df["product"].apply(_clean_product_name)

    if hierarchy.empty:
        df[["category", "subcategory", "product_en"]] = df["product_lookup"].apply(
            lambda n: pd.Series(_heuristic_fallback(n))
        )
        df["variant"]  = ""
        df["featured"] = 0
    else:
        # Match normalized names in hierarchy as well
        hier_clean = hierarchy.copy()
        hier_clean["product_clean"] = hier_clean["product"].apply(_clean_product_name)

        df = df.merge(
            hier_clean[["product_clean", "category", "subcategory", "product_en", "variant", "featured"]],
            left_on="product_lookup", right_on="product_clean",
            how="left", suffixes=("", "_hier")
        )

        # Apply heuristic fallback for any unmapped rows
        unmapped_mask = df["category"].isna() | (df["category"] == "Uncategorised")
        if unmapped_mask.any():
            fallback_res = df.loc[unmapped_mask, "product_lookup"].apply(
                lambda n: pd.Series(_heuristic_fallback(n))
            )
            df.loc[unmapped_mask, "category"] = fallback_res[0]
            df.loc[unmapped_mask, "subcategory"] = fallback_res[1]
            df.loc[unmapped_mask, "product_en"] = fallback_res[2]

        df["variant"]  = df["variant"].fillna("")
        df["featured"] = df["featured"].fillna(0).astype(int)

        is_variant = df["product"] != df["product_lookup"]
        df.loc[is_variant & (df["variant"] == ""), "variant"] = "no balls"

    # Combined display name: "Русское название / English Name"
    df["product_display"] = df.apply(
        lambda r: f"{r['product_lookup']} / {r['product_en']}"
        if r["product_en"] != r["product_lookup"] else r["product_lookup"],
        axis=1,
    )

    return df


def build(current_txn, prior_txn, hierarchy):
    parts = [section("3. Product Health & Menu Mix", 2)]

    cur = _enrich(current_txn[~current_txn["is_return"]], hierarchy)
    pri = _enrich(prior_txn[~prior_txn["is_return"]], hierarchy)

    # Filter out 0-revenue modifier lines
    cur = cur[cur["revenue"] > 0]
    pri = pri[pri["revenue"] > 0]

    cur_total_rev = cur["revenue"].sum()

    # ── Category Distribution ─────────────────────────────────────
    parts.append(section("Category Distribution", 3))

    cur_cat = cur.groupby("category").agg(revenue=("revenue", "sum"), qty=("qty", "sum")).reset_index()
    pri_cat = pri.groupby("category")["revenue"].sum().reset_index().rename(columns={"revenue": "prior_revenue"})
    cat = cur_cat.merge(pri_cat, on="category", how="outer").fillna(0)
    cat = cat[(cat["revenue"] > 0) | (cat["prior_revenue"] > 0)]
    cat["share"] = cat["revenue"] / cur_total_rev * 100 if cur_total_rev > 0 else 0
    cat["wow"]   = cat.apply(lambda r: pct_arrow(r["revenue"], r["prior_revenue"]), axis=1)
    cat["net_impact"] = cat.apply(lambda r: fmt_diff_rub(r["revenue"], r["prior_revenue"]), axis=1)
    cat = cat.sort_values("revenue", ascending=False)

    parts.append(md_table(
        cat[["category", "revenue", "prior_revenue", "share", "qty", "wow", "net_impact"]],
        formatters={
            "revenue":       fmt_rub,
            "prior_revenue": fmt_rub,
            "share":         fmt_pct,
            "qty":           lambda x: f"{int(x):,}",
        }
    ))

    # ── Subcategory Distribution ──────────────────────────────────
    parts.append(section("Subcategory Distribution", 3))
    parts.append("_Featured products (★) shown as a separate group within each subcategory._\n")

    cur_sub = cur.groupby(["category", "subcategory", "featured"]).agg(revenue=("revenue", "sum"), qty=("qty", "sum")).reset_index()
    pri_sub = pri.groupby(["category", "subcategory", "featured"])["revenue"].sum().reset_index().rename(columns={"revenue": "prior_revenue"})
    sub = cur_sub.merge(pri_sub, on=["category", "subcategory", "featured"], how="outer").fillna(0)
    sub["featured"] = sub["featured"].astype(int)
    sub = sub[(sub["revenue"] > 0) | (sub["prior_revenue"] > 0)]
    sub["share"] = sub["revenue"] / cur_total_rev * 100 if cur_total_rev > 0 else 0
    sub["wow"]   = sub.apply(lambda r: pct_arrow(r["revenue"], r["prior_revenue"]), axis=1)
    sub["net_impact"] = sub.apply(lambda r: fmt_diff_rub(r["revenue"], r["prior_revenue"]), axis=1)
    sub = sub.sort_values(["category", "subcategory", "featured", "revenue"], ascending=[True, True, False, False])
    sub["group"] = sub.apply(lambda r: f"{r['subcategory']} ★" if r["featured"] else r["subcategory"], axis=1)

    parts.append(md_table(
        sub[["category", "group", "revenue", "share", "qty", "wow", "net_impact"]],
        formatters={
            "revenue":    fmt_rub,
            "share":      fmt_pct,
            "qty":        lambda x: f"{int(x):,}",
        }
    ))

    # ── Per-Product Sales ─────────────────────────────────────────
    parts.append(section("Product Sales", 3))
    parts.append("_Grouped by subcategory; featured products (★) listed first within each group._\n")

    cur_prod = (
        cur.groupby(["category", "subcategory", "featured", "product_en", "product_display"])
        .agg(revenue=("revenue", "sum"), qty=("qty", "sum"))
        .reset_index()
    )
    pri_prod = (
        pri.groupby("product_en")["revenue"].sum()
        .reset_index().rename(columns={"revenue": "prior_revenue"})
    )
    prod = cur_prod.merge(pri_prod, on="product_en", how="outer")
    prod["prior_revenue"]    = prod["prior_revenue"].fillna(0)
    prod["revenue"]          = prod["revenue"].fillna(0)
    prod["qty"]              = prod["qty"].fillna(0)
    prod["category"]         = prod["category"].fillna("Other")
    prod["subcategory"]      = prod["subcategory"].fillna("Miscellaneous")
    prod["featured"]         = prod["featured"].fillna(0).astype(int)
    prod["product_display"]  = prod["product_display"].fillna(prod["product_en"])

    # Drop products with no sales in either week
    prod = prod[(prod["revenue"] > 0) | (prod["prior_revenue"] > 0)]

    prod["wow"] = prod.apply(lambda r: pct_arrow(r["revenue"], r["prior_revenue"]), axis=1)
    prod["net_impact"] = prod.apply(lambda r: fmt_diff_rub(r["revenue"], r["prior_revenue"]), axis=1)

    cat_totals = prod.groupby("category")["revenue"].sum().rename("cat_total")
    prod = prod.join(cat_totals, on="category")
    prod["% of cat"] = prod["revenue"] / prod["cat_total"].replace(0, float("nan")) * 100

    # Sort: category → subcategory → featured desc (featured first) → revenue desc
    prod = prod.sort_values(
        ["category", "subcategory", "featured", "revenue"],
        ascending=[True, True, False, False]
    )

    # Build display group label: "Coffee ★" or "Coffee"
    prod["group"] = prod.apply(
        lambda r: f"{r['subcategory']} ★" if r["featured"] else r["subcategory"], axis=1
    )

    parts.append(md_table(
        prod[["category", "group", "product_display", "qty", "revenue", "net_impact", "% of cat", "wow"]],
        formatters={
            "revenue":   fmt_rub,
            "% of cat":  fmt_pct,
            "qty":       lambda x: f"{int(x):,}",
        }
    ))

    # ── Menu Decision Signals & Recommendations ───────────────────
    signals = []
    for _, r in prod.iterrows():
        rev = r["revenue"]
        pri_rev = r["prior_revenue"]
        feat = r["featured"]
        cat_pct = r["% of cat"]
        cat_name = r["category"]
        p_name = r["product_display"]
        subcat = r["subcategory"]
        wow_str = r["wow"]
        net_imp = r["net_impact"]
        
        pct_change = (rev - pri_rev) / pri_rev if pri_rev > 0 else (1.0 if rev > 0 else 0)

        # 1. Promote Candidate
        if feat == 0 and rev >= 5000 and pct_change >= 0.10 and cat_name != "Toppings & Modifiers":
            signals.append({
                "action": "🌟 Promote",
                "product": p_name,
                "category": cat_name,
                "subcategory": subcat,
                "revenue": rev,
                "wow": wow_str,
                "net_impact": net_imp,
                "rationale": f"High organic demand (+{pct_change*100:.0f}% WoW); not currently featured.",
            })
        # 2. Demote / Review
        elif feat == 1 and (pct_change <= -0.15 or rev < 3000):
            signals.append({
                "action": "⚠️ Review / Demote",
                "product": p_name,
                "category": cat_name,
                "subcategory": subcat,
                "revenue": rev,
                "wow": wow_str,
                "net_impact": net_imp,
                "rationale": f"Featured item losing momentum ({pct_change*100:.0f}% WoW); review recipe/marketing.",
            })
        # 3. Cut Candidate
        elif feat == 0 and rev < 2000 and pct_change <= -0.15 and cat_name in ["Drink", "Dessert", "Food"]:
            signals.append({
                "action": "✂️ Cut / Replace",
                "product": p_name,
                "category": cat_name,
                "subcategory": subcat,
                "revenue": rev,
                "wow": wow_str,
                "net_impact": net_imp,
                "rationale": f"Low velocity (<{cat_pct:.1f}% cat share) with persistent drop.",
            })

    if signals:
        parts.append(section("Menu Decision Signals & Rationalization", 3))
        parts.append("_Automated menu recommendations based on product velocity, category share, and growth trajectory._\n")
        
        sig_df = pd.DataFrame(signals).sort_values(
            by=["action", "revenue"], ascending=[True, False]
        )
        parts.append(md_table(
            sig_df[["action", "product", "category", "subcategory", "revenue", "wow", "net_impact", "rationale"]],
            formatters={
                "revenue": fmt_rub,
            }
        ))

    return "\n".join(parts)

