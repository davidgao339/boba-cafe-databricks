"""
Shared markdown formatting helpers.
"""


def fmt_rub(value):
    return f"₽{int(round(value)):,}"


def fmt_pct(value):
    return f"{value:.1f}%"


def _fmt_diff(diff):
    sign = "+" if diff >= 0 else ""
    # Integer if within float precision, otherwise 1 decimal place
    if abs(diff - round(diff)) < 1e-9:
        return f"{sign}{int(round(diff)):,}"
    return f"{sign}{diff:,.1f}"


def wow_arrow(current, prior):
    if prior == 0:
        return "–"
    diff = current - prior
    pct = diff / prior * 100
    d = _fmt_diff(diff)
    if pct > 0:
        return f"🟢 ↑ {abs(pct):.1f}% ({d})"
    elif pct < 0:
        return f"🔴 ↓ {abs(pct):.1f}% ({d})"
    else:
        return f"→ 0.0% (0)"


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


def write_web_report(html_content, filename, web_reports_dir, title="Report"):
    """
    Write an HTML report to the web repo's reports/ directory and
    regenerate the reports/index.html listing page.

    Parameters
    ----------
    html_content    : str   Full HTML string to write.
    filename        : str   e.g. "2026-04_product_health.html"
    web_reports_dir : str   Absolute path to the reports/ folder in the web repo.
                            Set to None to skip export.
    title           : str   Human-readable title for the index listing.
    """
    import os, glob, re

    if not web_reports_dir:
        return

    os.makedirs(web_reports_dir, exist_ok=True)

    # Write the report file
    report_path = os.path.join(web_reports_dir, filename)
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(html_content)

    # Regenerate index.html from all *.html files in the folder
    pattern = os.path.join(web_reports_dir, "*.html")
    files = sorted(
        [f for f in glob.glob(pattern) if os.path.basename(f) != "index.html"],
        reverse=True,
    )

    def _label(fname):
        """Turn a filename into a readable label."""
        name = os.path.splitext(os.path.basename(fname))[0]
        name = name.replace("_", " ").replace("-", " ")
        return name.title()

    rows = "\n".join(
        f'      <li><a href="{os.path.basename(f)}">{_label(f)}</a></li>'
        for f in files
    )

    index_html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Reports — Boba Cafe</title>
  <style>
    body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
           background: #fdf6ec; color: #5d4037; margin: 0; padding: 40px; }}
    h1   {{ font-size: 1.6em; margin-bottom: 0.25em; }}
    p    {{ color: #8d6e63; margin-top: 0; }}
    ul   {{ list-style: none; padding: 0; max-width: 600px; }}
    li   {{ margin: 10px 0; }}
    a    {{ color: #5d4037; text-decoration: none; border: 1px solid #d7ccc8;
           padding: 10px 16px; border-radius: 6px; display: inline-block;
           background: #fff; width: 100%; box-sizing: border-box; }}
    a:hover {{ background: #8d6e63; color: #fff; border-color: #8d6e63; }}
  </style>
</head>
<body>
  <h1>📊 Boba Cafe Reports</h1>
  <p>Internal analytics — updated automatically.</p>
  <ul>
{rows}
  </ul>
</body>
</html>"""

    index_path = os.path.join(web_reports_dir, "index.html")
    with open(index_path, "w", encoding="utf-8") as f:
        f.write(index_html)

    print(f"Web → {report_path}")
    print(f"Web → {index_path}  ({len(files)} report(s) listed)")


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
