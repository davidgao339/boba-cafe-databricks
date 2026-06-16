"""
Tapioca cooking plan with percentile toggle (p75 / p90 / p95 / max).
Run from repo root: python ad_hoc/tapioca_cooking_plan.py
"""
import sys, os
sys.stdout.reconfigure(encoding="utf-8")

import math
import json
import pandas as pd
import numpy as np

CSV = os.path.join(os.path.dirname(__file__), "..", "POS", "data", "tapioca.csv")
OUT = os.path.join(os.path.dirname(__file__), "tapioca_cooking_plan.html")

df = pd.read_csv(CSV)
df["local_dt"] = pd.to_datetime(df["datetime"])
df["local_hour"] = df["local_dt"].dt.hour + df["local_dt"].dt.minute / 60
df["date"] = pd.to_datetime(df["date"]).dt.date

df = df[df["transaction_type"] != "Non-Fiscal"].copy()

sign = df["is_return"].apply(lambda x: -1 if x else 1)
df["net_qty"] = df["qty"].abs() * sign

def assign_slot(h):
    if h < 2 or h >= 20:   return "6:00 PM"
    elif h < 16:            return "9:30 AM"
    else:                   return "2:00 PM"

SLOT_ORDER   = ["9:30 AM", "2:00 PM", "6:00 PM"]
PERCENTILES  = {"avg": None, "p75": 75, "p90": 90, "p95": 95, "max": 100}
ROLLING_DAYS_DEFAULT = 90

df["slot"]     = df["local_hour"].apply(assign_slot)
df["day_type"] = df["local_dt"].dt.dayofweek.apply(lambda d: "Weekend" if d >= 5 else "Weekday")

daily = (
    df.groupby(["store_name", "date", "day_type", "slot"])["net_qty"]
    .sum()
    .reset_index()
    .rename(columns={"net_qty": "actual"})
)

# Filter data to rolling window
max_date = daily["date"].max()
min_date = max_date - pd.Timedelta(days=ROLLING_DAYS_DEFAULT)
daily_filtered = daily[daily["date"] >= min_date].copy()

stores = sorted(daily["store_name"].unique())

# Compute recommendation for every percentile option
def compute_rec(daily_to_use, pct):
    if pct is None:
        agg = daily_to_use.groupby(["store_name", "slot", "day_type"])["actual"].mean()
    elif pct == 100:
        agg = daily_to_use.groupby(["store_name", "slot", "day_type"])["actual"].max()
    else:
        agg = daily_to_use.groupby(["store_name", "slot", "day_type"])["actual"].quantile(pct / 100)
    return agg.apply(math.ceil).reset_index().rename(columns={"actual": "recommended"})

recs = {k: compute_rec(daily_filtered, v) for k, v in PERCENTILES.items()}

# Backtest for each option
def compute_backtest(daily, rec_df):
    bt = daily.merge(rec_df, on=["store_name", "slot", "day_type"])
    bt["under"]    = bt["actual"] > bt["recommended"]
    bt["shortfall"] = (bt["actual"] - bt["recommended"]).clip(lower=0)
    result = (
        bt.groupby(["store_name", "slot", "day_type"])
        .agg(
            recommended  = ("recommended", "first"),
            total_days   = ("actual", "count"),
            days_under   = ("under", "sum"),
            avg_shortfall = ("shortfall", lambda x: x[x > 0].mean() if (x > 0).any() else 0),
            max_shortfall = ("shortfall", "max"),
        )
        .reset_index()
    )
    result["pct_under"]     = (result["days_under"] / result["total_days"] * 100).round(1)
    result["avg_shortfall"] = result["avg_shortfall"].apply(lambda x: math.ceil(x) if x > 0 else 0)
    result["max_shortfall"] = result["max_shortfall"].astype(int)
    return result

backtests = {k: compute_backtest(daily, recs[k]) for k in PERCENTILES}

# ── Serialise data for JS ──────────────────────────────────────────────────────
# plan_data[store][slot][day_type][pct_key] = recommended
# bt_data[store][slot][day_type][pct_key]   = {recommended, total_days, days_under, pct_under, avg_shortfall, max_shortfall}

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

                bt = backtests[key]
                row = bt.loc[
                    (bt.store_name == store) & (bt.slot == slot) & (bt.day_type == day_type)
                ]
                if row.empty:
                    bt_data[store][slot][day_type][key] = {}
                else:
                    rw = row.iloc[0]
                    bt_data[store][slot][day_type][key] = {
                        "recommended":  rec_val,
                        "total_days":   int(rw["total_days"]),
                        "days_under":   int(rw["days_under"]),
                        "pct_under":    float(rw["pct_under"]),
                        "avg_shortfall": int(rw["avg_shortfall"]),
                        "max_shortfall": int(rw["max_shortfall"]),
                    }

plan_json = json.dumps(plan_data, ensure_ascii=False)
bt_json   = json.dumps(bt_data,   ensure_ascii=False)
stores_json = json.dumps(stores)
slots_json  = json.dumps(SLOT_ORDER)
rolling_json = json.dumps(ROLLING_DAYS_DEFAULT)

# ── Static store card skeletons (JS fills the numbers) ────────────────────────
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
    rows = ""
    for slot in SLOT_ORDER:
        for day_type in ["Weekday", "Weekend"]:
            key = f"{store}||{slot}||{day_type}"
            rows += f"""
        <tr data-store="{store}" data-slot="{slot}" data-day="{day_type}">
          <td class="slot">{slot}</td>
          <td class="dt-cell" data-day="{day_type}">{day_type}</td>
          <td class="num bt-rec">—</td>
          <td class="num bt-total">—</td>
          <td class="num bt-under bold">—</td>
          <td class="num bt-pct">—</td>
          <td class="num bt-shortfall">—</td>
        </tr>"""
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
<title>Tapioca Cooking Plan — Jan–Apr 2026</title>
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
          background: #f5f5f5; color: #222; padding: 32px 24px; }}
  h1  {{ font-size: 1.6rem; margin-bottom: 4px; }}
  h3  {{ font-size: 1.05rem; font-weight: 700; margin: 36px 0 14px; color: #333; }}
  .subtitle {{ color: #666; font-size: 0.9rem; margin-bottom: 20px; }}

  /* ── Language toggle ── */
  .lang-bar {{ display: flex; align-items: center; gap: 8px; margin-bottom: 22px; }}
  .lang-bar span {{ font-size: 0.8rem; color: #999; }}
  .lang-seg {{ display: flex; border: 1px solid #ccc; border-radius: 6px; overflow: hidden; }}
  .lang-seg button {{ padding: 4px 12px; border: none; background: #fff; cursor: pointer;
                      font-size: 0.82rem; font-weight: 600; color: #555;
                      border-right: 1px solid #ccc; transition: background .15s; }}
  .lang-seg button:last-child {{ border-right: none; }}
  .lang-seg button.active {{ background: #3b5bdb; color: #fff; }}
  .lang-ru {{ display: none; }}

  /* ── Guide ── */
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

  /* ── Toolbar ── */
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

  /* ── Cards & tables ── */
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
</style>
</head>
<body>

<!-- ── Header ── -->
<h1>
  <span class="lang-en">Tapioca Cooking Plan</span>
  <span class="lang-ru">План варки тапиоки</span>
</h1>
<p class="subtitle">
  <span class="lang-en">Jan – Apr 2026 &nbsp;·&nbsp; {len(stores)} stores &nbsp;·&nbsp; Weekday vs Weekend</span>
  <span class="lang-ru">Янв – Апр 2026 &nbsp;·&nbsp; {len(stores)} магазинов &nbsp;·&nbsp; Будни vs Выходные</span>
</p>

<div class="lang-bar">
  <span>🌐</span>
  <div class="lang-seg">
    <button id="lang-en" class="active" onclick="setLang('en')">EN</button>
    <button id="lang-ru" onclick="setLang('ru')">RU</button>
  </div>
</div>

<!-- ── User Guide ── -->
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
      <p>This report helps you decide <strong>how many portions of tapioca to cook</strong> for each time slot, per store, based on Jan–Apr 2026 sales data. The goal is to cook just enough to cover demand without running out mid-shift.</p>
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
            <li>Set this to the weight of <strong>dry tapioca pearls</strong> you use per drink.</li>
            <li>The grams column updates automatically.</li>
            <li>Default is 50 g — adjust to your recipe.</li>
          </ul>
        </div>
        <div class="guide-box">
          <h4>Backtest colour codes</h4>
          <ul>
            <li><span class="badge badge-red">≥ 30%</span> Short more than 1 in 3 days — raise the standard</li>
            <li><span class="badge badge-yellow">15–29%</span> Borderline — consider moving up one level</li>
            <li><span class="badge badge-teal">&lt; 15%</span> Acceptable — good balance of waste vs stockout</li>
          </ul>
        </div>
      </div>
      <p><strong>Shortfall column</strong> shows the average and maximum number of extra portions you would have needed on the days the recommendation fell short. Use this to judge whether a stockout is a minor inconvenience (shortfall 1–2) or a serious problem (shortfall 5+).</p>
    </div>

    <div class="lang-ru">
      <p>Этот отчёт помогает определить <strong>сколько порций тапиоки варить</strong> для каждого временного слота в каждом магазине, на основе данных продаж за январь–апрель 2026 года. Цель — сварить ровно столько, чтобы не закончилась в середине смены.</p>
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
            <li><span class="badge badge-red">≥ 30%</span> Не хватает чаще 1 раза из 3 — повысьте стандарт</li>
            <li><span class="badge badge-yellow">15–29%</span> Погранично — рассмотрите уровень выше</li>
            <li><span class="badge badge-teal">&lt; 15%</span> Приемлемо — хороший баланс</li>
          </ul>
        </div>
      </div>
      <p><strong>Столбец «нехватка»</strong> показывает среднее и максимальное количество лишних порций, которых не хватило бы в плохие дни. Используйте это, чтобы оценить масштаб проблемы: 1–2 порции — мелочь, 5+ — серьёзно.</p>
    </div>

  </div>
</div>

<!-- ── Toolbar ── -->
<div class="toolbar">
  <div>
    <label>
      <span class="lang-en">Percentile standard:</span>
      <span class="lang-ru">Уровень перцентиля:</span>
    </label><br>
    <div class="seg" style="margin-top:6px">
      <button onclick="setMode('avg')" id="btn-avg">Avg</button>
      <button onclick="setMode('p75')" id="btn-p75">p75</button>
      <button onclick="setMode('p90')" id="btn-p90" class="active">p90</button>
      <button onclick="setMode('p95')" id="btn-p95">p95</button>
      <button onclick="setMode('max')" id="btn-max">Max</button>
    </div>
  </div>
  <div>
    <label for="gpWeight">
      <span class="lang-en">Grams per portion:</span>
      <span class="lang-ru">Граммов на порцию:</span>
    </label><br>
    <input type="number" id="gpWeight" value="50" min="1" step="1" style="margin-top:6px">
  </div>
  <div>
    <label for="rollingDays">
      <span class="lang-en">Rolling average days:</span>
      <span class="lang-ru">Дни скользящего среднего:</span>
    </label><br>
    <input type="number" id="rollingDays" min="7" step="1" style="margin-top:6px" disabled>
    <span style="font-size: 0.75rem; color: #999; display: block; margin-top: 4px;">
      <span class="lang-en">Based on last <span id="rolling-display">90</span> days of sales</span>
      <span class="lang-ru">На основе последних <span id="rolling-display-ru">90</span> дней продаж</span>
    </span>
  </div>
</div>

<h3>
  <span class="lang-en">Cooking Plan</span>
  <span class="lang-ru">План варки</span>
</h3>
<div class="grid">
{plan_cards}
</div>

<h3>
  <span class="lang-en">Backtest — Days the recommendation falls short</span>
  <span class="lang-ru">Бэктест — дни, когда рекомендации не хватает</span>
</h3>
<div class="legend">
  <span><span class="dot dot-high"></span>
    <span class="lang-en">&ge;30% of days short</span>
    <span class="lang-ru">&ge;30% дней с нехваткой</span>
  </span>
  <span><span class="dot dot-med"></span>15–29%</span>
  <span><span class="dot dot-low"></span>
    <span class="lang-en">&lt;15%</span>
    <span class="lang-ru">&lt;15%</span>
  </span>
</div>
<div class="grid wide">
{bt_cards}
</div>

<script>
const PLAN  = {plan_json};
const BT    = {bt_json};
const SLOTS = {slots_json};
const ROLLING_DAYS_DEFAULT = {rolling_json};

let currentMode     = 'p90';
let gramsPerPortion = 50;
let rollingDays     = ROLLING_DAYS_DEFAULT;
let currentLang     = 'en';

// ── Language ──────────────────────────────────────────────────────────────────
function setLang(lang) {{
  currentLang = lang;
  document.querySelectorAll('.lang-en, .lang-ru').forEach(el => {{
    const show = el.classList.contains('lang-' + lang);
    el.style.display = show ? (el.tagName === 'SPAN' ? 'inline' : 'block') : 'none';
  }});
  document.getElementById('lang-en').classList.toggle('active', lang === 'en');
  document.getElementById('lang-ru').classList.toggle('active', lang === 'ru');

  // Translate table headers
  const TH = {{
    en: {{
      'th-slot':'Slot','th-weekday-p':'Weekday<br><small>portions</small>',
      'th-weekday-g':'Weekday<br><small>grams</small>',
      'th-weekend-p':'Weekend<br><small>portions</small>',
      'th-weekend-g':'Weekend<br><small>grams</small>',
      'th-daytype':'Day type','th-rec':'Recommended','th-total':'Total days',
      'th-under':'Days short','th-pct':'% short','th-shortfall':'Shortfall (avg / max)',
    }},
    ru: {{
      'th-slot':'Слот','th-weekday-p':'Будни<br><small>порции</small>',
      'th-weekday-g':'Будни<br><small>граммы</small>',
      'th-weekend-p':'Выходные<br><small>порции</small>',
      'th-weekend-g':'Выходные<br><small>граммы</small>',
      'th-daytype':'День','th-rec':'Рекомендовано','th-total':'Всего дней',
      'th-under':'Дней с нехваткой','th-pct':'% нехватки','th-shortfall':'Нехватка (ср / макс)',
    }},
  }};
  Object.entries(TH[lang]).forEach(([id, text]) => {{
    document.querySelectorAll('.' + id).forEach(el => el.innerHTML = text);
  }});

  // Translate day-type cells in backtest
  document.querySelectorAll('td.dt-cell').forEach(td => {{
    td.textContent = td.dataset.day === 'Weekday'
      ? (lang === 'en' ? 'Weekday' : 'Будни')
      : (lang === 'en' ? 'Weekend' : 'Выходные');
  }});
}}

// ── Guide toggle ──────────────────────────────────────────────────────────────
function toggleGuide() {{
  const body    = document.getElementById('guide-body');
  const chevron = document.getElementById('guide-chevron');
  const header  = chevron.closest('.guide-header');
  const open    = body.classList.toggle('open');
  chevron.classList.toggle('open', open);
  header.classList.toggle('open', open);
}}

// ── Percentile mode ───────────────────────────────────────────────────────────
function setMode(mode) {{
  currentMode = mode;
  document.querySelectorAll('.seg button').forEach(b => b.classList.remove('active'));
  document.getElementById('btn-' + mode).classList.add('active');
  render();
}}

function sevClass(pct) {{
  if (pct >= 30) return 'high';
  if (pct >= 15) return 'med';
  if (pct >  0)  return 'low';
  return '';
}}

// ── Main render ───────────────────────────────────────────────────────────────
function render() {{
  const g = gramsPerPortion;
  const m = currentMode;

  document.querySelectorAll('td.pval').forEach(td => {{
    const store = td.dataset.store, slot = td.dataset.slot, day = td.dataset.day;
    const val = (PLAN[store]?.[slot]?.[day]?.[m]) ?? 0;
    td.textContent = val;
    td.dataset.portions = val;
  }});

  document.querySelectorAll('td.grams').forEach(td => {{
    const p = parseFloat(td.previousElementSibling?.dataset?.portions) || 0;
    td.textContent = p > 0 ? Math.round(p * g) + ' g' : '—';
  }});

  document.querySelectorAll('tr[data-store]').forEach(tr => {{
    const store = tr.dataset.store, slot = tr.dataset.slot, day = tr.dataset.day;
    const d = BT[store]?.[slot]?.[day]?.[m];
    if (!d || !d.total_days) return;

    const sev = sevClass(d.pct_under);
    tr.className = sev ? 'sev-' + sev : '';

    tr.querySelector('.bt-rec').textContent   = d.recommended;
    tr.querySelector('.bt-total').textContent = d.total_days;
    tr.querySelector('.bt-under').textContent = d.days_under;

    const pctTd = tr.querySelector('.bt-pct');
    pctTd.textContent = d.pct_under + '%';
    pctTd.className   = 'num bt-pct' + (sev ? ' pct-' + sev : '');

    tr.querySelector('.bt-shortfall').textContent = d.days_under > 0
      ? d.avg_shortfall + ' avg / ' + d.max_shortfall + ' max'
      : '—';
  }});
}}

document.getElementById('gpWeight').addEventListener('input', e => {{
  gramsPerPortion = parseFloat(e.target.value) || 0;
  render();
}});

// Initialize rolling days display
document.getElementById('rollingDays').value = ROLLING_DAYS_DEFAULT;
document.getElementById('rolling-display').textContent = ROLLING_DAYS_DEFAULT;
document.getElementById('rolling-display-ru').textContent = ROLLING_DAYS_DEFAULT;

// Open guide by default
toggleGuide();
setLang('en');
render();
</script>
</body>
</html>"""

with open(OUT, "w", encoding="utf-8") as f:
    f.write(html)

print(f"Written: {OUT}")
