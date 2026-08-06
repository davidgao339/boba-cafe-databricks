import sys
import os
sys.stdout.reconfigure(encoding='utf-8')
import pandas as pd
from modules import publisher
import config

def test_publisher():
    print("--- Testing modules/publisher.py ---")

    sample_md = """# Weekly Business & Operational Report: 2026-03-30 to 2026-04-05

## 1. Store Network Overview
| store | this_week | prior_week | wow_% | 4w_avg | vs_4w_% | status |
| --- | --- | --- | --- | --- | --- | --- |
| НОВО КП | ₽155,815 | ₽130,845 | ↑ 19.1% | ₽142,000 | ↑ 9.7% | 🟢 Breakout |

## 4. Operational Anomaly & Loss Prevention
| date | store | on_duty_staff | cash | total | cash_% | baseline_% | drop_% | alert |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 2026-03-30 | НОВО КП | Анна Иванова (1 смена) | ₽0 | ₽50,000 | 0.0% | 30.0% | -30.0% | 🚨 High Alert |
"""

    week_start = "2026-03-30"
    week_end = "2026-04-05"

    latest_path, archive_path = publisher.publish_report(
        report_md=sample_md,
        week_start=week_start,
        week_end=week_end,
        docs_root=config.DOCS_INTERNAL_DIR,
        push_remote=False, # local test
    )

    print(f"Verified Latest HTML  : {latest_path}")
    print(f"Verified Archive HTML : {archive_path}")

    assert os.path.exists(latest_path), "Latest HTML file must exist"
    assert os.path.exists(archive_path), "Archive HTML file must exist"

    with open(latest_path, "r", encoding="utf-8") as f:
        content = f.read()

    assert "Внутренний портал" in content
    assert "https://bobacafe.net/internal/" in content
    assert "НОВО КП" in content
    assert "🟢 Breakout" in content
    assert "🚨 High Alert" in content

    print("\n[OK] Publisher module successfully verified!")

if __name__ == "__main__":
    test_publisher()
