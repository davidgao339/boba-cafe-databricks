"""
Automated Publisher for Weekly Reports to GitHub Pages (bobacafe.net/internal/weekly/)
Handles:
1. Branded portal HTML rendering with modern styling and navigation.
2. Local deployment to docs/internal/weekly/index.html and historical archive.
3. Automated push via GitHub REST API to main branch for instant GitHub Pages deployment.
"""
import os
import sys
import base64
import requests
from datetime import datetime, timezone


def render_portal_html(markdown_content, title="Еженедельный отчет", week_start="", week_end=""):
    """
    Renders the weekly markdown report in Style 4: Neo-Editorial (High Contrast Clean / Swiss Grid).
    """
    safe_md = (
        markdown_content
        .replace("\\", "\\\\")
        .replace("`", "\\`")
        .replace("${", "\\${")
    )

    date_badge = f"{week_start} – {week_end}" if week_start and week_end else "Актуальный отчет"

    return f"""<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
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
  --success-bg:   #E3F8E8;
  --success-text: #197A3B;
  --danger-bg:    #FFEBEA;
  --danger-text:  #D70015;
  --warning-bg:   #FFF4E5;
  --warning-text: #B35C00;
  --card-shadow:  0 2px 14px rgba(0, 0, 0, 0.04), 0 0 0 1px #E5E5EA;
}}
* {{ box-sizing: border-box; margin: 0; padding: 0; }}
body {{
  font-family: 'Inter', -apple-system, BlinkMacSystemFont, Arial, sans-serif;
  background: var(--bg);
  color: var(--text-1);
  font-size: 15px;
  line-height: 1.6;
}}
nav {{
  background: var(--surface);
  border-bottom: 1px solid var(--border-light);
  height: 68px;
  padding: 0 32px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  position: sticky;
  top: 0;
  z-index: 100;
  box-shadow: 0 1px 3px rgba(0,0,0,0.02);
}}
.nav-brand {{
  display: flex;
  align-items: center;
  gap: 10px;
  font-family: 'Space Grotesk', sans-serif;
  font-size: 19px;
  font-weight: 700;
  color: var(--text-1);
  text-decoration: none;
  letter-spacing: -0.02em;
}}
.nav-links {{
  display: flex;
  align-items: center;
  gap: 12px;
}}
.nav-link {{
  font-size: 13px;
  font-weight: 600;
  color: var(--text-2);
  text-decoration: none;
  padding: 8px 16px;
  border-radius: 8px;
  transition: all .15s ease;
}}
.nav-link:hover {{
  background: var(--bg-subtle);
  color: var(--text-1);
}}
.nav-link.active {{
  background: var(--brand-light);
  color: var(--brand);
  font-weight: 700;
}}
.nav-tag {{
  font-family: 'Space Grotesk', sans-serif;
  font-size: 11px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  color: var(--brand);
  background: var(--brand-light);
  border: 1px solid var(--brand);
  border-radius: 999px;
  padding: 4px 10px;
}}
.container {{
  max-width: 1200px;
  margin: 0 auto;
  padding: 40px 24px 80px;
}}
.report-card {{
  background: var(--surface);
  border: 1px solid var(--border-light);
  border-radius: 16px;
  box-shadow: var(--card-shadow);
  padding: 44px 52px;
}}
@media (max-width: 768px) {{
  .report-card {{ padding: 24px 18px; }}
  nav {{ padding: 0 16px; }}
}}

/* Typography & Headers */
#report-content h1 {{
  font-family: 'Space Grotesk', sans-serif;
  font-size: 28px;
  font-weight: 700;
  color: var(--text-1);
  letter-spacing: -0.02em;
  border-bottom: 2px solid var(--border-light);
  padding-bottom: 14px;
  margin-bottom: 24px;
}}
#report-content h2 {{
  font-family: 'Space Grotesk', sans-serif;
  font-size: 20px;
  font-weight: 700;
  color: var(--text-1);
  letter-spacing: -0.01em;
  border-bottom: 1px solid var(--border-light);
  padding-bottom: 10px;
  margin-top: 40px;
  margin-bottom: 18px;
}}
#report-content h3 {{
  font-family: 'Space Grotesk', sans-serif;
  font-size: 15px;
  font-weight: 700;
  color: var(--text-2);
  margin-top: 28px;
  margin-bottom: 12px;
  text-transform: uppercase;
  letter-spacing: 0.06em;
}}
#report-content p {{
  margin-bottom: 16px;
  color: var(--text-2);
  line-height: 1.65;
}}
#report-content hr {{
  border: none;
  border-top: 1px solid var(--border-light);
  margin: 36px 0;
}}

/* Tables (Neo-Editorial Precision) */
#report-content table {{
  border-collapse: collapse;
  width: 100%;
  margin: 20px 0 32px;
  font-size: 14px;
  border-radius: 10px;
  overflow: hidden;
  border: 1px solid var(--border-light);
  font-variant-numeric: tabular-nums;
}}
#report-content th {{
  font-family: 'Space Grotesk', sans-serif;
  background: var(--bg-subtle);
  color: var(--text-2);
  font-weight: 700;
  font-size: 12px;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  border-bottom: 1px solid var(--border-light);
  padding: 12px 16px;
  text-align: left;
  white-space: nowrap;
}}
#report-content td {{
  border-bottom: 1px solid var(--border-light);
  padding: 11px 16px;
  color: var(--text-1);
}}
#report-content tr:last-child td {{
  border-bottom: none;
}}
#report-content tr:hover td {{
  background: var(--brand-light);
}}

/* Monospace & Code */
#report-content code {{
  font-family: 'JetBrains Mono', monospace;
  background: var(--bg-subtle);
  padding: 3px 7px;
  border-radius: 4px;
  font-size: 13px;
  border: 1px solid var(--border-light);
}}
#report-content em {{
  color: var(--text-3);
  font-style: italic;
}}

footer {{
  text-align: center;
  padding: 40px 24px;
  font-size: 13px;
  color: var(--text-3);
  border-top: 1px solid var(--border-light);
  margin-top: 60px;
}}
footer a {{ color: var(--brand); text-decoration: none; font-weight: 600; }}
footer a:hover {{ text-decoration: underline; }}
</style>
</head>
<body>

<nav>
  <div style="display:flex; align-items:center; gap:16px;">
    <a href="https://bobacafe.net/internal/" class="nav-brand">🧋 Боба Кролик</a>
    <span class="nav-tag">Executive Portal</span>
  </div>
  <div class="nav-links">
    <a href="https://bobacafe.net/internal/" class="nav-link">← Портал</a>
    <a href="https://bobacafe.net/internal/weekly/" class="nav-link active">📊 Еженедельный отчет</a>
  </div>
</nav>

<div class="container">
  <div class="report-card">
    <div id="report-content"></div>
  </div>
</div>

<footer>
  <a href="https://bobacafe.net/internal/">← Внутренний портал</a> &nbsp;·&nbsp;
  Боба Кролик &copy; 2026 — Только для сотрудников сети
</footer>

<script>
  const md = `{safe_md}`;
  document.getElementById("report-content").innerHTML = marked.parse(md);
</script>
</body>
</html>"""


def get_github_token():
    """Attempt to load GitHub PAT token from secrets or environment."""
    # 1. Environment variable
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        return token

    # 2. pipeline.secrets (used across Databricks repo)
    try:
        from pipeline.secrets import GITHUB_TOKEN
        if GITHUB_TOKEN:
            return GITHUB_TOKEN
    except Exception:
        pass

    try:
        # Databricks dbutils secrets fallback
        import IPython
        dbutils = IPython.get_ipython().user_ns.get("dbutils")
        if dbutils:
            return dbutils.secrets.get(scope="boba-secrets", key="github-token")
    except Exception:
        pass

    return None


def push_to_github(
    html_content,
    path,
    token=None,
    repo="davidgao339/boba-cafe-databricks",
    branch="main",
    message=None,
):
    """
    Pushes HTML content directly to GitHub repo via Contents API to trigger GitHub Pages build.
    """
    token = (token or get_github_token() or "").strip()
    if not token:
        print(f"[Publisher] GITHUB_TOKEN not found. Skipping remote push for {path}.")
        return False

    if not message:
        message = f"auto: publish weekly report to {path} [skip ci]"

    url = f"https://api.github.com/repos/{repo}/contents/{path}"
    auth_header = f"Bearer {token}" if not token.startswith(("Bearer ", "token ")) else token
    headers = {
        "Authorization": auth_header,
        "Accept": "application/vnd.github+json",
        "User-Agent": "BobaCafe-WeeklyReportPublisher",
        "X-GitHub-Api-Version": "2022-11-28",
    }

    try:
        # Check if file exists to retrieve SHA
        r = requests.get(url, headers=headers, params={"ref": branch}, timeout=10)
        sha = r.json().get("sha") if r.status_code == 200 else None

        payload = {
            "message": message,
            "content": base64.b64encode(html_content.encode("utf-8")).decode("ascii"),
            "branch": branch,
        }
        if sha:
            payload["sha"] = sha

        put_res = requests.put(url, headers=headers, json=payload, timeout=15)
        put_res.raise_for_status()
        commit_sha = put_res.json().get("commit", {}).get("sha", "")[:8]
        print(f"[Publisher] Successfully pushed {path} to GitHub ({branch} @ {commit_sha})")
        return True
    except requests.exceptions.HTTPError as he:
        status_code = he.response.status_code if he.response is not None else 0
        if status_code == 401:
            print(f"[Publisher] GITHUB_TOKEN unauthorized (401). Please verify GITHUB_TOKEN in pipeline/secrets.py has 'repo' / 'contents:write' permission.")
        else:
            print(f"[Publisher] Failed to push {path} to GitHub: {he}")
        return False
    except Exception as e:
        print(f"[Publisher] Failed to push {path} to GitHub: {e}")
        return False


def publish_report(
    report_md,
    week_start,
    week_end,
    docs_root=None,
    push_remote=True,
    token=None,
    repo="davidgao339/boba-cafe-databricks",
    branch="main",
):
    """
    Complete publishing lifecycle:
    1. Compiles branded HTML.
    2. Writes locally to docs/internal/weekly/index.html and docs/internal/weekly/archive/{week_start}.html.
    3. Pushes to GitHub via REST API for instant deployment to bobacafe.net/internal/weekly/.
    """
    html_content = render_portal_html(
        markdown_content=report_md,
        title=f"Отчет {week_start} – {week_end}",
        week_start=week_start,
        week_end=week_end,
    )

    # 1. Local filesystem deployment
    if docs_root is None:
        # Resolve docs/internal relative to repository root
        base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        docs_root = os.path.join(base_dir, "docs", "internal", "weekly")

    os.makedirs(docs_root, exist_ok=True)
    archive_dir = os.path.join(docs_root, "archive")
    os.makedirs(archive_dir, exist_ok=True)

    latest_path = os.path.join(docs_root, "index.html")
    archive_path = os.path.join(archive_dir, f"{week_start}.html")

    with open(latest_path, "w", encoding="utf-8") as f:
        f.write(html_content)
    with open(archive_path, "w", encoding="utf-8") as f:
        f.write(html_content)

    print(f"[Publisher] Local report saved -> {latest_path}")
    print(f"[Publisher] Local archive saved -> {archive_path}")

    # 2. Remote GitHub API push
    if push_remote:
        resolved_token = token or get_github_token()
        if resolved_token:
            msg_latest = f"auto: weekly report {week_start} [skip ci]"
            push_to_github(
                html_content=html_content,
                path="docs/internal/weekly/index.html",
                token=resolved_token,
                repo=repo,
                branch=branch,
                message=msg_latest,
            )
            push_to_github(
                html_content=html_content,
                path=f"docs/internal/weekly/archive/{week_start}.html",
                token=resolved_token,
                repo=repo,
                branch=branch,
                message=f"auto: archive weekly report {week_start} [skip ci]",
            )
        else:
            print("[Publisher] Note: No GitHub token configured. Remote push skipped; local files updated.")

    return latest_path, archive_path
