"""
Phase 2 Verification Test Script
Tests:
1. sales.py Weekday vs Weekend split and pattern categorization.
2. basket.py multi-tier attach intelligence (Food, Toppings, Multi-Drink) and upsell gap calculation.
3. product_health.py menu decision signals (Promote, Demote, Cut).
"""
import pandas as pd
from modules import sales, basket, product_health

def test_sales_weekday_weekend():
    print("--- Testing sales.py: Weekday vs. Weekend Dynamics ---")
    cur_sales = pd.DataFrame([
        {"date": "2026-03-30", "store": "НОВО КП", "payment_type": "card", "revenue": 20000}, # Mon
        {"date": "2026-03-31", "store": "НОВО КП", "payment_type": "card", "revenue": 25000}, # Tue
        {"date": "2026-04-03", "store": "НОВО КП", "payment_type": "card", "revenue": 50000}, # Fri (Weekend)
        {"date": "2026-04-04", "store": "НОВО КП", "payment_type": "card", "revenue": 60000}, # Sat (Weekend)
        {"date": "2026-03-30", "store": "СОВЕТОВ", "payment_type": "card", "revenue": 10000},
        {"date": "2026-04-04", "store": "СОВЕТОВ", "payment_type": "card", "revenue": 15000},
    ])

    pri_sales = pd.DataFrame([
        {"date": "2026-03-23", "store": "НОВО КП", "payment_type": "card", "revenue": 18000},
        {"date": "2026-03-24", "store": "НОВО КП", "payment_type": "card", "revenue": 20000},
        {"date": "2026-03-27", "store": "НОВО КП", "payment_type": "card", "revenue": 40000},
        {"date": "2026-03-28", "store": "НОВО КП", "payment_type": "card", "revenue": 45000},
        {"date": "2026-03-23", "store": "СОВЕТОВ", "payment_type": "card", "revenue": 15000},
        {"date": "2026-03-28", "store": "СОВЕТОВ", "payment_type": "card", "revenue": 20000},
    ])

    result = sales.build(cur_sales, pri_sales)
    assert "Weekday (Mon–Thu) vs. Weekend (Fri–Sun) Dynamics" in result
    assert "weekend_share" in result
    print("[OK] sales.py Weekday vs Weekend tests passed")

def test_basket_attach_intelligence():
    print("\n--- Testing basket.py: Attach Rates & Upsell Gap ---")
    hierarchy = pd.DataFrame([
        {"product": "Boba Classic", "category": "Drink", "subcategory": "Milk Tea", "product_en": "Boba Classic", "variant": "", "featured": 1},
        {"product": "Mochi Strawberry", "category": "Dessert", "subcategory": "Mochi", "product_en": "Mochi Strawberry", "variant": "", "featured": 0},
    ])

    # Store A: High food attach
    # Store B: Low food attach
    cur_txn = pd.DataFrame([
        # Store A: 50 drink orders, 20 with mochi (40% attach)
        * [{"store_name": "Store A", "order_number": i, "is_return": False, "revenue": 350, "transaction_type": "Card", "online": False, "product": "Boba Classic", "qty": 1} for i in range(1, 51)],
        * [{"store_name": "Store A", "order_number": i, "is_return": False, "revenue": 200, "transaction_type": "Card", "online": False, "product": "Mochi Strawberry", "qty": 1} for i in range(1, 21)],
        # Store B: 50 drink orders, 2 with mochi (4% attach)
        * [{"store_name": "Store B", "order_number": 100 + i, "is_return": False, "revenue": 350, "transaction_type": "Card", "online": False, "product": "Boba Classic", "qty": 1} for i in range(1, 51)],
        * [{"store_name": "Store B", "order_number": 100 + i, "is_return": False, "revenue": 200, "transaction_type": "Card", "online": False, "product": "Mochi Strawberry", "qty": 1} for i in range(1, 3)],
    ])

    pri_txn = pd.DataFrame([
        * [{"store_name": "Store A", "order_number": 200 + i, "is_return": False, "revenue": 350, "transaction_type": "Card", "online": False, "product": "Boba Classic", "qty": 1} for i in range(1, 41)],
        * [{"store_name": "Store B", "order_number": 300 + i, "is_return": False, "revenue": 350, "transaction_type": "Card", "online": False, "product": "Boba Classic", "qty": 1} for i in range(1, 41)],
    ])

    result = basket.build(cur_txn, pri_txn, hierarchy)
    assert "Attach Rates & Upsell Opportunity Gap" in result
    assert "food_attach" in result
    assert "topping_attach" in result
    assert "multi_drink_pct" in result
    assert "Network Upsell Opportunity" in result
    print("[OK] basket.py attach intelligence tests passed")

def test_product_decision_signals():
    print("\n--- Testing product_health.py: Menu Decision Signals ---")
    hierarchy = pd.DataFrame([
        {"product": "Boba Star", "category": "Drink", "subcategory": "Bubble tea", "product_en": "Boba Star", "variant": "", "featured": 1},
        {"product": "Hidden Gem Tea", "category": "Drink", "subcategory": "Fruit tea", "product_en": "Hidden Gem Tea", "variant": "", "featured": 0},
        {"product": "Old Boring Drink", "category": "Drink", "subcategory": "Tea", "product_en": "Old Boring Drink", "variant": "", "featured": 0},
    ])

    cur_txn = pd.DataFrame([
        # Featured item falling
        * [{"product": "Boba Star", "revenue": 100, "qty": 1, "is_return": False} for _ in range(25)], # 2,500 ₽ (< 3,000)
        # Unfeatured item surging
        * [{"product": "Hidden Gem Tea", "revenue": 350, "qty": 1, "is_return": False} for _ in range(25)], # 8,750 ₽ (growing)
        # Low tail product
        * [{"product": "Old Boring Drink", "revenue": 200, "qty": 1, "is_return": False} for _ in range(5)], # 1,000 ₽ (< 2,000)
    ])

    pri_txn = pd.DataFrame([
        * [{"product": "Boba Star", "revenue": 100, "qty": 1, "is_return": False} for _ in range(60)], # 6,000 ₽
        * [{"product": "Hidden Gem Tea", "revenue": 350, "qty": 1, "is_return": False} for _ in range(10)], # 3,500 ₽
        * [{"product": "Old Boring Drink", "revenue": 200, "qty": 1, "is_return": False} for _ in range(15)], # 3,000 ₽
    ])

    result = product_health.build(cur_txn, pri_txn, hierarchy)
    assert "Menu Decision Signals & Rationalization" in result
    assert "🌟 Promote" in result
    assert "⚠️ Review / Demote" in result
    assert "✂️ Cut / Replace" in result
    print("[OK] product_health.py decision signals tests passed")

if __name__ == "__main__":
    test_sales_weekday_weekend()
    test_basket_attach_intelligence()
    test_product_decision_signals()
    print("\n=================================")
    print("ALL PHASE 2 TESTS PASSED!")
    print("=================================")
