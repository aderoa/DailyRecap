#!/usr/bin/env python3
"""
NBA Daily Recap — Presto CMS HTML Generator
Matches exact Presto inline-style format.
Usage: python generate_recap.py → index.html
"""
import csv, io, os, json
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

SM = {
    "GLOBAL RATING":              {"title": "Best players of the day",     "note": '* (RAT) <a href="https://www.hoopshype.com/story/sports/nba/2021/10/26/what-is-hoopshypes-global-rating/82908126007/" target="_blank" style="color:#0000EE; text-decoration:underline;">Global Rating</a>, which measures performance based on individual and team stats.'},
    "WORST GLOBAL RATING":        {"title": "Worst players of the day",    "note": "* Minimum 15 minutes played"},
    "BREAKTHROUGH PLAYER":        {"title": "Breakout players of the day", "note": '* (DIFF) Difference between last game and 2025-26 Global Rating (minimum five games played)', "rat_label": "DIFF"},
    "DISAPPOINTMENT":             {"title": "Bombs of the day",            "note": '* (DIFF) Difference between last game and 2025-26 Global Rating (minimum five games played)', "rat_label": "DIFF"},
    "BEST ROOKIES":               {"title": "Best rookies of the day",     "note": '* You can check season rankings <a href="https://www.hoopshype.com/rankings/players/?rookie=true" target="_blank" style="color:#0000EE; text-decoration:underline;">here</a>.'},
    "CLUTCH RATING":              {"title": "Most clutch players",         "note": "* (RAT) Clutch Rating, which measures performance in the last five minutes of 4Q or OT when the score is within five points"},
    "BEST INTERNATIONAL PLAYERS": {"title": "Best international players",  "note": "* Includes players who represent national teams other than Team USA"},
    "BEST BENCH PLAYERS":         {"title": "Best bench players",          "note": ""},
    "NET RATING":                 {"title": "Stats per country",           "note": "* Includes players who represent national teams other than Team USA"},
    "MILESTONES":                 {"title": "All-Time Ranking",            "note": ""},
    "SNEAKERS":                   {"title": "Sneakers",                    "note": ""},
}

S_H2 = "font-size: 22px; font-weight: 700; margin-bottom: 10px; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;"
S_TBL = "border-collapse: collapse; font-family: Arial, sans-serif; font-size: 14px; width: 100%;"
S_TH = "border: 1px solid #ccc; padding: 6px; height:40px; padding:4px 0 4px 6px; min-width:40px; white-space:nowrap"
S_TH_NAME = "border: 1px solid #ccc; height:40px; text-align:left; padding:4px 0 4px 6px; min-width:40px; white-space:nowrap"
S_TD = "height:40px; padding:4px 0 4px 6px; min-width:40px; white-space:nowrap;"
S_TD_NAME = "text-align: left; height: 40px; white-space: nowrap; min-width: 140px"
S_TD_NAME_PAD = "text-align: left; height: 40px; white-space: nowrap; padding: 4px 0 4px 6px; min-width: 140px"
S_TD_STAT = "height:40px; padding:4px 0; text-align: center; min-width:40px; white-space:nowrap"
S_TD_RAT = "height:40px; text-align: center; padding:4px 0 4px 6px; min-width:40px; white-space:nowrap"
S_NOTE = "padding:8px; font-size:13px; font-style:italic;"
S_WRAP = "overflow-x:auto; -webkit-overflow-scrolling:touch; width:100%;"


def fetch_csv(url):
    import requests
    return requests.get(url, timeout=30).text


def build_name_map(csv_text):
    nm = {}
    reader = csv.reader(io.StringIO(csv_text))
    try: next(reader)
    except: return nm
    for row in reader:
        if len(row) < 13: continue
        nba, hh = row[11].strip(), row[12].strip()
        if nba and hh: nm[nba] = hh
    return nm


def bg(i):
    return "#f2f2f2" if i % 2 == 1 else "#ffffff"


def nba_logo_cell(rank, logo_url):
    return (f'<td style="{S_TD}">'
            f"<div style='display:flex; align-items:center; gap:6px;'>"
            f"<span style='font-weight:bold;'>{rank}</span>"
            f'<img src="{logo_url}" style="width:24px; height:24px; object-fit:contain;">'
            f"</div></td>")


def flag_logo_cell(rank, logo_url):
    return (f'<td style="{S_TD}">'
            f"<div style='display:flex; align-items:center; gap:10px;'>"
            f"<span style='font-weight:bold;min-width:20px'>{rank}</span>"
            f'<img src="{logo_url}" style="width:28px; height:20px; object-fit:cover; border-radius:2px;">'
            f"</div></td>")


def parse_sections(csv_text):
    rows_raw = list(csv.reader(io.StringIO(csv_text)))
    secs, cn, cr = [], None, []
    for row in rows_raw:
        if not row or all(not c.strip() for c in row[:3]):
            if cn and cr: secs.append((cn, cr)); cr = []; cn = None
            continue
        n = row[0].strip()
        if not n: continue
        r = row[1].strip() if len(row) > 1 else ""
        if n.isupper() and len(n) > 3 and (not r or r in ("RAT", "")):
            if cn and cr: secs.append((cn, cr))
            cn = n; cr = []; continue
        if any("#N/A" in str(c) for c in row[:11]): continue
        if n and cn: cr.append(row)
    if cn and cr: secs.append((cn, cr))
    return secs


def build_presto_html(secs, nm):
    hh = lambda n: nm.get(n, n)
    h = '<div style="overflow-x: auto; -webkit-overflow-scrolling: touch;">\n'

    for sn, sr in secs:
        m = SM.get(sn, {"title": sn, "note": ""})
        rat_label = m.get("rat_label", "RAT")

        h += f'<h2 style="{S_H2}">{m["title"]}</h2>\n'
        h += f'<div style="{S_WRAP}"><table style="{S_TBL}">\n<thead>\n<tr style="background-color: #f2f2f2;">\n'

        if sn == "MILESTONES":
            h += f'<th style="{S_TH}"></th>\n<th style="{S_TH_NAME}">PLAYER</th>\n'
            h += f'<th style="{S_TH}">CATEGORY</th>\n<th style="{S_TH}">RANK</th>\n'
            h += f'<th style="{S_TH}; text-align:center">PASSED</th>\n'
            h += '</tr>\n</thead>\n<tbody>\n'
            for i, row in enumerate(sr):
                name = hh(row[0].strip())
                passing = row[2].strip() if len(row) > 2 else ""
                cat = row[3].strip() if len(row) > 3 else ""
                rank = row[4].strip() if len(row) > 4 else ""
                logo = row[11].strip() if len(row) > 11 else ""
                h += f'<tr style="background-color:{bg(i)};">\n'
                h += flag_logo_cell("", logo) if logo and ("cdn.nba.com" in logo or "wikimedia" in logo) else f'<td style="{S_TD}"></td>'
                h += f'<td style="{S_TD_NAME_PAD}"><strong>{name}</strong></td>\n'
                h += f'<td style="{S_TD_STAT}">{cat}</td>\n<td style="{S_TD_STAT}">{rank}</td>\n'
                h += f'<td style="{S_TD_STAT}">{passing}</td>\n</tr>\n'

        elif sn == "NET RATING":
            h += f'<th style="{S_TH}"></th>\n<th style="{S_TH_NAME}">COUNTRY</th>\n'
            h += f'<th style="{S_TH}">STATS</th>\n<th style="{S_TH}">PLAYERS</th>\n'
            h += '</tr>\n</thead>\n<tbody>\n'
            rank_counter = 0
            for i, row in enumerate(sr):
                name = row[0].strip()
                stats = row[2].strip() if len(row) > 2 else ""
                players = row[9].strip() if len(row) > 9 else ""
                logo = row[11].strip() if len(row) > 11 else ""
                if "Rest of the World" in name:
                    rn = ""
                else:
                    rank_counter += 1
                    rn = str(rank_counter)
                h += f'<tr style="background-color:{bg(i)};">\n'
                h += flag_logo_cell(rn, logo) if logo and "wikimedia" in logo else f'<td style="{S_TD}"><span style="font-weight:bold">{rn}</span></td>'
                h += f'<td style="{S_TD_NAME_PAD}"><strong>{name}</strong></td>\n'
                h += f'<td style="{S_TD_STAT}">{stats}</td>\n<td style="{S_TD_STAT}">{players}</td>\n</tr>\n'

        elif sn == "SNEAKERS":
            h += f'<th style="{S_TH_NAME}">BRAND</th>\n'
            h += f'<th style="{S_TH}">STATS</th>\n<th style="{S_TH}">PLAYERS</th>\n'
            h += '</tr>\n</thead>\n<tbody>\n'
            for i, row in enumerate(sr):
                name = row[0].strip()
                stats = row[2].strip() if len(row) > 2 else ""
                players = row[9].strip() if len(row) > 9 else ""
                h += f'<tr style="background-color:{bg(i)};">\n'
                h += f'<td style="{S_TD_NAME_PAD}"><strong>{name}</strong></td>\n'
                h += f'<td style="{S_TD_STAT}">{stats}</td>\n<td style="{S_TD_STAT}">{players}</td>\n</tr>\n'

        elif sn == "BEST INTERNATIONAL PLAYERS":
            h += f'<th style="{S_TH}"></th>\n<th style="{S_TH_NAME}">PLAYER</th>\n'
            h += f'<th style="{S_TH}">{rat_label}</th>\n<th style="{S_TH}">STATS</th>\n'
            h += '</tr>\n</thead>\n<tbody>\n'
            for i, row in enumerate(sr):
                name = hh(row[0].strip()); rat = row[1].strip()
                stats = row[2].strip() if len(row) > 2 else ""
                logo = row[11].strip() if len(row) > 11 else ""
                h += f'<tr style="background-color:{bg(i)};">\n'
                h += flag_logo_cell(i + 1, logo) if logo and "wikimedia" in logo else nba_logo_cell(i + 1, logo) if logo and "cdn.nba.com" in logo else f'<td style="{S_TD}"><span style="font-weight:bold">{i+1}</span></td>'
                h += f'<td style="{S_TD_NAME_PAD}"><strong>{name}</strong></td>\n'
                h += f'<td style="{S_TD_RAT}"><strong>{rat}</strong></td>\n'
                h += f'<td style="{S_TD_STAT}">{stats}</td>\n</tr>\n'

        else:
            h += f'<th style="{S_TH}"></th>\n<th style="{S_TH_NAME}">PLAYER</th>\n'
            h += f'<th style="{S_TH}">{rat_label}</th>\n<th style="{S_TH}">STATS</th>\n'
            h += '</tr>\n</thead>\n<tbody>\n'
            for i, row in enumerate(sr):
                name = hh(row[0].strip()); rat = row[1].strip()
                stats = row[2].strip() if len(row) > 2 else ""
                logo = row[11].strip() if len(row) > 11 else ""
                h += f'<tr style="background-color:{bg(i)};">\n'
                h += nba_logo_cell(i + 1, logo) if logo and "cdn.nba.com" in logo else f'<td style="{S_TD}"><span style="font-weight:bold">{i+1}</span></td>'
                h += f'<td style="{S_TD_NAME}"><strong>{name}</strong></td>\n'
                h += f'<td style="{S_TD_RAT}"><strong>{rat}</strong></td>\n'
                h += f'<td style="{S_TD_STAT}">{stats}</td>\n</tr>\n'

        h += '</tbody></table></div>\n'
        if m["note"]:
            h += f'<div style="{S_NOTE}">{m["note"]}</div><br>\n'
        else:
            h += '<br>\n'

    h += '</div>'
    return h


def build_page(presto_html):
    pj = json.dumps(presto_html)
    return f'''<!DOCTYPE html>
<html lang="en"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>NBA Daily Recap</title>
<style>body{{font-family:Arial,sans-serif;background:#f5f5f5;margin:0;padding:20px}}.tb{{max-width:750px;margin:0 auto 12px;display:flex;align-items:center;gap:12px}}.cb{{padding:10px 24px;border:none;border-radius:6px;background:#1a1a2e;color:#fff;font-size:13px;font-weight:700;cursor:pointer}}.cb:hover{{background:#2d2d5e}}.cb.ok{{background:#1e8449}}.cl{{font-size:11px;color:#888}}.pv{{max-width:750px;margin:0 auto;background:#fff;border-radius:8px;box-shadow:0 2px 12px rgba(0,0,0,0.08);padding:16px}}</style>
</head><body>
<div class="tb"><button class="cb" id="cb" onclick="cp()">📋 Copy for Presto</button><span class="cl" id="cl">Click to copy HTML for Presto CMS</span></div>
<div class="pv">{presto_html}</div>
<script>var PH={pj};function cp(){{navigator.clipboard.writeText(PH).then(function(){{var b=document.getElementById("cb"),l=document.getElementById("cl");b.textContent="✅ Copied!";b.className="cb ok";l.textContent="Paste into Presto Source/HTML mode";setTimeout(function(){{b.textContent="📋 Copy for Presto";b.className="cb";l.textContent="Click to copy HTML for Presto CMS"}},3000)}})}}</script>
</body></html>'''


def main():
    print("=" * 50)
    print("  NBA DAILY RECAP — HTML Generator")
    print("=" * 50)

    print("  Fetching name mappings...")
    try:
        nm = build_name_map(fetch_csv(NAME_MAP_URL))
        print(f"  Loaded {len(nm)} name mappings")
    except Exception as e:
        print(f"  Warning: name map failed ({e})")
        nm = {}

    print("  Fetching recap data...")
    secs = parse_sections(fetch_csv(RECAP_URL))
    print(f"  Parsed {len(secs)} sections:")
    for n, r in secs:
        print(f"    {SM.get(n, {}).get('title', n)}: {len(r)} rows")

    presto = build_presto_html(secs, nm)
    page = build_page(presto)

    out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "index.html")
    with open(out, "w", encoding="utf-8") as f:
        f.write(page)

    print(f"\n  Presto payload: {len(presto)/1024:.1f} KB")
    print(f"  Full page: {os.path.getsize(out)/1024:.1f} KB")
    print("  Open in browser → Copy for Presto → paste into CMS ✓")


if __name__ == "__main__":
    main()
