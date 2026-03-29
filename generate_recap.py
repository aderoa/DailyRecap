#!/usr/bin/env python3
"""
NBA Daily Recap — Presto CMS HTML Generator
Team abbreviations, country codes, dark section headers, no images.
Usage: python generate_recap.py → index.html
"""
import csv, io, os, json, re

# ── Data URLs ────────────────────────────────────────────────────────
RECAP_URL = "https://docs.google.com/spreadsheets/d/e/2PACX-1vSg6im6IYB6HXMGzQbmmBnLw9SfQLzxCSo8OfChxlJLhsB6BBCO0wPF_TMch0YgAbtFqYkwDWrsxRe7/pub?gid=869619953&single=true&output=csv"
NAME_MAP_URL = "https://docs.google.com/spreadsheets/d/e/2PACX-1vS2iZj3avZ_-CAWKu-f_pxZkf38M0quXQwMbyTXmHsN6-c9V8vU1l_sNaxg0y8dl07dqraU3_5Z3b8D/pub?gid=1197809522&single=true&output=csv"

# ── Mappings ─────────────────────────────────────────────────────────
# NBA team ID (from cdn.nba.com logo URLs) → 3-letter abbreviation
TEAM_ID_MAP = {
    "1610612737": "ATL", "1610612738": "BOS", "1610612739": "CLE",
    "1610612740": "NOP", "1610612741": "CHI", "1610612742": "DAL",
    "1610612743": "DEN", "1610612744": "GSW", "1610612745": "HOU",
    "1610612746": "LAC", "1610612747": "LAL", "1610612748": "MIA",
    "1610612749": "MIL", "1610612750": "MIN", "1610612751": "BKN",
    "1610612752": "NYK", "1610612753": "ORL", "1610612754": "IND",
    "1610612755": "PHI", "1610612756": "PHX", "1610612757": "POR",
    "1610612758": "SAC", "1610612759": "SAS", "1610612760": "OKC",
    "1610612761": "TOR", "1610612762": "UTA", "1610612763": "MEM",
    "1610612764": "WAS", "1610612765": "DET", "1610612766": "CHA",
}

# Flag URL substring → 2-letter ISO country code (for international section)
FLAG_TO_CODE = {
    "Canada": "CA", "Serbia": "RS", "Bosnia": "BA", "France": "FR",
    "Dominican_Republic": "DO", "Turkey": "TR", "Israel": "IL",
    "Austria": "AT", "Portugal": "PT", "Jamaica": "JM",
    "United_Kingdom": "GB", "Philippines": "PH", "Switzerland": "CH",
    "Montenegro": "ME", "Spain": "ES", "Germany": "DE",
    "Australia": "AU", "Cameroon": "CM", "Belgium": "BE",
    "Georgia": "GE", "Slovenia": "SI", "Latvia": "LV",
    "Brazil": "BR", "Lithuania": "LT", "Nigeria": "NG",
    "Sweden": "SE", "China": "CN", "Senegal": "SN",
    "United_States": "US", "US_Virgin": "VI", "Czech": "CZ",
    "Croatia": "HR", "Greece": "GR", "Japan": "JP",
    "South_Sudan": "SS", "Ukraine": "UA", "Italy": "IT",
    "Mexico": "MX", "New_Zealand": "NZ", "Congo": "CD",
    "Argentina": "AR", "Colombia": "CO", "Puerto_Rico": "PR",
    "Bahamas": "BS", "Trinidad": "TT", "Tunisia": "TN",
    "Mali": "ML", "Egypt": "EG", "Korea": "KR",
    "Poland": "PL", "Finland": "FI", "Norway": "NO",
    "Denmark": "DK", "Ireland": "IE", "Taiwan": "TW",
    "Haiti": "HT", "Cape_Verde": "CV", "the_People": "CN",
    "Russia": "RU", "Gabon": "GA", "Guinea": "GN",
    "Angola": "AO", "South_Africa": "ZA", "Morocco": "MA",
    "Iran": "IR", "Lebanon": "LB", "India": "IN",
    "Netherlands": "NL",
}

# ── Section config ───────────────────────────────────────────────────
SM = {
    "GLOBAL RATING":           {"title": "Best players of the day",
        "note": '* (RAT) <a href="https://www.hoopshype.com/story/sports/nba/2021/10/26/what-is-hoopshypes-global-rating/82908126007/" target="_blank" style="color:#0000EE;text-decoration:underline">Global Rating</a>, which measures performance based on individual and team stats. You can check season rankings <a href="https://www.hoopshype.com/rankings/players/" target="_blank" style="color:#0000EE;text-decoration:underline">here</a>.'},
    "WORST GLOBAL RATING":     {"title": "Worst players of the day",
        "note": "* Minimum 15 minutes played"},
    "BREAKTHROUGH PLAYER":     {"title": "Breakout players of the day",
        "note": '* (DIFF) Difference between last game and 2025-26 Global Rating (minimum five games played)', "rl": "DIFF"},
    "DISAPPOINTMENT":          {"title": "Bombs of the day",
        "note": '* (DIFF) Difference between last game and 2025-26 Global Rating (minimum five games played)', "rl": "DIFF"},
    "BEST ROOKIES":            {"title": "Best rookies of the day",
        "note": '* You can check season rankings <a href="https://www.hoopshype.com/rankings/players/?rookie=true" target="_blank" style="color:#0000EE;text-decoration:underline">here</a>.'},
    "CLUTCH RATING":           {"title": "Most clutch players",
        "note": "* (RAT) Clutch Rating, which measures performance in the last five minutes of 4Q or OT when the score is within five points"},
    "BEST INTERNATIONAL PLAYERS": {"title": "Best international players",
        "note": "* Includes players who represent national teams other than Team USA"},
    "BEST BENCH PLAYERS":      {"title": "Best bench players", "note": ""},
    "NET RATING":              {"title": "Stats per country",
        "note": "* Includes players who represent national teams other than Team USA"},
    "MILESTONES":              {"title": "All-Time Ranking", "note": ""},
    "SNEAKERS":                {"title": "Sneakers", "note": ""},
}
EM = {
    "GLOBAL RATING": "🏀", "WORST GLOBAL RATING": "📉",
    "BREAKTHROUGH PLAYER": "🚀", "DISAPPOINTMENT": "😞",
    "BEST ROOKIES": "⭐", "CLUTCH RATING": "🎯",
    "BEST INTERNATIONAL PLAYERS": "🌍", "BEST BENCH PLAYERS": "💺",
    "NET RATING": "🌐", "MILESTONES": "🏆", "SNEAKERS": "👟",
}

# ── Inline styles (Presto-compatible) ────────────────────────────────
FN = "font-family:Arial,Helvetica,sans-serif"
SH = FN + ";padding:8px 12px;background:#1a1a2e;color:#fff;font-size:14px;font-weight:700;letter-spacing:0.5px;margin-top:24px;margin-bottom:0;border-radius:5px 5px 0 0"
TBL = "border-collapse: collapse; font-family: Arial, sans-serif; font-size: 14px; width: 100%; border: none;"
TH = "border: none; padding:4px 0 4px 6px; height:40px; min-width:40px; white-space:nowrap"
TH_NAME = "border: none; height:40px; text-align:left; padding:4px 0 4px 6px; min-width:40px; white-space:nowrap"
TD = "border: none; height:40px; padding:4px 0 4px 6px; min-width:40px; white-space:nowrap"
TD_NAME = "border: none; text-align:left; height:40px; white-space:nowrap; min-width:140px"
TD_STAT = "border: none; height:40px; padding:4px 0; text-align:center; min-width:40px; white-space:nowrap"
TD_RAT = "border: none; height:40px; text-align:center; padding:4px 0 4px 6px; min-width:40px; white-space:nowrap"
NOTE = "padding:8px; font-size:13px; font-style:italic;"
ZW = "&#8203;"  # zero-width space — Presto can't strip this

INTRO = '<p style="font-size:14px;color:#333;margin:0 0 16px;font-family:Arial,sans-serif">Every day, we bring you the best and worst performers from the previous night in the NBA.</p>'
OUTRO = (
    '<p style="font-size:13px;color:#555;margin:16px 0 4px;font-family:Arial,sans-serif;font-style:italic">'
    'This content may be blocked in parts of Europe due to GDPR. To use it, connect your VPN to a non-EU country and try again.</p>'
    '<p style="font-size:13px;color:#555;margin:4px 0;font-family:Arial,sans-serif;font-style:italic">'
    'We highly recommend you add HoopsHype as a preferred source on Google. You just have to '
    '<a href="https://news.google.com/publications/CAAqBwgKMK_RpQswnMOxAw" target="_blank" style="color:#0000EE;text-decoration:underline">click here</a>.</p>'
)


# ── Helpers ──────────────────────────────────────────────────────────
def fetch_csv(url):
    """Fetch CSV with cache-busting and forced UTF-8."""
    import requests, time
    url += f"&_cb={int(time.time())}"
    r = requests.get(url, timeout=30, headers={"Cache-Control": "no-cache"})
    r.encoding = "utf-8"
    return r.text


def build_name_map(text):
    """Build NBA API name → HoopsHype name map from Database sheet."""
    nm = {}
    reader = csv.reader(io.StringIO(text))
    try:
        next(reader)
    except StopIteration:
        return nm
    for row in reader:
        if len(row) < 13:
            continue
        nba, hh = row[11].strip(), row[12].strip()
        if nba and hh:
            nm[nba] = hh
    return nm


def bg(i):
    return "#f2f2f2" if i % 2 == 1 else "#ffffff"


def get_team_abbr(logo_url):
    """Extract team abbreviation from NBA CDN logo URL."""
    if not logo_url or "cdn.nba.com" not in logo_url:
        return ""
    m = re.search(r"/(\d{10})/", logo_url)
    return TEAM_ID_MAP.get(m.group(1), "") if m else ""


def get_country_code(flag_url):
    """Extract 2-letter country code from Wikimedia flag URL."""
    if not flag_url:
        return ""
    for substr, code in FLAG_TO_CODE.items():
        if substr in flag_url:
            return code
    return ""


def fix_sep(s):
    """Replace middot separators with hyphens.
    Handles both proper UTF-8 middot and double-encoded Â· from latin-1."""
    s = s.replace("\u00c2\u00b7", "-").replace("\u00c2\xb7", "-")
    s = s.replace(" \u00b7 ", " - ").replace("\u00b7", "-")
    s = s.replace("\u00c2-", "-").replace("\u00c2 ", " ").replace("  ", " ")
    return s


# ── Parsing ──────────────────────────────────────────────────────────
def parse_sections(text):
    """Parse CSV into list of (section_name, rows) tuples."""
    rows = list(csv.reader(io.StringIO(text)))
    secs = []
    cur_name = None
    cur_rows = []
    for row in rows:
        if not row or all(not c.strip() for c in row[:3]):
            if cur_name and cur_rows:
                secs.append((cur_name, cur_rows))
                cur_rows = []
                cur_name = None
            continue
        name = row[0].strip()
        if not name:
            continue
        val = row[1].strip() if len(row) > 1 else ""
        if name.isupper() and len(name) > 3 and (not val or val in ("RAT", "")):
            if cur_name and cur_rows:
                secs.append((cur_name, cur_rows))
            cur_name = name
            cur_rows = []
            continue
        if any("#N/A" in str(c) for c in row[:11]):
            continue
        if name and cur_name:
            cur_rows.append(row)
    if cur_name and cur_rows:
        secs.append((cur_name, cur_rows))
    return secs


# ── HTML Builder ─────────────────────────────────────────────────────
def build_presto_html(secs, nm):
    hh = lambda n: nm.get(n, n)
    o = f'<div style="overflow-x: auto; -webkit-overflow-scrolling: touch;">\n{INTRO}\n'

    for sn, sr in secs:
        m = SM.get(sn, {"title": sn, "note": ""})
        rl = m.get("rl", "RAT")
        emoji = EM.get(sn, "📊")

        # Section header
        o += f'<div style="{SH}"><span style="font-size:16px;margin-right:6px">{emoji}</span> {m["title"]}</div>\n'
        o += f'<div style="overflow-x:auto; -webkit-overflow-scrolling:touch; width:100%;"><table style="{TBL}">\n<thead>\n<tr style="background-color: #f2f2f2;">\n'

        # ── Milestones: TEAM | Player | Category | Rank | Passed
        if sn == "MILESTONES":
            o += f'<th style="{TH}">{ZW}</th>\n<th style="{TH_NAME}">PLAYER</th>\n<th style="{TH}">CATEGORY</th>\n<th style="{TH}">RANK</th>\n<th style="{TH}; text-align:center">PASSED</th>\n</tr>\n</thead>\n<tbody>\n'
            for i, row in enumerate(sr):
                name = hh(row[0].strip())
                passed = row[2].strip() if len(row) > 2 else ""
                cat = row[3].strip() if len(row) > 3 else ""
                rank = row[4].strip() if len(row) > 4 else ""
                logo = row[11].strip() if len(row) > 11 else ""
                team = get_team_abbr(logo)
                o += f'<tr style="background-color:{bg(i)};">\n'
                o += f'<td style="{TD};font-size:11px;color:#888;text-align:center"><strong>{team}</strong></td>\n'
                o += f'<td style="{TD_NAME}"><strong>{name}</strong></td>\n'
                o += f'<td style="{TD_STAT}">{cat}</td>\n<td style="{TD_STAT}">{rank}</td>\n<td style="{TD_STAT}">{passed}</td>\n</tr>\n'

        # ── Stats per country: # | Country | Stats | Players
        elif sn == "NET RATING":
            o += f'<th style="{TH}">{ZW}</th>\n<th style="{TH_NAME}">COUNTRY</th>\n<th style="{TH}">STATS</th>\n<th style="{TH}">PLAYERS</th>\n</tr>\n</thead>\n<tbody>\n'
            rc = 0
            for i, row in enumerate(sr):
                name = row[0].strip()
                stats = fix_sep(row[2].strip()) if len(row) > 2 else ""
                players = row[9].strip() if len(row) > 9 else ""
                if "Rest of the World" in name:
                    rn = ZW
                else:
                    rc += 1
                    rn = str(rc)
                o += f'<tr style="background-color:{bg(i)};">\n'
                o += f'<td style="{TD}"><span style="font-weight:bold;">{rn}</span></td>\n'
                o += f'<td style="{TD_NAME}"><strong>{name}</strong></td>\n'
                o += f'<td style="{TD_STAT}">{stats}</td>\n<td style="{TD_STAT}">{players}</td>\n</tr>\n'

        # ── Sneakers: Brand | Stats | Players
        elif sn == "SNEAKERS":
            o += f'<th style="{TH_NAME}">BRAND</th>\n<th style="{TH}">STATS</th>\n<th style="{TH}">PLAYERS</th>\n</tr>\n</thead>\n<tbody>\n'
            for i, row in enumerate(sr):
                name = row[0].strip()
                stats = fix_sep(row[2].strip()) if len(row) > 2 else ""
                players = row[9].strip() if len(row) > 9 else ""
                o += f'<tr style="background-color:{bg(i)};">\n'
                o += f'<td style="{TD_NAME}"><strong>{name}</strong></td>\n'
                o += f'<td style="{TD_STAT}">{stats}</td>\n<td style="{TD_STAT}">{players}</td>\n</tr>\n'

        # ── International: #/CC | Player | RAT | Stats
        elif sn == "BEST INTERNATIONAL PLAYERS":
            o += f'<th style="{TH}">{ZW}</th>\n<th style="{TH_NAME}">PLAYER</th>\n<th style="{TH}">{rl}</th>\n<th style="{TH}">STATS</th>\n</tr>\n</thead>\n<tbody>\n'
            for i, row in enumerate(sr):
                name = hh(row[0].strip())
                rat = row[1].strip()
                stats = fix_sep(row[2].strip()) if len(row) > 2 else ""
                flag = row[11].strip() if len(row) > 11 else ""
                cc = get_country_code(flag)
                o += f'<tr style="background-color:{bg(i)};">\n'
                o += f'<td style="{TD}"><span style="font-weight:bold;">{i + 1}</span> <span style="font-size:11px;color:#888;margin-left:8px">{cc}</span></td>\n'
                o += f'<td style="{TD_NAME}"><strong>{name}</strong></td>\n'
                o += f'<td style="{TD_RAT}"><strong>{rat}</strong></td>\n<td style="{TD_STAT}">{stats}</td>\n</tr>\n'

        # ── Standard: #/TEAM | Player | RAT/DIFF | Stats
        else:
            o += f'<th style="{TH}">{ZW}</th>\n<th style="{TH_NAME}">PLAYER</th>\n<th style="{TH}">{rl}</th>\n<th style="{TH}">STATS</th>\n</tr>\n</thead>\n<tbody>\n'
            for i, row in enumerate(sr):
                name = hh(row[0].strip())
                rat = row[1].strip()
                stats = fix_sep(row[2].strip()) if len(row) > 2 else ""
                logo = row[11].strip() if len(row) > 11 else ""
                team = get_team_abbr(logo)
                o += f'<tr style="background-color:{bg(i)};">\n'
                o += f'<td style="{TD}"><span style="font-weight:bold;">{i + 1}</span> <span style="font-size:11px;color:#888;margin-left:8px">{team}</span></td>\n'
                o += f'<td style="{TD_NAME}"><strong>{name}</strong></td>\n'
                o += f'<td style="{TD_RAT}"><strong>{rat}</strong></td>\n<td style="{TD_STAT}">{stats}</td>\n</tr>\n'

        o += '</tbody></table></div>\n'
        if m.get("note"):
            o += f'<div style="{NOTE}">{m["note"]}</div><br>\n'
        else:
            o += '<br>\n'

    o += f'{OUTRO}\n</div>'
    return o


def build_page(presto_html):
    payload_json = json.dumps(presto_html)
    return f'''<!DOCTYPE html>
<html lang="en"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>NBA Daily Recap</title>
<style>body{{font-family:Arial,sans-serif;background:#f5f5f5;margin:0;padding:20px}}.tb{{max-width:750px;margin:0 auto 12px;display:flex;align-items:center;gap:12px}}.cb{{padding:10px 24px;border:none;border-radius:6px;background:#1a1a2e;color:#fff;font-size:13px;font-weight:700;cursor:pointer}}.cb:hover{{background:#2d2d5e}}.cb.ok{{background:#1e8449}}.cl{{font-size:11px;color:#888}}.pv{{max-width:750px;margin:0 auto;background:#fff;border-radius:8px;box-shadow:0 2px 12px rgba(0,0,0,0.08);padding:16px}}</style>
</head><body>
<div class="tb"><button class="cb" id="cb" onclick="cp()">📋 Copy for Presto</button><span class="cl" id="cl">Click to copy HTML for Presto CMS</span></div>
<div class="pv">{presto_html}</div>
<script>var PH={payload_json};function cp(){{navigator.clipboard.writeText(PH).then(function(){{var b=document.getElementById("cb"),l=document.getElementById("cl");b.textContent="\\u2705 Copied!";b.className="cb ok";l.textContent="Paste into Presto Source/HTML mode";setTimeout(function(){{b.textContent="\\ud83d\\udccb Copy for Presto";b.className="cb";l.textContent="Click to copy HTML for Presto CMS"}},3000)}})}}</script>
</body></html>'''


# ── Main ─────────────────────────────────────────────────────────────
MILESTONES_CSV = "milestones_today.csv"   # auto-generated by milestones.py


def load_auto_milestones():
    """Load milestones from milestones_today.csv if it exists.
    Returns list of fake CSV rows matching the MILESTONES section format:
      row[0]=player, row[2]=passed, row[3]=category, row[4]=rank, row[11]=logo
    """
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), MILESTONES_CSV)
    if not os.path.exists(path):
        return None
    rows = []
    with open(path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for r in reader:
            # Build a 12-element row matching the Sheet format
            row = [""] * 12
            row[0] = r.get("PLAYER", "")
            row[1] = ""
            row[2] = r.get("PASSED", "")
            row[3] = r.get("CATEGORY", "")
            row[4] = r.get("RANK", "")
            row[11] = r.get("LOGO_URL", "")  # team logo URL (optional)
            rows.append(row)
    return rows if rows else None


def main():
    print("=" * 50)
    print("  NBA DAILY RECAP — HTML Generator")
    print("=" * 50)

    print("  Fetching name mappings...")
    try:
        nm = build_name_map(fetch_csv(NAME_MAP_URL))
        print(f"  Loaded {len(nm)} mappings")
    except Exception as e:
        print(f"  Warning: {e}")
        nm = {}

    print("  Fetching recap data...")
    secs = parse_sections(fetch_csv(RECAP_URL))

    # ── Auto-milestones: replace Sheet milestones with auto-detected ones
    auto_ms = load_auto_milestones()
    if auto_ms:
        print(f"  Loaded {len(auto_ms)} auto-detected milestones from {MILESTONES_CSV}")
        # Replace the MILESTONES section if present, or add it
        found = False
        for i, (name, rows) in enumerate(secs):
            if name == "MILESTONES":
                secs[i] = ("MILESTONES", auto_ms)
                found = True
                break
        if not found:
            secs.append(("MILESTONES", auto_ms))
    else:
        print(f"  No {MILESTONES_CSV} found — using Sheet milestones")

    print(f"  Parsed {len(secs)} sections:")
    for name, rows in secs:
        print(f"    {SM.get(name, {}).get('title', name)}: {len(rows)} rows")

    presto_html = build_presto_html(secs, nm)
    page = build_page(presto_html)

    out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "index.html")
    with open(out, "w", encoding="utf-8") as f:
        f.write(page)

    print(f"\n  Presto payload: {len(presto_html) / 1024:.1f} KB")
    print(f"  Full page: {os.path.getsize(out) / 1024:.1f} KB")
    print("  Open → Copy for Presto → paste into CMS ✓")


if __name__ == "__main__":
    main()
