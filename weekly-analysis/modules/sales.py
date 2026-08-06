"""
Section 1: Sales — Executive Snapshot, Store Performance Matrix (Dual Baseline),
           Traffic vs. Ticket Drivers, Channel Distribution, and Store Breakdowns.
"""
import pandas as pd
from modules.utils import (
    fmt_rub, fmt_pct, fmt_diff_rub, pct_arrow, wow_arrow,
    trend_status, md_table, section
)


def _compute_order_stats(txn):
    """Compute order count and avg basket per store and chain-wide."""
    if txn is None or txn.empty:
        return pd.DataFrame(), 0, 0

    # Filter out non-fiscal items if column exists
    df = txn.copy()
    if "transaction_type" in df.columns:
        df = df[df["transaction_type"] != "Non-Fiscal"]
    if "online" in df.columns:
        df = df[~df["online"]]

    if "order_number" not in df.columns:
        return pd.DataFrame(), 0, 0

    order_col = "order_number"
    store_col = "store_name" if "store_name" in df.columns else ("store" if "store" in df.columns else None)

    # Net revenue per order
    order_rev = df.groupby([store_col, order_col, "is_return"])["revenue"].sum().reset_index() if store_col else pd.DataFrame()
    
    # Store-level stats
    if not order_rev.empty:
        non_returns = order_rev[order_rev["is_return"] == False]
        orders_per_store = non_returns.groupby(store_col)[order_col].nunique().rename("orders")
        rev_per_store = order_rev.groupby(store_col)["revenue"].sum().rename("revenue")
        store_stats = pd.concat([orders_per_store, rev_per_store], axis=1).fillna(0).reset_index().rename(columns={store_col: "store"})
        store_stats["avg_ticket"] = store_stats.apply(
            lambda r: r["revenue"] / r["orders"] if r["orders"] > 0 else 0, axis=1
        )
    else:
        store_stats = pd.DataFrame()

    # Chain-wide stats
    chain_order_rev = df.groupby([order_col, "is_return"])["revenue"].sum().reset_index()
    chain_orders = (chain_order_rev["is_return"] == False).sum()
    chain_rev = chain_order_rev["revenue"].sum()
    chain_ticket = chain_rev / chain_orders if chain_orders > 0 else 0

    return store_stats, chain_orders, chain_ticket


def build(current_sales, prior_sales, rolling_sales=None, current_txn=None, prior_txn=None):
    parts = [section("1. Sales & Store Performance", 2)]

    # ── 1.1 Executive Totals & Dual Baseline ───────────────────────
    cur_total   = current_sales["revenue"].sum()
    prior_total = prior_sales["revenue"].sum()
    rolling_4w_avg = rolling_sales["revenue"].sum() / 4.0 if (rolling_sales is not None and not rolling_sales.empty) else 0

    cur_store_stats, cur_orders, cur_ticket = _compute_order_stats(current_txn)
    pri_store_stats, pri_orders, pri_ticket = _compute_order_stats(prior_txn)

    overall_status = trend_status(cur_total, prior_total, rolling_4w_avg)
    net_rub_str = fmt_diff_rub(cur_total, prior_total)

    # Executive Snapshot Summary Table
    snapshot_rows = [
        {
            "Metric": "Total Revenue",
            "This Week": fmt_rub(cur_total),
            "Prior Week": fmt_rub(prior_total),
            "WoW %": pct_arrow(cur_total, prior_total),
            "4W Avg (Wkly)": fmt_rub(rolling_4w_avg) if rolling_4w_avg > 0 else "–",
            "vs. 4W Avg": pct_arrow(cur_total, rolling_4w_avg) if rolling_4w_avg > 0 else "–",
            "Net Impact": net_rub_str,
            "Status": overall_status,
        }
    ]

    if cur_orders > 0 and pri_orders > 0:
        order_diff = cur_orders - pri_orders
        sign_o = "+" if order_diff > 0 else ""
        ticket_diff = cur_ticket - pri_ticket
        sign_t = "+" if ticket_diff > 0 else ""

        snapshot_rows.append({
            "Metric": "Total Orders (Traffic)",
            "This Week": f"{cur_orders:,}",
            "Prior Week": f"{pri_orders:,}",
            "WoW %": pct_arrow(cur_orders, pri_orders),
            "4W Avg (Wkly)": "–",
            "vs. 4W Avg": "–",
            "Net Impact": f"{sign_o}{order_diff:,} orders",
            "Status": "🟢 Traffic-Led" if (cur_orders / pri_orders) > (cur_total / prior_total if prior_total > 0 else 1) else "⚪ Traffic",
        })
        snapshot_rows.append({
            "Metric": "Avg Ticket (Check Size)",
            "This Week": fmt_rub(cur_ticket),
            "Prior Week": fmt_rub(pri_ticket),
            "WoW %": pct_arrow(cur_ticket, pri_ticket),
            "4W Avg (Wkly)": "–",
            "vs. 4W Avg": "–",
            "Net Impact": f"{sign_t}₽{abs(int(round(ticket_diff)))}",
            "Status": "🟢 Upsell Win" if cur_ticket > pri_ticket * 1.03 else "⚪ Stable",
        })

    parts.append(md_table(pd.DataFrame(snapshot_rows)))
    parts.append("")

    # ── 1.2 Store Performance Matrix (Dual Baseline) ───────────────
    parts.append(section("Store Performance Matrix", 3))
    parts.append("_Evaluates both Week-over-Week (WoW) and 4-Week Rolling Average to filter out one-week volatility._\n")

    cur_store = (
        current_sales.groupby("store")["revenue"].sum()
        .reset_index().rename(columns={"revenue": "this_week"})
    )
    pri_store = (
        prior_sales.groupby("store")["revenue"].sum()
        .reset_index().rename(columns={"revenue": "prior_week"})
    )
    store = cur_store.merge(pri_store, on="store", how="outer").fillna(0)

    # Add 4-week rolling average per store
    if rolling_sales is not None and not rolling_sales.empty:
        roll_store = (
            rolling_sales.groupby("store")["revenue"].sum()
            .reset_index().rename(columns={"revenue": "rolling_4w_total"})
        )
        roll_store["rolling_4w_avg"] = roll_store["rolling_4w_total"] / 4.0
        store = store.merge(roll_store[["store", "rolling_4w_avg"]], on="store", how="left").fillna(0)
    else:
        store["rolling_4w_avg"] = 0

    # Filter out inactive UNKNOWN_ terminals with 0 revenue
    store = store[
        ~(store["store"].str.startswith("UNKNOWN_") & (store["this_week"] == 0) & (store["prior_week"] == 0))
    ].copy()

    store["share"] = store["this_week"] / cur_total * 100 if cur_total > 0 else 0
    store["wow"] = store.apply(lambda r: pct_arrow(r["this_week"], r["prior_week"]), axis=1)
    store["vs_4w_avg"] = store.apply(
        lambda r: pct_arrow(r["this_week"], r["rolling_4w_avg"]) if r["rolling_4w_avg"] > 0 else "–",
        axis=1
    )
    store["net_impact"] = store.apply(lambda r: fmt_diff_rub(r["this_week"], r["prior_week"]), axis=1)
    store["status"] = store.apply(lambda r: trend_status(r["this_week"], r["prior_week"], r["rolling_4w_avg"]), axis=1)

    # Sort primarily by this_week revenue descending
    store = store.sort_values("this_week", ascending=False)

    display_cols = ["store", "this_week", "prior_week", "rolling_4w_avg", "wow", "vs_4w_avg", "net_impact", "share", "status"]
    parts.append(md_table(
        store[display_cols].rename(columns={
            "rolling_4w_avg": "4w_avg",
        }),
        formatters={
            "this_week":  fmt_rub,
            "prior_week": fmt_rub,
            "4w_avg":     fmt_rub,
            "share":      fmt_pct,
        }
    ))

    # Highlight Growth Drivers & Action Items
    growth_stores = store[store["this_week"] > store["prior_week"]].sort_values(
        by=["this_week"], ascending=False
    )
    decline_stores = store[store["this_week"] < store["prior_week"]].sort_values(
        by=["this_week"], ascending=True
    )

    callouts = []
    if not growth_stores.empty:
        top_g = growth_stores.head(3)["store"].tolist()
        callouts.append(f"- 🚀 **Top Growth Drivers:** {', '.join(top_g)}")
    if not decline_stores.empty:
        top_d = decline_stores[decline_stores["status"].str.contains("Underperforming|Action", na=False)]
        if not top_d.empty:
            callouts.append(f"- ⚠️ **Action Needed:** {', '.join(top_d['store'].tolist())}")

    if callouts:
        parts.append("\n" + "\n".join(callouts) + "\n")

    # ── 1.3 Traffic vs. Ticket Decomposition (Store Level) ──────────
    if not cur_store_stats.empty and not pri_store_stats.empty:
        parts.append(section("Traffic (Orders) vs. Ticket (Avg Basket) by Store", 3))
        parts.append("_Decomposes store revenue changes into Customer Traffic (Order Count) vs. Check Size (Avg Basket)._\n")

        traffic_df = cur_store_stats.merge(
            pri_store_stats, on="store", how="outer", suffixes=("_cur", "_pri")
        ).fillna(0)

        # Exclude unknown stores with 0 orders
        traffic_df = traffic_df[
            ~(traffic_df["store"].str.startswith("UNKNOWN_") & (traffic_df["orders_cur"] == 0))
        ].copy()

        traffic_df["orders_wow"] = traffic_df.apply(
            lambda r: pct_arrow(r["orders_cur"], r["orders_pri"]), axis=1
        )
        traffic_df["ticket_wow"] = traffic_df.apply(
            lambda r: pct_arrow(r["avg_ticket_cur"], r["avg_ticket_pri"]), axis=1
        )

        def _primary_driver(r):
            o_pct = (r["orders_cur"] - r["orders_pri"]) / r["orders_pri"] if r["orders_pri"] > 0 else 0
            t_pct = (r["avg_ticket_cur"] - r["avg_ticket_pri"]) / r["avg_ticket_pri"] if r["avg_ticket_pri"] > 0 else 0
            if o_pct > 0.05 and t_pct > 0.03:
                return "🟢 Traffic & Ticket"
            elif o_pct >= t_pct and o_pct > 0:
                return f"👥 Traffic ({o_pct*100:+.0f}%)"
            elif t_pct > o_pct and t_pct > 0:
                return f"💳 Ticket ({t_pct*100:+.0f}%)"
            elif o_pct < -0.05 and t_pct < -0.05:
                return "🔴 Traffic & Ticket Slump"
            elif o_pct <= t_pct:
                return f"⚠️ Traffic Slump ({o_pct*100:+.0f}%)"
            else:
                return f"⚠️ Ticket Drop ({t_pct*100:+.0f}%)"

        traffic_df["driver"] = traffic_df.apply(_primary_driver, axis=1)
        traffic_df = traffic_df.sort_values("orders_cur", ascending=False)

        parts.append(md_table(
            traffic_df[["store", "orders_cur", "orders_pri", "orders_wow", "avg_ticket_cur", "avg_ticket_pri", "ticket_wow", "driver"]].rename(
                columns={
                    "orders_cur": "orders_this_wk",
                    "orders_pri": "orders_prior_wk",
                    "avg_ticket_cur": "ticket_this_wk",
                    "avg_ticket_pri": "ticket_prior_wk",
                    "driver": "primary_driver",
                }
            ),
            formatters={
                "orders_this_wk":  lambda x: f"{int(x):,}",
                "orders_prior_wk": lambda x: f"{int(x):,}",
                "ticket_this_wk":  fmt_rub,
                "ticket_prior_wk": fmt_rub,
            }
        ))

    # ── 1.4 Weekday (Mon–Thu) vs. Weekend (Fri–Sun) Dynamics ─────────
    if "date" in current_sales.columns and "date" in prior_sales.columns and not current_sales.empty:
        cur_d = current_sales.copy()
        pri_d = prior_sales.copy()
        cur_d["date"] = pd.to_datetime(cur_d["date"])
        pri_d["date"] = pd.to_datetime(pri_d["date"])

        cur_d["day_type"] = cur_d["date"].dt.weekday.apply(lambda w: "Weekday" if w < 4 else "Weekend")
        pri_d["day_type"] = pri_d["date"].dt.weekday.apply(lambda w: "Weekday" if w < 4 else "Weekend")

        cur_day = cur_d.groupby(["store", "day_type"])["revenue"].sum().unstack(fill_value=0).reset_index()
        pri_day = pri_d.groupby(["store", "day_type"])["revenue"].sum().unstack(fill_value=0).reset_index()

        for col in ["Weekday", "Weekend"]:
            if col not in cur_day.columns:
                cur_day[col] = 0
            if col not in pri_day.columns:
                pri_day[col] = 0

        day_df = cur_day.merge(pri_day, on="store", suffixes=("_cur", "_pri"), how="outer").fillna(0)
        day_df = day_df[
            ~(day_df["store"].str.startswith("UNKNOWN_") & (day_df["Weekday_cur"] == 0) & (day_df["Weekend_cur"] == 0))
        ].copy()

        day_df["total_cur"] = day_df["Weekday_cur"] + day_df["Weekend_cur"]
        day_df["weekday_wow"] = day_df.apply(lambda r: pct_arrow(r["Weekday_cur"], r["Weekday_pri"]), axis=1)
        day_df["weekend_wow"] = day_df.apply(lambda r: pct_arrow(r["Weekend_cur"], r["Weekend_pri"]), axis=1)
        day_df["weekend_share"] = day_df.apply(
            lambda r: (r["Weekend_cur"] / r["total_cur"] * 100) if r["total_cur"] > 0 else 0, axis=1
        )

        def _day_pattern(r):
            w_pct = (r["Weekday_cur"] - r["Weekday_pri"]) / r["Weekday_pri"] if r["Weekday_pri"] > 0 else 0
            e_pct = (r["Weekend_cur"] - r["Weekend_pri"]) / r["Weekend_pri"] if r["Weekend_pri"] > 0 else 0
            if w_pct > 0.05 and e_pct > 0.05:
                return "🔥 Full Growth"
            elif w_pct > 0.03 and e_pct < -0.05:
                return "🌤️ Weekend Drag"
            elif w_pct < -0.05 and e_pct > 0.03:
                return "🏢 Weekday Weakness"
            elif w_pct < -0.05 and e_pct < -0.05:
                return "❄️ Full Slump"
            else:
                return "⚪ Balanced"

        day_df["pattern"] = day_df.apply(_day_pattern, axis=1)
        day_df = day_df.sort_values("total_cur", ascending=False)

        parts.append(section("Weekday (Mon–Thu) vs. Weekend (Fri–Sun) Dynamics", 3))
        parts.append("_Isolates weekday baseline trends from weekend weather/event volatility._\n")

        parts.append(md_table(
            day_df[["store", "Weekday_cur", "Weekday_pri", "weekday_wow", "Weekend_cur", "Weekend_pri", "weekend_wow", "weekend_share", "pattern"]].rename(
                columns={
                    "Weekday_cur": "weekday_rev",
                    "Weekday_pri": "weekday_prior",
                    "Weekend_cur": "weekend_rev",
                    "Weekend_pri": "weekend_prior",
                }
            ),
            formatters={
                "weekday_rev":   fmt_rub,
                "weekday_prior": fmt_rub,
                "weekend_rev":   fmt_rub,
                "weekend_prior": fmt_rub,
                "weekend_share": fmt_pct,
            }
        ))

    # ── 1.5 Overall Channel Distribution ───────────────────────────
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
    ch["share"] = ch["this_week"] / cur_total * 100 if cur_total > 0 else 0
    ch["wow"]   = ch.apply(lambda r: pct_arrow(r["this_week"], r["prior_week"]), axis=1)
    ch["net_impact"] = ch.apply(lambda r: fmt_diff_rub(r["this_week"], r["prior_week"]), axis=1)
    ch = ch.sort_values("this_week", ascending=False)

    parts.append(md_table(
        ch[["payment_type", "this_week", "prior_week", "share", "wow", "net_impact"]],
        formatters={
            "this_week":   fmt_rub,
            "prior_week":  fmt_rub,
            "share":       fmt_pct,
        }
    ))

    # ── 1.5 Per-Store Channel Breakdown ────────────────────────────
    parts.append(section("Channel Breakdown by Store", 3))

    all_types = sorted(current_sales["payment_type"].unique())
    known_stores = [s for s in store["store"].tolist() if not str(s).startswith("UNKNOWN_")]

    for store_name in known_stores:
        cur_s = current_sales[current_sales["store"] == store_name]
        pri_s = prior_sales[prior_sales["store"] == store_name]
        store_total = cur_s["revenue"].sum()
        if store_total == 0 and pri_s["revenue"].sum() == 0:
            continue

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
                "wow":        pct_arrow(cur_rev, pri_rev),
                "net_impact": fmt_diff_rub(cur_rev, pri_rev),
            })

        df_s = pd.DataFrame(rows).sort_values("this_week", ascending=False)
        parts.append(f"\n**{store_name}** — total {fmt_rub(store_total)}\n")
        parts.append(md_table(
            df_s[["channel", "this_week", "prior_week", "share", "wow", "net_impact"]],
            formatters={
                "this_week":  fmt_rub,
                "prior_week": fmt_rub,
                "share":      fmt_pct,
            }
        ))

    return "\n".join(parts)

