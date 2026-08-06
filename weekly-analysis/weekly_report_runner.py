"""
Weekly Report Runner Script — Production Runner for Databricks Jobs & Local Execution
Runs weekly report generation pipeline and writes markdown and styled HTML outputs.
"""
import os
import sys
from datetime import datetime, timedelta

# Import config and modules
import config
from modules.loader import (
    load_transactions,
    load_daily_sales,
    load_product_hierarchy,
    load_employee_schedule,
)
from modules import sales, basket, product_health, anomaly, publisher
from modules.utils import md_to_html


def run_weekly_report(week_start=None, spark=None, push_remote=True, token=None):
    (
        week_start,
        week_end,
        prior_start,
        prior_end,
        rolling_start,
        rolling_end,
    ) = config.get_week_bounds(week_start)

    print(f"==================================================")
    print(f"Generating Weekly Report: {week_start} to {week_end}")
    print(f"Prior Period            : {prior_start} to {prior_end}")
    print(f"4W Baseline Period      : {rolling_start} to {rolling_end}")
    print(f"==================================================")

    # 1. Load Data
    hierarchy = load_product_hierarchy(config.HIERARCHY_CSV)
    
    if spark is not None:
        cur_txn = load_transactions(spark, config.TRANSACTIONS_TABLE, week_start, week_end)
        pri_txn = load_transactions(spark, config.TRANSACTIONS_TABLE, prior_start, prior_end)
        cur_sales = load_daily_sales(spark, config.DAILY_SALES_TABLE, week_start, week_end)
        pri_sales = load_daily_sales(spark, config.DAILY_SALES_TABLE, prior_start, prior_end)
        rolling_sales = load_daily_sales(spark, config.DAILY_SALES_TABLE, rolling_start, rolling_end)
        schedule_df = load_employee_schedule(spark, config.EMPLOYEE_SCHEDULE_TABLE, week_start, week_end)
    else:
        # Standalone mock / local fallback
        print("Note: Running in standalone mode without active Spark session.")
        cur_txn, pri_txn = pd.DataFrame(), pd.DataFrame()
        cur_sales, pri_sales, rolling_sales = pd.DataFrame(), pd.DataFrame(), pd.DataFrame()
        schedule_df = pd.DataFrame()

    anomaly_cfg = {
        "LOW_SALES_PCT": config.LOW_SALES_PCT,
        "LOW_CASH_DROP_PCT": config.LOW_CASH_DROP_PCT,
        "SALES_GAP_MINUTES": config.SALES_GAP_MINUTES,
        "TAPIOCA_GAP_MINUTES": config.TAPIOCA_GAP_MINUTES,
        "TAPIOCA_KEYWORD": config.TAPIOCA_KEYWORD,
        "MIN_TRADING_REVENUE": config.MIN_TRADING_REVENUE,
    }

    # 2. Build Report Sections
    header = f"""# Weekly Business & Operational Report: {week_start} to {week_end}

_Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}_

---
"""

    sections = [
        header,
        sales.build(cur_sales, pri_sales, rolling_sales, cur_txn, pri_txn),
        "\n---\n",
        basket.build(cur_txn, pri_txn, hierarchy),
        "\n---\n",
        product_health.build(cur_txn, pri_txn, hierarchy),
        "\n---\n",
        anomaly.build(
            current_txn=cur_txn,
            schedule_df=schedule_df,
            cfg=anomaly_cfg,
            spark=spark,
            transactions_table=config.TRANSACTIONS_TABLE,
            week_start=week_start,
            week_end=week_end,
        ),
    ]

    report_md = "\n".join(sections)

    # 3. Save Local Markdown and HTML
    base_name = f"{week_start}_weekly_report"
    report_title = f"Weekly Report: {week_start} to {week_end}"
    html_content = md_to_html(report_md, title=report_title)

    os.makedirs(config.ANALYSIS_DIR, exist_ok=True)
    md_path = os.path.join(config.ANALYSIS_DIR, f"{base_name}.md")
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(report_md)
    print(f"MD Report saved   → {md_path}")

    os.makedirs(config.ANALYSIS_HTML_DIR, exist_ok=True)
    html_path = os.path.join(config.ANALYSIS_HTML_DIR, f"{base_name}.html")
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(html_content)
    print(f"HTML Report saved → {html_path}")

    # 4. Automated Publishing to GitHub Pages (bobacafe.net/internal/weekly/)
    publisher.publish_report(
        report_md=report_md,
        week_start=week_start,
        week_end=week_end,
        docs_root=config.DOCS_INTERNAL_DIR,
        push_remote=push_remote,
        token=token,
        repo=config.GITHUB_REPO,
        branch=config.GITHUB_BRANCH,
    )

    return md_path, html_path


if __name__ == "__main__":
    run_weekly_report()
