"""
Sprint 1 verification test script.
Tests:
1. utils.py formatting, percentage arrows, ruble diffs, and trend status.
2. sales.py dual baseline, executive snapshot, traffic vs ticket decomposition, and store filtering.
3. product_health.py whitespace normalization, heuristic categorization, and write-off exclusion.
"""
import pandas as pd
from datetime import datetime, timedelta
from modules.utils import fmt_rub, fmt_diff_rub, fmt_pct, pct_arrow, trend_status, md_table
from modules import sales, product_health
import config

def test_utils():
    print("--- Testing utils.py ---")
    assert fmt_rub(155815) == "₽155,815", f"Expected ₽155,815, got {fmt_rub(155815)}"
    assert fmt_diff_rub(155815, 130845) == "+₽24,970", f"Expected +₽24,970, got {fmt_diff_rub(155815, 130845)}"
    assert fmt_diff_rub(39008, 51755) == "-₽12,747", f"Expected -₽12,747, got {fmt_diff_rub(39008, 51755)}"
    assert pct_arrow(120, 100) == "↑ 20.0%", f"Expected ↑ 20.0%, got {pct_arrow(120, 100)}"
    assert pct_arrow(80, 100) == "↓ 20.0%", f"Expected ↓ 20.0%, got {pct_arrow(80, 100)}"
    assert pct_arrow(100, 100) == "→ 0.0%", f"Expected → 0.0%, got {pct_arrow(100, 100)}"
    
    # Trend status tests (using realistic revenue amounts > min_revenue)
    assert trend_status(120000, 100000, 100000) == "🟢 Breakout"
    assert trend_status(120000, 80000, 140000) == "🟡 Rebound"
    assert trend_status(80000, 90000, 100000) == "🔴 Underperforming"
    assert trend_status(102000, 100000, 100000) == "⚪ Core"
    print("[OK] utils.py tests passed")

def test_sales():
    print("\n--- Testing sales.py ---")
    cur_sales = pd.DataFrame([
        {"store": "НОВО КП", "payment_type": "card", "revenue": 100000},
        {"store": "НОВО КП", "payment_type": "cash", "revenue": 55815},
        {"store": "ОЗМОЛЛ", "payment_type": "card", "revenue": 71030},
        {"store": "СОВЕТОВ", "payment_type": "card", "revenue": 39008},
        {"store": "UNKNOWN_2898", "payment_type": "card", "revenue": 0},
    ])
    pri_sales = pd.DataFrame([
        {"store": "НОВО КП", "payment_type": "card", "revenue": 85000},
        {"store": "НОВО КП", "payment_type": "cash", "revenue": 45845},
        {"store": "ОЗМОЛЛ", "payment_type": "card", "revenue": 41450},
        {"store": "СОВЕТОВ", "payment_type": "card", "revenue": 51755},
        {"store": "UNKNOWN_2898", "payment_type": "card", "revenue": 0},
    ])
    rolling_sales = pd.DataFrame([
        {"store": "НОВО КП", "payment_type": "card", "revenue": 4 * 140000},
        {"store": "ОЗМОЛЛ", "payment_type": "card", "revenue": 4 * 68000},
        {"store": "СОВЕТОВ", "payment_type": "card", "revenue": 4 * 49000},
    ])

    cur_txn = pd.DataFrame([
        {"store_name": "НОВО КП", "order_number": 1, "is_return": False, "revenue": 500, "transaction_type": "Card", "online": False},
        {"store_name": "НОВО КП", "order_number": 2, "is_return": False, "revenue": 500, "transaction_type": "Card", "online": False},
        {"store_name": "ОЗМОЛЛ", "order_number": 3, "is_return": False, "revenue": 400, "transaction_type": "Card", "online": False},
        {"store_name": "СОВЕТОВ", "order_number": 4, "is_return": False, "revenue": 350, "transaction_type": "Card", "online": False},
    ])
    pri_txn = pd.DataFrame([
        {"store_name": "НОВО КП", "order_number": 10, "is_return": False, "revenue": 450, "transaction_type": "Card", "online": False},
        {"store_name": "ОЗМОЛЛ", "order_number": 11, "is_return": False, "revenue": 380, "transaction_type": "Card", "online": False},
        {"store_name": "СОВЕТОВ", "order_number": 12, "is_return": False, "revenue": 480, "transaction_type": "Card", "online": False},
    ])

    result = sales.build(cur_sales, pri_sales, rolling_sales, cur_txn, pri_txn)
    assert "UNKNOWN_2898" not in result, "UNKNOWN_2898 with 0 revenue should be filtered"
    assert "Store Performance Matrix" in result
    assert "Traffic (Orders) vs. Ticket (Avg Basket) by Store" in result
    assert "4w_avg" in result
    print("[OK] sales.py tests passed")

def test_product_health():
    print("\n--- Testing product_health.py ---")
    hierarchy = pd.DataFrame([
        {"product": "Bubble Tea Wild Berries", "category": "Drink", "subcategory": "Bubble tea", "product_en": "Bubble Tea Wild Berries", "variant": "", "featured": 1},
        {"product": "Mochi Nutella", "category": "Dessert", "subcategory": "Mochi", "product_en": "Mochi Nutella", "variant": "", "featured": 0},
    ])

    cur_txn = pd.DataFrame([
        {"product": "Bubble Tea Wild Berries", "revenue": 1000, "qty": 3, "is_return": False},
        {"product": "Порция тапиоки", "revenue": 500, "qty": 10, "is_return": False},  # Unmapped topping -> should be Toppings & Modifiers
        {"product": "Списание- Тапиока 50 гр", "revenue": 100, "qty": 1, "is_return": False}, # Write off -> should be excluded
        {"product": "Бабл-ти  Лаймовый (чай)", "revenue": 800, "qty": 2, "is_return": False}, # Extra whitespace unmapped -> should be Drink
    ])
    pri_txn = pd.DataFrame([
        {"product": "Bubble Tea Wild Berries", "revenue": 800, "qty": 2, "is_return": False},
        {"product": "Порция тапиоки", "revenue": 300, "qty": 6, "is_return": False},
        {"product": "Бабл-ти  Лаймовый (чай)", "revenue": 700, "qty": 2, "is_return": False},
    ])

    result = product_health.build(cur_txn, pri_txn, hierarchy)
    assert "Списание" not in result, "Write-offs should be excluded"
    assert "Toppings & Modifiers" in result, "Unmapped topping should fall into Toppings & Modifiers"
    assert "Uncategorised" not in result, "No products should remain as Uncategorised"
    print("[OK] product_health.py tests passed")

if __name__ == "__main__":
    test_utils()
    test_sales()
    test_product_health()
    print("\n=================================")
    print("ALL SPRINT 1 TESTS PASSED!")
    print("=================================")
