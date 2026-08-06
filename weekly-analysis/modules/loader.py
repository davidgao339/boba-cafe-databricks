"""
Data loader — pulls transactions and daily_sales from Delta tables.
"""
import pandas as pd
from pyspark.sql import functions as F


def load_transactions(spark, table, date_from, date_to):
    sdf = (
        spark.table(table)
        .filter(F.col("date").between(date_from, date_to))
    )
    df = sdf.toPandas()
    df["datetime"] = pd.to_datetime(df["datetime"])
    df["date"] = pd.to_datetime(df["date"])
    return df


def load_daily_sales(spark, table, date_from, date_to):
    sdf = (
        spark.table(table)
        .filter(F.col("date").between(date_from, date_to))
    )
    df = sdf.toPandas()
    df["date"] = pd.to_datetime(df["date"])
    return df


def load_product_hierarchy(path):
    try:
        h = pd.read_csv(path, encoding="utf-8")
    except Exception:
        return pd.DataFrame()

    required = {"product_ru", "category", "subcategory", "product"}
    if not required.issubset(h.columns):
        return pd.DataFrame()

    if "status" in h.columns:
        h = h[h["status"] == "mapped"]

    if "featured" not in h.columns:
        h["featured"] = 0
    h = h[["product_ru", "category", "subcategory", "product", "variant", "featured"]].copy()
    h.columns = ["product", "category", "subcategory", "product_en", "variant", "featured"]
    h["featured"] = h["featured"].fillna(0).astype(int)
    return h.reset_index(drop=True)


def _fetch_schedule_from_sheet(sheet_url, date_from=None, date_to=None):
    try:
        raw = pd.read_csv(sheet_url)
        melt_cols = [
            col for col in raw.columns
            if col != "Дата" and not col.startswith("Unnamed") and not col.startswith("проверка")
        ]
        flat_df = raw.melt(id_vars="Дата", value_vars=melt_cols, var_name="store_shift", value_name="employee")
        flat_df = flat_df[
            flat_df["employee"].notna() &
            (flat_df["employee"].astype(str).str.strip() != "")
        ]
        split = flat_df["store_shift"].str.rsplit(" - ", n=1, expand=True)
        flat_df["store"] = split[0].str.strip()
        flat_df["shift"] = split[1].str.strip().str.replace(r"\.\d+$", "", regex=True) if 1 in split.columns else ""
        flat_df["date"] = pd.to_datetime(flat_df["Дата"], errors="coerce")
        flat_df = flat_df[flat_df["date"].notna()].copy()

        if date_from and date_to:
            d_from = pd.to_datetime(date_from)
            d_to = pd.to_datetime(date_to)
            flat_df = flat_df[(flat_df["date"] >= d_from) & (flat_df["date"] <= d_to)]

        return flat_df[["date", "store", "shift", "employee"]].reset_index(drop=True)
    except Exception as e:
        print(f"Note: Could not fetch schedule from live Google Sheet ({e}).")
        return pd.DataFrame()


def load_employee_schedule(spark, table, date_from, date_to, sheet_url=None):
    df = pd.DataFrame()
    if spark is not None and table:
        try:
            sdf = (
                spark.table(table)
                .filter(F.col("date").between(date_from, date_to))
            )
            df = sdf.toPandas()
            if not df.empty and "date" in df.columns:
                df["date"] = pd.to_datetime(df["date"])
        except Exception as e:
            print(f"Note: Could not query Delta table {table} ({e}).")

    if df.empty:
        # Fallback to Google Sheet
        fallback_url = sheet_url or "https://docs.google.com/spreadsheets/d/e/2PACX-1vQEUW3vd8VtYtI7vy_wpMeATDMZDuW5-y4u7jmyw0qlEaBSZ8fBdNnFKMl1yTwJmQ8mRVC2jvE812b9/pub?gid=1943990106&single=true&output=csv"
        df = _fetch_schedule_from_sheet(fallback_url, date_from, date_to)

    return df

