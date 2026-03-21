#!/usr/bin/env python3
"""
NBA Daily Recap — Presto CMS HTML Generator
Fetches stats recap from Google Sheet (GID 869619953) and generates
a light-themed, Presto-compatible HTML report.

Usage: python generate_recap.py
Output: nba_daily_recap.html (paste into Presto CMS)
"""
import csv, io, os, sys
from datetime import datetime

SHEET_URL = (
    "https://docs.google.com/spreadsheets/d/e/"
    "2PACX-1vSg6im6IYB6HXMGzQbmmBnLw9SfQLzxCSo8OfChxlJLhsB6BBCO0wPF_TMch0YgAbtFqYkwDWrsxRe7"
    "/pub?gid=869619953&single=true&output=csv"
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
    "NET RATING":                 {"emoji": "🌐", "desc": "Points scored by country"},
    "MILESTONES":                 {"emoji": "🏆", "desc": "Approaching or passing career milestones"},
    "SNEAKERS":                   {"emoji": "👟", "desc": "Points scored by sneaker brand"},
}

CSS = """
.nr{font-family:Arial,Helvetica,sans-serif;max-width:720px;margin:0 auto;color:#333}
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
.nr td.sc{color:#888;text-align:center;font-size:10px}
.nr td.lg{width:24px;text-align:center}
.nr td.lg img{width:20px;height:20px;vertical-align:middle}
.nr .ft{text-align:center;font-size:9px;color:#aaa;margin-top:16px;padding-top:8px;border-top:1px solid #eee}
.nr .ft a{color:#1a5276;text-decoration:none}
"""


def fetch_csv():
    """Fetch CSV from Google Sheets."""
    import requests
    print("Fetching recap data from Google Sheets...")
    resp = requests.get(SHEET_URL, timeout=30)
    resp.raise_for_status()
    return resp.text


def parse_sections(csv_text):
    """Parse CSV into named sections with rows."""
    rows_raw = list(csv.reader(io.StringIO(csv_text)))
    sections = []
    cur_name = None
    cur_rows = []

    for row in rows_raw:
        # Empty row = section break
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

        # Detect section headers (ALL CAPS, no numeric RAT)
        if (name.isupper() and len(name) > 3
                and (not rat or rat in ("RAT", ""))):
            if cur_name and cur_rows:
                sections.append((cur_name, cur_rows))
            cur_name = name
            cur_rows = []
            continue

        # Skip #N/A rows (DNP players)
        if any("#N/A" in str(c) for c in row[:11]):
            continue

        if name and cur_name:
            cur_rows.append(row)

    if cur_name and cur_rows:
        sections.append((cur_name, cur_rows))

    return sections


def logo_td(logo_url):
    """Generate logo <td> if URL is valid."""
    if logo_url and ("cdn.nba.com" in logo_url or "wikimedia" in logo_url):
        return f'<td class="lg"><img src="{logo_url}" alt=""></td>'
    return '<td class="lg"></td>'


def render_standard(rows):
    """Render a standard player table (Global Rating, Clutch, etc.)."""
    html = '<table><tr><th class="c">#</th><th class="c"></th>'
    html += '<th>Player</th><th class="r">RAT</th><th>Stats</th><th class="c">Score</th></tr>\n'

    for i, row in enumerate(rows):
        name = row[0].strip()
        rat = row[1].strip()
        stats = row[2].strip() if len(row) > 2 else ""
        score = row[10].strip() if len(row) > 10 else ""
        logo = row[11].strip() if len(row) > 11 else ""

        rk_cls = " g" if i < 3 else ""
        rat_cls = " neg" if rat.startswith("-") else ""
        if score.endswith("-0"):
            score = ""

        html += (f'<tr><td class="rk{rk_cls}">{i+1}</td>'
                 f'{logo_td(logo)}'
                 f'<td class="nm">{name}</td>'
                 f'<td class="rt{rat_cls}">{rat}</td>'
                 f'<td class="st">{stats}</td>'
                 f'<td class="sc">{score}</td></tr>\n')

    html += "</table>\n"
    return html


def render_aggregate(rows):
    """Render aggregate table (Net Rating, Sneakers)."""
    html = '<table><tr><th class="c">#</th><th class="c"></th>'
    html += '<th>Name</th><th class="r">PTS</th><th class="r">REB</th><th class="r">AST</th></tr>\n'

    for i, row in enumerate(rows):
        name = row[0].strip()
        pts = row[3].strip() if len(row) > 3 else ""
        reb = row[4].strip() if len(row) > 4 else ""
        ast = row[5].strip() if len(row) > 5 else ""
        logo = row[11].strip() if len(row) > 11 else ""

        rk_cls = " g" if i < 3 else ""
        html += (f'<tr><td class="rk{rk_cls}">{i+1}</td>'
                 f'{logo_td(logo)}'
                 f'<td class="nm">{name}</td>'
                 f'<td class="rt">{pts}</td>'
                 f'<td class="rt">{reb}</td>'
                 f'<td class="rt">{ast}</td></tr>\n')

    html += "</table>\n"
    return html


def render_milestones(rows):
    """Render milestones table."""
    html = '<table><tr><th class="c">#</th><th class="c"></th>'
    html += '<th>Player</th><th class="r">Rank</th><th>Passing</th>'
    html += '<th>Category</th><th class="r">Behind</th></tr>\n'

    for i, row in enumerate(rows):
        name = row[0].strip()
        rank = row[1].strip()
        passing = row[2].strip()
        cat = row[3].strip() if len(row) > 3 else ""
        behind = row[4].strip() if len(row) > 4 else ""
        logo = row[11].strip() if len(row) > 11 else ""

        rk_cls = " g" if i < 3 else ""
        html += (f'<tr><td class="rk{rk_cls}">{i+1}</td>'
                 f'{logo_td(logo)}'
                 f'<td class="nm">{name}</td>'
                 f'<td class="rt">{rank}</td>'
                 f'<td class="st">{passing}</td>'
                 f'<td class="st">{cat}</td>'
                 f'<td class="rt">{behind}</td></tr>\n')

    html += "</table>\n"
    return html


def generate_html(sections):
    """Generate complete Presto-compatible HTML."""
    today = datetime.now().strftime("%B %d, %Y")

    html = '<div class="nr">\n'
    html += '<h1>NBA DAILY RECAP</h1>\n'
    html += f'<div class="sub">{today} · Powered by HoopsMatic</div>\n'

    for sec_name, sec_rows in sections:
        meta = SECTION_META.get(sec_name, {"emoji": "📊", "desc": ""})

        html += '<div class="sec">\n'
        html += (f'<div class="sh"><span class="se">{meta["emoji"]}</span>'
                 f'{sec_name}<span class="sd">{meta["desc"]}</span></div>\n')

        if sec_name == "MILESTONES":
            html += render_milestones(sec_rows)
        elif sec_name in ("NET RATING", "SNEAKERS"):
            html += render_aggregate(sec_rows)
        else:
            html += render_standard(sec_rows)

        html += '</div>\n'

    html += ('<div class="ft">Data by <a href="https://hoopsmatic.com">'
             'HoopsMatic</a> · NBA Daily Stats Recap</div>\n')
    html += '</div>'

    # Wrap with style tag (Presto-safe escaping)
    full = f'<style>{CSS}\n{"<" + "/style>"}\n{html}'
    return full


def main():
    print("=" * 50)
    print("  NBA DAILY RECAP — HTML Generator")
    print("=" * 50)

    csv_text = fetch_csv()
    sections = parse_sections(csv_text)

    print(f"  Parsed {len(sections)} sections:")
    for name, rows in sections:
        print(f"    {name}: {len(rows)} rows")

    html = generate_html(sections)

    out_path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                            "nba_daily_recap.html")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(html)

    size = os.path.getsize(out_path)
    print(f"\n  Saved: {out_path}")
    print(f"  Size: {size/1024:.1f} KB (Presto limit: 85 KB)")
    print(f"\n  Ready to paste into Presto CMS! ✓")


if __name__ == "__main__":
    main()
