#!/usr/bin/env python3
"""
NBA Daily Recap — Presto CMS HTML Generator
Fetches stats recap from Google Sheet (GID 869619953) and generates
a light-themed, Presto-compatible HTML report.

Usage: python generate_recap.py
Output: index.html (paste into Presto CMS)
"""
import csv, io, os
from datetime import datetime

RECAP_URL = (
    "https://docs.google.com/spreadsheets/d/e/"
    "2PACX-1vSg6im6IYB6HXMGzQbmmBnLw9SfQLzxCSo8OfChxlJLhsB6BBCO0wPF_TMch0YgAbtFqYkwDWrsxRe7"
    "/pub?gid=869619953&single=true&output=csv"
)

# Name mapping sheet: col L = NBA NAME, col M = HH NAME
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


def fetch_csv(url):
    import requests
    resp = requests.get(url, timeout=30)
    resp.raise_for_status()
    return resp.text


def build_name_map(csv_text):
    """Build NBA NAME -> HH NAME mapping from Database sheet."""
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


def hh(name, name_map):
    """Convert a name to HH version."""
    return name_map.get(name, name)


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

        if (name.isupper() and len(name) > 3
                and (not rat or rat in ("RAT", ""))):
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


def logo_td(logo_url):
    if logo_url and ("cdn.nba.com" in logo_url or "wikimedia" in logo_url):
        return f'<td class="lg"><img src="{logo_url}" alt=""></td>'
    return '<td class="lg"></td>'


def clean_score(score):
    score = score.strip()
    if score.endswith("-0") and not score.startswith("0"):
        return ""
    return score


def clean_num(val):
    """Remove trailing .00 from aggregate numbers."""
    val = val.strip()
    if val.endswith(".00"):
        return val[:-3]
    return val


def render_standard(rows, name_map):
    html = ('<table><tr><th class="c">#</th><th class="c"></th>'
            '<th>Player</th><th class="r">RAT</th>'
            '<th>Stats</th><th class="c">Score</th></tr>\n')

    for i, row in enumerate(rows):
        name = hh(row[0].strip(), name_map)
        rat = row[1].strip()
        stats = row[2].strip() if len(row) > 2 else ""
        score = clean_score(row[10]) if len(row) > 10 else ""
        logo = row[11].strip() if len(row) > 11 else ""

        rk_cls = " g" if i < 3 else ""
        rat_cls = " neg" if rat.startswith("-") else ""

        html += (f'<tr><td class="rk{rk_cls}">{i+1}</td>'
                 f'{logo_td(logo)}'
                 f'<td class="nm">{name}</td>'
                 f'<td class="rt{rat_cls}">{rat}</td>'
                 f'<td class="st">{stats}</td>'
                 f'<td class="sc">{score}</td></tr>\n')

    html += "</table>\n"
    return html


def render_aggregate(rows):
    html = ('<table><tr><th class="c">#</th><th class="c"></th>'
            '<th>Name</th><th class="r">PTS</th>'
            '<th class="r">REB</th><th class="r">AST</th></tr>\n')

    for i, row in enumerate(rows):
        name = row[0].strip()
        pts = clean_num(row[3]) if len(row) > 3 else ""
        reb = clean_num(row[4]) if len(row) > 4 else ""
        ast = clean_num(row[5]) if len(row) > 5 else ""
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


def render_milestones(rows, name_map):
    # Columns: [0]=player, [1]=rank(skip), [2]=passing, [3]=category, [4]=behind, [11]=logo
    html = ('<table><tr><th class="c">#</th><th class="c"></th>'
            '<th>Player</th><th>Passing</th>'
            '<th>Category</th><th class="r">Behind</th></tr>\n')

    for i, row in enumerate(rows):
        name = hh(row[0].strip(), name_map)
        passing = row[2].strip() if len(row) > 2 else ""
        cat = row[3].strip() if len(row) > 3 else ""
        behind = row[4].strip() if len(row) > 4 else ""
        logo = row[11].strip() if len(row) > 11 else ""

        rk_cls = " g" if i < 3 else ""
        html += (f'<tr><td class="rk{rk_cls}">{i+1}</td>'
                 f'{logo_td(logo)}'
                 f'<td class="nm">{name}</td>'
                 f'<td class="st">{passing}</td>'
                 f'<td class="st">{cat}</td>'
                 f'<td class="rt">{behind}</td></tr>\n')

    html += "</table>\n"
    return html


def generate_html(sections, name_map):
    today = datetime.now().strftime("%B %d, %Y")

    html = '<div class="nr">\n'
    html += '<h1>NBA DAILY RECAP</h1>\n'
    html += f'<div class="sub">{today} · Powered by HoopsMatic</div>\n'

    for sec_name, sec_rows in sections:
        meta = SECTION_META.get(sec_name, {"emoji": "📊", "desc": ""})
        display_name = meta.get("display_name", sec_name)

        html += '<div class="sec">\n'
        html += (f'<div class="sh"><span class="se">{meta["emoji"]}</span>'
                 f'{display_name}'
                 f'<span class="sd">{meta["desc"]}</span></div>\n')

        if sec_name == "MILESTONES":
            html += render_milestones(sec_rows, name_map)
        elif sec_name in ("NET RATING", "SNEAKERS"):
            html += render_aggregate(sec_rows)
        else:
            html += render_standard(sec_rows, name_map)

        html += '</div>\n'

    html += ('<div class="ft">Data by <a href="https://hoopsmatic.com">'
             'HoopsMatic</a> · NBA Daily Stats Recap</div>\n')
    html += '</div>'

    full = f'<style>{CSS}\n{"<" + "/style>"}\n{html}'
    return full


def main():
    print("=" * 50)
    print("  NBA DAILY RECAP — HTML Generator")
    print("=" * 50)

    print("  Fetching name mappings...")
    try:
        name_csv = fetch_csv(NAME_MAP_URL)
        name_map = build_name_map(name_csv)
        print(f"  Loaded {len(name_map)} name mappings")
    except Exception as e:
        print(f"  Warning: Could not load name map ({e}), using raw names")
        name_map = {}

    print("  Fetching recap data...")
    csv_text = fetch_csv(RECAP_URL)
    sections = parse_sections(csv_text)

    print(f"  Parsed {len(sections)} sections:")
    for name, rows in sections:
        display = SECTION_META.get(name, {}).get("display_name", name)
        print(f"    {display}: {len(rows)} rows")

    html = generate_html(sections, name_map)

    out_path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                            "index.html")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(html)

    size = os.path.getsize(out_path)
    print(f"\n  Saved: index.html")
    print(f"  Size: {size/1024:.1f} KB (Presto limit: 85 KB)")
    print(f"\n  Ready to paste into Presto CMS! ✓")


if __name__ == "__main__":
    main()
