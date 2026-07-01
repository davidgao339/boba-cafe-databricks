"""
Weekly report configuration — edit thresholds here.
"""
import os
from datetime import datetime, timedelta

# ── Date Range ────────────────────────────────────────────────────
# Set WEEK_START manually or leave None to auto-detect last Monday
WEEK_START = None

def get_week_bounds(week_start=None):
    if week_start:
        start = datetime.strptime(week_start, "%Y-%m-%d")
    else:
        today = datetime.now()
        start = today - timedelta(days=today.weekday() + 7)  # last Monday
    end = start + timedelta(days=6)
    prior_start = start - timedelta(days=7)
    prior_end   = start - timedelta(days=1)
    return (
        start.strftime("%Y-%m-%d"),
        end.strftime("%Y-%m-%d"),
        prior_start.strftime("%Y-%m-%d"),
        prior_end.strftime("%Y-%m-%d"),
    )

# ── Delta Tables ─────────────────────────────────────────────────
DATABRICKS_REPO = "/Workspace/Users/davidgao734@gmail.com/boba-cafe/POS"
TRANSACTIONS_TABLE  = "workspace.default.transactions"
DAILY_SALES_TABLE   = "workspace.default.daily_sales_v2"

# ── Product Hierarchy ────────────────────────────────────────────
HIERARCHY_CSV = "https://docs.google.com/spreadsheets/d/e/2PACX-1vS4Ot_b26DzF-VNSVhMTH9WeCXz5zFR9cavGA9U6S8X1VlGkYPbbIkT4QydxIENgRb79ISHEvRlZR8E/pubhtml"

# ── Anomaly Thresholds ───────────────────────────────────────────
LOW_SALES_PCT          = 0.50   # flag if daily revenue < 50% of 4-week rolling avg
LOW_CASH_DROP_PCT      = 0.30   # flag if cash share drops 30%+ vs store baseline
SALES_GAP_MINUTES      = 60     # flag intra-day sales gaps > 60 min
TAPIOCA_GAP_MINUTES    = 60     # flag tapioca gaps > 60 min
TAPIOCA_KEYWORD        = "тапиок"
MIN_TRADING_REVENUE    = 500    # ignore days with < 500 revenue (closed/near-closed)

# ── Output ────────────────────────────────────────────────────────
ANALYSIS_DIR      = os.path.join(HERE, "analysis")
ANALYSIS_HTML_DIR = os.path.join(HERE, "analysis-html")

