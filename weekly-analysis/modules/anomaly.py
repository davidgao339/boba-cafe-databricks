"""
Section 4: Anomaly Detection
  - Low daily sales vs rolling average
  - Low cash ratio (potential theft signal)
  - Long intra-day sales gaps (employee absence)
  - Long tapioca gaps (tapioca not prepared)
"""
import pandas as pd
from modules.utils import fmt_rub, fmt_pct, md_table, section
from pyspark.sql import functions as F


def build(current_txn, spark, transactions_table, week_start, week_end, cfg):
    parts = [section("4. Anomaly Detection", 2)]

    # ── 4.1 Low Sales ─────────────────────────────────────────────
    parts.append(section("Low Sales Days", 3))

    # 4-week rolling baseline: weeks prior to this week
    rolling_start = (pd.to_datetime(week_start) - pd.Timedelta(days=28)).strftime("%Y-%m-%d")
    rolling_end   = (pd.to_datetime(week_start) - pd.Timedelta(days=1)).strftime("%Y-%m-%d")

    baseline_sdf = (
        spark.table(transactions_table)
        .filter(F.col("date").between(rolling_start, rolling_end))
        .filter(~F.col("is_return"))
        .groupBy("store_name", "date")
        .agg(F.sum("revenue").alias("daily_revenue"))
    )
    baseline = baseline_sdf.toPandas()
    rolling_avg = (
        baseline.groupby("store_name")["daily_revenue"]
        .mean().reset_index()
        .rename(columns={"daily_revenue": "rolling_avg", "store_name": "store_name"})
    )

    cur_daily = (
        current_txn[~current_txn["is_return"]]
        .groupby(["store_name", "date"])["revenue"].sum()
        .reset_index()
    )
    cur_daily = cur_daily.merge(rolling_avg, on="store_name", how="left")
    cur_daily["threshold"] = cur_daily["rolling_avg"] * cfg["LOW_SALES_PCT"]
    low_sales = cur_daily[
        (cur_daily["revenue"] < cur_daily["threshold"])
        & (cur_daily["revenue"] > cfg["MIN_TRADING_REVENUE"])
    ].copy()

    if low_sales.empty:
        parts.append("_No low sales days detected._\n")
    else:
        low_sales["date"] = low_sales["date"].dt.strftime("%Y-%m-%d")
        low_sales["vs_avg"] = (low_sales["revenue"] / low_sales["rolling_avg"] * 100).round(1).astype(str) + "%"
        parts.append(md_table(
            low_sales[["date", "store_name", "revenue", "rolling_avg", "vs_avg"]].rename(
                columns={"store_name": "store"}
            ).sort_values(["store", "date"]),
            formatters={"revenue": fmt_rub, "rolling_avg": fmt_rub}
        ))

    # ── 4.2 Low Cash Ratio ────────────────────────────────────────
    parts.append(section("Low Cash Ratio (Potential Theft Signal)", 3))

    # Baseline cash ratio per store from rolling 4 weeks
    baseline_full_sdf = (
        spark.table(transactions_table)
        .filter(F.col("date").between(rolling_start, rolling_end))
        .filter(~F.col("is_return"))
        .groupBy("store_name", "date")
        .agg(
            F.sum(F.when(F.col("transaction_type") == "Cash", F.col("revenue")).otherwise(0)).alias("cash"),
            F.sum("revenue").alias("total")
        )
    )
    baseline_full = baseline_full_sdf.toPandas()
    baseline_ratio = (
        baseline_full.groupby("store_name")
        .apply(lambda g: (g["cash"].sum() / g["total"].sum()) if g["total"].sum() > 0 else 0)
        .reset_index().rename(columns={0: "baseline_cash_ratio", "store_name": "store_name"})
    )

    cur_cash = (
        current_txn[~current_txn["is_return"]]
        .groupby(["store_name", "date"])
        .apply(lambda g: pd.Series({
            "cash":  g.loc[g["transaction_type"] == "Cash", "revenue"].sum(),
            "total": g["revenue"].sum(),
        }))
        .reset_index()
    )
    cur_cash["cash_ratio"] = cur_cash["cash"] / cur_cash["total"].replace(0, float("nan"))
    cur_cash = cur_cash.merge(baseline_ratio, on="store_name", how="left")
    cur_cash["drop"] = cur_cash["baseline_cash_ratio"] - cur_cash["cash_ratio"]

    low_cash = cur_cash[
        (cur_cash["drop"] > cfg["LOW_CASH_DROP_PCT"])
        & (cur_cash["total"] > cfg["MIN_TRADING_REVENUE"])
    ].copy()

    if low_cash.empty:
        parts.append("_No unusual cash ratio drops detected._\n")
    else:
        low_cash["date"] = low_cash["date"].dt.strftime("%Y-%m-%d")
        low_cash["cash_ratio_fmt"]     = (low_cash["cash_ratio"]     * 100).round(1).astype(str) + "%"
        low_cash["baseline_ratio_fmt"] = (low_cash["baseline_cash_ratio"] * 100).round(1).astype(str) + "%"
        parts.append(md_table(
            low_cash[["date", "store_name", "cash", "total", "cash_ratio_fmt", "baseline_ratio_fmt"]]
            .rename(columns={"store_name": "store", "cash_ratio_fmt": "cash_%", "baseline_ratio_fmt": "baseline_%"})
            .sort_values(["store", "date"]),
            formatters={"cash": fmt_rub, "total": fmt_rub}
        ))

    # ── 4.3 Long Sales Gaps ───────────────────────────────────────
    parts.append(section("Long Sales Gaps (Employee Absence)", 3))

    gap_rows = []
    for (store, date), grp in (
        current_txn[~current_txn["is_return"]]
        .sort_values("datetime")
        .groupby(["store_name", "date"])
    ):
        times = grp["datetime"].sort_values().reset_index(drop=True)
        for i in range(1, len(times)):
            gap_min = (times[i] - times[i - 1]).total_seconds() / 60
            if gap_min >= cfg["SALES_GAP_MINUTES"]:
                gap_rows.append({
                    "date":      date,
                    "store":     store,
                    "gap_start": times[i - 1].strftime("%H:%M"),
                    "gap_end":   times[i].strftime("%H:%M"),
                    "gap_min":   int(gap_min),
                })

    if not gap_rows:
        parts.append("_No long sales gaps detected._\n")
    else:
        gap_df = pd.DataFrame(gap_rows)
        gap_df["date"] = pd.to_datetime(gap_df["date"]).dt.strftime("%Y-%m-%d")
        gap_df = gap_df.sort_values(["store", "date", "gap_start"])
        parts.append(md_table(gap_df))

    # ── 4.4 Tapioca Gaps ─────────────────────────────────────────
    parts.append(section("Tapioca Preparation Gaps", 3))

    tap_mask = (
        current_txn["product"].str.contains(cfg["TAPIOCA_KEYWORD"], case=False, na=False)
        & (~current_txn["is_return"])
        & (
            (current_txn["qty"] > 0)                               # real sale
            | (current_txn["transaction_type"] == "Non-Fiscal")    # write-off (qty may be 0 or negative)
        )
    )
    tap_txn = current_txn[tap_mask].sort_values("datetime")

    tap_gaps = []
    for (store, date), grp in tap_txn.groupby(["store_name", "date"]):
        times = grp["datetime"].sort_values().reset_index(drop=True)
        for i in range(1, len(times)):
            gap_min = (times[i] - times[i - 1]).total_seconds() / 60
            if gap_min >= cfg["TAPIOCA_GAP_MINUTES"]:
                # Revenue during the gap
                between_rev = current_txn[
                    (current_txn["store_name"] == store)
                    & (current_txn["datetime"] > times[i - 1])
                    & (current_txn["datetime"] < times[i])
                    & (~current_txn["is_return"])
                ]["revenue"].sum()
                tap_gaps.append({
                    "date":      date,
                    "store":     store,
                    "gap_start": times[i - 1].strftime("%H:%M"),
                    "gap_end":   times[i].strftime("%H:%M"),
                    "gap_min":   int(gap_min),
                    "rev_in_gap": int(round(between_rev)),
                })

    tap_gaps = [g for g in tap_gaps if g["rev_in_gap"] >= 1000]

    if not tap_gaps:
        parts.append("_No tapioca gaps detected._\n")
    else:
        tap_df = pd.DataFrame(tap_gaps)
        tap_df["date"] = pd.to_datetime(tap_df["date"]).dt.strftime("%Y-%m-%d")
        tap_df = tap_df.sort_values(["store", "date", "gap_start"])
        parts.append(md_table(
            tap_df,
            formatters={"rev_in_gap": fmt_rub}
        ))

    return "\n".join(parts)
