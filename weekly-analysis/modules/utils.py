"""
Shared markdown formatting helpers.
"""


def fmt_rub(value):
    return f"₽{int(round(value)):,}"


def fmt_pct(value):
    return f"{value:.1f}%"


def wow_arrow(current, prior):
    if prior == 0:
        return "–"
    pct = (current - prior) / prior * 100
    if pct > 0:
        return f"🟢 ↑ {abs(pct):.1f}%"
    elif pct < 0:
        return f"🔴 ↓ {abs(pct):.1f}%"
    else:
        return "→ 0.0%"


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
    Wrap markdown in a self-contained HTML page rendered by marked.js (CDN).
    Produces clean, styled output suitable for serving as a website page.
    """
    # Escape backticks and backslashes so the markdown is safe inside a JS template literal
    safe_md = markdown_content.replace("\\", "\\\\").replace("`", "\\`").replace("${", "\\${")

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>{title}</title>
  <script src="https://cdn.jsdelivr.net/npm/marked/marked.min.js"></script>
  <style>
    *, *::before, *::after {{ box-sizing: border-box; }}
    body {{
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
      font-size: 15px;
      line-height: 1.6;
      color: #24292e;
      background: #f6f8fa;
      margin: 0;
      padding: 24px;
    }}
    #content {{
      max-width: 1100px;
      margin: 0 auto;
      background: #fff;
      border: 1px solid #d0d7de;
      border-radius: 8px;
      padding: 40px 48px;
    }}
    h1 {{ font-size: 1.9em; border-bottom: 2px solid #d0d7de; padding-bottom: 10px; }}
    h2 {{ font-size: 1.4em; border-bottom: 1px solid #eaecef; padding-bottom: 6px; margin-top: 2em; }}
    h3 {{ font-size: 1.1em; color: #444; margin-top: 1.6em; }}
    table {{
      border-collapse: collapse;
      width: 100%;
      margin: 1em 0;
      font-size: 0.9em;
    }}
    th {{
      background: #f6f8fa;
      border: 1px solid #d0d7de;
      padding: 7px 12px;
      text-align: left;
      white-space: nowrap;
    }}
    td {{
      border: 1px solid #d0d7de;
      padding: 6px 12px;
    }}
    tr:nth-child(even) td {{ background: #f9fafb; }}
    tr:hover td {{ background: #eef2ff; }}
    hr {{ border: none; border-top: 1px solid #d0d7de; margin: 2em 0; }}
    code {{ background: #f3f4f6; padding: 2px 5px; border-radius: 4px; font-size: 0.88em; }}
    em {{ color: #666; }}
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
