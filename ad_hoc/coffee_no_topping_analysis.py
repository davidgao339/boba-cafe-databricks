# Databricks notebook source

# COMMAND ----------

# MAGIC %md
# MAGIC # Coffee Orders with No Toppings — Per-Store, 6-Month Rolling
# MAGIC
# MAGIC For each store and month: what % of orders include a coffee drink but zero toppings?
# MAGIC Rolling 6-month window so each month's number smooths over short-term noise.

# COMMAND ----------

import re
import pandas as pd
from datetime import datetime, timedelta, timezone
from pyspark.sql import functions as F

HIERARCHY_PATH  = "/Workspace/Users/davidgao734@gmail.com/boba-cafe/weekly-analysis/data/products_mapped.csv"
EXCLUDE_STORES  = {"АНАПА", "КПК"}
ROLLING_MONTHS  = 6
LOAD_MONTHS     = 8   # extra buffer so the first rolling window is fully populated

_VARIANT_SUFFIXES = re.compile(
    r"\s*\(шарики не включены\)"
    r"|\s*\(без шариков\)"
    r"|\s*\(no balls\)",
    flags=re.IGNORECASE,
)

# COMMAND ----------

# MAGIC %md
# MAGIC ## Load transactions

# COMMAND ----------

start_date = (datetime.now(timezone.utc) - timedelta(days=30 * LOAD_MONTHS)).strftime("%Y-%m-%d")

sdf = (
    spark.table("workspace.default.transactions")
    .filter(F.col("date") >= start_date)
    .filter(F.col("is_return")         == False)
    .filter(F.col("online")            == False)
    .filter(F.col("transaction_type")  != "Non-Fiscal")
)
df = sdf.toPandas()
df = df[~df["store_name"].isin(EXCLUDE_STORES)].copy()
df["date"] = pd.to_datetime(df["date"])

print(f"Loaded {len(df):,} rows from {df['date'].min().date()} to {df['date'].max().date()}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Tag coffee line items via product hierarchy

# COMMAND ----------

hier = pd.read_csv(HIERARCHY_PATH)
if "status" in hier.columns:
    hier = hier[hier["status"] == "mapped"]
hier = hier[["product_ru", "subcategory"]].rename(columns={"product_ru": "product_key"})

# Strip "(no balls)" variants before joining — they're still coffee drinks
df["product_key"] = df["product"].apply(
    lambda n: _VARIANT_SUFFIXES.sub("", n).strip() if isinstance(n, str) else n
)
df = df.merge(hier, on="product_key", how="left")
df["is_coffee"] = df["subcategory"] == "Coffee"

# COMMAND ----------

# MAGIC %md
# MAGIC ## Aggregate per order

# COMMAND ----------

# is_topping already exists as a column in the transactions table
order_flags = (
    df.groupby(["store_name", "order_number", "date"])
    .agg(
        has_coffee  = ("is_coffee",   "any"),
        has_topping = ("is_topping",  "any"),
    )
    .reset_index()
)
order_flags["coffee_no_topping"] = order_flags["has_coffee"] & ~order_flags["has_topping"]
order_flags["month"] = order_flags["date"].dt.to_period("M")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Monthly counts → 6-month rolling %

# COMMAND ----------

monthly = (
    order_flags
    .groupby(["store_name", "month"])
    .agg(
        total_orders      = ("order_number",      "count"),
        coffee_no_topping = ("coffee_no_topping", "sum"),
    )
    .reset_index()
    .sort_values(["store_name", "month"])
)

def add_rolling(grp):
    grp = grp.sort_values("month").copy()
    grp["rolling_orders"]      = grp["total_orders"].rolling(ROLLING_MONTHS, min_periods=1).sum()
    grp["rolling_cof_no_top"]  = grp["coffee_no_topping"].rolling(ROLLING_MONTHS, min_periods=1).sum()
    grp["pct_coffee_no_topping"] = (
        grp["rolling_cof_no_top"] / grp["rolling_orders"] * 100
    ).round(1)
    return grp

result = (
    monthly
    .groupby("store_name", group_keys=False)
    .apply(add_rolling)
    .reset_index(drop=True)
)

# Keep only the last ROLLING_MONTHS months for display (window is fully populated)
latest_months = sorted(result["month"].unique())[-ROLLING_MONTHS:]
display_df = result[result["month"].isin(latest_months)].copy()
display_df["month"] = display_df["month"].astype(str)

display(display_df[[
    "store_name", "month",
    "rolling_orders", "rolling_cof_no_top", "pct_coffee_no_topping"
]].sort_values(["store_name", "month"]))

# COMMAND ----------

# MAGIC %md
# MAGIC ## Latest rolling snapshot per store (most recent 6-month window)

# COMMAND ----------

snapshot = (
    result[result["month"] == result["month"].max()]
    [["store_name", "month", "rolling_orders", "rolling_cof_no_top", "pct_coffee_no_topping"]]
    .sort_values("pct_coffee_no_topping", ascending=False)
    .reset_index(drop=True)
)
snapshot["month"] = snapshot["month"].astype(str)
display(snapshot)
