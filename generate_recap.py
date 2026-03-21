#!/usr/bin/env python3
"""
NBA Daily Recap — Presto CMS HTML Generator
Class-based CSS (~51KB). JSON copy button for clean clipboard.

Usage: python generate_recap.py
Output: index.html
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
    "GLOBAL RATING":              {"e": "🏀", "d": "Top performers by RAT 365"},
    "WORST GLOBAL RATING":        {"e": "📉", "d": "Lowest-rated performances"},
    "BREAKTHROUGH PLAYER":        {"e": "🚀", "d": "Exceeded season average"},
    "DISAPPOINTMENT":             {"e": "😞", "d": "Fell short of season average"},
    "BEST ROOKIES":               {"e": "⭐", "d": "Top first-year players"},
    "CLUTCH RATING":              {"e": "🎯", "d": "Best in clutch situations"},
    "BEST INTERNATIONAL PLAYERS": {"e": "🌍", "d": "Top non-US players"},
    "BEST BENCH PLAYERS":         {"e": "💺", "d": "Top off the bench"},
    "NET RATING":                 {"e": "🌐", "d": "Points by country", "dn": "STATS PER COUNTRY"},
    "MILESTONES":                 {"e": "🏆", "d": "Career milestones"},
    "SNEAKERS":                   {"e": "👟", "d": "Points by sneaker brand"},
}

CSS = (".nr{font-family:Arial,sans-serif;max-width:700px;margin:0 auto;color:#333}"
       ".nr h1{font-size:20px;font-weight:800;color:#1a1a2e;text-align:center;margin:0 0 2px}"
       ".nr .su{font-size:10px;color:#888;text-align:center;margin:0 0 16px}"
       ".nr .sc{margin-bottom:20px}"
       ".nr .sh{padding:6px 10px;background:#1a1a2e;color:#fff;border-radius:5px 5px 0 0;font-size:13px;font-weight:700}"
       ".nr .sh em{font-size:9px;color:#aaa;font-weight:400;font-style:normal;float:right;margin-top:2px}"
       ".nr table{width:100%;border-collapse:collapse;font-size:11px;border:1px solid #ddd}"
       ".nr th{background:#f2f2f2;color:#555;font-size:9px;font-weight:700;text-transform:uppercase;padding:5px 6px;border-bottom:2px solid #ddd;text-align:left}"
       ".nr th.r{text-align:right}.nr th.c{text-align:center}"
       ".nr td{padding:4px 6px;border-bottom:1px solid #eee;vertical-align:middle}"
       ".nr .rk{text-align:center;font-weight:800;width:24px}.nr .g{color:#d4930d}"
       ".nr .nm{font-weight:600}"
       ".nr .rt{font-weight:700;color:#1a5276;text-align:right;font-size:12px}.nr .ng{color:#c0392b}"
       ".nr .st{color:#555;font-size:10px}"
       ".nr .lg{width:22px;text-align:center}.nr .lg img{width:18px;height:18px;vertical-align:middle}"
       ".nr .ft{text-align:center;font-size:9px;color:#aaa;margin-top:12px;border-top:1px solid #eee;padding-top:8px}"
       ".nr .ft a{color:#1a5276;text-decoration:none}")


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


def cn(v):
    v = v.strip()
    return v[:-3] if v.endswith(".00") else v


def lt(url):
    if url and ("cdn.nba.com" in url or "wikimedia" in url):
        return f'<td class="lg"><img src="{url}"></td>'
    return '<td class="lg"></td>'


def parse_sections(csv_text):
    rows_raw = list(csv.reader(io.StringIO(csv_text)))
    secs, cn2, cr = [], None, []
    for row in rows_raw:
        if not row or all(not c.strip() for c in row[:3]):
            if cn2 and cr: secs.append((cn2, cr)); cr = []; cn2 = None
            continue
        n = row[0].strip()
        if not n: continue
        r = row[1].strip() if len(row) > 1 else ""
        if n.isupper() and len(n) > 3 and (not r or r in ("RAT", "")):
            if cn2 and cr: secs.append((cn2, cr))
            cn2 = n; cr = []; continue
        if any("#N/A" in str(c) for c in row[:11]): continue
        if n and cn2: cr.append(row)
    if cn2 and cr: secs.append((cn2, cr))
    return secs


def build_presto_html(secs, nm):
    hh = lambda n: nm.get(n, n)
    today = datetime.now().strftime("%B %d, %Y")

    o = f'<style>{CSS}</style>'
    o += f'<div class="nr"><h1>NBA DAILY RECAP</h1><p class="su">{today} · Powered by HoopsMatic</p>'

    for sn, sr in secs:
        m = SM.get(sn, {"e": "📊", "d": ""})
        dn = m.get("dn", sn)
        o += f'<div class="sc"><div class="sh">{m["e"]} {dn} <em>{m["d"]}</em></div><table>'

        if sn == "MILESTONES":
            o += '<tr><th class="c">#</th><th class="c"></th><th>Player</th><th class="r">Rank</th><th>Category</th><th>Passing</th></tr>'
            for i, row in enumerate(sr):
                n = hh(row[0].strip()); ps = row[2].strip() if len(row) > 2 else ""
                ct = row[3].strip() if len(row) > 3 else ""; rk = row[4].strip() if len(row) > 4 else ""
                lg = row[11].strip() if len(row) > 11 else ""
                gc = " g" if i < 3 else ""
                o += f'<tr><td class="rk{gc}">{i+1}</td>{lt(lg)}<td class="nm">{n}</td><td class="rt">{rk}</td><td class="st">{ct}</td><td class="st">{ps}</td></tr>'

        elif sn in ("NET RATING", "SNEAKERS"):
            o += '<tr><th class="c">#</th><th class="c"></th><th>Name</th><th class="r">PTS</th><th class="r">REB</th><th class="r">AST</th></tr>'
            for i, row in enumerate(sr):
                n = row[0].strip(); pts = cn(row[3]) if len(row) > 3 else ""
                reb = cn(row[4]) if len(row) > 4 else ""; ast = cn(row[5]) if len(row) > 5 else ""
                lg = row[11].strip() if len(row) > 11 else ""
                gc = " g" if i < 3 else ""
                o += f'<tr><td class="rk{gc}">{i+1}</td>{lt(lg)}<td class="nm">{n}</td><td class="rt">{pts}</td><td class="rt">{reb}</td><td class="rt">{ast}</td></tr>'

        else:
            o += '<tr><th class="c">#</th><th class="c"></th><th>Player</th><th class="r">RAT</th><th>Stats</th></tr>'
            for i, row in enumerate(sr):
                n = hh(row[0].strip()); rat = row[1].strip()
                st = row[2].strip() if len(row) > 2 else ""
                lg = row[11].strip() if len(row) > 11 else ""
                gc = " g" if i < 3 else ""
                rc = " ng" if rat.startswith("-") else ""
                o += f'<tr><td class="rk{gc}">{i+1}</td>{lt(lg)}<td class="nm">{n}</td><td class="rt{rc}">{rat}</td><td class="st">{st}</td></tr>'

        o += '</table></div>'

    o += '<p class="ft">Data by <a href="https://hoopsmatic.com">HoopsMatic</a></p></div>'
    return o


def build_page(presto_html):
    pj = json.dumps(presto_html)
    return f'''<!DOCTYPE html>
<html lang="en"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>NBA Daily Recap</title>
<style>body{{font-family:Arial,sans-serif;background:#f5f5f5;margin:0;padding:20px}}.tb{{max-width:700px;margin:0 auto 12px;display:flex;align-items:center;gap:12px}}.cb{{padding:10px 24px;border:none;border-radius:6px;background:#1a1a2e;color:#fff;font-size:13px;font-weight:700;cursor:pointer}}.cb:hover{{background:#2d2d5e}}.cb.ok{{background:#1e8449}}.cl{{font-size:11px;color:#888}}.pv{{max-width:700px;margin:0 auto;background:#fff;border-radius:8px;box-shadow:0 2px 12px rgba(0,0,0,0.08);padding:16px}}
{CSS}
</style>
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
        print(f"    {SM.get(n, {}).get('dn', n)}: {len(r)} rows")

    presto = build_presto_html(secs, nm)
    page = build_page(presto)

    out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "index.html")
    with open(out, "w", encoding="utf-8") as f:
        f.write(page)

    print(f"\n  Presto payload: {len(presto)/1024:.1f} KB (limit: 85 KB)")
    print(f"  Full page: {os.path.getsize(out)/1024:.1f} KB")
    print("  Open in browser → Copy for Presto → paste into CMS ✓")


if __name__ == "__main__":
    main()
