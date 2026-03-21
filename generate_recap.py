#!/usr/bin/env python3
"""
NBA Daily Recap — Presto CMS HTML Generator
Fetches stats recap from Google Sheet (GID 869619953) and generates
index.html with visual preview + "Copy for Presto" button.

Usage: python generate_recap.py
Output: index.html
"""
import csv, io, os, html as html_mod
from datetime import datetime

RECAP_URL = (
    "https://docs.google.com/spreadsheets/d/e/"
    "2PACX-1vSg6im6IYB6HXMGzQbmmBnLw9SfQLzxCSo8OfChxlJLhsB6BBCO0wPF_TMch0YgAbtFqYkwDWrsxRe7"
    "/pub?gid=869619953&single=true&output=csv"
)

NAME_MAP_URL = (
    "https://docs.google.com/spreadsheets/d/e/"
    "2PACX-1vS2iZj3avZ_-CAWKu-f_pxZkf38M0quXQwMbyTXmHsN6-c9V8vU1l_sNaxg0y8dl07dqraU3_5Z3b8D"
    "/pub?gid=1197809522&single=true&output=csv"
)

SECTION_META = {
    "GLOBAL RATING":              {"emoji": "🏀", "desc": "Top performers by RAT 365 rating"},
    "WORST GLOBAL RATING":        {"emoji": "📉", "desc": "Lowest-rated performances"},
    "BREAKTHROUGH PLAYER":        {"emoji": "🚀", "desc": "Exceeded season average the most"},
    "DISAPPOINTMENT":             {"emoji": "😞", "desc": "Fell short of season average"},
    "BEST ROOKIES":               {"emoji": "⭐", "desc": "Top first-year players"},
    "CLUTCH RATING":              {"emoji": "🎯", "desc": "Best in clutch situations (last 5 min, ±5 pts)"},
    "BEST INTERNATIONAL PLAYERS": {"emoji": "🌍", "desc": "Top non-US players"},
    "BEST BENCH PLAYERS":         {"emoji": "💺", "desc": "Top performers off the bench"},
    "NET RATING":                 {"emoji": "🌐", "desc": "Points scored by country", "display_name": "STATS PER COUNTRY"},
    "MILESTONES":                 {"emoji": "🏆", "desc": "Approaching or passing career milestones"},
    "SNEAKERS":                   {"emoji": "👟", "desc": "Points scored by sneaker brand"},
}

PRESTO_CSS = """.nr{font-family:Arial,Helvetica,sans-serif;max-width:720px;margin:0 auto;color:#333}
.nr h1{font-size:22px;font-weight:800;color:#1a1a2e;text-align:center;margin:0 0 4px;letter-spacing:1px}
.nr .sub{font-size:11px;color:#888;text-align:center;margin-bottom:20px}
.nr .sec{margin-bottom:24px}
.nr .sh{display:flex;align-items:center;gap:8px;padding:8px 12px;background:#1a1a2e;color:#fff;border-radius:6px 6px 0 0;font-size:14px;font-weight:700;letter-spacing:0.5px}
.nr .sh .se{font-size:16px}
.nr .sd{font-size:10px;color:#aaa;font-weight:400;margin-left:auto}
.nr table{width:100%;border-collapse:collapse;font-size:11px;border:1px solid #ddd;border-top:none}
.nr th{background:#f2f2f2;color:#555;font-size:9px;font-weight:700;text-transform:uppercase;letter-spacing:0.5px;padding:6px 8px;text-align:left;border-bottom:2px solid #ddd}
.nr th.r{text-align:right}
.nr th.c{text-align:center}
.nr td{padding:5px 8px;border-bottom:1px solid #eee;vertical-align:middle}
.nr tr:nth-child(even) td{background:#fafafa}
.nr td.rk{font-weight:800;color:#1a1a2e;text-align:center;width:28px;font-size:12px}
.nr td.rk.g{color:#d4930d}
.nr td.nm{font-weight:600;color:#222;white-space:nowrap}
.nr td.rt{font-weight:700;color:#1a5276;text-align:right;font-size:12px}
.nr td.rt.neg{color:#c0392b}
.nr td.st{color:#555;font-size:10px}
.nr td.lg{width:24px;text-align:center}
.nr td.lg img{width:20px;height:20px;vertical-align:middle}
.nr .ft{text-align:center;font-size:9px;color:#aaa;margin-top:16px;padding-top:8px;border-top:1px solid #eee}
.nr .ft a{color:#1a5276;text-decoration:none}"""


def fetch_csv(url):
    import requests
    resp = requests.get(url, timeout=30)
    resp.raise_for_status()
    return resp.text


def build_name_map(csv_text):
    nba_to_hh = {}
    reader = csv.reader(io.StringIO(csv_text))
    try:
        next(reader)
    except StopIteration:
        return nba_to_hh
    for row in reader:
        if len(row) < 13:
            continue
        nba = row[11].strip()
        hh = row[12].strip()
        if nba and hh:
            nba_to_hh[nba] = hh
    return nba_to_hh


def hh(name, nm):
    return nm.get(name, name)


def clean_num(v):
    v = v.strip()
    return v[:-3] if v.endswith(".00") else v


def parse_sections(csv_text):
    rows_raw = list(csv.reader(io.StringIO(csv_text)))
    sections = []
    cur_name = None
    cur_rows = []
    for row in rows_raw:
        if not row or all(not c.strip() for c in row[:3]):
            if cur_name and cur_rows:
                sections.append((cur_name, cur_rows))
                cur_rows = []
                cur_name = None
            continue
        name = row[0].strip()
        if not name:
            continue
        rat = row[1].strip() if len(row) > 1 else ""
        if name.isupper() and len(name) > 3 and (not rat or rat in ("RAT", "")):
            if cur_name and cur_rows:
                sections.append((cur_name, cur_rows))
            cur_name = name
            cur_rows = []
            continue
        if any("#N/A" in str(c) for c in row[:11]):
            continue
        if name and cur_name:
            cur_rows.append(row)
    if cur_name and cur_rows:
        sections.append((cur_name, cur_rows))
    return sections


def logo_td(url):
    if url and ("cdn.nba.com" in url or "wikimedia" in url):
        return f'<td class="lg"><img src="{url}" alt=""></td>'
    return '<td class="lg"></td>'


def render_standard(rows, nm):
    h = ('<table><tr><th class="c">#</th><th class="c"></th>'
         '<th>Player</th><th class="r">RAT</th><th>Stats</th></tr>\n')
    for i, row in enumerate(rows):
        name = hh(row[0].strip(), nm)
        rat = row[1].strip()
        stats = row[2].strip() if len(row) > 2 else ""
        logo = row[11].strip() if len(row) > 11 else ""
        rk = " g" if i < 3 else ""
        rc = " neg" if rat.startswith("-") else ""
        h += (f'<tr><td class="rk{rk}">{i+1}</td>{logo_td(logo)}'
              f'<td class="nm">{name}</td><td class="rt{rc}">{rat}</td>'
              f'<td class="st">{stats}</td></tr>\n')
    return h + "</table>\n"


def render_aggregate(rows):
    h = ('<table><tr><th class="c">#</th><th class="c"></th>'
         '<th>Name</th><th class="r">PTS</th>'
         '<th class="r">REB</th><th class="r">AST</th></tr>\n')
    for i, row in enumerate(rows):
        name = row[0].strip()
        pts = clean_num(row[3]) if len(row) > 3 else ""
        reb = clean_num(row[4]) if len(row) > 4 else ""
        ast = clean_num(row[5]) if len(row) > 5 else ""
        logo = row[11].strip() if len(row) > 11 else ""
        rk = " g" if i < 3 else ""
        h += (f'<tr><td class="rk{rk}">{i+1}</td>{logo_td(logo)}'
              f'<td class="nm">{name}</td><td class="rt">{pts}</td>'
              f'<td class="rt">{reb}</td><td class="rt">{ast}</td></tr>\n')
    return h + "</table>\n"


def render_milestones(rows, nm):
    h = ('<table><tr><th class="c">#</th><th class="c"></th>'
         '<th>Player</th><th class="r">Rank</th>'
         '<th>Category</th><th>Passing</th></tr>\n')
    for i, row in enumerate(rows):
        name = hh(row[0].strip(), nm)
        passing = row[2].strip() if len(row) > 2 else ""
        cat = row[3].strip() if len(row) > 3 else ""
        rank = row[4].strip() if len(row) > 4 else ""
        logo = row[11].strip() if len(row) > 11 else ""
        rk = " g" if i < 3 else ""
        h += (f'<tr><td class="rk{rk}">{i+1}</td>{logo_td(logo)}'
              f'<td class="nm">{name}</td><td class="rt">{rank}</td>'
              f'<td class="st">{cat}</td><td class="st">{passing}</td></tr>\n')
    return h + "</table>\n"


def build_presto_html(sections, nm):
    """Build the Presto-compatible HTML snippet (style + content)."""
    today = datetime.now().strftime("%B %d, %Y")

    body = '<div class="nr">\n<h1>NBA DAILY RECAP</h1>\n'
    body += f'<div class="sub">{today} · Powered by HoopsMatic</div>\n'

    for sec_name, sec_rows in sections:
        meta = SECTION_META.get(sec_name, {"emoji": "📊", "desc": ""})
        display = meta.get("display_name", sec_name)
        body += '<div class="sec">\n'
        body += (f'<div class="sh"><span class="se">{meta["emoji"]}</span>'
                 f'{display}<span class="sd">{meta["desc"]}</span></div>\n')
        if sec_name == "MILESTONES":
            body += render_milestones(sec_rows, nm)
        elif sec_name in ("NET RATING", "SNEAKERS"):
            body += render_aggregate(sec_rows)
        else:
            body += render_standard(sec_rows, nm)
        body += '</div>\n'

    body += ('<div class="ft">Data by <a href="https://hoopsmatic.com">'
             'HoopsMatic</a> · NBA Daily Stats Recap</div>\n</div>')

    # Presto-safe style tag
    presto = f'<style>{PRESTO_CSS}\n{"<" + "/style>"}\n{body}'
    return presto


def build_full_page(presto_html):
    """Wrap Presto HTML in a full page with copy button."""
    escaped = html_mod.escape(presto_html)

    return f'''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>NBA Daily Recap</title>
<style>
body {{ font-family: Arial, sans-serif; background: #f5f5f5; margin: 0; padding: 20px; }}
.toolbar {{ max-width: 720px; margin: 0 auto 16px; display: flex; align-items: center; gap: 12px; }}
.copy-btn {{ padding: 10px 24px; border: none; border-radius: 6px; background: #1a1a2e; color: #fff;
  font-size: 13px; font-weight: 700; cursor: pointer; letter-spacing: 0.5px; transition: all 0.15s; }}
.copy-btn:hover {{ background: #2d2d5e; }}
.copy-btn.ok {{ background: #1e8449; }}
.copy-label {{ font-size: 11px; color: #888; }}
.preview {{ max-width: 720px; margin: 0 auto; background: #fff; border-radius: 8px;
  box-shadow: 0 2px 12px rgba(0,0,0,0.08); padding: 20px; }}
{PRESTO_CSS}
</style>
</head>
<body>
<div class="toolbar">
  <button class="copy-btn" id="copyBtn" onclick="copyForPresto()">📋 Copy for Presto</button>
  <span class="copy-label" id="copyLabel">Click to copy HTML for Presto CMS</span>
</div>
<div class="preview" id="preview">
{presto_html}
</div>
<textarea id="prestoCode" style="position:absolute;left:-9999px">{escaped}</textarea>
<script>
function copyForPresto() {{
  const ta = document.getElementById("prestoCode");
  ta.style.position = "fixed";
  ta.style.left = "0";
  ta.style.top = "0";
  ta.select();
  ta.setSelectionRange(0, ta.value.length);
  navigator.clipboard.writeText(ta.value).then(function() {{
    const btn = document.getElementById("copyBtn");
    const lbl = document.getElementById("copyLabel");
    btn.textContent = "✅ Copied!";
    btn.classList.add("ok");
    lbl.textContent = "Paste into Presto CMS Source/HTML mode";
    setTimeout(function() {{
      btn.textContent = "📋 Copy for Presto";
      btn.classList.remove("ok");
      lbl.textContent = "Click to copy HTML for Presto CMS";
    }}, 3000);
  }}).catch(function() {{
    // Fallback
    document.execCommand("copy");
    document.getElementById("copyBtn").textContent = "✅ Copied!";
  }});
  ta.style.position = "absolute";
  ta.style.left = "-9999px";
}}
</script>
</body>
</html>'''


def main():
    print("=" * 50)
    print("  NBA DAILY RECAP — HTML Generator")
    print("=" * 50)

    print("  Fetching name mappings...")
    try:
        nm = build_name_map(fetch_csv(NAME_MAP_URL))
        print(f"  Loaded {len(nm)} name mappings")
    except Exception as e:
        print(f"  Warning: Could not load name map ({e})")
        nm = {}

    print("  Fetching recap data...")
    csv_text = fetch_csv(RECAP_URL)
    sections = parse_sections(csv_text)

    print(f"  Parsed {len(sections)} sections:")
    for name, rows in sections:
        d = SECTION_META.get(name, {}).get("display_name", name)
        print(f"    {d}: {len(rows)} rows")

    presto_html = build_presto_html(sections, nm)
    full_page = build_full_page(presto_html)

    out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "index.html")
    with open(out, "w", encoding="utf-8") as f:
        f.write(full_page)

    print(f"\n  Saved: index.html ({os.path.getsize(out)/1024:.1f} KB)")
    print("  Open in browser → click 'Copy for Presto' → paste into CMS ✓")


if __name__ == "__main__":
    main()
