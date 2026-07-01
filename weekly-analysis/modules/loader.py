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
