"""
Section 1: Sales — store distribution, channel distribution, WoW,
           and per-store channel breakdown.
"""
import pandas as pd
from modules.utils import fmt_rub, fmt_pct, wow_arrow, md_table, section


def build(current_sales, prior_sales):
    parts = [section("1. Sales", 2)]

    # ── Totals ────────────────────────────────────────────────────
    cur_total   = current_sales["revenue"].sum()
    prior_total = prior_sales["revenue"].sum()
    parts.append(
        f"**Week total:** {fmt_rub(cur_total)}  "
        f"**WoW:** {wow_arrow(cur_total, prior_total)}\n"
    )

    # ── Store Distribution ────────────────────────────────────────
    parts.append(section("Store Distribution", 3))

    cur_store = (
        current_sales.groupby("store")["revenue"].sum()
        .reset_index().rename(columns={"revenue": "this_week"})
    )
    pri_store = (
        prior_sales.groupby("store")["revenue"].sum()
        .reset_index().rename(columns={"revenue": "prior_week"})
    )
    store = cur_store.merge(pri_store, on="store", how="outer").fillna(0)
    store["share"] = store["this_week"] / store["this_week"].sum() * 100
    store["wow"]   = store.apply(lambda r: wow_arrow(r["this_week"], r["prior_week"]), axis=1)
    store = store.sort_values("this_week", ascending=False)

    parts.append(md_table(
        store[["store", "this_week", "prior_week", "share", "wow"]],
        formatters={
            "this_week":  fmt_rub,
            "prior_week": fmt_rub,
            "share":      fmt_pct,
        }
    ))

    # ── Overall Channel Distribution ──────────────────────────────
    parts.append(section("Channel Distribution", 3))

    cur_ch = (
        current_sales.groupby("payment_type")["revenue"].sum()
        .reset_index().rename(columns={"revenue": "this_week"})
    )
    pri_ch = (
        prior_sales.groupby("payment_type")["revenue"].sum()
        .reset_index().rename(columns={"revenue": "prior_week"})
    )
    ch = cur_ch.merge(pri_ch, on="payment_type", how="outer").fillna(0)
    ch["share"] = ch["this_week"] / ch["this_week"].sum() * 100
    ch["wow"]   = ch.apply(lambda r: wow_arrow(r["this_week"], r["prior_week"]), axis=1)
    ch = ch.sort_values("this_week", ascending=False)

    parts.append(md_table(
        ch[["payment_type", "this_week", "prior_week", "share", "wow"]],
        formatters={
            "this_week":  fmt_rub,
            "prior_week": fmt_rub,
            "share":      fmt_pct,
        }
    ))

    # ── Per-Store Channel Breakdown ───────────────────────────────
    parts.append(section("Channel Breakdown by Store", 3))

    all_types = sorted(current_sales["payment_type"].unique())

    known_stores = [s for s in store["store"].tolist() if not str(s).startswith("UNKNOWN_")]
    for store_name in known_stores:
        cur_s = current_sales[current_sales["store"] == store_name]
        pri_s = prior_sales[prior_sales["store"] == store_name]
        store_total = cur_s["revenue"].sum()

        rows = []
        for pt in all_types:
            cur_rev  = cur_s[cur_s["payment_type"] == pt]["revenue"].sum()
            pri_rev  = pri_s[pri_s["payment_type"] == pt]["revenue"].sum()
            share    = cur_rev / store_total * 100 if store_total > 0 else 0
            rows.append({
                "channel":    pt,
                "this_week":  cur_rev,
                "prior_week": pri_rev,
                "share":      share,
                "wow":        wow_arrow(cur_rev, pri_rev),
            })

        df_s = pd.DataFrame(rows).sort_values("this_week", ascending=False)
        parts.append(f"\n**{store_name}** — total {fmt_rub(store_total)}\n")
        parts.append(md_table(
            df_s[["channel", "this_week", "prior_week", "share", "wow"]],
            formatters={
                "this_week":  fmt_rub,
                "prior_week": fmt_rub,
                "share":      fmt_pct,
            }
        ))

    return "\n".join(parts)
