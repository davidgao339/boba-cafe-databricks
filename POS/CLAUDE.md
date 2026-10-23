# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

This is a **Databricks-based POS data pipeline** for a boba tea café chain with 13+ store locations (Russia). It fetches transaction data from the SBIS retail POS API, transforms it into normalized Delta Lake tables, and supports product gap analysis.

## Running the Pipeline

All execution is done via Databricks notebook UI — there is no CLI, Makefile, or package.json.

**Incremental refresh (run in order):**
1. `1_refresh_transactions.ipynb` — Fetch from SBIS API → `transactions` Delta table
2. `2_refresh_daily_sales.ipynb` — Aggregate → `daily_sales_v2` Delta table
3. `3_refresh_product_sales.ipynb` — Aggregate → `product_sales_v2` Delta table

**Full pipeline orchestration:**
- `4_run_pipeline.ipynb` — Runs all 3 steps; set date range in the config cell
- `4_run_pipeline_auto.ipynb` — Same, but hardcoded to Jan 1 – Jun 30, 2025

**Other notebooks:**
- `backfill_google_sheet_sales.ipynb` — Import legacy 2025 sales from `data/2025_google_sheet.csv`
- `tapioca_gap_analysis.ipynb` — Detect tapioca availability gaps, output CSV + chart

## Architecture

### Data Flow

```
SBIS API → sbis_api.py → transforms.py → Delta Lake tables
```

1. `sbis_api.authenticate()` → session ID
2. `sbis_api.get_sales_points()` → 13 store terminals
3. `sbis_api.fetch_orders(sid, points, start_dt, end_dt)` → raw order list (paginated, with exponential backoff retry)
4. `transforms.build_transactions(raw_data)` → pandas DataFrame (14 cols, line-item level)
5. `transforms.save_delta(df, table, schema, date_from, date_to)` → upsert: delete range → append

Notebooks 2 and 3 read from the `transactions` Delta table (via `transforms.load_transactions()`) and aggregate into `daily_sales_v2` and `product_sales_v2`.

### Delta Tables (`workspace.default.*`)

| Table | Key Columns |
|---|---|
| `transactions` | datetime, date, order_number, store_name, rnm, transaction_type, customer_name, online, product, is_return, is_topping, qty, revenue, discount_amount |
| `daily_sales_v2` | date, store, payment_type, revenue |
| `product_sales_v2` | date, store, product, qty, revenue |

### `pipeline/` Library

| File | Purpose |
|---|---|
| `config.py` | API endpoints, terminal-to-store name mapping (13 stores), Delta table names |
| `secrets.py` | SBIS credentials — **not in repo**, must be configured locally |
| `sbis_api.py` | API client: authenticate, list stores, paginated order fetch |
| `transforms.py` | Pandas transforms, Spark StructType schemas, Delta upsert logic |

## Key Domain Logic

**Revenue calculation:**
- Online & E-Transfer orders: `revenue = discount_amount` (aggregator commission & 100% discount SBP/transfer model)
- All other orders: `revenue = qty × price − discount_amount`
- Returns: qty and revenue are negated

**Transaction types:** `Cash`, `Card`, `Mixed`, `Online`, `E-Transfer`, `Non-Fiscal`, `Unknown`

**Payment types (in `daily_sales_v2`):** `cash`, `card`, `online`, `other` (e-transfer/mixed/non-fiscal/unknown)

**Delta upsert pattern** (`save_delta`): deletes all rows in the target date range first, then appends — safe to re-run notebooks idempotently.

**Backfill deduplication:** `backfill_google_sheet_sales` only appends Google Sheet rows for (date, store) combos absent from the API-sourced data.

## Credentials

`pipeline/secrets.py` must contain:
```python
APP_CLIENT_ID = ""
LOGIN = ""
PASSWORD = ""
```
These are SBIS API credentials. The file is gitignored.

## Dependencies

- `requests` — SBIS API HTTP calls
- `pandas` — All data transformations
- `pyspark` / `delta` — Spark session and Delta Lake I/O (provided by Databricks runtime)
- `matplotlib` — Tapioca gap visualization
