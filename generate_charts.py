import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import numpy as np
from datetime import datetime

plt.rcParams['figure.dpi'] = 150
plt.rcParams['font.size'] = 9

df = pd.read_csv('ozmall_sales.csv')
sales = df[(df['is_return']==False) & (~df['product'].str.startswith('Списание')) & (df['transaction_type']!='Non-Fiscal')].copy()
offline = sales[sales['online']==False].copy()

def categorize(row):
    if row['is_topping']:
        return 'Topping'
    name = row['product'].lower()
    if any(k in name for k in ['корн-дог', 'блинчик', 'моти', 'чизкейк', 'печенье']):
        return 'Food'
    return 'Drink'

offline['category'] = offline.apply(categorize, axis=1)
offline['date_dt'] = pd.to_datetime(offline['date'])

# === CHART 1: Daily Revenue with pre/post split ===
daily = offline.groupby('date').agg(
    revenue=('revenue','sum'),
    orders=('order_number','nunique'),
).reset_index()
daily['date_dt'] = pd.to_datetime(daily['date'])
daily['period'] = daily['date'].apply(lambda d: 'Post' if d >= '2026-03-21' else 'Pre')

fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 7), sharex=True)

# Revenue bars
colors = ['#4A90D9' if p == 'Pre' else '#E85D3A' for p in daily['period']]
ax1.bar(daily['date_dt'], daily['revenue'], color=colors, width=0.8, edgecolor='white', linewidth=0.5)
ax1.axvline(x=pd.Timestamp('2026-03-20 12:00'), color='black', linestyle='--', alpha=0.7, linewidth=1)
ax1.text(pd.Timestamp('2026-03-20 18:00'), ax1.get_ylim()[1]*0.9, 'Price Change\nMar 21',
         ha='right', va='top', fontsize=8, style='italic')

pre_avg = daily[daily['period']=='Pre']['revenue'].mean()
post_avg = daily[daily['period']=='Post']['revenue'].mean()
ax1.axhline(y=pre_avg, color='#4A90D9', linestyle=':', alpha=0.6, linewidth=1.5)
ax1.axhline(y=post_avg, color='#E85D3A', linestyle=':', alpha=0.6, linewidth=1.5)
ax1.text(daily['date_dt'].iloc[0], pre_avg+200, f'Pre avg: {pre_avg:,.0f}', color='#4A90D9', fontsize=8)
ax1.text(daily['date_dt'].iloc[-1], post_avg+200, f'Post avg: {post_avg:,.0f}', color='#E85D3A', fontsize=8, ha='right')

ax1.set_ylabel('Revenue (RUB)')
ax1.set_title('OZMALL Daily Revenue — Offline Sales (Pre vs Post Price Change)', fontweight='bold', fontsize=11)
ax1.grid(axis='y', alpha=0.3)

# Orders bars
colors2 = ['#6BB5E0' if p == 'Pre' else '#F4A582' for p in daily['period']]
ax2.bar(daily['date_dt'], daily['orders'], color=colors2, width=0.8, edgecolor='white', linewidth=0.5)
ax2.axvline(x=pd.Timestamp('2026-03-20 12:00'), color='black', linestyle='--', alpha=0.7, linewidth=1)

pre_avg_o = daily[daily['period']=='Pre']['orders'].mean()
post_avg_o = daily[daily['period']=='Post']['orders'].mean()
ax2.axhline(y=pre_avg_o, color='#6BB5E0', linestyle=':', alpha=0.6, linewidth=1.5)
ax2.axhline(y=post_avg_o, color='#F4A582', linestyle=':', alpha=0.6, linewidth=1.5)
ax2.text(daily['date_dt'].iloc[0], pre_avg_o+0.5, f'Pre avg: {pre_avg_o:.1f}', color='#4A90D9', fontsize=8)
ax2.text(daily['date_dt'].iloc[-1], post_avg_o+0.5, f'Post avg: {post_avg_o:.1f}', color='#E85D3A', fontsize=8, ha='right')

ax2.set_ylabel('Orders')
ax2.set_xlabel('Date')
ax2.xaxis.set_major_formatter(mdates.DateFormatter('%b %d'))
ax2.xaxis.set_major_locator(mdates.DayLocator(interval=2))
plt.xticks(rotation=45, ha='right')
ax2.grid(axis='y', alpha=0.3)

plt.tight_layout()
plt.savefig('chart1_daily_revenue_orders.png', bbox_inches='tight')
plt.close()
print('Chart 1 saved.')

# === CHART 2: Topping Attachment Rate ===
topping_daily = offline[offline['is_topping']].groupby('date').agg(
    topping_orders=('order_number','nunique'),
    topping_rev=('revenue','sum'),
    topping_qty=('qty','sum')
).reset_index()
order_daily = offline.groupby('date')['order_number'].nunique().reset_index()
order_daily.columns = ['date','total_orders']
topping_daily = order_daily.merge(topping_daily, on='date', how='left').fillna(0)
topping_daily['attach_rate'] = topping_daily['topping_orders'] / topping_daily['total_orders'] * 100
topping_daily['date_dt'] = pd.to_datetime(topping_daily['date'])
topping_daily['period'] = topping_daily['date'].apply(lambda d: 'Post' if d >= '2026-03-21' else 'Pre')

fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 6), sharex=True)

# Attachment rate
colors_att = ['#4A90D9' if p == 'Pre' else '#E85D3A' for p in topping_daily['period']]
ax1.bar(topping_daily['date_dt'], topping_daily['attach_rate'], color=colors_att, width=0.8, edgecolor='white', linewidth=0.5)
ax1.axvline(x=pd.Timestamp('2026-03-20 12:00'), color='black', linestyle='--', alpha=0.7, linewidth=1)

pre_att = topping_daily[topping_daily['period']=='Pre']['attach_rate'].mean()
post_att = topping_daily[topping_daily['period']=='Post']['attach_rate'].mean()
ax1.axhline(y=pre_att, color='#4A90D9', linestyle=':', alpha=0.6)
ax1.axhline(y=post_att, color='#E85D3A', linestyle=':', alpha=0.6)
ax1.text(topping_daily['date_dt'].iloc[1], pre_att+2, f'Pre avg: {pre_att:.1f}%', color='#4A90D9', fontsize=8)
ax1.text(topping_daily['date_dt'].iloc[-1], post_att+2, f'Post avg: {post_att:.1f}%', color='#E85D3A', fontsize=8, ha='right')

ax1.set_ylabel('Attachment Rate (%)')
ax1.set_title('Topping Attachment Rate & Revenue — OZMALL Offline', fontweight='bold', fontsize=11)
ax1.grid(axis='y', alpha=0.3)

# Topping revenue
colors_tr = ['#7DCEA0' if p == 'Pre' else '#F1948A' for p in topping_daily['period']]
ax2.bar(topping_daily['date_dt'], topping_daily['topping_rev'], color=colors_tr, width=0.8, edgecolor='white', linewidth=0.5)
ax2.axvline(x=pd.Timestamp('2026-03-20 12:00'), color='black', linestyle='--', alpha=0.7, linewidth=1)
ax2.set_ylabel('Topping Revenue (RUB)')
ax2.set_xlabel('Date')
ax2.xaxis.set_major_formatter(mdates.DateFormatter('%b %d'))
ax2.xaxis.set_major_locator(mdates.DayLocator(interval=2))
plt.xticks(rotation=45, ha='right')
ax2.grid(axis='y', alpha=0.3)

plt.tight_layout()
plt.savefig('chart2_topping_attachment.png', bbox_inches='tight')
plt.close()
print('Chart 2 saved.')

# === CHART 3: Revenue Composition (Stacked) ===
cat_daily = offline.groupby(['date', 'category']).agg(rev=('revenue','sum')).reset_index()
cat_pivot = cat_daily.pivot(index='date', columns='category', values='rev').fillna(0)
for c in ['Drink','Food','Topping']:
    if c not in cat_pivot.columns:
        cat_pivot[c] = 0
cat_pivot = cat_pivot[['Drink','Food','Topping']]
cat_pivot.index = pd.to_datetime(cat_pivot.index)

fig, ax = plt.subplots(figsize=(12, 5))
ax.bar(cat_pivot.index, cat_pivot['Drink'], label='Drinks', color='#5DADE2', width=0.8)
ax.bar(cat_pivot.index, cat_pivot['Food'], bottom=cat_pivot['Drink'], label='Food', color='#F5B041', width=0.8)
ax.bar(cat_pivot.index, cat_pivot['Topping'], bottom=cat_pivot['Drink']+cat_pivot['Food'], label='Toppings', color='#58D68D', width=0.8)
ax.axvline(x=pd.Timestamp('2026-03-20 12:00'), color='black', linestyle='--', alpha=0.7, linewidth=1)
ax.text(pd.Timestamp('2026-03-20 18:00'), ax.get_ylim()[1]*0.95, 'Price Change', ha='right', fontsize=8, style='italic')

ax.set_ylabel('Revenue (RUB)')
ax.set_title('Revenue Composition by Category — OZMALL Offline', fontweight='bold', fontsize=11)
ax.legend(loc='upper left')
ax.xaxis.set_major_formatter(mdates.DateFormatter('%b %d'))
ax.xaxis.set_major_locator(mdates.DayLocator(interval=2))
plt.xticks(rotation=45, ha='right')
ax.grid(axis='y', alpha=0.3)

plt.tight_layout()
plt.savefig('chart3_revenue_composition.png', bbox_inches='tight')
plt.close()
print('Chart 3 saved.')

# === CHART 4: Avg Ticket & Effective Drink Price ===
# Per-day metrics
drink_daily = offline[offline['category']=='Drink'].groupby('date').agg(
    drink_rev=('revenue','sum'), drink_qty=('qty','sum')
).reset_index()
topping_by_day = offline[offline['is_topping']].groupby('date').agg(
    top_rev=('revenue','sum')
).reset_index()
drink_daily = drink_daily.merge(topping_by_day, on='date', how='left').fillna(0)
drink_daily['avg_drink_base'] = drink_daily['drink_rev'] / drink_daily['drink_qty']
drink_daily['avg_drink_effective'] = (drink_daily['drink_rev'] + drink_daily['top_rev']) / drink_daily['drink_qty']
drink_daily['date_dt'] = pd.to_datetime(drink_daily['date'])
drink_daily['period'] = drink_daily['date'].apply(lambda d: 'Post' if d >= '2026-03-21' else 'Pre')

fig, ax = plt.subplots(figsize=(12, 5))
ax.plot(drink_daily['date_dt'], drink_daily['avg_drink_base'], 'o-', color='#3498DB', label='Avg Drink Base Price', markersize=5, linewidth=1.5)
ax.plot(drink_daily['date_dt'], drink_daily['avg_drink_effective'], 's--', color='#E74C3C', label='Avg Drink + Topping (Effective)', markersize=5, linewidth=1.5)
ax.axvline(x=pd.Timestamp('2026-03-20 12:00'), color='black', linestyle='--', alpha=0.7, linewidth=1)
ax.axhline(y=324, color='gray', linestyle=':', alpha=0.5)
ax.text(drink_daily['date_dt'].iloc[0], 328, 'Pre-change avg: 324 RUB', color='gray', fontsize=8)

ax.set_ylabel('Price (RUB)')
ax.set_title('Average Drink Price: Base vs Effective (with Toppings) — OZMALL Offline', fontweight='bold', fontsize=11)
ax.legend(loc='lower left')
ax.xaxis.set_major_formatter(mdates.DateFormatter('%b %d'))
ax.xaxis.set_major_locator(mdates.DayLocator(interval=2))
plt.xticks(rotation=45, ha='right')
ax.grid(axis='y', alpha=0.3)
ax.set_ylim(100, 500)

plt.tight_layout()
plt.savefig('chart4_drink_price_effective.png', bbox_inches='tight')
plt.close()
print('Chart 4 saved.')

# === CHART 5: Day-of-week comparison ===
offline_dow = offline.copy()
offline_dow['dow'] = offline_dow['date_dt'].dt.dayofweek
offline_dow['dow_name'] = offline_dow['date_dt'].dt.day_name()
offline_dow['period'] = offline_dow['date'].apply(lambda d: 'Post' if d >= '2026-03-21' else 'Pre')

dow_rev = offline_dow.groupby(['date','dow','dow_name','period']).agg(rev=('revenue','sum')).reset_index()
dow_avg = dow_rev.groupby(['dow','dow_name','period']).agg(avg_rev=('rev','mean')).reset_index()

fig, ax = plt.subplots(figsize=(10, 5))
dow_order = ['Monday','Tuesday','Wednesday','Thursday','Friday','Saturday','Sunday']
x = np.arange(len(dow_order))
width = 0.35

pre_vals = []
post_vals = []
for d in dow_order:
    pre_row = dow_avg[(dow_avg['dow_name']==d) & (dow_avg['period']=='Pre')]
    post_row = dow_avg[(dow_avg['dow_name']==d) & (dow_avg['period']=='Post')]
    pre_vals.append(pre_row['avg_rev'].values[0] if len(pre_row) > 0 else 0)
    post_vals.append(post_row['avg_rev'].values[0] if len(post_row) > 0 else 0)

bars1 = ax.bar(x - width/2, pre_vals, width, label='Pre (Mar 1-20)', color='#4A90D9', edgecolor='white')
bars2 = ax.bar(x + width/2, post_vals, width, label='Post (Mar 21-25)', color='#E85D3A', edgecolor='white')

# Mark days with no post data
for i, v in enumerate(post_vals):
    if v == 0:
        ax.text(x[i] + width/2, 100, 'No data', ha='center', fontsize=7, color='gray', style='italic')

ax.set_xticks(x)
ax.set_xticklabels([d[:3] for d in dow_order])
ax.set_ylabel('Avg Daily Revenue (RUB)')
ax.set_title('Day-of-Week Revenue Comparison — OZMALL Offline', fontweight='bold', fontsize=11)
ax.legend()
ax.grid(axis='y', alpha=0.3)

plt.tight_layout()
plt.savefig('chart5_dow_comparison.png', bbox_inches='tight')
plt.close()
print('Chart 5 saved.')

print('\nAll charts generated successfully.')
