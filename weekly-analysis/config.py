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
    prior_start   = start - timedelta(days=7)
    prior_end     = start - timedelta(days=1)
    rolling_start = start - timedelta(days=28)
    rolling_end   = start - timedelta(days=1)
    return (
        start.strftime("%Y-%m-%d"),
        end.strftime("%Y-%m-%d"),
        prior_start.strftime("%Y-%m-%d"),
        prior_end.strftime("%Y-%m-%d"),
        rolling_start.strftime("%Y-%m-%d"),
        rolling_end.strftime("%Y-%m-%d"),
    )

# ── Delta Tables ─────────────────────────────────────────────────
DATABRICKS_REPO = "/Workspace/Users/davidgao734@gmail.com/boba-cafe/POS"
TRANSACTIONS_TABLE      = "workspace.default.transactions"
DAILY_SALES_TABLE       = "workspace.default.daily_sales_v2"
EMPLOYEE_SCHEDULE_TABLE = "workspace.default.employee_schedule_snapshot"

# ── Product Hierarchy ────────────────────────────────────────────
HIERARCHY_CSV = "https://docs.google.com/spreadsheets/d/e/2PACX-1vS4Ot_b26DzF-VNSVhMTH9WeCXz5zFR9cavGA9U6S8X1VlGkYPbbIkT4QydxIENgRb79ISHEvRlZR8E/pub?output=csv"

# ── Trend Classification Thresholds ──────────────────────────────
# Used for automated store trend status badges
STATUS_BREAKOUT_PCT    = 0.05   # +5% vs 4W avg & positive WoW -> 🟢 Breakout
STATUS_DECLINE_PCT     = -0.05  # < -5% vs 4W avg & negative WoW -> 🔴 Underperforming
STATUS_STABLE_BAND_PCT = 0.03   # within +/-3% vs 4W avg -> ⚪ Stable

# ── Anomaly Thresholds ───────────────────────────────────────────
LOW_SALES_PCT          = 0.50   # flag if daily revenue < 50% of 4-week rolling avg
LOW_CASH_DROP_PCT      = 0.30   # flag if cash share drops 30%+ vs store baseline
SALES_GAP_MINUTES      = 60     # flag intra-day sales gaps > 60 min
TAPIOCA_GAP_MINUTES    = 60     # flag tapioca gaps > 60 min
TAPIOCA_KEYWORD        = "тапиок"
MIN_TRADING_REVENUE    = 500    # ignore days with < 500 revenue (closed/near-closed)

# ── Output & GitHub Pages Publishing ─────────────────────────────
_HERE = os.path.dirname(os.path.abspath(__file__)) if "__file__" in dir() else \
        "/Workspace/Users/davidgao734@gmail.com/boba-cafe/weekly-analysis"
ANALYSIS_DIR      = os.path.join(_HERE, "analysis")
ANALYSIS_HTML_DIR = os.path.join(_HERE, "analysis-html")

# GitHub Pages internal portal configuration (bobacafe.net/internal/weekly/)
GITHUB_REPO        = "davidgao339/boba-cafe-databricks"
GITHUB_BRANCH      = "main"
GITHUB_WEEKLY_PATH = "docs/internal/weekly/index.html"
DOCS_INTERNAL_DIR  = os.path.abspath(os.path.join(_HERE, "..", "docs", "internal", "weekly"))


