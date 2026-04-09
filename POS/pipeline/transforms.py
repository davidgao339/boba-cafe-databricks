"""
Data transformations: raw API data → transactions, daily_sales, product_sales.
All storage uses Delta tables via PySpark.
"""
import pandas as pd
from pyspark.sql import SparkSession, functions as F
from pyspark.sql.types import (
    StructType, StructField, StringType, DoubleType, BooleanType,
    IntegerType, TimestampType, DateType,
)
from delta.tables import DeltaTable


def _get_spark():
    return SparkSession.builder.getOrCreate()


# -- Schema definitions for Delta tables --

TRANSACTIONS_SCHEMA = StructType([
    StructField("datetime", TimestampType()),
    StructField("date", DateType()),
    StructField("order_number", StringType()),
    StructField("store_name", StringType()),
    StructField("rnm", StringType()),
    StructField("transaction_type", StringType()),
    StructField("customer_name", StringType()),
    StructField("online", BooleanType()),
    StructField("product", StringType()),
    StructField("is_return", BooleanType()),
    StructField("is_topping", BooleanType()),
    StructField("qty", DoubleType()),
    StructField("revenue", DoubleType()),
    StructField("discount_amount", DoubleType()),
])

DAILY_SALES_SCHEMA = StructType([
    StructField("date", DateType()),
    StructField("store", StringType()),
    StructField("payment_type", StringType()),
    StructField("revenue", DoubleType()),
])

PRODUCT_SALES_SCHEMA = StructType([
    StructField("date", DateType()),
    StructField("store", StringType()),
    StructField("product", StringType()),
    StructField("qty", DoubleType()),
    StructField("revenue", DoubleType()),
])


# -- Transforms --

def build_transactions(raw_data):
    """Transform raw API line items into the transactions DataFrame."""
    if not raw_data:
        return pd.DataFrame()

    df = pd.DataFrame(raw_data)

    df["datetime"] = pd.to_datetime(df["datetime"], format="mixed")
    df["date"] = df["datetime"].dt.strftime("%Y-%m-%d")

    sign = df["is_return"].apply(lambda x: -1 if x else 1)
    df["qty"] = df["qty_raw"] * sign
    df["standard_revenue"] = df["revenue_raw"] * sign

    # Online orders: revenue = discount_amount (aggregator commission model)
    df["revenue"] = df.apply(
        lambda r: r["discount_amount"] * sign[r.name] if r["online"] else r["standard_revenue"],
        axis=1,
    )

    df["customer_name"] = df["customer_name"].fillna("")
    df["online"] = df["online"].astype(bool)
    df["is_topping"] = df["is_topping"].astype(bool)

    cols = [
        "datetime", "date", "order_number", "store_name", "rnm",
        "transaction_type", "customer_name", "online",
        "product", "is_return", "is_topping",
        "qty", "revenue", "discount_amount",
    ]
    return df[cols]


def build_daily_sales(transactions_df):
    """
    Aggregate transactions into daily sales by store and payment type.
    Columns: date, store, payment_type, revenue
    """
    if transactions_df.empty:
        return pd.DataFrame(columns=["date", "store", "payment_type", "revenue"])

    df = transactions_df.copy()

    def classify(row):
        if row["online"]:
            return "online"
        elif row["transaction_type"] == "Cash":
            return "cash"
        else:
            return "card"

    df["payment_type"] = df.apply(classify, axis=1)

    result = (
        df.groupby(["date", "store_name", "payment_type"], as_index=False)["revenue"]
        .sum()
        .rename(columns={"store_name": "store"})
    )
    result["revenue"] = result["revenue"].round().astype(int)
    return result.sort_values(["date", "store", "payment_type"]).reset_index(drop=True)


def build_product_sales(transactions_df):
    """
    Aggregate transactions into product-level sales by date and store.
    Columns: date, store, product, qty, revenue
    """
    if transactions_df.empty:
        return pd.DataFrame(columns=["date", "store", "product", "qty", "revenue"])

    result = (
        transactions_df.groupby(["date", "store_name", "product"], as_index=False)
        .agg({"qty": "sum", "revenue": "sum"})
        .rename(columns={"store_name": "store"})
    )
    result["revenue"] = result["revenue"].astype(int)
    return result.sort_values(["date", "store", "revenue"], ascending=[True, True, False]).reset_index(drop=True)


# -- Delta table I/O --

def save_delta(pdf, table_name, schema, date_from, date_to):
    """
    Write a pandas DataFrame to a Delta table.
    Deletes existing rows in the date range first to avoid duplicates,
    then appends the new data.
    """
    spark = _get_spark()

    # Convert pandas → Spark with explicit schema
    sdf = spark.createDataFrame(pdf, schema=schema)

    # If the table already exists, delete rows in the target date range
    if spark.catalog.tableExists(table_name):
        dt = DeltaTable.forName(spark, table_name)
        dt.delete(F.col("date").between(date_from, date_to))
        sdf.write.mode("append").saveAsTable(table_name)
        print(f"  Replaced date range {date_from}..{date_to} in {table_name} ({pdf.shape[0]:,} rows)")
    else:
        sdf.write.mode("overwrite").saveAsTable(table_name)
        print(f"  Created {table_name} ({pdf.shape[0]:,} rows)")


def load_transactions(date_from=None, date_to=None):
    """Load transactions from the Delta table, optionally filtered by date range."""
    from pipeline.config import TRANSACTIONS_TABLE

    spark = _get_spark()

    if not spark.catalog.tableExists(TRANSACTIONS_TABLE):
        raise RuntimeError(f"Table {TRANSACTIONS_TABLE} does not exist. Run refresh_transactions first.")

    sdf = spark.table(TRANSACTIONS_TABLE)

    if date_from:
        sdf = sdf.filter(F.col("date") >= date_from)
    if date_to:
        sdf = sdf.filter(F.col("date") <= date_to)

    pdf = sdf.toPandas()
    pdf["date"] = pdf["date"].astype(str)
    return pdf
