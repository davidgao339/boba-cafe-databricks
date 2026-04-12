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
    arrow = "↑" if pct > 0 else "↓" if pct < 0 else "→"
    return f"{arrow} {abs(pct):.1f}%"


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
