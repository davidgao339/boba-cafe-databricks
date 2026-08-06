import sys
import os
sys.stdout.reconfigure(encoding='utf-8')
import pandas as pd
from datetime import datetime
from modules import anomaly

def test_anomaly_with_schedule():
    print("--- Testing anomaly.py with Employee Shift Schedule Linkage ---")

    # 1. Mock Employee Schedule Snapshot (matching workspace.default.employee_schedule_snapshot schema)
    schedule_df = pd.DataFrame([
        {"date": "2026-03-30", "store": "НОВО КП", "shift": "1 смена", "employee": "Анна Иванова"},
        {"date": "2026-03-30", "store": "НОВО КП", "shift": "2 смена", "employee": "Максим Смирнов"},
        {"date": "2026-03-31", "store": "НОВО КП", "shift": "1 смена", "employee": "Дарья Ковалева"},
        {"date": "2026-03-30", "store": "СОВЕТОВ", "shift": "весь день", "employee": "Сергей Васильев"},
    ])

    # 2. Mock 4-week rolling baseline transactions
    # НОВО КП has 30% cash baseline
    # СОВЕТОВ has 35% cash baseline
    base_rows = []
    for d in range(1, 29):
        dt_str = f"2026-03-{d:02d}"
        base_rows.append({"date": dt_str, "datetime": f"{dt_str} 12:00:00", "store_name": "НОВО КП", "transaction_type": "Cash", "revenue": 15000, "is_return": False})
        base_rows.append({"date": dt_str, "datetime": f"{dt_str} 14:00:00", "store_name": "НОВО КП", "transaction_type": "Card", "revenue": 35000, "is_return": False})
        base_rows.append({"date": dt_str, "datetime": f"{dt_str} 12:00:00", "store_name": "СОВЕТОВ", "transaction_type": "Cash", "revenue": 7000, "is_return": False})
        base_rows.append({"date": dt_str, "datetime": f"{dt_str} 14:00:00", "store_name": "СОВЕТОВ", "transaction_type": "Card", "revenue": 13000, "is_return": False})
    rolling_txn = pd.DataFrame(base_rows)

    # 3. Mock Current Week Transactions
    # On 2026-03-30: НОВО КП cash drops from 30% to 0% (Cash theft/discrepancy anomaly on Anna & Maxim's shift)
    # On 2026-03-30: СОВЕТОВ has 90 min sales gap (Employee absence on Sergey's shift)
    cur_rows = [
        # НОВО КП: 2026-03-30: 0 cash, 50,000 card
        {"date": "2026-03-30", "datetime": "2026-03-30 10:00:00", "store_name": "НОВО КП", "transaction_type": "Card", "revenue": 25000, "product": "Bubble Tea", "qty": 1, "is_return": False},
        {"date": "2026-03-30", "datetime": "2026-03-30 16:00:00", "store_name": "НОВО КП", "transaction_type": "Card", "revenue": 25000, "product": "Bubble Tea", "qty": 1, "is_return": False},
        # НОВО КП: 2026-03-31: normal 15k cash, 35k card
        {"date": "2026-03-31", "datetime": "2026-03-31 10:00:00", "store_name": "НОВО КП", "transaction_type": "Cash", "revenue": 15000, "product": "Bubble Tea", "qty": 1, "is_return": False},
        {"date": "2026-03-31", "datetime": "2026-03-31 16:00:00", "store_name": "НОВО КП", "transaction_type": "Card", "revenue": 35000, "product": "Bubble Tea", "qty": 1, "is_return": False},
        
        # СОВЕТОВ: 2026-03-30: sales gap from 11:00 to 13:00 (120 minutes)
        {"date": "2026-03-30", "datetime": "2026-03-30 11:00:00", "store_name": "СОВЕТОВ", "transaction_type": "Card", "revenue": 5000, "product": "Bubble Tea", "qty": 1, "is_return": False},
        {"date": "2026-03-30", "datetime": "2026-03-30 13:00:00", "store_name": "СОВЕТОВ", "transaction_type": "Cash", "revenue": 5000, "product": "Bubble Tea", "qty": 1, "is_return": False},
    ]
    cur_txn = pd.DataFrame(cur_rows)

    cfg = {
        "LOW_SALES_PCT": 0.50,
        "LOW_CASH_DROP_PCT": 0.25,
        "SALES_GAP_MINUTES": 60,
        "TAPIOCA_GAP_MINUTES": 60,
        "TAPIOCA_KEYWORD": "тапиок",
        "MIN_TRADING_REVENUE": 500,
    }

    result = anomaly.build(
        current_txn=cur_txn,
        rolling_txn=rolling_txn,
        schedule_df=schedule_df,
        cfg=cfg
    )

    print("Output Result Snippet:\n")
    print(result)

    # Verifications
    assert "Cash Discrepancy & Theft Signals" in result
    assert "НОВО КП" in result
    assert "Анна Иванова (1 смена), Максим Смирнов (2 смена)" in result
    assert "🚨 High Alert" in result
    assert "Long Sales Gaps (Employee Absence)" in result
    assert "Сергей Васильев (весь день)" in result

    print("\n[OK] Anomaly module successfully linked to Employee Shift Schedule!")

if __name__ == "__main__":
    test_anomaly_with_schedule()
