"""
Generate a sample weekly report demonstrating complete Phase 1, Phase 2, and Phase 3 output.
"""
import pandas as pd
from datetime import datetime, timedelta
import config
from modules import sales, basket, product_health, anomaly
from modules.utils import md_to_html

# Mock sample realistic data matching Databricks Delta tables
cur_sales = pd.DataFrame([
    {"store": "НОВО КП", "payment_type": "Безналичный расчет", "revenue": 115815},
    {"store": "НОВО КП", "payment_type": "Наличные", "revenue": 40000},
    {"store": "ОЗМОЛЛ", "payment_type": "Безналичный расчет", "revenue": 85030},
    {"store": "СОВЕТОВ", "payment_type": "Безналичный расчет", "revenue": 49008},
    {"store": "КРАСНАЯ", "payment_type": "Безналичный расчет", "revenue": 62000},
    {"store": "UNKNOWN_2898", "payment_type": "Безналичный расчет", "revenue": 0},
])

pri_sales = pd.DataFrame([
    {"store": "НОВО КП", "payment_type": "Безналичный расчет", "revenue": 95000},
    {"store": "НОВО КП", "payment_type": "Наличные", "revenue": 35845},
    {"store": "ОЗМОЛЛ", "payment_type": "Безналичный расчет", "revenue": 61450},
    {"store": "СОВЕТОВ", "payment_type": "Безналичный расчет", "revenue": 58755},
    {"store": "КРАСНАЯ", "payment_type": "Безналичный расчет", "revenue": 61000},
    {"store": "UNKNOWN_2898", "payment_type": "Безналичный расчет", "revenue": 0},
])

rolling_sales = pd.DataFrame([
    {"store": "НОВО КП", "payment_type": "Безналичный расчет", "revenue": 4 * 142000},
    {"store": "ОЗМОЛЛ", "payment_type": "Безналичный расчет", "revenue": 4 * 72000},
    {"store": "СОВЕТОВ", "payment_type": "Безналичный расчет", "revenue": 4 * 55000},
    {"store": "КРАСНАЯ", "payment_type": "Безналичный расчет", "revenue": 4 * 61500},
])

# Mock transactions
cur_txn = pd.DataFrame([
    {"date": "2026-03-30", "datetime": "2026-03-30 11:00:00", "store_name": "НОВО КП", "order_number": i, "is_return": False, "revenue": 500, "transaction_type": "Card", "online": False, "product": "Bubble Tea Wild Berries", "qty": 1} for i in range(1, 312)
] + [
    {"date": "2026-03-30", "datetime": "2026-03-30 12:00:00", "store_name": "ОЗМОЛЛ", "order_number": i, "is_return": False, "revenue": 480, "transaction_type": "Card", "online": False, "product": "Mochi Nutella", "qty": 1} for i in range(312, 489)
] + [
    {"date": "2026-03-30", "datetime": "2026-03-30 13:00:00", "store_name": "СОВЕТОВ", "order_number": i, "is_return": False, "revenue": 460, "transaction_type": "Card", "online": False, "product": "Порция тапиоки", "qty": 2} for i in range(489, 595)
] + [
    {"date": "2026-03-30", "datetime": "2026-03-30 14:00:00", "store_name": "КРАСНАЯ", "order_number": i, "is_return": False, "revenue": 470, "transaction_type": "Card", "online": False, "product": "Бабл-ти Лаймовый (чай)", "qty": 1} for i in range(595, 726)
])

pri_txn = pd.DataFrame([
    {"date": "2026-03-23", "datetime": "2026-03-23 11:00:00", "store_name": "НОВО КП", "order_number": i, "is_return": False, "revenue": 480, "transaction_type": "Card", "online": False, "product": "Bubble Tea Wild Berries", "qty": 1} for i in range(1001, 1272)
] + [
    {"date": "2026-03-23", "datetime": "2026-03-23 12:00:00", "store_name": "ОЗМОЛЛ", "order_number": i, "is_return": False, "revenue": 460, "transaction_type": "Card", "online": False, "product": "Mochi Nutella", "qty": 1} for i in range(1272, 1405)
] + [
    {"date": "2026-03-23", "datetime": "2026-03-23 13:00:00", "store_name": "СОВЕТОВ", "order_number": i, "is_return": False, "revenue": 470, "transaction_type": "Card", "online": False, "product": "Порция тапиоки", "qty": 2} for i in range(1405, 1530)
] + [
    {"date": "2026-03-23", "datetime": "2026-03-23 14:00:00", "store_name": "КРАСНАЯ", "order_number": i, "is_return": False, "revenue": 470, "transaction_type": "Card", "online": False, "product": "Бабл-ти Лаймовый (чай)", "qty": 1} for i in range(1530, 1660)
])

hierarchy = pd.DataFrame([
    {"product": "Bubble Tea Wild Berries", "category": "Drink", "subcategory": "Bubble tea", "product_en": "Bubble Tea Wild Berries", "variant": "", "featured": 1},
    {"product": "Mochi Nutella", "category": "Dessert", "subcategory": "Mochi", "product_en": "Mochi Nutella", "variant": "", "featured": 0},
])

schedule_df = pd.DataFrame([
    {"date": "2026-03-30", "store": "НОВО КП", "shift": "1 смена", "employee": "Анна Иванова"},
    {"date": "2026-03-30", "store": "НОВО КП", "shift": "2 смена", "employee": "Максим Смирнов"},
    {"date": "2026-03-31", "store": "НОВО КП", "shift": "1 смена", "employee": "Дарья Ковалева"},
    {"date": "2026-03-30", "store": "СОВЕТОВ", "shift": "весь день", "employee": "Сергей Васильев"},
    {"date": "2026-03-30", "store": "КРАСНАЯ", "shift": "1 смена", "employee": "Ольга Попова"},
    {"date": "2026-03-30", "store": "ОЗМОЛЛ", "shift": "1 смена", "employee": "Алина Морозова"},
])

report_md = "\n".join([
    "# Weekly Business & Operational Report: 2026-03-30 to 2026-04-05\n\n---\n",
    sales.build(cur_sales, pri_sales, rolling_sales, cur_txn, pri_txn),
    "\n---\n",
    basket.build(cur_txn, pri_txn, hierarchy),
    "\n---\n",
    product_health.build(cur_txn, pri_txn, hierarchy),
    "\n---\n",
    anomaly.build(current_txn=cur_txn, schedule_df=schedule_df),
])

from modules import publisher

publisher.publish_report(
    report_md=report_md,
    week_start="2026-03-30",
    week_end="2026-04-05",
    docs_root=config.DOCS_INTERNAL_DIR,
    push_remote=False,
)

with open("analysis/sample_weekly_report_complete.md", "w", encoding="utf-8") as f:
    f.write(report_md)

print("Generated sample_weekly_report_complete.md and published to docs/internal/weekly/index.html successfully!")
