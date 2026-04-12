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
    """Load product hierarchy CSV if it exists, else return empty DataFrame."""
    import os
    if not os.path.exists(path):
        return pd.DataFrame()
    h = pd.read_csv(path)
    required = {"product", "category", "subcategory", "product_mapped"}
    if not required.issubset(h.columns):
        return pd.DataFrame()
    return h
