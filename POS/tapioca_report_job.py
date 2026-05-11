# Databricks notebook source

# COMMAND ----------

# MAGIC %md
# MAGIC # Tapioca Cooking Plan — Daily Report Job
# MAGIC Reads last 90 days from `transactions` Delta table, generates HTML, pushes to GitHub Pages.
# MAGIC
# MAGIC **Schedule:** daily. **Token:** paste your GitHub PAT into `GITHUB_TOKEN` below.

# COMMAND ----------

import math, json, base64, requests
import pandas as pd
from datetime import datetime, timedelta, timezone
from pyspark.sql import functions as F

# COMMAND ----------

# MAGIC %md
# MAGIC ## Config

# COMMAND ----------

GITHUB_REPO   = "davidgao339/boba-cafe-databricks"
GITHUB_FILE   = "docs/internal/boba/index.html"
GITHUB_BRANCH = "main"
from pipeline.secrets import GITHUB_TOKEN

ROLLING_DAYS = 90
SLOT_ORDER   = ["9:30 AM", "2:00 PM", "6:00 PM"]
PERCENTILES  = {"avg": None, "p75": 75, "p90": 90, "p95": 95, "max": 100}

# COMMAND ----------

# MAGIC %md
# MAGIC ## Load data

# COMMAND ----------

end_date   = datetime.now(timezone.utc)
start_date = end_date - timedelta(days=ROLLING_DAYS)

sdf = (
    spark.table("workspace.default.transactions")
    .filter(F.col("date") >= start_date.strftime("%Y-%m-%d"))
    .filter(F.col("product") == "Порция тапиоки")
    .filter(F.col("transaction_type") != "Non-Fiscal")
)
df = sdf.toPandas()
EXCLUDE_STORES = {"АНАПА", "КПК"}
df = df[~df["store_name"].isin(EXCLUDE_STORES)]
date_range_str = f"{start_date.strftime('%d %b %Y')} – {end_date.strftime('%d %b %Y')}"
print(f"Loaded {len(df):,} rows  |  {date_range_str}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Transform

# COMMAND ----------

df["local_dt"]   = pd.to_datetime(df["datetime"])
df["local_hour"] = df["local_dt"].dt.hour + df["local_dt"].dt.minute / 60
df["date"]       = df["local_dt"].dt.date

sign          = df["is_return"].apply(lambda x: -1 if x else 1)
df["net_qty"] = df["qty"].abs() * sign

def assign_slot(h):
    if h < 2 or h >= 20: return "6:00 PM"
    elif h < 16:          return "9:30 AM"
    else:                 return "2:00 PM"

df["slot"]     = df["local_hour"].apply(assign_slot)
df["day_type"] = df["local_dt"].dt.dayofweek.apply(lambda d: "Weekend" if d >= 5 else "Weekday")

daily = (
    df.groupby(["store_name", "date", "day_type", "slot"])["net_qty"]
    .sum().reset_index().rename(columns={"net_qty": "actual"})
)

# COMMAND ----------

# MAGIC %md
# MAGIC ## Recommendations & backtest

# COMMAND ----------

def compute_rec(daily, pct):
    if pct is None:
        agg = daily.groupby(["store_name", "slot", "day_type"])["actual"].mean()
    elif pct == 100:
        agg = daily.groupby(["store_name", "slot", "day_type"])["actual"].max()
    else:
        agg = daily.groupby(["store_name", "slot", "day_type"])["actual"].quantile(pct / 100)
    return agg.apply(math.ceil).reset_index().rename(columns={"actual": "recommended"})

recs = {k: compute_rec(daily, v) for k, v in PERCENTILES.items()}

def compute_backtest(daily, rec_df):
    bt = daily.merge(rec_df, on=["store_name", "slot", "day_type"])
    bt["under"]     = bt["actual"] > bt["recommended"]
    bt["shortfall"] = (bt["actual"] - bt["recommended"]).clip(lower=0)
    result = (
        bt.groupby(["store_name", "slot", "day_type"])
        .agg(
            recommended   = ("recommended", "first"),
            total_days    = ("actual", "count"),
            days_under    = ("under", "sum"),
            avg_shortfall = ("shortfall", lambda x: x[x > 0].mean() if (x > 0).any() else 0),
            max_shortfall = ("shortfall", "max"),
        ).reset_index()
    )
    result["pct_under"]     = (result["days_under"] / result["total_days"] * 100).round(1)
    result["avg_shortfall"] = result["avg_shortfall"].apply(lambda x: math.ceil(x) if x > 0 else 0)
    result["max_shortfall"] = result["max_shortfall"].astype(int)
    return result

backtests = {k: compute_backtest(daily, recs[k]) for k in PERCENTILES}
stores    = sorted(daily["store_name"].unique())

# COMMAND ----------

# MAGIC %md
# MAGIC ## Build JSON for JS

# COMMAND ----------

plan_data = {}
bt_data   = {}

for store in stores:
    plan_data[store] = {}
    bt_data[store]   = {}
    for slot in SLOT_ORDER:
        plan_data[store][slot] = {}
        bt_data[store][slot]   = {}
        for day_type in ["Weekday", "Weekend"]:
            plan_data[store][slot][day_type] = {}
            bt_data[store][slot][day_type]   = {}
            for key, rec_df in recs.items():
                r = rec_df.loc[
                    (rec_df.store_name == store) &
                    (rec_df.slot == slot) &
                    (rec_df.day_type == day_type), "recommended"
                ]
                rec_val = int(r.iloc[0]) if len(r) else 0
                plan_data[store][slot][day_type][key] = rec_val

                row = backtests[key].loc[
                    (backtests[key].store_name == store) &
                    (backtests[key].slot == slot) &
                    (backtests[key].day_type == day_type)
                ]
                if row.empty:
                    bt_data[store][slot][day_type][key] = {}
                else:
                    rw = row.iloc[0]
                    bt_data[store][slot][day_type][key] = {
                        "recommended":   rec_val,
                        "total_days":    int(rw["total_days"]),
                        "days_under":    int(rw["days_under"]),
                        "pct_under":     float(rw["pct_under"]),
                        "avg_shortfall": int(rw["avg_shortfall"]),
                        "max_shortfall": int(rw["max_shortfall"]),
                    }

plan_json   = json.dumps(plan_data, ensure_ascii=False)
bt_json     = json.dumps(bt_data,   ensure_ascii=False)
stores_json = json.dumps(list(stores))
slots_json  = json.dumps(SLOT_ORDER)
n_stores    = len(stores)

# COMMAND ----------

# MAGIC %md
# MAGIC ## Generate HTML

# COMMAND ----------

def plan_card(store):
    rows = "".join(f"""
        <tr>
          <td class="slot">{slot}</td>
          <td class="num pval" data-store="{store}" data-slot="{slot}" data-day="Weekday">—</td>
          <td class="num grams" data-store="{store}" data-slot="{slot}" data-day="Weekday">—</td>
          <td class="num pval" data-store="{store}" data-slot="{slot}" data-day="Weekend">—</td>
          <td class="num grams" data-store="{store}" data-slot="{slot}" data-day="Weekend">—</td>
        </tr>""" for slot in SLOT_ORDER)
    return f"""
  <div class="store-card">
    <h2>{store}</h2>
    <table>
      <thead><tr>
        <th class="th-slot">Slot</th>
        <th class="th-weekday-p">Weekday<br><small>portions</small></th>
        <th class="th-weekday-g">Weekday<br><small>grams</small></th>
        <th class="th-weekend-p">Weekend<br><small>portions</small></th>
        <th class="th-weekend-g">Weekend<br><small>grams</small></th>
      </tr></thead>
      <tbody>{rows}</tbody>
    </table>
  </div>"""

def bt_card(store):
    rows = "".join(f"""
        <tr data-store="{store}" data-slot="{slot}" data-day="{day_type}">
          <td class="slot">{slot}</td>
          <td class="dt-cell" data-day="{day_type}">{day_type}</td>
          <td class="num bt-rec">—</td>
          <td class="num bt-total">—</td>
          <td class="num bt-under bold">—</td>
          <td class="num bt-pct">—</td>
          <td class="num bt-shortfall">—</td>
        </tr>"""
        for slot in SLOT_ORDER for day_type in ["Weekday", "Weekend"])
    return f"""
  <div class="store-card wide">
    <h2>{store}</h2>
    <table>
      <thead><tr>
        <th class="th-slot">Slot</th>
        <th class="th-daytype">Day type</th>
        <th class="th-rec">Recommended</th>
        <th class="th-total">Total days</th>
        <th class="th-under">Days short</th>
        <th class="th-pct">% short</th>
        <th class="th-shortfall">Shortfall (avg / max)</th>
      </tr></thead>
      <tbody>{rows}</tbody>
    </table>
  </div>"""

plan_cards = "\n".join(plan_card(s) for s in stores)
bt_cards   = "\n".join(bt_card(s)   for s in stores)

html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>План варки тапиоки</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Roboto:wght@400;500;700&display=swap" rel="stylesheet">
<style>
:root {{
  --bg:        #f8f9fa;
  --surface:   #ffffff;
  --border:    #dadce0;
  --text-1:    #202124;
  --text-2:    #5f6368;
  --text-3:    #80868b;
  --accent:    #8d6e63;
  --accent-bg: #f4ede9;
  --shadow-sm: 0 1px 2px rgba(60,64,67,.3), 0 1px 3px rgba(60,64,67,.15);
  --shadow-md: 0 1px 3px rgba(60,64,67,.3), 0 4px 8px rgba(60,64,67,.15);
}}
* {{ box-sizing: border-box; margin: 0; padding: 0; }}
body {{ font-family: 'Roboto', Arial, sans-serif; background: var(--bg); color: var(--text-1); font-size: 16px; line-height: 1.5; }}
nav {{
  background: var(--surface); border-bottom: 1px solid var(--border);
  height: 64px; padding: 0 24px; display: flex; align-items: center;
  justify-content: space-between; position: sticky; top: 0; z-index: 100;
}}
.nav-brand {{ display: flex; align-items: center; gap: 10px; font-size: 18px; font-weight: 700; color: var(--text-1); letter-spacing: -0.01em; }}
.nav-right {{ display: flex; align-items: center; gap: 12px; }}
.nav-tag {{ font-size: 12px; font-weight: 500; color: var(--text-3); border: 1px solid var(--border); border-radius: 4px; padding: 3px 8px; }}
.nav-back {{ font-size: 13px; color: var(--accent); text-decoration: none; font-weight: 500; }}
.nav-back:hover {{ text-decoration: underline; }}
.page {{ max-width: 1200px; margin: 0 auto; padding: 40px 24px 80px; }}
.page-header {{ margin-bottom: 32px; }}
.page-title {{ font-size: 28px; font-weight: 700; color: var(--text-1); letter-spacing: -0.02em; margin-bottom: 6px; }}
.page-sub {{ font-size: 15px; color: var(--text-2); margin-bottom: 16px; }}
.lang-bar {{ display: flex; align-items: center; gap: 8px; }}
.lang-bar-label {{ font-size: 13px; color: var(--text-3); }}
.lang-seg {{ display: flex; border: 1px solid var(--border); border-radius: 6px; overflow: hidden; }}
.lang-seg button {{ padding: 4px 14px; border: none; background: var(--surface); cursor: pointer; font-size: 13px; font-weight: 500; color: var(--text-2); border-right: 1px solid var(--border); transition: background .15s; font-family: 'Roboto', Arial, sans-serif; }}
.lang-seg button:last-child {{ border-right: none; }}
.lang-seg button.active {{ background: var(--accent); color: #fff; }}
.lang-ru {{ display: none; }}
.section-label {{ font-size: 12px; font-weight: 700; letter-spacing: 0.08em; text-transform: uppercase; color: var(--text-3); margin-bottom: 14px; }}
.card {{ background: var(--surface); border: 1px solid var(--border); border-radius: 12px; padding: 20px 24px; margin-bottom: 16px; }}
.guide-header {{ display: flex; justify-content: space-between; align-items: center; cursor: pointer; user-select: none; }}
.guide-header:hover .guide-title {{ color: var(--accent); }}
.guide-title {{ font-weight: 700; font-size: 14px; color: var(--text-1); transition: color .15s; }}
.guide-chevron {{ font-size: 12px; color: var(--text-3); transition: transform .2s; }}
.guide-chevron.open {{ transform: rotate(180deg); }}
.guide-body {{ display: none; padding-top: 16px; margin-top: 16px; border-top: 1px solid var(--border); }}
.guide-body.open {{ display: block; }}
.guide-body p {{ font-size: 14px; line-height: 1.65; color: var(--text-2); margin-bottom: 14px; }}
.guide-body p:last-child {{ margin-bottom: 0; }}
.guide-body strong {{ color: var(--text-1); }}
.guide-grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 12px; margin-bottom: 14px; }}
.guide-box {{ background: var(--bg); border-radius: 8px; padding: 12px 14px; border: 1px solid var(--border); }}
.guide-box h4 {{ font-size: 11px; font-weight: 700; color: var(--text-3); text-transform: uppercase; letter-spacing: .08em; margin-bottom: 8px; }}
.guide-box ul {{ padding-left: 16px; font-size: 13px; line-height: 1.7; color: var(--text-2); }}
.slot-chip {{ display: inline-block; background: var(--accent-bg); color: var(--accent); border-radius: 4px; padding: 1px 7px; font-weight: 700; font-size: 12px; margin-right: 4px; }}
.badge {{ display: inline-block; border-radius: 4px; padding: 1px 7px; font-size: 12px; font-weight: 700; }}
.badge-red    {{ background: #fce8e6; color: #c5221f; }}
.badge-yellow {{ background: #fef7e0; color: #b06000; }}
.badge-teal   {{ background: #e6f4ea; color: #137333; }}
.toolbar {{ display: flex; flex-wrap: wrap; gap: 24px; align-items: flex-end; }}
.toolbar-group label {{ font-size: 13px; font-weight: 500; color: var(--text-2); display: block; margin-bottom: 8px; }}
.toolbar-group input {{ width: 80px; padding: 6px 10px; border: 1px solid var(--border); border-radius: 6px; font-size: 14px; font-family: 'Roboto', Arial, sans-serif; color: var(--text-1); outline: none; }}
.toolbar-group input:focus {{ border-color: var(--accent); }}
.seg {{ display: flex; border: 1px solid var(--border); border-radius: 7px; overflow: hidden; }}
.seg button {{ padding: 6px 14px; border: none; background: var(--surface); cursor: pointer; font-size: 13px; font-weight: 500; color: var(--text-2); border-right: 1px solid var(--border); transition: background .15s; font-family: 'Roboto', Arial, sans-serif; }}
.seg button:last-child {{ border-right: none; }}
.seg button.active {{ background: var(--accent); color: #fff; }}
.seg button:hover:not(.active) {{ background: var(--bg); }}
.grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(440px, 1fr)); gap: 16px; margin-bottom: 40px; }}
.grid.wide {{ grid-template-columns: repeat(auto-fill, minmax(620px, 1fr)); }}
.store-card {{ background: var(--surface); border: 1px solid var(--border); border-radius: 12px; padding: 20px 24px; transition: box-shadow .2s; }}
.store-card:hover {{ box-shadow: var(--shadow-sm); }}
.store-card h2 {{ font-size: 12px; font-weight: 700; letter-spacing: .06em; text-transform: uppercase; color: var(--text-3); margin-bottom: 12px; }}
table {{ width: 100%; border-collapse: collapse; font-size: 13px; }}
thead tr {{ background: var(--bg); }}
th {{ padding: 7px 10px; text-align: center; font-weight: 600; border-bottom: 2px solid var(--border); line-height: 1.3; color: var(--text-2); font-size: 12px; }}
th:first-child {{ text-align: left; }}
td {{ padding: 7px 10px; border-bottom: 1px solid var(--border); }}
td.slot {{ font-weight: 600; color: var(--text-2); white-space: nowrap; }}
td.num {{ text-align: center; }}
td.grams {{ color: var(--accent); font-weight: 600; }}
td.bold {{ font-weight: 700; }}
tr:last-child td {{ border-bottom: none; }}
tr:hover td {{ background: var(--bg); }}
.legend {{ display: flex; gap: 16px; margin-bottom: 12px; font-size: 13px; color: var(--text-2); }}
.legend span {{ display: flex; align-items: center; gap: 6px; }}
.dot {{ width: 8px; height: 8px; border-radius: 50%; }}
.dot-high {{ background: #fce8e6; border: 1px solid #f5c2c7; }}
.dot-med  {{ background: #fef7e0; border: 1px solid #ffecb5; }}
.dot-low  {{ background: #e6f4ea; border: 1px solid #b7dfbc; }}
.sev-high {{ background: #fef9f8; }}
.sev-med  {{ background: #fefdf5; }}
.sev-low  {{ background: #f3faf5; }}
.pct-high {{ color: #c5221f; font-weight: 700; }}
.pct-med  {{ color: #b06000; font-weight: 700; }}
.pct-low  {{ color: #137333; font-weight: 600; }}
.updated {{ font-size: 12px; color: var(--text-3); margin-top: 8px; text-align: right; }}
footer {{ padding: 20px 24px; font-size: 13px; color: var(--text-3); border-top: 1px solid var(--border); text-align: center; }}
footer a {{ color: var(--accent); text-decoration: none; }}
footer a:hover {{ text-decoration: underline; }}
@media (max-width: 640px) {{
  .page {{ padding: 24px 16px 60px; }}
  .page-title {{ font-size: 22px; }}
  .grid, .grid.wide {{ grid-template-columns: 1fr; }}
  .guide-grid {{ grid-template-columns: 1fr; }}
  nav {{ padding: 0 16px; }}
}}
</style>
</head>
<body>

<nav>
  <div class="nav-brand">🐰 Боба Кролик</div>
  <div class="nav-right">
    <a href="https://bobacafe.net/internal/" class="nav-back">← Портал</a>
    <span class="nav-tag">Внутренний</span>
  </div>
</nav>

<div class="page">
  <div class="page-header">
    <h1 class="page-title">
      <span class="lang-en">Tapioca Cooking Plan</span>
      <span class="lang-ru">План варки тапиоки</span>
    </h1>
    <p class="page-sub">
      <span class="lang-en">Rolling 90 days: {date_range_str} &nbsp;·&nbsp; {n_stores} stores &nbsp;·&nbsp; Weekday vs Weekend</span>
      <span class="lang-ru">Скользящие 90 дней: {date_range_str} &nbsp;·&nbsp; {n_stores} магазинов &nbsp;·&nbsp; Будни vs Выходные</span>
    </p>
    <div class="lang-bar">
      <span class="lang-bar-label">🌐</span>
      <div class="lang-seg">
        <button id="lang-en" class="active" onclick="setLang('en')">EN</button>
        <button id="lang-ru" onclick="setLang('ru')">RU</button>
      </div>
    </div>
  </div>

  <div class="card">
    <div class="guide-header" onclick="toggleGuide()">
      <span class="guide-title">
        <span class="lang-en">📖 How to use this report</span>
        <span class="lang-ru">📖 Как пользоваться отчётом</span>
      </span>
      <span class="guide-chevron" id="guide-chevron">▼</span>
    </div>
    <div class="guide-body" id="guide-body">
      <div class="lang-en">
        <p>This report shows <strong>how many portions of tapioca to cook</strong> for each time slot per store, based on the last 90 days of sales. It updates automatically every day.</p>
        <div class="guide-grid">
          <div class="guide-box">
            <h4>Cooking slots</h4>
            <ul>
              <li><span class="slot-chip">9:30 AM</span> Covers sales until <strong>4:00 PM</strong></li>
              <li><span class="slot-chip">2:00 PM</span> Ready at 4 PM, covers until <strong>8:00 PM</strong></li>
              <li><span class="slot-chip">6:00 PM</span> Ready at 8 PM, covers until <strong>close</strong></li>
            </ul>
          </div>
          <div class="guide-box">
            <h4>Percentile toggle</h4>
            <ul>
              <li><strong>Avg</strong> — runs short ~50% of days</li>
              <li><strong>p75</strong> — short 1 in 4 days</li>
              <li><strong>p90</strong> — short ~2–3 days/month <em>(recommended)</em></li>
              <li><strong>p95</strong> — short ~1–2 days/month</li>
              <li><strong>Max</strong> — never short, but wastes the most</li>
            </ul>
          </div>
          <div class="guide-box">
            <h4>Grams per portion</h4>
            <ul>
              <li>Set this to the weight of <strong>dry tapioca pearls</strong> per drink.</li>
              <li>The grams column updates automatically.</li>
              <li>Default is 50 g — adjust to your recipe.</li>
            </ul>
          </div>
          <div class="guide-box">
            <h4>Backtest colour codes</h4>
            <ul>
              <li><span class="badge badge-red">≥ 30%</span> Short more than 1 in 3 days</li>
              <li><span class="badge badge-yellow">15–29%</span> Borderline</li>
              <li><span class="badge badge-teal">&lt; 15%</span> Acceptable</li>
            </ul>
          </div>
        </div>
        <p><strong>Shortfall</strong> shows average and maximum extra portions needed on days the recommendation fell short.</p>
      </div>
      <div class="lang-ru">
        <p>Этот отчёт показывает <strong>сколько порций тапиоки варить</strong> для каждого временного слота в каждом магазине, на основе продаж за последние 90 дней. Обновляется автоматически каждый день.</p>
        <div class="guide-grid">
          <div class="guide-box">
            <h4>Временные слоты</h4>
            <ul>
              <li><span class="slot-chip">9:30</span> Покрывает продажи до <strong>16:00</strong></li>
              <li><span class="slot-chip">14:00</span> Готова в 16:00, покрывает до <strong>20:00</strong></li>
              <li><span class="slot-chip">18:00</span> Готова в 20:00, покрывает до <strong>закрытия</strong></li>
            </ul>
          </div>
          <div class="guide-box">
            <h4>Переключатель перцентиля</h4>
            <ul>
              <li><strong>Avg</strong> — не хватает ~в 50% дней</li>
              <li><strong>p75</strong> — не хватает 1 день из 4</li>
              <li><strong>p90</strong> — не хватает ~2–3 дня/мес <em>(рекомендуется)</em></li>
              <li><strong>p95</strong> — не хватает ~1–2 дня/мес</li>
              <li><strong>Max</strong> — никогда не заканчивается, но больше отходов</li>
            </ul>
          </div>
          <div class="guide-box">
            <h4>Граммов на порцию</h4>
            <ul>
              <li>Укажите вес <strong>сухих шариков тапиоки</strong> на один напиток.</li>
              <li>Столбец граммов пересчитается автоматически.</li>
              <li>По умолчанию 50 г — измените под ваш рецепт.</li>
            </ul>
          </div>
          <div class="guide-box">
            <h4>Цвета в бэктесте</h4>
            <ul>
              <li><span class="badge badge-red">≥ 30%</span> Не хватает чаще 1 раза из 3</li>
              <li><span class="badge badge-yellow">15–29%</span> Погранично</li>
              <li><span class="badge badge-teal">&lt; 15%</span> Приемлемо</li>
            </ul>
          </div>
        </div>
        <p><strong>Нехватка</strong> — среднее и максимальное количество лишних порций, которых не хватило бы в плохие дни.</p>
      </div>
    </div>
  </div>

  <div class="card">
    <div class="toolbar">
      <div class="toolbar-group">
        <label><span class="lang-en">Percentile standard</span><span class="lang-ru">Уровень перцентиля</span></label>
        <div class="seg">
          <button onclick="setMode('avg')" id="btn-avg">Avg</button>
          <button onclick="setMode('p75')" id="btn-p75">p75</button>
          <button onclick="setMode('p90')" id="btn-p90" class="active">p90</button>
          <button onclick="setMode('p95')" id="btn-p95">p95</button>
          <button onclick="setMode('max')" id="btn-max">Max</button>
        </div>
      </div>
      <div class="toolbar-group">
        <label for="gpWeight"><span class="lang-en">Grams per portion</span><span class="lang-ru">Граммов на порцию</span></label>
        <input type="number" id="gpWeight" value="50" min="1" step="1">
      </div>
    </div>
  </div>

  <div class="section-label"><span class="lang-en">Cooking Plan</span><span class="lang-ru">План варки</span></div>
  <div class="grid">{plan_cards}</div>

  <div class="section-label">
    <span class="lang-en">Backtest — Days the recommendation falls short</span>
    <span class="lang-ru">Бэктест — дни, когда рекомендации не хватает</span>
  </div>
  <div class="legend">
    <span><span class="dot dot-high"></span><span class="lang-en">&ge;30% of days short</span><span class="lang-ru">&ge;30% дней с нехваткой</span></span>
    <span><span class="dot dot-med"></span>15–29%</span>
    <span><span class="dot dot-low"></span>&lt;15%</span>
  </div>
  <div class="grid wide">{bt_cards}</div>

  <p class="updated">
    <span class="lang-en">Last updated: {date_range_str}</span>
    <span class="lang-ru">Обновлено: {date_range_str}</span>
  </p>
</div>

<footer>
  <a href="https://bobacafe.net/internal/">← Внутренний портал</a> &nbsp;·&nbsp; Боба Кролик &copy; 2024 — Только для сотрудников
</footer>

<script>
const PLAN  = {plan_json};
const BT    = {bt_json};
const SLOTS = {slots_json};
let currentMode = 'p90', gramsPerPortion = 50;

function setLang(lang) {{
  document.querySelectorAll('.lang-en, .lang-ru').forEach(el => {{
    const show = el.classList.contains('lang-' + lang);
    el.style.display = show ? (el.tagName === 'SPAN' ? 'inline' : 'block') : 'none';
  }});
  document.getElementById('lang-en').classList.toggle('active', lang === 'en');
  document.getElementById('lang-ru').classList.toggle('active', lang === 'ru');
  const TH = {{
    en: {{ 'th-slot':'Slot','th-weekday-p':'Weekday<br><small>portions</small>','th-weekday-g':'Weekday<br><small>grams</small>','th-weekend-p':'Weekend<br><small>portions</small>','th-weekend-g':'Weekend<br><small>grams</small>','th-daytype':'Day type','th-rec':'Recommended','th-total':'Total days','th-under':'Days short','th-pct':'% short','th-shortfall':'Shortfall (avg / max)' }},
    ru: {{ 'th-slot':'Слот','th-weekday-p':'Будни<br><small>порции</small>','th-weekday-g':'Будни<br><small>граммы</small>','th-weekend-p':'Выходные<br><small>порции</small>','th-weekend-g':'Выходные<br><small>граммы</small>','th-daytype':'День','th-rec':'Рекомендовано','th-total':'Всего дней','th-under':'Дней с нехваткой','th-pct':'% нехватки','th-shortfall':'Нехватка (ср / макс)' }},
  }};
  Object.entries(TH[lang]).forEach(([cls, text]) =>
    document.querySelectorAll('.' + cls).forEach(el => el.innerHTML = text));
  document.querySelectorAll('td.dt-cell').forEach(td => {{
    td.textContent = td.dataset.day === 'Weekday'
      ? (lang === 'en' ? 'Weekday' : 'Будни')
      : (lang === 'en' ? 'Weekend' : 'Выходные');
  }});
}}

function toggleGuide() {{
  const body = document.getElementById('guide-body');
  const chev = document.getElementById('guide-chevron');
  const open = body.classList.toggle('open');
  chev.classList.toggle('open', open);
  chev.closest('.guide-header').classList.toggle('open', open);
}}

function setMode(mode) {{
  currentMode = mode;
  document.querySelectorAll('.seg button').forEach(b => b.classList.remove('active'));
  document.getElementById('btn-' + mode).classList.add('active');
  render();
}}

function sevClass(p) {{ return p >= 30 ? 'high' : p >= 15 ? 'med' : p > 0 ? 'low' : ''; }}

function render() {{
  const g = gramsPerPortion, m = currentMode;
  document.querySelectorAll('td.pval').forEach(td => {{
    const val = PLAN[td.dataset.store]?.[td.dataset.slot]?.[td.dataset.day]?.[m] ?? 0;
    td.textContent = val; td.dataset.portions = val;
  }});
  document.querySelectorAll('td.grams').forEach(td => {{
    const p = parseFloat(td.previousElementSibling?.dataset?.portions) || 0;
    td.textContent = p > 0 ? Math.round(p * g) + ' g' : '—';
  }});
  document.querySelectorAll('tr[data-store]').forEach(tr => {{
    const d = BT[tr.dataset.store]?.[tr.dataset.slot]?.[tr.dataset.day]?.[m];
    if (!d?.total_days) return;
    const sev = sevClass(d.pct_under);
    tr.className = sev ? 'sev-' + sev : '';
    tr.querySelector('.bt-rec').textContent   = d.recommended;
    tr.querySelector('.bt-total').textContent = d.total_days;
    tr.querySelector('.bt-under').textContent = d.days_under;
    const pctTd = tr.querySelector('.bt-pct');
    pctTd.textContent = d.pct_under + '%';
    pctTd.className   = 'num bt-pct' + (sev ? ' pct-' + sev : '');
    tr.querySelector('.bt-shortfall').textContent = d.days_under > 0
      ? d.avg_shortfall + ' avg / ' + d.max_shortfall + ' max' : '—';
  }});
}}

document.getElementById('gpWeight').addEventListener('input', e => {{
  gramsPerPortion = parseFloat(e.target.value) || 0; render();
}});

toggleGuide(); setLang('en'); render();
</script>
</body>
</html>"""

# COMMAND ----------

# MAGIC %md
# MAGIC ## Push to GitHub Pages

# COMMAND ----------

def push_to_github(html_content, token, repo, path, branch, message):
    url     = f"https://api.github.com/repos/{repo}/contents/{path}"
    headers = {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github.v3+json",
    }
    r   = requests.get(url, headers=headers, params={"ref": branch})
    sha = r.json().get("sha") if r.status_code == 200 else None

    payload = {
        "message": message,
        "content": base64.b64encode(html_content.encode("utf-8")).decode("ascii"),
        "branch":  branch,
    }
    if sha:
        payload["sha"] = sha

    r = requests.put(url, headers=headers, json=payload)
    r.raise_for_status()
    commit_sha = r.json()["commit"]["sha"][:8]
    print(f"Pushed {path}  |  commit {commit_sha}")

today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
push_to_github(
    html_content = html,
    token        = GITHUB_TOKEN,
    repo         = GITHUB_REPO,
    path         = GITHUB_FILE,
    branch       = GITHUB_BRANCH,
    message      = f"auto: tapioca report {today} [skip ci]",
)
