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
    """
    Load products_mapped.csv.
    Columns: product_ru, status, category, subcategory, product (EN name), variant
    Returns a DataFrame with a clean join key 'product_ru' → transactions 'product'.
    """
    import os
    if not os.path.exists(path):
        return pd.DataFrame()

    h = pd.read_csv(path, encoding="utf-8")

    required = {"product_ru", "category", "subcategory", "product"}
    if not required.issubset(h.columns):
        return pd.DataFrame()

    # Only keep mapped rows
    if "status" in h.columns:
        h = h[h["status"] == "mapped"]

    h = h[["product_ru", "category", "subcategory", "product", "variant"]].copy()
    h.columns = ["product", "category", "subcategory", "product_en", "variant"]
    return h.reset_index(drop=True)
