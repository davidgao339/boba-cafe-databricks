# Databricks notebook source

# COMMAND ----------

# MAGIC %md
# MAGIC # Coffee Orders with No Toppings — Per-Store, Last 6 Months
# MAGIC
# MAGIC Per store: what % of orders include a coffee drink but zero toppings,
# MAGIC calculated over the last 6 full calendar months of data?

# COMMAND ----------

import re
import pandas as pd
from datetime import datetime, timedelta, timezone
from pyspark.sql import functions as F

HIERARCHY_PATH = "/Workspace/Users/davidgao734@gmail.com/boba-cafe/weekly-analysis/data/products_mapped.csv"
EXCLUDE_STORES = {"АНАПА", "КПК"}

display = globals().get("display", lambda df: print(df.to_string(index=False)))

_VARIANT_SUFFIXES = re.compile(
    r"\s*\(шарики не включены\)"
    r"|\s*\(без шариков\)"
    r"|\s*\(no balls\)",
    flags=re.IGNORECASE,
)

# COMMAND ----------

# MAGIC %md
# MAGIC ## Load transactions — last 6 months

# COMMAND ----------

# Anchor to the start of 6 full calendar months ago
today      = datetime.now(timezone.utc).date()
# e.g. if today is 2026-05-15, start = 2025-11-01
start_date = (today.replace(day=1) - timedelta(days=1)).replace(day=1)  # start of prior month
for _ in range(5):
    start_date = (start_date - timedelta(days=1)).replace(day=1)

sdf = (
    spark.table("workspace.default.transactions")
    .filter(F.col("date") >= start_date.strftime("%Y-%m-%d"))
    .filter(F.col("is_return")        == False)
    .filter(F.col("online")           == False)
    .filter(F.col("transaction_type") != "Non-Fiscal")
)
df = sdf.toPandas()
df = df[~df["store_name"].isin(EXCLUDE_STORES)].copy()
df["date"] = pd.to_datetime(df["date"])

print(f"Window : {start_date} → {today}")
print(f"Rows   : {len(df):,}")
print(f"Stores : {sorted(df['store_name'].unique())}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Tag coffee line items via product hierarchy

# COMMAND ----------

hier = pd.read_csv(HIERARCHY_PATH)
if "status" in hier.columns:
    hier = hier[hier["status"] == "mapped"]
hier = hier[["product_ru", "subcategory"]].rename(columns={"product_ru": "product_key"})

# Strip "(no balls)" suffix — those drinks are still coffee
df["product_key"] = df["product"].apply(
    lambda n: _VARIANT_SUFFIXES.sub("", n).strip() if isinstance(n, str) else n
)
df = df.merge(hier, on="product_key", how="left")
df["is_coffee"] = df["subcategory"] == "Coffee"

# COMMAND ----------

# MAGIC %md
# MAGIC ## Aggregate per order, then per store

# COMMAND ----------

# One row per order: does it contain coffee? does it contain any topping?
# is_topping comes directly from the transactions table
order_flags = (
    df.groupby(["store_name", "order_number"])
    .agg(
        has_coffee  = ("is_coffee",  "any"),
        has_topping = ("is_topping", "any"),
    )
    .reset_index()
)
order_flags["coffee_no_topping"] = order_flags["has_coffee"] & ~order_flags["has_topping"]

# Aggregate across all 6 months per store
result = (
    order_flags
    .groupby("store_name")
    .agg(
        total_orders      = ("order_number",      "count"),
        coffee_orders     = ("has_coffee",         "sum"),
        coffee_no_topping = ("coffee_no_topping",  "sum"),
    )
    .reset_index()
)
result["pct_coffee_no_topping"] = (
    result["coffee_no_topping"] / result["total_orders"] * 100
).round(1)
result["pct_of_coffee_orders"] = (
    result["coffee_no_topping"] / result["coffee_orders"] * 100
).round(1)

result = result.sort_values("pct_coffee_no_topping", ascending=False).reset_index(drop=True)

display(result[[
    "store_name",
    "total_orders",
    "coffee_orders",
    "coffee_no_topping",
    "pct_coffee_no_topping",   # % of ALL orders that are coffee with no topping
    "pct_of_coffee_orders",    # % of coffee orders specifically that have no topping
]])

# COMMAND ----------

# MAGIC %md
# MAGIC ## Month-by-month breakdown (trend view)

# COMMAND ----------

order_flags_monthly = df.groupby(["store_name", "order_number", df["date"].dt.to_period("M").rename("month")]).agg(
    has_coffee  = ("is_coffee",  "any"),
    has_topping = ("is_topping", "any"),
).reset_index()
order_flags_monthly["coffee_no_topping"] = order_flags_monthly["has_coffee"] & ~order_flags_monthly["has_topping"]

monthly = (
    order_flags_monthly
    .groupby(["store_name", "month"])
    .agg(
        total_orders      = ("order_number",      "count"),
        coffee_no_topping = ("coffee_no_topping", "sum"),
    )
    .reset_index()
    .sort_values(["store_name", "month"])
)
monthly["pct_coffee_no_topping"] = (
    monthly["coffee_no_topping"] / monthly["total_orders"] * 100
).round(1)
monthly["month"] = monthly["month"].astype(str)

display(monthly[["store_name", "month", "total_orders", "coffee_no_topping", "pct_coffee_no_topping"]])
