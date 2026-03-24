#!/usr/bin/env python3
"""
NBA Daily Recap — Presto CMS HTML Generator
No logos. Team abbreviations. Dark section headers.
Usage: python generate_recap.py → index.html
"""
import csv,io,os,json,re

RECAP_URL="https://docs.google.com/spreadsheets/d/e/2PACX-1vSg6im6IYB6HXMGzQbmmBnLw9SfQLzxCSo8OfChxlJLhsB6BBCO0wPF_TMch0YgAbtFqYkwDWrsxRe7/pub?gid=869619953&single=true&output=csv"
NAME_MAP_URL="https://docs.google.com/spreadsheets/d/e/2PACX-1vS2iZj3avZ_-CAWKu-f_pxZkf38M0quXQwMbyTXmHsN6-c9V8vU1l_sNaxg0y8dl07dqraU3_5Z3b8D/pub?gid=1197809522&single=true&output=csv"

TEAM_ID_MAP={
    "1610612737":"ATL","1610612738":"BOS","1610612739":"CLE","1610612740":"NOP",
    "1610612741":"CHI","1610612742":"DAL","1610612743":"DEN","1610612744":"GSW",
    "1610612745":"HOU","1610612746":"LAC","1610612747":"LAL","1610612748":"MIA",
    "1610612749":"MIL","1610612750":"MIN","1610612751":"BKN","1610612752":"NYK",
    "1610612753":"ORL","1610612754":"IND","1610612755":"PHI","1610612756":"PHX",
    "1610612757":"POR","1610612758":"SAC","1610612759":"SAS","1610612760":"OKC",
    "1610612761":"TOR","1610612762":"UTA","1610612763":"MEM","1610612764":"WAS",
    "1610612765":"DET","1610612766":"CHA",
}

SM={"GLOBAL RATING":{"title":"Best players of the day","note":'* (RAT) <a href="https://www.hoopshype.com/story/sports/nba/2021/10/26/what-is-hoopshypes-global-rating/82908126007/" target="_blank" style="color:#0000EE;text-decoration:underline">Global Rating</a>, which measures performance based on individual and team stats. You can check season rankings <a href="https://www.hoopshype.com/rankings/players/" target="_blank" style="color:#0000EE;text-decoration:underline">here</a>.'},"WORST GLOBAL RATING":{"title":"Worst players of the day","note":"* Minimum 15 minutes played"},"BREAKTHROUGH PLAYER":{"title":"Breakout players of the day","note":'* (DIFF) Difference between last game and 2025-26 Global Rating (minimum five games played)',"rl":"DIFF"},"DISAPPOINTMENT":{"title":"Bombs of the day","note":'* (DIFF) Difference between last game and 2025-26 Global Rating (minimum five games played)',"rl":"DIFF"},"BEST ROOKIES":{"title":"Best rookies of the day","note":'* You can check season rankings <a href="https://www.hoopshype.com/rankings/players/?rookie=true" target="_blank" style="color:#0000EE;text-decoration:underline">here</a>.'},"CLUTCH RATING":{"title":"Most clutch players","note":"* (RAT) Clutch Rating, which measures performance in the last five minutes of 4Q or OT when the score is within five points"},"BEST INTERNATIONAL PLAYERS":{"title":"Best international players","note":"* Includes players who represent national teams other than Team USA"},"BEST BENCH PLAYERS":{"title":"Best bench players","note":""},"NET RATING":{"title":"Stats per country","note":"* Includes players who represent national teams other than Team USA"},"MILESTONES":{"title":"All-Time Ranking","note":""},"SNEAKERS":{"title":"Sneakers","note":""}}
EM={"GLOBAL RATING":"🏀","WORST GLOBAL RATING":"📉","BREAKTHROUGH PLAYER":"🚀","DISAPPOINTMENT":"😞","BEST ROOKIES":"⭐","CLUTCH RATING":"🎯","BEST INTERNATIONAL PLAYERS":"🌍","BEST BENCH PLAYERS":"💺","NET RATING":"🌐","MILESTONES":"🏆","SNEAKERS":"👟"}

FN="font-family:Arial,Helvetica,sans-serif"
SH=FN+";padding:8px 12px;background:#1a1a2e;color:#fff;font-size:14px;font-weight:700;letter-spacing:0.5px;margin-top:24px;margin-bottom:0;border-radius:5px 5px 0 0"
TBL="border-collapse: collapse; font-family: Arial, sans-serif; font-size: 14px; width: 100%;"
TH="padding: 6px; height:40px; padding:4px 0 4px 6px; min-width:40px; white-space:nowrap"
TH_NAME="height:40px; text-align:left; padding:4px 0 4px 6px; min-width:40px; white-space:nowrap"
TD="height:40px; padding:4px 0 4px 6px; min-width:40px; white-space:nowrap"
TD_NAME="text-align: left; height: 40px; white-space: nowrap; min-width: 140px"
TD_STAT="height:40px; padding:4px 0; text-align: center; min-width:40px; white-space:nowrap"
TD_RAT="height:40px; text-align: center; padding:4px 0 4px 6px; min-width:40px; white-space:nowrap"
NOTE="padding:8px; font-size:13px; font-style:italic;"

INTRO='<p style="font-size:14px;color:#333;margin:0 0 16px;font-family:Arial,sans-serif">Every day, we bring you the best and worst performers from the previous night in the NBA.</p>'
OUTRO=('<p style="font-size:13px;color:#555;margin:16px 0 4px;font-family:Arial,sans-serif;font-style:italic">'
       'This content may be blocked in parts of Europe due to GDPR. To use it, connect your VPN to a non-EU country and try again.</p>'
       '<p style="font-size:13px;color:#555;margin:4px 0;font-family:Arial,sans-serif;font-style:italic">'
       'We highly recommend you add HoopsHype as a preferred source on Google. You just have to '
       '<a href="https://news.google.com/publications/CAAqBwgKMK_RpQswnMOxAw" target="_blank" style="color:#0000EE;text-decoration:underline">click here</a>.</p>')

def fetch_csv(url):
    import requests; r=requests.get(url,timeout=30); r.encoding='utf-8'; return r.text

def build_name_map(t):
    nm={}; r=csv.reader(io.StringIO(t))
    try: next(r)
    except: return nm
    for row in r:
        if len(row)<13: continue
        a,b=row[11].strip(),row[12].strip()
        if a and b: nm[a]=b
    return nm

def bg(i): return "#f2f2f2" if i%2==1 else "#ffffff"

def get_team_abbr(logo_url):
    if not logo_url or "cdn.nba.com" not in logo_url: return ""
    m=re.search(r'/(\d{10})/',logo_url)
    return TEAM_ID_MAP.get(m.group(1),"") if m else ""

def fix_middot(s):
    s=s.replace("\u00c2\u00b7","-").replace("\u00c2\xb7","-").replace(" \u00b7 "," - ").replace("\u00b7","-")
    s=s.replace("\u00c2-","-").replace("\u00c2 "," ").replace("  "," ")
    return s

def parse_sections(t):
    rows=list(csv.reader(io.StringIO(t))); secs=[]; cn=None; cr=[]
    for row in rows:
        if not row or all(not c.strip() for c in row[:3]):
            if cn and cr: secs.append((cn,cr)); cr=[]; cn=None
            continue
        n=row[0].strip()
        if not n: continue
        r=row[1].strip() if len(row)>1 else ""
        if n.isupper() and len(n)>3 and (not r or r in ("RAT","")):
            if cn and cr: secs.append((cn,cr))
            cn=n; cr=[]; continue
        if any("#N/A" in str(c) for c in row[:11]): continue
        if n and cn: cr.append(row)
    if cn and cr: secs.append((cn,cr))
    return secs

def build_presto_html(secs,nm):
    hh=lambda n:nm.get(n,n)
    o=f'<div style="overflow-x: auto; -webkit-overflow-scrolling: touch;">\n{INTRO}\n'
    for sn,sr in secs:
        m=SM.get(sn,{"title":sn,"note":""}); rl=m.get("rl","RAT"); emoji=EM.get(sn,"📊")
        o+=f'<div style="{SH}"><span style="font-size:16px;margin-right:6px">{emoji}</span> {m["title"]}</div>\n'
        o+=f'<div style="overflow-x:auto; -webkit-overflow-scrolling:touch; width:100%;"><table style="{TBL}">\n<thead>\n<tr style="background-color: #f2f2f2;">\n'

        if sn=="MILESTONES":
            o+=f'<th style="{TH}"></th>\n<th style="{TH_NAME}">PLAYER</th>\n<th style="{TH}">CATEGORY</th>\n<th style="{TH}">RANK</th>\n<th style="{TH}; text-align:center">PASSED</th>\n</tr>\n</thead>\n<tbody>\n'
            for i,row in enumerate(sr):
                n=hh(row[0].strip());ps=row[2].strip() if len(row)>2 else "";ct=row[3].strip() if len(row)>3 else "";rk=row[4].strip() if len(row)>4 else "";lg=row[11].strip() if len(row)>11 else ""
                team=get_team_abbr(lg)
                o+=f'<tr style="background-color:{bg(i)};">\n<td style="{TD}"><strong>{team}</strong></td>\n<td style="{TD_NAME}"><strong>{n}</strong></td>\n<td style="{TD_STAT}">{ct}</td>\n<td style="{TD_STAT}">{rk}</td>\n<td style="{TD_STAT}">{ps}</td>\n</tr>\n'

        elif sn=="NET RATING":
            o+=f'<th style="{TH}"></th>\n<th style="{TH_NAME}">COUNTRY</th>\n<th style="{TH}">STATS</th>\n<th style="{TH}">PLAYERS</th>\n</tr>\n</thead>\n<tbody>\n'
            rc=0
            for i,row in enumerate(sr):
                n=row[0].strip();st=fix_middot(row[2].strip()) if len(row)>2 else "";pl=row[9].strip() if len(row)>9 else ""
                if "Rest of the World" in n: rn=""
                else: rc+=1; rn=str(rc)
                o+=f'<tr style="background-color:{bg(i)};">\n<td style="{TD}"><span style="font-weight:bold;">{rn}</span></td>\n<td style="{TD_NAME}"><strong>{n}</strong></td>\n<td style="{TD_STAT}">{st}</td>\n<td style="{TD_STAT}">{pl}</td>\n</tr>\n'

        elif sn=="SNEAKERS":
            o+=f'<th style="{TH_NAME}">BRAND</th>\n<th style="{TH}">STATS</th>\n<th style="{TH}">PLAYERS</th>\n</tr>\n</thead>\n<tbody>\n'
            for i,row in enumerate(sr):
                n=row[0].strip();st=fix_middot(row[2].strip()) if len(row)>2 else "";pl=row[9].strip() if len(row)>9 else ""
                o+=f'<tr style="background-color:{bg(i)};">\n<td style="{TD_NAME}"><strong>{n}</strong></td>\n<td style="{TD_STAT}">{st}</td>\n<td style="{TD_STAT}">{pl}</td>\n</tr>\n'

        elif sn=="BEST INTERNATIONAL PLAYERS":
            o+=f'<th style="{TH}"></th>\n<th style="{TH_NAME}">PLAYER</th>\n<th style="{TH}">{rl}</th>\n<th style="{TH}">STATS</th>\n</tr>\n</thead>\n<tbody>\n'
            for i,row in enumerate(sr):
                n=hh(row[0].strip());rat=row[1].strip();st=fix_middot(row[2].strip()) if len(row)>2 else ""
                o+=f'<tr style="background-color:{bg(i)};">\n<td style="{TD}"><span style="font-weight:bold;">{i+1}</span></td>\n<td style="{TD_NAME}"><strong>{n}</strong></td>\n<td style="{TD_RAT}"><strong>{rat}</strong></td>\n<td style="{TD_STAT}">{st}</td>\n</tr>\n'

        else:
            o+=f'<th style="{TH}"></th>\n<th style="{TH}"></th>\n<th style="{TH_NAME}">PLAYER</th>\n<th style="{TH}">{rl}</th>\n<th style="{TH}">STATS</th>\n</tr>\n</thead>\n<tbody>\n'
            for i,row in enumerate(sr):
                n=hh(row[0].strip());rat=row[1].strip();st=fix_middot(row[2].strip()) if len(row)>2 else "";lg=row[11].strip() if len(row)>11 else ""
                team=get_team_abbr(lg)
                o+=f'<tr style="background-color:{bg(i)};">\n<td style="{TD}"><span style="font-weight:bold;">{i+1}</span></td>\n<td style="{TD};font-size:11px;color:#888;text-align:center"><strong>{team}</strong></td>\n<td style="{TD_NAME}"><strong>{n}</strong></td>\n<td style="{TD_RAT}"><strong>{rat}</strong></td>\n<td style="{TD_STAT}">{st}</td>\n</tr>\n'

        o+='</tbody></table></div>\n'
        if m.get("note"): o+=f'<div style="{NOTE}">{m["note"]}</div><br>\n'
        else: o+='<br>\n'
    o+=f'{OUTRO}\n</div>'
    return o

def build_page(ph):
    pj=json.dumps(ph)
    return f'''<!DOCTYPE html>
<html lang="en"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>NBA Daily Recap</title>
<style>body{{font-family:Arial,sans-serif;background:#f5f5f5;margin:0;padding:20px}}.tb{{max-width:750px;margin:0 auto 12px;display:flex;align-items:center;gap:12px}}.cb{{padding:10px 24px;border:none;border-radius:6px;background:#1a1a2e;color:#fff;font-size:13px;font-weight:700;cursor:pointer}}.cb:hover{{background:#2d2d5e}}.cb.ok{{background:#1e8449}}.cl{{font-size:11px;color:#888}}.pv{{max-width:750px;margin:0 auto;background:#fff;border-radius:8px;box-shadow:0 2px 12px rgba(0,0,0,0.08);padding:16px}}</style>
</head><body>
<div class="tb"><button class="cb" id="cb" onclick="cp()">📋 Copy for Presto</button><span class="cl" id="cl">Click to copy HTML for Presto CMS</span></div>
<div class="pv">{ph}</div>
<script>var PH={pj};function cp(){{navigator.clipboard.writeText(PH).then(function(){{var b=document.getElementById("cb"),l=document.getElementById("cl");b.textContent="✅ Copied!";b.className="cb ok";l.textContent="Paste into Presto Source/HTML mode";setTimeout(function(){{b.textContent="📋 Copy for Presto";b.className="cb";l.textContent="Click to copy HTML for Presto CMS"}},3000)}})}}</script>
</body></html>'''

def main():
    print("="*50);print("  NBA DAILY RECAP — HTML Generator");print("="*50)
    print("  Fetching name mappings...")
    try: nm=build_name_map(fetch_csv(NAME_MAP_URL));print(f"  Loaded {len(nm)} mappings")
    except Exception as e: print(f"  Warning: {e}");nm={}
    print("  Fetching recap data...")
    secs=parse_sections(fetch_csv(RECAP_URL))
    print(f"  Parsed {len(secs)} sections:")
    for n,r in secs: print(f"    {SM.get(n,{}).get('title',n)}: {len(r)} rows")
    ph=build_presto_html(secs,nm);pg=build_page(ph)
    out=os.path.join(os.path.dirname(os.path.abspath(__file__)),"index.html")
    with open(out,"w",encoding="utf-8") as f: f.write(pg)
    print(f"\n  Presto payload: {len(ph)/1024:.1f} KB")
    print(f"  Full page: {os.path.getsize(out)/1024:.1f} KB")
    print("  Open → Copy for Presto → paste into CMS ✓")

if __name__=="__main__": main()
