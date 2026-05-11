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
GITHUB_TOKEN  = "ghp_your_token_here"   # paste PAT here — do not commit

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
<title>Tapioca Cooking Plan</title>
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
          background: #f5f5f5; color: #222; padding: 32px 24px; }}
  h1  {{ font-size: 1.6rem; margin-bottom: 4px; }}
  h3  {{ font-size: 1.05rem; font-weight: 700; margin: 36px 0 14px; color: #333; }}
  .subtitle {{ color: #666; font-size: 0.9rem; margin-bottom: 20px; }}
  .lang-bar {{ display: flex; align-items: center; gap: 8px; margin-bottom: 22px; }}
  .lang-bar span {{ font-size: 0.8rem; color: #999; }}
  .lang-seg {{ display: flex; border: 1px solid #ccc; border-radius: 6px; overflow: hidden; }}
  .lang-seg button {{ padding: 4px 12px; border: none; background: #fff; cursor: pointer;
                      font-size: 0.82rem; font-weight: 600; color: #555;
                      border-right: 1px solid #ccc; transition: background .15s; }}
  .lang-seg button:last-child {{ border-right: none; }}
  .lang-seg button.active {{ background: #3b5bdb; color: #fff; }}
  .lang-ru {{ display: none; }}
  .guide {{ background: #fff; border-radius: 10px; box-shadow: 0 1px 4px rgba(0,0,0,.08);
            margin-bottom: 28px; overflow: hidden; }}
  .guide-header {{ display: flex; justify-content: space-between; align-items: center;
                   padding: 14px 20px; cursor: pointer; user-select: none;
                   border-bottom: 1px solid transparent; transition: border-color .2s; }}
  .guide-header:hover {{ background: #fafafa; }}
  .guide-header.open {{ border-bottom-color: #eee; }}
  .guide-title {{ font-weight: 700; font-size: 0.95rem; color: #333; }}
  .guide-chevron {{ font-size: 0.75rem; color: #999; transition: transform .2s; }}
  .guide-chevron.open {{ transform: rotate(180deg); }}
  .guide-body {{ display: none; padding: 20px; }}
  .guide-body.open {{ display: block; }}
  .guide-body p  {{ font-size: 0.88rem; line-height: 1.65; color: #444; margin-bottom: 14px; }}
  .guide-body p:last-child {{ margin-bottom: 0; }}
  .guide-body strong {{ color: #222; }}
  .guide-grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 16px; margin-bottom: 14px; }}
  @media (max-width: 640px) {{ .guide-grid {{ grid-template-columns: 1fr; }} }}
  .guide-box {{ background: #f7f7f7; border-radius: 8px; padding: 12px 14px; }}
  .guide-box h4 {{ font-size: 0.82rem; font-weight: 700; color: #555;
                   text-transform: uppercase; letter-spacing: .05em; margin-bottom: 8px; }}
  .guide-box ul {{ padding-left: 16px; font-size: 0.85rem; line-height: 1.7; color: #444; }}
  .slot-chip {{ display: inline-block; background: #e8f5e9; color: #2d6a4f;
                border-radius: 4px; padding: 1px 7px; font-weight: 700;
                font-size: 0.8rem; margin-right: 4px; }}
  .badge {{ display: inline-block; border-radius: 4px; padding: 1px 7px;
             font-size: 0.78rem; font-weight: 700; }}
  .badge-red    {{ background: #fff5f5; color: #c0392b; }}
  .badge-yellow {{ background: #fffdf0; color: #d68910; }}
  .badge-teal   {{ background: #f5fffe; color: #1a7a6e; }}
  .toolbar {{ display: flex; flex-wrap: wrap; gap: 20px; align-items: center;
              background: #fff; border-radius: 10px; padding: 16px 22px;
              box-shadow: 0 1px 4px rgba(0,0,0,.08); margin-bottom: 28px; }}
  .toolbar label {{ font-weight: 600; white-space: nowrap; font-size: 0.9rem; }}
  .toolbar input  {{ width: 80px; padding: 5px 9px; border: 1px solid #ccc;
                     border-radius: 6px; font-size: 0.95rem; }}
  .seg {{ display: flex; border: 1px solid #ccc; border-radius: 7px; overflow: hidden; }}
  .seg button {{ padding: 6px 14px; border: none; background: #fff; cursor: pointer;
                 font-size: 0.88rem; font-weight: 600; color: #555;
                 border-right: 1px solid #ccc; transition: background .15s; }}
  .seg button:last-child {{ border-right: none; }}
  .seg button.active {{ background: #2d6a4f; color: #fff; }}
  .seg button:hover:not(.active) {{ background: #f0f0f0; }}
  .grid      {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(500px, 1fr)); gap: 18px; }}
  .grid.wide {{ grid-template-columns: repeat(auto-fill, minmax(680px, 1fr)); }}
  .store-card {{ background: #fff; border-radius: 10px; padding: 18px 22px;
                 box-shadow: 0 1px 4px rgba(0,0,0,.08); }}
  .store-card h2 {{ font-size: 0.95rem; font-weight: 700; margin-bottom: 10px;
                    color: #444; letter-spacing: .04em; }}
  table  {{ width: 100%; border-collapse: collapse; font-size: 0.84rem; }}
  thead tr {{ background: #f0f0f0; }}
  th {{ padding: 7px 11px; text-align: center; font-weight: 600;
        border-bottom: 2px solid #ddd; line-height: 1.3; }}
  th:first-child {{ text-align: left; }}
  td {{ padding: 7px 11px; border-bottom: 1px solid #eee; }}
  td.slot  {{ font-weight: 600; color: #555; white-space: nowrap; }}
  td.num   {{ text-align: center; }}
  td.grams {{ color: #c84b31; font-weight: 600; }}
  td.bold  {{ font-weight: 700; }}
  tr:last-child td {{ border-bottom: none; }}
  tr:hover td {{ background: #fafafa; }}
  .legend {{ display: flex; gap: 18px; margin-bottom: 14px; font-size: 0.81rem; color: #555; }}
  .legend span {{ display: flex; align-items: center; gap: 5px; }}
  .dot {{ width: 9px; height: 9px; border-radius: 50%; }}
  .dot-high {{ background: #f8d7da; border: 1px solid #f5c2c7; }}
  .dot-med  {{ background: #fff3cd; border: 1px solid #ffecb5; }}
  .dot-low  {{ background: #d1ecf1; border: 1px solid #bee5eb; }}
  .sev-high {{ background: #fff5f5; }}
  .sev-med  {{ background: #fffdf0; }}
  .sev-low  {{ background: #f5fffe; }}
  .pct-high {{ color: #c0392b; font-weight: 700; }}
  .pct-med  {{ color: #d68910; font-weight: 700; }}
  .pct-low  {{ color: #1a7a6e; font-weight: 600; }}
  .updated  {{ font-size: 0.78rem; color: #aaa; margin-top: 40px; text-align: right; }}
</style>
</head>
<body>

<h1>
  <span class="lang-en">Tapioca Cooking Plan</span>
  <span class="lang-ru">План варки тапиоки</span>
</h1>
<p class="subtitle">
  <span class="lang-en">Rolling 90 days: {date_range_str} &nbsp;·&nbsp; {n_stores} stores &nbsp;·&nbsp; Weekday vs Weekend</span>
  <span class="lang-ru">Скользящие 90 дней: {date_range_str} &nbsp;·&nbsp; {n_stores} магазинов &nbsp;·&nbsp; Будни vs Выходные</span>
</p>

<div class="lang-bar">
  <span>🌐</span>
  <div class="lang-seg">
    <button id="lang-en" class="active" onclick="setLang('en')">EN</button>
    <button id="lang-ru" onclick="setLang('ru')">RU</button>
  </div>
</div>

<div class="guide">
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

<div class="toolbar">
  <div>
    <label><span class="lang-en">Percentile standard:</span><span class="lang-ru">Уровень перцентиля:</span></label><br>
    <div class="seg" style="margin-top:6px">
      <button onclick="setMode('avg')" id="btn-avg">Avg</button>
      <button onclick="setMode('p75')" id="btn-p75">p75</button>
      <button onclick="setMode('p90')" id="btn-p90" class="active">p90</button>
      <button onclick="setMode('p95')" id="btn-p95">p95</button>
      <button onclick="setMode('max')" id="btn-max">Max</button>
    </div>
  </div>
  <div>
    <label for="gpWeight"><span class="lang-en">Grams per portion:</span><span class="lang-ru">Граммов на порцию:</span></label><br>
    <input type="number" id="gpWeight" value="50" min="1" step="1" style="margin-top:6px">
  </div>
</div>

<h3><span class="lang-en">Cooking Plan</span><span class="lang-ru">План варки</span></h3>
<div class="grid">{plan_cards}</div>

<h3>
  <span class="lang-en">Backtest — Days the recommendation falls short</span>
  <span class="lang-ru">Бэктест — дни, когда рекомендации не хватает</span>
</h3>
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
