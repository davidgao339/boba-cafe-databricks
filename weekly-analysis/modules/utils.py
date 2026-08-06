"""
Shared markdown formatting helpers.
"""
import pandas as pd


def fmt_rub(value):
    if pd.isna(value):
        return "₽0"
    return f"₽{int(round(value)):,}"


def fmt_diff_rub(current, prior):
    if pd.isna(current) or pd.isna(prior):
        return "–"
    diff = current - prior
    if abs(diff) < 1:
        return "₽0"
    sign = "+" if diff > 0 else "-"
    return f"{sign}₽{abs(int(round(diff))):,}"


def fmt_pct(value):
    if pd.isna(value):
        return "0.0%"
    return f"{value:.1f}%"


def pct_arrow(current, baseline):
    """Clean directional percentage change string (e.g. ↑ 19.1% or ↓ 24.6%)."""
    if pd.isna(current) or pd.isna(baseline) or baseline == 0:
        return "–"
    diff = current - baseline
    pct = diff / baseline * 100
    if pct > 0:
        return f"↑ {pct:.1f}%"
    elif pct < 0:
        return f"↓ {abs(pct):.1f}%"
    else:
        return "→ 0.0%"


def wow_arrow(current, prior):
    """Backwards-compatible directional percentage change."""
    return pct_arrow(current, prior)


def trend_status(this_week, prior_week, rolling_avg, min_revenue=1000):
    """
    Computes an executive trend status badge by evaluating both WoW and 4-Week Rolling Average:
    - 🟢 Breakout: Gaining momentum above 4W baseline and positive WoW
    - 🟡 Rebound: Positive WoW but still below 4W baseline (recovering from a prior dip)
    - 🔴 Underperforming: Down vs both prior week and 4W baseline
    - ⚪ Core / Stable: Operating within expected baseline range (±5%)
    - ⚪ Normalizing: Post-peak cool off, but still healthy vs 4W baseline
    """
    if pd.isna(this_week) or this_week < min_revenue:
        return "⚪ Inactive"
    if pd.isna(rolling_avg) or rolling_avg <= 0:
        return "⚪ New / Baseline"

    prior = 0 if pd.isna(prior_week) else prior_week
    wow_pct = (this_week - prior) / prior if prior > 0 else 0
    vs_4w_pct = (this_week - rolling_avg) / rolling_avg

    if vs_4w_pct >= 0.05 and wow_pct >= 0:
        return "🟢 Breakout"
    elif wow_pct >= 0.05 and vs_4w_pct < -0.05:
        return "🟡 Rebound"
    elif vs_4w_pct <= -0.05 and wow_pct <= 0:
        return "🔴 Underperforming"
    elif vs_4w_pct <= -0.10:
        return "🔴 Action Needed"
    elif wow_pct < 0 and vs_4w_pct >= 0.03:
        return "⚪ Normalizing"
    elif abs(vs_4w_pct) <= 0.05:
        return "⚪ Core"
    elif vs_4w_pct > 0:
        return "🟢 Solid"
    else:
        return "⚪ Stable"


def md_table(df, formatters=None):
    """Render a pandas DataFrame as a markdown table string."""
    formatters = formatters or {}
    df = df.copy()
    for col, fn in formatters.items():
        if col in df.columns:
            df[col] = df[col].apply(fn)

    header = "| " + " | ".join(str(c) for c in df.columns) + " |"
    sep    = "| " + " | ".join("---" for _ in df.columns) + " |"
    rows   = [
        "| " + " | ".join(str(v) for v in row) + " |"
        for row in df.itertuples(index=False)
    ]
    return "\n".join([header, sep] + rows)


def section(title, level=2):
    return "\n" + "#" * level + " " + title + "\n"



def md_to_html(markdown_content, title="Weekly Report"):
    """
    Wrap markdown in a clean, self-contained HTML page in Neo-Editorial style.
    """
    safe_md = markdown_content.replace("\\", "\\\\").replace("`", "\\`").replace("${", "\\${")

    return f"""<!DOCTYPE html>
<html lang="ru">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>{title} | Боба Кролик</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=Space+Grotesk:wght@500;600;700&family=JetBrains+Mono:wght@400;500;600&display=swap" rel="stylesheet">
  <script src="https://cdn.jsdelivr.net/npm/marked/marked.min.js"></script>
  <style>
    :root {{
      --bg:           #F5F5F7;
      --bg-subtle:    #EBEBEF;
      --surface:      #FFFFFF;
      --border:       #D1D1D6;
      --border-light: #E5E5EA;
      --text-1:       #1C1C1E;
      --text-2:       #636366;
      --text-3:       #8E8E93;
      --brand:        #FF453A;
      --brand-light:  #FFF1F0;
      --card-shadow:  0 2px 14px rgba(0, 0, 0, 0.04), 0 0 0 1px #E5E5EA;
    }}
    *, *::before, *::after {{ box-sizing: border-box; }}
    body {{
      font-family: 'Inter', -apple-system, BlinkMacSystemFont, Arial, sans-serif;
      font-size: 15px;
      line-height: 1.65;
      color: var(--text-1);
      background: var(--bg);
      margin: 0;
      padding: 32px 24px;
    }}
    #content {{
      max-width: 1140px;
      margin: 0 auto;
      background: var(--surface);
      border: 1px solid var(--border-light);
      border-radius: 16px;
      padding: 44px 52px;
      box-shadow: var(--card-shadow);
    }}
    h1 {{
      font-family: 'Space Grotesk', sans-serif;
      font-size: 26px;
      font-weight: 700;
      letter-spacing: -0.02em;
      border-bottom: 2px solid var(--border-light);
      padding-bottom: 12px;
      margin-top: 0;
    }}
    h2 {{
      font-family: 'Space Grotesk', sans-serif;
      font-size: 19px;
      font-weight: 700;
      letter-spacing: -0.01em;
      border-bottom: 1px solid var(--border-light);
      padding-bottom: 8px;
      margin-top: 36px;
    }}
    h3 {{
      font-family: 'Space Grotesk', sans-serif;
      font-size: 14px;
      font-weight: 700;
      color: var(--text-2);
      text-transform: uppercase;
      letter-spacing: 0.06em;
      margin-top: 24px;
    }}
    p {{ color: var(--text-2); margin-bottom: 14px; }}
    table {{
      border-collapse: collapse;
      width: 100%;
      margin: 18px 0 28px;
      font-size: 14px;
      border-radius: 10px;
      overflow: hidden;
      border: 1px solid var(--border-light);
      font-variant-numeric: tabular-nums;
    }}
    th {{
      font-family: 'Space Grotesk', sans-serif;
      background: var(--bg-subtle);
      color: var(--text-2);
      font-weight: 700;
      font-size: 12px;
      text-transform: uppercase;
      letter-spacing: 0.05em;
      border-bottom: 1px solid var(--border-light);
      padding: 11px 15px;
      text-align: left;
      white-space: nowrap;
    }}
    td {{
      border-bottom: 1px solid var(--border-light);
      padding: 10px 15px;
      color: var(--text-1);
    }}
    tr:last-child td {{ border-bottom: none; }}
    tr:hover td {{ background: var(--brand-light); }}
    hr {{ border: none; border-top: 1px solid var(--border-light); margin: 32px 0; }}
    code {{
      font-family: 'JetBrains Mono', monospace;
      background: var(--bg-subtle);
      padding: 2px 6px;
      border-radius: 4px;
      font-size: 13px;
      border: 1px solid var(--border-light);
    }}
    em {{ color: var(--text-3); }}
  </style>
</head>
<body>
  <div id="content"></div>
  <script>
    const md = `{safe_md}`;
    document.getElementById("content").innerHTML = marked.parse(md);
  </script>
</body>
</html>"""
