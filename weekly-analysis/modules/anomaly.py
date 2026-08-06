"""
Section 4: Operational Anomaly & Loss Prevention Engine
  - Low daily sales vs rolling baseline
  - Cash ratio drops (potential theft & loss prevention signal linked to employee shifts)
  - Long intra-day sales gaps (employee absence / unstaffed store linked to schedule)
  - Tapioca preparation gaps (unreported stockouts linked to scheduled baristas)
"""
import pandas as pd
import numpy as np
from modules.utils import fmt_rub, fmt_pct, md_table, section


def _get_scheduled_staff(schedule_df, date_str, store_name):
    """
    Look up scheduled employees for a given date and store from the employee schedule table.
    """
    if schedule_df is None or schedule_df.empty:
        return "—"

    sched = schedule_df.copy()
    if "date" in sched.columns:
        sched["date_str"] = pd.to_datetime(sched["date"]).dt.strftime("%Y-%m-%d")
    else:
        return "—"

    store_col = "store" if "store" in sched.columns else "store_name"
    sched["store_clean"] = sched[store_col].astype(str).str.strip().str.upper()
    store_clean = str(store_name).strip().upper()

    matched = sched[(sched["date_str"] == str(date_str)) & (sched["store_clean"] == store_clean)]
    if matched.empty:
        # Fallback: check if store name is substring
        matched = sched[(sched["date_str"] == str(date_str)) & (sched["store_clean"].str.contains(store_clean, regex=False))]

    if matched.empty:
        return "Unscheduled"

    staff_list = []
    for _, row in matched.iterrows():
        emp = str(row.get("employee", "")).strip()
        shift = str(row.get("shift", "")).strip()
        if emp and emp.lower() != "nan":
            if shift and shift.lower() != "nan" and shift != "-":
                staff_list.append(f"{emp} ({shift})")
            else:
                staff_list.append(emp)

    return ", ".join(dict.fromkeys(staff_list)) if staff_list else "Unscheduled"


def build(
    current_txn,
    rolling_txn=None,
    schedule_df=None,
    cfg=None,
    spark=None,
    transactions_table=None,
    week_start=None,
    week_end=None,
):
    parts = [section("4. Operational Anomaly & Loss Prevention", 2)]

    if cfg is None:
        cfg = {
            "LOW_SALES_PCT":       0.50,
            "LOW_CASH_DROP_PCT":   0.25,
            "SALES_GAP_MINUTES":   60,
            "TAPIOCA_GAP_MINUTES": 60,
            "TAPIOCA_KEYWORD":     "тапиок",
            "MIN_TRADING_REVENUE": 500,
        }

    cur_txn = current_txn.copy()
    if "datetime" in cur_txn.columns and not pd.api.types.is_datetime64_any_dtype(cur_txn["datetime"]):
        cur_txn["datetime"] = pd.to_datetime(cur_txn["datetime"])
    if "date" in cur_txn.columns and not pd.api.types.is_datetime64_any_dtype(cur_txn["date"]):
        cur_txn["date"] = pd.to_datetime(cur_txn["date"])

    store_col = "store_name" if "store_name" in cur_txn.columns else "store"
    cur_txn["store_clean"] = cur_txn[store_col].astype(str).str.strip()

    # Determine rolling baseline dataframe
    baseline_df = pd.DataFrame()
    if rolling_txn is not None and not rolling_txn.empty:
        baseline_df = rolling_txn.copy()
        if "date" in baseline_df.columns and not pd.api.types.is_datetime64_any_dtype(baseline_df["date"]):
            baseline_df["date"] = pd.to_datetime(baseline_df["date"])
        b_store_col = "store_name" if "store_name" in baseline_df.columns else "store"
        baseline_df["store_clean"] = baseline_df[b_store_col].astype(str).str.strip()
    elif spark is not None and transactions_table and week_start:
        try:
            from pyspark.sql import functions as F
            rolling_start = (pd.to_datetime(week_start) - pd.Timedelta(days=28)).strftime("%Y-%m-%d")
            rolling_end   = (pd.to_datetime(week_start) - pd.Timedelta(days=1)).strftime("%Y-%m-%d")
            b_sdf = (
                spark.table(transactions_table)
                .filter(F.col("date").between(rolling_start, rolling_end))
            )
            baseline_df = b_sdf.toPandas()
            baseline_df["date"] = pd.to_datetime(baseline_df["date"])
            b_store_col = "store_name" if "store_name" in baseline_df.columns else "store"
            baseline_df["store_clean"] = baseline_df[b_store_col].astype(str).str.strip()
        except Exception as e:
            print(f"Note: Could not query Spark baseline ({e}); using current week statistics.")

    # ── 4.1 Low Sales Days ────────────────────────────────────────
    parts.append(section("Low Daily Sales", 3))

    cur_valid = cur_txn[~cur_txn["is_return"]] if "is_return" in cur_txn.columns else cur_txn
    cur_daily = (
        cur_valid.groupby(["store_clean", "date"])["revenue"].sum()
        .reset_index()
    )

    if not baseline_df.empty:
        base_valid = baseline_df[~baseline_df["is_return"]] if "is_return" in baseline_df.columns else baseline_df
        rolling_avg = (
            base_valid.groupby(["store_clean", "date"])["revenue"].sum()
            .reset_index()
            .groupby("store_clean")["revenue"].mean()
            .reset_index().rename(columns={"revenue": "rolling_avg"})
        )
    else:
        rolling_avg = (
            cur_daily.groupby("store_clean")["revenue"].mean()
            .reset_index().rename(columns={"revenue": "rolling_avg"})
        )

    cur_daily = cur_daily.merge(rolling_avg, on="store_clean", how="left")
    cur_daily["threshold"] = cur_daily["rolling_avg"] * cfg.get("LOW_SALES_PCT", 0.50)
    low_sales = cur_daily[
        (cur_daily["revenue"] < cur_daily["threshold"])
        & (cur_daily["revenue"] > cfg.get("MIN_TRADING_REVENUE", 500))
    ].copy()

    if low_sales.empty:
        parts.append("_No low sales days detected._\n")
    else:
        low_sales["date_str"] = low_sales["date"].dt.strftime("%Y-%m-%d")
        low_sales["on_duty_staff"] = low_sales.apply(
            lambda r: _get_scheduled_staff(schedule_df, r["date_str"], r["store_clean"]), axis=1
        )
        low_sales["vs_avg"] = (low_sales["revenue"] / low_sales["rolling_avg"] * 100).round(1).astype(str) + "%"
        parts.append(md_table(
            low_sales[["date_str", "store_clean", "on_duty_staff", "revenue", "rolling_avg", "vs_avg"]].rename(
                columns={"date_str": "date", "store_clean": "store"}
            ).sort_values(["store", "date"]),
            formatters={"revenue": fmt_rub, "rolling_avg": fmt_rub}
        ))

    # ── 4.2 Low Cash Ratio (Theft / Discrepancy Signal + Employee Link) ─
    parts.append(section("Cash Discrepancy & Theft Signals", 3))
    parts.append("_Identifies days where the cash-to-total sales ratio dropped significantly below the store's baseline, linked to the barista/cashier on duty._\n")

    # Determine baseline cash ratio per store
    if not baseline_df.empty:
        base_valid = baseline_df[~baseline_df["is_return"]] if "is_return" in baseline_df.columns else baseline_df
        base_txn_type = "transaction_type" if "transaction_type" in base_valid.columns else "payment_type"
        base_cash_mask = base_valid[base_txn_type].astype(str).str.lower().str.contains("cash|нал", regex=True)
        base_valid["is_cash"] = base_cash_mask
        
        base_store_cash = base_valid.groupby("store_clean").agg(
            tot_cash=("revenue", lambda s: s[base_valid.loc[s.index, "is_cash"]].sum()),
            tot_rev=("revenue", "sum")
        ).reset_index()
        base_store_cash["baseline_cash_ratio"] = base_store_cash.apply(
            lambda r: r["tot_cash"] / r["tot_rev"] if r["tot_rev"] > 0 else 0.0, axis=1
        )
        baseline_ratio = base_store_cash[["store_clean", "baseline_cash_ratio"]]
    else:
        cur_txn_type = "transaction_type" if "transaction_type" in cur_valid.columns else "payment_type"
        cur_cash_mask = cur_valid[cur_txn_type].astype(str).str.lower().str.contains("cash|нал", regex=True)
        cur_valid_tmp = cur_valid.copy()
        cur_valid_tmp["is_cash"] = cur_cash_mask
        base_store_cash = cur_valid_tmp.groupby("store_clean").agg(
            tot_cash=("revenue", lambda s: s[cur_valid_tmp.loc[s.index, "is_cash"]].sum()),
            tot_rev=("revenue", "sum")
        ).reset_index()
        base_store_cash["baseline_cash_ratio"] = base_store_cash.apply(
            lambda r: r["tot_cash"] / r["tot_rev"] if r["tot_rev"] > 0 else 0.20, axis=1
        )
        baseline_ratio = base_store_cash[["store_clean", "baseline_cash_ratio"]]

    cur_txn_type = "transaction_type" if "transaction_type" in cur_valid.columns else "payment_type"
    cur_valid["is_cash"] = cur_valid[cur_txn_type].astype(str).str.lower().str.contains("cash|нал", regex=True)

    cur_daily_cash = cur_valid.groupby(["store_clean", "date"]).agg(
        cash=("revenue", lambda s: s[cur_valid.loc[s.index, "is_cash"]].sum()),
        total=("revenue", "sum"),
    ).reset_index()

    cur_daily_cash["cash_ratio"] = cur_daily_cash["cash"] / cur_daily_cash["total"].replace(0, float("nan"))
    cur_daily_cash = cur_daily_cash.merge(baseline_ratio, on="store_clean", how="left")
    cur_daily_cash["drop"] = cur_daily_cash["baseline_cash_ratio"] - cur_daily_cash["cash_ratio"]

    low_cash = cur_daily_cash[
        (cur_daily_cash["drop"] >= cfg.get("LOW_CASH_DROP_PCT", 0.25))
        & (cur_daily_cash["total"] > cfg.get("MIN_TRADING_REVENUE", 500))
        & (cur_daily_cash["baseline_cash_ratio"] > 0.10) # Only alert if store normally has cash receipts
    ].copy()

    if low_cash.empty:
        parts.append("_No unusual cash ratio drops detected._\n")
    else:
        low_cash["date_str"] = low_cash["date"].dt.strftime("%Y-%m-%d")
        low_cash["on_duty_staff"] = low_cash.apply(
            lambda r: _get_scheduled_staff(schedule_df, r["date_str"], r["store_clean"]), axis=1
        )
        low_cash["cash_%"] = (low_cash["cash_ratio"] * 100).round(1).astype(str) + "%"
        low_cash["baseline_%"] = (low_cash["baseline_cash_ratio"] * 100).round(1).astype(str) + "%"
        low_cash["drop_%"] = "-" + (low_cash["drop"] * 100).round(1).astype(str) + "%"
        low_cash["alert"] = low_cash.apply(
            lambda r: "🚨 High Alert" if (r["drop"] >= 0.30 or r["cash"] == 0) else "⚠️ Notice",
            axis=1
        )

        parts.append(md_table(
            low_cash[[
                "date_str", "store_clean", "on_duty_staff", "cash", "total",
                "cash_%", "baseline_%", "drop_%", "alert"
            ]].rename(columns={"date_str": "date", "store_clean": "store"}).sort_values(["store", "date"]),
            formatters={"cash": fmt_rub, "total": fmt_rub}
        ))

    # ── 4.3 Long Sales Gaps (Employee Absence) ────────────────────
    parts.append(section("Long Sales Gaps (Employee Absence)", 3))

    gap_rows = []
    if "datetime" in cur_valid.columns:
        for (store, date), grp in (
            cur_valid.sort_values("datetime")
            .groupby(["store_clean", "date"])
        ):
            times = grp["datetime"].sort_values().reset_index(drop=True)
            for i in range(1, len(times)):
                gap_min = (times[i] - times[i - 1]).total_seconds() / 60
                if gap_min >= cfg.get("SALES_GAP_MINUTES", 60):
                    date_str = pd.to_datetime(date).strftime("%Y-%m-%d")
                    gap_rows.append({
                        "date":          date_str,
                        "store":         store,
                        "on_duty_staff": _get_scheduled_staff(schedule_df, date_str, store),
                        "gap_start":     times[i - 1].strftime("%H:%M"),
                        "gap_end":       times[i].strftime("%H:%M"),
                        "gap_min":       int(gap_min),
                    })

    if not gap_rows:
        parts.append("_No long sales gaps detected._\n")
    else:
        gap_df = pd.DataFrame(gap_rows).sort_values(["store", "date", "gap_start"])
        parts.append(md_table(gap_df))

    # ── 4.4 Tapioca Gaps (Ingredient Stockouts) ───────────────────
    parts.append(section("Tapioca Preparation Gaps", 3))

    if "product" in cur_txn.columns and "datetime" in cur_txn.columns:
        tap_keyword = cfg.get("TAPIOCA_KEYWORD", "тапиок")
        tap_mask = (
            cur_txn["product"].astype(str).str.contains(tap_keyword, case=False, na=False)
            & ~cur_txn["product"].astype(str).str.contains("не тапиок", case=False, na=False)
            & (~cur_txn["is_return"] if "is_return" in cur_txn.columns else True)
            & (
                (cur_txn["qty"] > 0 if "qty" in cur_txn.columns else True)
                | (cur_txn["transaction_type"] == "Non-Fiscal" if "transaction_type" in cur_txn.columns else False)
            )
        )
        tap_txn = cur_txn[tap_mask].sort_values("datetime")

        tap_gaps = []
        for (store, date), grp in tap_txn.groupby(["store_clean", "date"]):
            times = grp["datetime"].sort_values().reset_index(drop=True)
            for i in range(1, len(times)):
                gap_min = (times[i] - times[i - 1]).total_seconds() / 60
                if gap_min >= cfg.get("TAPIOCA_GAP_MINUTES", 60):
                    # Revenue during the gap
                    between_rev = cur_txn[
                        (cur_txn["store_clean"] == store)
                        & (cur_txn["datetime"] > times[i - 1])
                        & (cur_txn["datetime"] < times[i])
                        & (~cur_txn["is_return"] if "is_return" in cur_txn.columns else True)
                    ]["revenue"].sum()
                    
                    if between_rev >= 1000:
                        date_str = pd.to_datetime(date).strftime("%Y-%m-%d")
                        tap_gaps.append({
                            "date":          date_str,
                            "store":         store,
                            "on_duty_staff": _get_scheduled_staff(schedule_df, date_str, store),
                            "gap_start":     times[i - 1].strftime("%H:%M"),
                            "gap_end":       times[i].strftime("%H:%M"),
                            "gap_min":       int(gap_min),
                            "rev_in_gap":    int(round(between_rev)),
                        })

        if not tap_gaps:
            parts.append("_No tapioca gaps detected._\n")
        else:
            tap_df = pd.DataFrame(tap_gaps).sort_values(["store", "date", "gap_start"])
            parts.append(md_table(
                tap_df,
                formatters={"rev_in_gap": fmt_rub}
            ))

    return "\n".join(parts)

