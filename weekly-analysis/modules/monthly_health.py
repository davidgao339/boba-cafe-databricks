"""
Monthly Product Health analysis.

Produces a full markdown report covering:
  1. Month Summary
  2. Category Overview
  3. Subcategory Overview  (featured ★ split)
  4. Product Performance   (featured-first, weekly avg, MoM, % of subcat)
  5. Decision Signals      (promote / demote / cut candidates)

Decision thresholds (all overridable via cfg dict):
  PROMOTE_MIN_REV     minimum monthly revenue to be a promote candidate  (default 5 000)
  PROMOTE_REL_SUBCAT  min revenue as fraction of subcat featured avg      (default 0.50)
  DEMOTE_REL_SUBCAT   revenue ≤ this fraction of subcat avg → demote flag (default 0.50)
  DEMOTE_MOM_PCT      MoM decline beyond this triggers demote flag        (default -0.25)
  CUT_MAX_REV         revenue ceiling for cut candidates                  (default 1 500)
  CUT_MOM_PCT         MoM decline threshold for cut signal                (default -0.30)
"""

import re
from datetime import datetime
import pandas as pd
from modules.utils import fmt_rub, fmt_pct, wow_arrow, md_table, section


# ── Shared enrichment helpers ─────────────────────────────────────────────────

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


def _clean(name):
    if not isinstance(name, str):
        return name
    return _VARIANT_SUFFIXES.sub("", name).strip()


def _should_exclude(name):
    if not isinstance(name, str):
        return False
    low = name.lower().strip()
    return any(low.startswith(p) for p in _EXCLUDE_PREFIXES) or low in _ZERO_REV_MODIFIERS


def _enrich(txn, hierarchy):
    """Join non-return transactions with product hierarchy."""
    df = txn[~txn["is_return"]].copy()
    df = df[~df["product"].apply(_should_exclude)]
    df["product_lookup"] = df["product"].apply(_clean)

    if hierarchy.empty:
        df["category"]    = "Uncategorised"
        df["subcategory"] = "Uncategorised"
        df["product_en"]  = df["product_lookup"]
        df["variant"]     = ""
        df["featured"]    = 0
    else:
        hier_cols = ["product", "category", "subcategory", "product_en", "variant", "featured"]
        df = df.merge(
            hierarchy[hier_cols],
            left_on="product_lookup", right_on="product",
            how="left", suffixes=("", "_hier"),
        )
        df["category"]    = df["category"].fillna("Uncategorised")
        df["subcategory"] = df["subcategory"].fillna("Uncategorised")
        df["product_en"]  = df["product_en"].fillna(df["product_lookup"])
        df["variant"]     = df["variant"].fillna("")
        df["featured"]    = df["featured"].fillna(0).astype(int)
        is_variant = df["product"] != df["product_lookup"]
        df.loc[is_variant & (df["variant"] == ""), "variant"] = "no balls"

    return df


def _num_weeks(txn):
    """Count distinct ISO calendar weeks covered by the transaction dates."""
    if txn.empty:
        return 1
    return max(int(txn["date"].dt.isocalendar().week.nunique()), 1)


def _mom_pct(row):
    if row["prior_revenue"] > 0:
        return (row["revenue"] - row["prior_revenue"]) / row["prior_revenue"]
    return float("nan")


# ── Main builder ──────────────────────────────────────────────────────────────

def build(cur_txn, pri_txn, hierarchy, month_label, prior_label, cfg=None):
    """
    Build the full monthly product health markdown report string.

    Parameters
    ----------
    cur_txn, pri_txn : pd.DataFrame
        Raw transaction tables for the current and prior month.
    hierarchy : pd.DataFrame
        Product hierarchy loaded by loader.load_product_hierarchy().
    month_label : str   e.g. "March 2026"
    prior_label : str   e.g. "February 2026"
    cfg : dict          Optional threshold overrides (see module docstring).
    """
    cfg = cfg or {}
    PROMOTE_MIN_REV    = cfg.get("PROMOTE_MIN_REV",    5_000)
    PROMOTE_REL_SUBCAT = cfg.get("PROMOTE_REL_SUBCAT", 0.50)
    DEMOTE_REL_SUBCAT  = cfg.get("DEMOTE_REL_SUBCAT",  0.50)
    DEMOTE_MOM_PCT     = cfg.get("DEMOTE_MOM_PCT",     -0.25)
    CUT_MAX_REV        = cfg.get("CUT_MAX_REV",        1_500)
    CUT_MOM_PCT        = cfg.get("CUT_MOM_PCT",        -0.30)

    cur = _enrich(cur_txn, hierarchy)
    pri = _enrich(pri_txn, hierarchy)
    cur_weeks = _num_weeks(cur_txn)

    parts = [
        f"# Monthly Product Health: {month_label}\n",
        f"_Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}_\n\n---\n",
    ]

    # ── 1. Month Summary ──────────────────────────────────────────────────────
    parts.append(section("1. Month Summary", 2))

    cur_rev  = cur["revenue"].sum()
    pri_rev  = pri["revenue"].sum()
    cur_qty  = int(cur["qty"].sum())
    pri_qty  = int(pri["qty"].sum())
    active   = int((cur.groupby("product_en")["revenue"].sum() > 0).sum())

    parts.append(
        f"| Metric | {month_label} | {prior_label} | MoM |\n"
        f"| --- | --- | --- | --- |\n"
        f"| Revenue | {fmt_rub(cur_rev)} | {fmt_rub(pri_rev)} | {wow_arrow(cur_rev, pri_rev)} |\n"
        f"| Items sold | {cur_qty:,} | {pri_qty:,} | {wow_arrow(cur_qty, pri_qty)} |\n"
        f"| Active products | {active} | – | – |\n"
        f"| Weeks in period | {cur_weeks} | – | – |\n"
    )

    # ── 2. Category Overview ──────────────────────────────────────────────────
    parts.append(section("2. Category Overview", 2))

    cur_cat = cur.groupby("category").agg(revenue=("revenue", "sum"), qty=("qty", "sum")).reset_index()
    pri_cat = pri.groupby("category")["revenue"].sum().reset_index().rename(columns={"revenue": "prior_revenue"})
    cat = cur_cat.merge(pri_cat, on="category", how="outer").fillna(0)
    cat = cat[(cat["revenue"] > 0) | (cat["prior_revenue"] > 0)]
    cat["share"] = cat["revenue"] / cat["revenue"].sum() * 100
    cat["mom"]   = cat.apply(lambda r: wow_arrow(r["revenue"], r["prior_revenue"]), axis=1)
    cat = cat.sort_values("revenue", ascending=False)

    parts.append(md_table(
        cat[["category", "revenue", "share", "qty", "mom"]],
        formatters={"revenue": fmt_rub, "share": fmt_pct, "qty": lambda x: f"{int(x):,}"},
    ))

    # ── 3. Subcategory Overview ───────────────────────────────────────────────
    parts.append(section("3. Subcategory Overview", 2))
    parts.append("_Featured (★) shown as a separate row within each subcategory._\n")

    cur_sub = cur.groupby(["category", "subcategory", "featured"]).agg(revenue=("revenue", "sum"), qty=("qty", "sum")).reset_index()
    pri_sub = pri.groupby(["category", "subcategory", "featured"])["revenue"].sum().reset_index().rename(columns={"revenue": "prior_revenue"})
    sub = cur_sub.merge(pri_sub, on=["category", "subcategory", "featured"], how="outer").fillna(0)
    sub["featured"] = sub["featured"].astype(int)
    sub = sub[(sub["revenue"] > 0) | (sub["prior_revenue"] > 0)]
    sub["share"] = sub["revenue"] / sub["revenue"].sum() * 100
    sub["mom"]   = sub.apply(lambda r: wow_arrow(r["revenue"], r["prior_revenue"]), axis=1)
    sub = sub.sort_values(["category", "subcategory", "featured", "revenue"], ascending=[True, True, False, False])
    sub["group"] = sub.apply(lambda r: f"{r['subcategory']} ★" if r["featured"] else r["subcategory"], axis=1)

    parts.append(md_table(
        sub[["category", "group", "revenue", "share", "qty", "mom"]],
        formatters={"revenue": fmt_rub, "share": fmt_pct, "qty": lambda x: f"{int(x):,}"},
    ))

    # ── 4. Product Performance ────────────────────────────────────────────────
    parts.append(section("4. Product Performance", 2))
    parts.append("_Featured-first within each subcategory. Weekly avg = monthly revenue ÷ weeks in period._\n")

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

    # Drop products with no sales in either month
    prod = prod[(prod["revenue"] > 0) | (prod["prior_revenue"] > 0)]

    prod["mom"]        = prod.apply(lambda r: wow_arrow(r["revenue"], r["prior_revenue"]), axis=1)
    prod["weekly_avg"] = prod["revenue"] / cur_weeks

    subcat_totals = prod.groupby(["category", "subcategory"])["revenue"].sum().rename("subcat_total")
    prod = prod.join(subcat_totals, on=["category", "subcategory"])
    prod["% of subcat"] = prod["revenue"] / prod["subcat_total"].replace(0, float("nan")) * 100

    prod = prod.sort_values(
        ["category", "subcategory", "featured", "revenue"],
        ascending=[True, True, False, False],
    )
    prod["group"] = prod.apply(
        lambda r: f"{r['subcategory']} ★" if r["featured"] else r["subcategory"], axis=1
    )

    parts.append(md_table(
        prod[["category", "group", "product_en", "qty", "revenue", "weekly_avg", "% of subcat", "mom"]],
        formatters={
            "revenue":     fmt_rub,
            "weekly_avg":  fmt_rub,
            "% of subcat": fmt_pct,
            "qty":         lambda x: f"{int(x):,}",
        },
    ))

    # ── 5. Decision Signals ───────────────────────────────────────────────────
    parts.append(section("5. Decision Signals", 2))
    parts.append(
        f"_Thresholds — promote: revenue ≥ {fmt_rub(PROMOTE_MIN_REV)} and ≥ {PROMOTE_REL_SUBCAT*100:.0f}% of subcat featured avg; "
        f"demote: revenue ≤ {DEMOTE_REL_SUBCAT*100:.0f}% of subcat avg or MoM ≤ {DEMOTE_MOM_PCT*100:.0f}%; "
        f"cut: revenue ≤ {fmt_rub(CUT_MAX_REV)} and MoM ≤ {CUT_MOM_PCT*100:.0f}% (or no prior month sales)._\n"
    )

    # Subcat-level reference averages
    subcat_feat_avg = (
        prod[prod["featured"] == 1]
        .groupby(["category", "subcategory"])["revenue"].mean()
        .rename("subcat_feat_avg")
    )
    subcat_all_avg = (
        prod.groupby(["category", "subcategory"])["revenue"].mean()
        .rename("subcat_all_avg")
    )
    prod2 = prod.join(subcat_feat_avg, on=["category", "subcategory"])
    prod2 = prod2.join(subcat_all_avg, on=["category", "subcategory"])
    prod2["mom_pct"] = prod2.apply(_mom_pct, axis=1)

    _signal_cols = ["category", "subcategory", "product_en", "revenue", "weekly_avg", "% of subcat", "mom"]
    _signal_fmt  = {"revenue": fmt_rub, "weekly_avg": fmt_rub, "% of subcat": fmt_pct}

    # ── Promote ──────────────────────────────────────────────────────────────
    parts.append(section("⬆  Promote to Featured", 3))
    promote = prod2[
        (prod2["featured"] == 0)
        & (prod2["revenue"] >= PROMOTE_MIN_REV)
        & (prod2["revenue"] >= prod2["subcat_feat_avg"].fillna(0) * PROMOTE_REL_SUBCAT)
    ].sort_values("revenue", ascending=False)

    if promote.empty:
        parts.append("_No promote candidates this month._\n")
    else:
        parts.append(md_table(promote[_signal_cols], formatters=_signal_fmt))

    # ── Demote ───────────────────────────────────────────────────────────────
    parts.append(section("⬇  Demote from Featured", 3))
    demote = prod2[
        (prod2["featured"] == 1)
        & (
            (prod2["revenue"] <= prod2["subcat_all_avg"].fillna(float("inf")) * DEMOTE_REL_SUBCAT)
            | (prod2["mom_pct"] <= DEMOTE_MOM_PCT)
        )
    ].copy()
    demote["reason"] = demote.apply(
        lambda r: " + ".join(filter(None, [
            "low revenue" if r["revenue"] <= (r.get("subcat_all_avg") or float("inf")) * DEMOTE_REL_SUBCAT else "",
            f"MoM {r['mom_pct']*100:.1f}%" if pd.notna(r["mom_pct"]) and r["mom_pct"] <= DEMOTE_MOM_PCT else "",
        ])),
        axis=1,
    )
    demote = demote.sort_values("revenue", ascending=True)

    if demote.empty:
        parts.append("_No demote candidates this month._\n")
    else:
        parts.append(md_table(
            demote[_signal_cols + ["reason"]],
            formatters=_signal_fmt,
        ))

    # ── Cut ──────────────────────────────────────────────────────────────────
    parts.append(section("✂  Cut Candidates", 3))
    cut = prod2[
        (prod2["featured"] == 0)
        & (prod2["revenue"] <= CUT_MAX_REV)
        & ((prod2["mom_pct"] <= CUT_MOM_PCT) | prod2["mom_pct"].isna())
    ].sort_values("revenue", ascending=True)

    if cut.empty:
        parts.append("_No cut candidates this month._\n")
    else:
        parts.append(md_table(
            cut[["category", "subcategory", "product_en", "revenue", "weekly_avg", "mom"]],
            formatters={"revenue": fmt_rub, "weekly_avg": fmt_rub},
        ))

    return "\n".join(parts)
