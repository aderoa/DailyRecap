#!/usr/bin/env python3
"""
NBA All-Time Milestone Detector v4

Two snapshots:
  snapshot.csv      = frozen baseline (rotated each morning)
  snapshot_live.csv = baseline + accumulated box scores

Modes:
  python milestones.py                 # Night: add today's games, detect milestones
  python milestones.py --date YYYY-MM-DD  # Add specific date's games
  python milestones.py --rotate        # Morning: copy live → baseline
"""
import csv, io, os, sys, time, json, unicodedata, re
from datetime import datetime, timezone, timedelta

import requests

# ── CONFIG ────────────────────────────────────────────────────
SNAPSHOT_FILE = "snapshot.csv"
SNAPSHOT_LIVE = "snapshot_live.csv"
OUTPUT_FILE = "milestones_today.csv"
PROCESSED_FILE = "processed_games.txt"

STATS = ["PTS", "REB", "AST", "STL", "BLK"]
STAT_LABELS = {"PTS": "Scoring", "REB": "Rebounds", "AST": "Assists",
               "STL": "Steals", "BLK": "Blocks"}
MAX_RANK = 250

ESPN_SCOREBOARD = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/scoreboard"
ESPN_SUMMARY = "https://site.web.api.espn.com/apis/site/v2/sports/basketball/nba/summary"

NAME_MAP_URL = os.environ.get(
    "NAME_MAP_URL",
    "https://docs.google.com/spreadsheets/d/e/2PACX-1vS2iZj3avZ_-CAWKu-f_pxZkf38M0quXQwMbyTXmHsN6-c9V8vU1l_sNaxg0y8dl07dqraU3_5Z3b8D/pub?gid=1197809522&single=true&output=csv"
)

ESPN_TEAM_TO_ID = {
    "ATL": "1610612737", "BOS": "1610612738", "CLE": "1610612739",
    "NOP": "1610612740", "NO": "1610612740", "CHI": "1610612741",
    "DAL": "1610612742", "DEN": "1610612743", "GS": "1610612744",
    "GSW": "1610612744", "HOU": "1610612745", "LAC": "1610612746",
    "LAL": "1610612747", "MIA": "1610612748", "MIL": "1610612749",
    "MIN": "1610612750", "BKN": "1610612751", "BK": "1610612751",
    "NYK": "1610612752", "NY": "1610612752", "ORL": "1610612753",
    "IND": "1610612754", "PHI": "1610612755", "PHX": "1610612756",
    "POR": "1610612757", "SAC": "1610612758", "SAS": "1610612759",
    "SA": "1610612759", "OKC": "1610612760", "TOR": "1610612761",
    "UTA": "1610612762", "UTAH": "1610612762", "MEM": "1610612763",
    "WAS": "1610612764", "WSH": "1610612764", "DET": "1610612765",
    "CHA": "1610612766", "CHO": "1610612766",
}

ESPN_ABBR_FIX = {
    "GS": "GSW", "NO": "NOP", "SA": "SAS", "BK": "BKN",
    "NY": "NYK", "WSH": "WAS", "UTAH": "UTA", "CHO": "CHA",
}


def fix_abbr(a):
    return ESPN_ABBR_FIX.get(a, a)


def make_logo_url(team_abbr):
    tid = ESPN_TEAM_TO_ID.get(team_abbr, "")
    return f"https://cdn.nba.com/logos/nba/{tid}/primary/L/logo.svg" if tid else ""


def normalize_name(name):
    s = unicodedata.normalize("NFD", name)
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    return s.strip()


# ── HELPERS ───────────────────────────────────────────────────
def fetch_csv_text(url):
    url += f"&_cb={int(time.time())}"
    r = requests.get(url, timeout=30, headers={"Cache-Control": "no-cache"})
    r.encoding = "utf-8"
    return r.text


def build_name_map():
    nm = {}
    try:
        text = fetch_csv_text(NAME_MAP_URL)
        reader = csv.reader(io.StringIO(text))
        next(reader, None)
        for row in reader:
            if len(row) >= 13:
                nba, hh = row[11].strip(), row[12].strip()
                if nba and hh:
                    nm[nba] = hh
    except Exception as e:
        print(f"  Warning: name map failed: {e}")
    return nm


# ── SNAPSHOT I/O ──────────────────────────────────────────────
def save_snapshot(rankings, path):
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["STAT", "RANK", "PLAYER_ID", "PLAYER_NAME", "TOTAL", "ACTIVE"])
        for stat in STATS:
            for e in rankings.get(stat, []):
                w.writerow([stat, e["rank"], e.get("player_id", ""), e["name"],
                            e["total"], "TRUE" if e.get("active") else "FALSE"])
    print(f"  Saved: {path} ({os.path.getsize(path) / 1024:.1f} KB)")


def load_snapshot(path):
    if not os.path.exists(path):
        return None
    rankings = {s: [] for s in STATS}
    with open(path, "r", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            stat = row.get("STAT", "").strip()
            if stat in rankings:
                rankings[stat].append({
                    "player_id": row.get("PLAYER_ID", ""),
                    "name": row.get("PLAYER_NAME", "").strip(),
                    "total": int(row.get("TOTAL", 0)),
                    "rank": int(row.get("RANK", 0)),
                    "active": row.get("ACTIVE", "").strip().upper() in ("TRUE", "1"),
                })
    total = sum(len(v) for v in rankings.values())
    return rankings if total > 0 else None


# ── PROCESSED GAMES TRACKING ─────────────────────────────────
def load_processed():
    if not os.path.exists(PROCESSED_FILE):
        return set()
    with open(PROCESSED_FILE, "r") as f:
        return {line.strip() for line in f if line.strip()}


def save_processed(ids):
    with open(PROCESSED_FILE, "w") as f:
        for gid in sorted(ids):
            f.write(gid + "\n")


# ── ESPN FETCH ────────────────────────────────────────────────
def fetch_game_ids(game_date):
    date_str = game_date.replace("-", "")
    url = f"{ESPN_SCOREBOARD}?dates={date_str}"
    print(f"  Scoreboard {game_date}...", end=" ")
    r = requests.get(url, timeout=30)
    data = r.json()
    games = []
    for ev in data.get("events", []):
        eid = ev.get("id", "")
        status = ev.get("status", {}).get("type", {}).get("name", "")
        short = ev.get("shortName", "")
        games.append((eid, status, short))
    final = sum(1 for _, s, _ in games if s == "STATUS_FINAL")
    print(f"{len(games)} games ({final} final)")
    return games


def fetch_box_scores(game_list):
    """Returns {player_name: {PTS, REB, AST, STL, BLK, team_abbr, espn_id}}"""
    stats = {}
    for eid, status, short in game_list:
        if status != "STATUS_FINAL":
            continue
        try:
            print(f"    {short}...", end=" ")
            r = requests.get(f"{ESPN_SUMMARY}?event={eid}", timeout=30)
            data = r.json()
            time.sleep(0.3)

            # Debug: show response structure
            boxscore = data.get("boxscore", {})
            players_list = boxscore.get("players", [])
            if not players_list:
                print(f"DEBUG: boxscore keys={list(boxscore.keys())}, top keys={list(data.keys())[:10]}")
                # Try alternate path: maybe ESPN changed structure
                # Check if data is nested differently
                if "header" in data:
                    print(f"  DEBUG header keys: {list(data['header'].keys())[:5]}")
                print("0 players")
                continue

            count = 0
            for team_data in players_list:
                abbr = fix_abbr(team_data.get("team", {}).get("abbreviation", ""))
                stat_groups = team_data.get("statistics", [])
                if count == 0:
                    print(f"DEBUG {abbr}: {len(stat_groups)} stat groups", end=" ")
                for sg in stat_groups:
                    keys = sg.get("keys", [])
                    athletes = sg.get("athletes", [])
                    if count == 0:
                        print(f"keys={len(keys)} athletes={len(athletes)}", end=" ")
                        if athletes:
                            a0 = athletes[0]
                            print(f"a0_keys={list(a0.keys())[:6]}", end=" ")
                            info0 = a0.get("athlete", {})
                            print(f"name={info0.get('displayName','')} reason={a0.get('reason','')}", end=" ")
                    ki = {}
                    for i, k in enumerate(keys):
                        if k == "points": ki[i] = "PTS"
                        elif k == "rebounds": ki[i] = "REB"
                        elif k == "assists": ki[i] = "AST"
                        elif k == "steals": ki[i] = "STL"
                        elif k == "blocks": ki[i] = "BLK"
                    if not ki:
                        continue
                    for ath in sg.get("athletes", []):
                        info = ath.get("athlete", {})
                        name = info.get("displayName", "").strip()
                        if not name or ath.get("reason"):
                            continue
                        vals = ath.get("stats", [])
                        entry = {"PTS": 0, "REB": 0, "AST": 0, "STL": 0, "BLK": 0,
                                 "team_abbr": abbr, "espn_id": str(info.get("id", ""))}
                        for idx, our_key in ki.items():
                            if idx < len(vals):
                                try:
                                    v = vals[idx]
                                    entry[our_key] = int(v) if v not in ("--", "", None) else 0
                                except (ValueError, TypeError):
                                    pass
                        if name not in stats:
                            stats[name] = entry
                            count += 1
            print(f"{count} players")
        except Exception as e:
            print(f"FAILED: {e}")
            time.sleep(1)
    return stats


# ── UPDATE RANKINGS ───────────────────────────────────────────
def update_rankings(old_rankings, box_stats, name_map):
    nm_reverse = {v: k for k, v in name_map.items()}
    espn_norm = {}
    for espn_name, box in box_stats.items():
        nn = normalize_name(espn_name)
        espn_norm[nn] = (espn_name, box)

    new_rankings = {}
    matched = 0
    for stat in STATS:
        entries = []
        for e in old_rankings.get(stat, []):
            new_entry = dict(e)
            name = e["name"]
            nn = normalize_name(name)
            box = None
            if nn in espn_norm:
                box = espn_norm[nn][1]
            if not box:
                alt = nm_reverse.get(name)
                if alt and normalize_name(alt) in espn_norm:
                    box = espn_norm[normalize_name(alt)][1]
            if not box:
                box = box_stats.get(name)
            if box and box.get(stat, 0) > 0:
                new_entry["total"] = e["total"] + box[stat]
                new_entry["gained"] = box[stat]
                if box.get("team_abbr"):
                    new_entry["team_abbr"] = box["team_abbr"]
                if stat == "PTS":
                    matched += 1
            entries.append(new_entry)
        entries.sort(key=lambda x: x["total"], reverse=True)
        for i, e in enumerate(entries):
            e["rank"] = i + 1
        new_rankings[stat] = entries
    print(f"  Matched {matched} players (PTS)")
    return new_rankings


# ── MILESTONES ────────────────────────────────────────────────
def detect_milestones(old_rankings, new_rankings, name_map=None):
    nm = name_map or {}
    milestones = []
    for stat in STATS:
        old_list = old_rankings.get(stat, [])
        new_list = new_rankings.get(stat, [])
        if not old_list or not new_list:
            continue
        old_by_name = {e["name"]: e for e in old_list}
        old_by_rank = {e["rank"]: e for e in old_list}
        for entry in new_list:
            name = entry["name"]
            new_rank = entry["rank"]
            gained = entry.get("gained", 0)
            old_entry = old_by_name.get(name)
            if not old_entry:
                continue
            old_rank = old_entry["rank"]
            if new_rank >= old_rank or gained <= 0 or new_rank > MAX_RANK:
                continue
            for pr in range(new_rank, old_rank):
                pe = old_by_rank.get(pr)
                if not pe or pe["name"] == name:
                    continue
                display_name = nm.get(name, name)
                passed_name = nm.get(pe["name"], pe["name"])
                milestones.append({
                    "player": display_name, "player_raw": name,
                    "team_abbr": entry.get("team_abbr", ""),
                    "stat": stat, "label": STAT_LABELS[stat],
                    "new_rank": new_rank, "new_total": entry["total"],
                    "passed": passed_name, "passed_raw": pe["name"],
                    "passed_total": pe["total"],
                })
    milestones.sort(key=lambda m: (m["new_rank"], STATS.index(m["stat"])))
    return milestones


def combine_milestones(milestones):
    combined = {}
    for m in milestones:
        key = (m["player"], m["stat"])
        if key in combined:
            combined[key]["passed"] += ", " + m["passed"]
        else:
            combined[key] = dict(m)
    result = list(combined.values())
    result.sort(key=lambda m: (m["new_rank"], STATS.index(m["stat"])))
    return result


def save_milestones(milestones, path):
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["PLAYER", "RAT", "PASSED", "CATEGORY", "RANK",
                     "STAT_TOTAL", "PASSED_TOTAL", "STAT_CODE", "LOGO_URL"])
        for m in milestones:
            logo = make_logo_url(m.get("team_abbr", ""))
            w.writerow([m["player"], "", m["passed"], m["label"], m["new_rank"],
                         m["new_total"], m["passed_total"], m["stat"], logo])
    print(f"  Milestones: {path} ({len(milestones)} entries)")


def print_milestones(milestones):
    if not milestones:
        print("\n  No milestones detected.")
        return
    print(f"\n  ┌─ {len(milestones)} MILESTONE(S) ──────────────────────────")
    for m in milestones:
        t = m.get("team_abbr", "???")
        print(f"  │ {t:>3} #{m['new_rank']:>3}  {m['player']:<28} {m['label']:<10} "
              f"({m['new_total']:,})  passed  {m['passed']} ({m['passed_total']:,})")
    print("  └─────────────────────────────────────────────")


# ── MAIN ─────────────────────────────────────────────────────
def main():
    import argparse
    parser = argparse.ArgumentParser(description="NBA All-Time Milestone Detector v4")
    parser.add_argument("--date", help="Game date YYYY-MM-DD")
    parser.add_argument("--rotate", action="store_true",
                        help="Morning: copy snapshot_live → snapshot")
    args = parser.parse_args()

    et = timezone(timedelta(hours=-5))
    now = datetime.now(et)
    print("=" * 55)
    print("  NBA ALL-TIME MILESTONE DETECTOR v4")
    print(f"  {now.strftime('%Y-%m-%d %H:%M')} ET")
    print("=" * 55)

    # ── ROTATE MODE
    if args.rotate:
        if os.path.exists(SNAPSHOT_LIVE):
            import shutil
            shutil.copy2(SNAPSHOT_LIVE, SNAPSHOT_FILE)
            print(f"\n  ✓ Rotated: {SNAPSHOT_LIVE} → {SNAPSHOT_FILE}")
        else:
            print(f"\n  No {SNAPSHOT_LIVE} to rotate.")
        return

    # ── DETECT MODE
    print("\n  Loading name mappings...")
    name_map = build_name_map()
    print(f"  Loaded {len(name_map)} translations")

    # Load live snapshot (or fall back to baseline)
    live = load_snapshot(SNAPSHOT_LIVE)
    if not live:
        print(f"  No {SNAPSHOT_LIVE} — copying from {SNAPSHOT_FILE}...")
        base = load_snapshot(SNAPSHOT_FILE)
        if not base:
            print(f"  ERROR: {SNAPSHOT_FILE} not found!")
            sys.exit(1)
        live = base

    total = sum(len(v) for v in live.values())
    print(f"  Loaded live snapshot: {total} entries")

    processed = load_processed()
    print(f"  Processed games: {len(processed)}")

    # Determine which date(s) to fetch
    if args.date:
        dates = [args.date]
    else:
        yesterday = (now - timedelta(days=1)).strftime("%Y-%m-%d")
        today = now.strftime("%Y-%m-%d")
        dates = [yesterday, today]

    # Fetch new games
    all_new = []
    for d in dates:
        try:
            gids = fetch_game_ids(d)
            new = [(e, s, n) for e, s, n in gids if s == "STATUS_FINAL" and e not in processed]
            if new:
                all_new.extend(new)
        except Exception as ex:
            print(f"  {d} failed: {ex}")

    if not all_new:
        print("\n  No new games to process.")
        save_milestones([], OUTPUT_FILE)
        return

    print(f"\n  {len(all_new)} new games to process")
    box_stats = fetch_box_scores(all_new)
    active = sum(1 for v in box_stats.values() if any(v.get(s, 0) > 0 for s in STATS))
    print(f"\n  Box scores: {len(box_stats)} players, {active} with stats")

    # Compare: live (before) → updated (after)
    print("  Updating career totals...")
    updated = update_rankings(live, box_stats, name_map)

    print("  Detecting milestones...")
    milestones = detect_milestones(live, updated, name_map)
    milestones = combine_milestones(milestones)
    print_milestones(milestones)

    # Save everything
    save_milestones(milestones, OUTPUT_FILE)
    save_snapshot(updated, SNAPSHOT_LIVE)

    for e, s, n in all_new:
        processed.add(e)
    save_processed(processed)

    print(f"\n  ✓ Done: {len(all_new)} games, {len(milestones)} milestones")


if __name__ == "__main__":
    main()
