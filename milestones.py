#!/usr/bin/env python3
"""
NBA All-Time Milestone Detector v3 (ESPN Box Scores)

Baseline: snapshot.csv built from NBA.com AllTimeLeadersGrids (through Mar 26 2026)
Daily:    ESPN API box scores → update career totals → detect rank changes

ESPN API (no auth, works from GitHub Actions):
  Scoreboard: site.api.espn.com/apis/site/v2/sports/basketball/nba/scoreboard?dates=YYYYMMDD
  Summary:    site.web.api.espn.com/apis/site/v2/sports/basketball/nba/summary?event={id}

Usage:
  python milestones.py                    # Yesterday's box scores
  python milestones.py --date 2026-03-27  # Specific date
"""
import csv, io, os, sys, time, json, unicodedata, re
from datetime import datetime, timezone, timedelta

import requests

# ── CONFIG ────────────────────────────────────────────────────
SNAPSHOT_FILE = "snapshot.csv"
OUTPUT_FILE = "milestones_today.csv"
STATS = ["PTS", "REB", "AST", "STL", "BLK"]
STAT_LABELS = {"PTS": "Scoring", "REB": "Rebounds", "AST": "Assists",
               "STL": "Steals", "BLK": "Blocks"}
MAX_RANK = 250  # Only report milestones within top 250

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

# Manual name fixes: ESPN name → NBA.com name
ESPN_NAME_FIXES = {
    "Luka Doncic": "Luka Doncic",       # ESPN sometimes drops diacritics
    "Nikola Jokic": "Nikola Jokic",
    "Nikola Vucevic": "Nikola Vucevic",
    "Jonas Valanciunas": "Jonas Valanciunas",
    "Bogdan Bogdanovic": "Bogdan Bogdanovic",
    "Bojan Bogdanovic": "Bojan Bogdanovic",
    "Dario Saric": "Dario Saric",
    "Jusuf Nurkic": "Jusuf Nurkic",
    "Dennis Schroder": "Dennis Schroder",
    "Kristaps Porzingis": "Kristaps Porzingis",
    "Goran Dragic": "Goran Dragic",
    "Nikola Mirotic": "Nikola Mirotic",
    "Timothe Luwawu-Cabarrot": "Timothe Luwawu-Cabarrot",
}


def make_logo_url(team_abbr):
    tid = ESPN_TEAM_TO_ID.get(team_abbr, "")
    return f"https://cdn.nba.com/logos/nba/{tid}/primary/L/logo.svg" if tid else ""


def normalize_name(name):
    """Strip diacritics and normalize for matching."""
    s = unicodedata.normalize("NFD", name)
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    s = s.strip()
    # Remove suffixes like Jr., III, II, IV
    s = re.sub(r'\s+(Jr\.?|Sr\.?|III|II|IV)$', '', s)
    return s


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
            if len(row) < 13:
                continue
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
    print(f"  Snapshot saved: {path} ({os.path.getsize(path) / 1024:.1f} KB)")


def load_snapshot(path):
    if not os.path.exists(path):
        return None
    rankings = {s: [] for s in STATS}
    with open(path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            stat = row.get("STAT", "").strip()
            if stat not in rankings:
                continue
            rankings[stat].append({
                "player_id": row.get("PLAYER_ID", ""),
                "name": row.get("PLAYER_NAME", "").strip(),
                "total": int(row.get("TOTAL", 0)),
                "rank": int(row.get("RANK", 0)),
                "active": row.get("ACTIVE", "").strip().upper() in ("TRUE", "1"),
            })
    total = sum(len(v) for v in rankings.values())
    return rankings if total > 0 else None


# ── ESPN: FETCH GAME IDS ─────────────────────────────────────
def fetch_game_ids_espn(game_date):
    date_str = game_date.replace("-", "")
    url = f"{ESPN_SCOREBOARD}?dates={date_str}"
    print(f"  Fetching ESPN scoreboard for {game_date}...")
    r = requests.get(url, timeout=30)
    data = r.json()
    events = data.get("events", [])
    game_ids = []
    for ev in events:
        eid = ev.get("id", "")
        status = ev.get("status", {}).get("type", {}).get("name", "")
        short = ev.get("shortName", "")
        game_ids.append((eid, status, short))
    completed = sum(1 for _, s, _ in game_ids if s == "STATUS_FINAL")
    print(f"    Found {len(game_ids)} games ({completed} final)")
    return game_ids


# ── ESPN: FETCH BOX SCORES ───────────────────────────────────
def fetch_box_scores_espn(game_ids):
    """Returns: {player_name: {PTS, REB, AST, STL, BLK, team_abbr, espn_id}}"""
    player_stats = {}

    for eid, status, short in game_ids:
        if status != "STATUS_FINAL":
            continue
        try:
            print(f"    {short} ({eid})...", end=" ")
            url = f"{ESPN_SUMMARY}?event={eid}"
            r = requests.get(url, timeout=30)
            data = r.json()
            time.sleep(0.3)

            boxscore = data.get("boxscore", {})
            count = 0
            for team_data in boxscore.get("players", []):
                team_abbr = team_data.get("team", {}).get("abbreviation", "")

                for stat_group in team_data.get("statistics", []):
                    keys = stat_group.get("keys", [])
                    # Map ESPN stat keys to our stat names
                    key_idx = {}
                    for i, k in enumerate(keys):
                        if k == "points": key_idx[i] = "PTS"
                        elif k == "rebounds": key_idx[i] = "REB"
                        elif k == "assists": key_idx[i] = "AST"
                        elif k == "steals": key_idx[i] = "STL"
                        elif k == "blocks": key_idx[i] = "BLK"

                    if not key_idx:
                        continue

                    for athlete in stat_group.get("athletes", []):
                        info = athlete.get("athlete", {})
                        name = info.get("displayName", "").strip()
                        if not name:
                            continue
                        espn_id = str(info.get("id", ""))

                        vals = athlete.get("stats", [])
                        entry = {"PTS": 0, "REB": 0, "AST": 0, "STL": 0, "BLK": 0,
                                 "team_abbr": team_abbr, "espn_id": espn_id}

                        for idx, our_key in key_idx.items():
                            if idx < len(vals):
                                try:
                                    v = vals[idx]
                                    entry[our_key] = int(v) if v not in ("--", "", None) else 0
                                except (ValueError, TypeError):
                                    pass

                        # Only keep first entry per player (avoid dups from multiple stat groups)
                        if name not in player_stats:
                            player_stats[name] = entry
                            count += 1

            print(f"{count} players")
        except Exception as e:
            print(f"FAILED: {e}")
            time.sleep(1)

    return player_stats


# ── UPDATE RANKINGS ───────────────────────────────────────────
def update_rankings(old_rankings, box_stats, name_map):
    """Add box score stats to snapshot career totals."""
    nm_reverse = {v: k for k, v in name_map.items()}

    # Build normalized name lookup for snapshot players per stat
    # normalized_name → original_name
    norm_lookup = {}
    for stat in STATS:
        for e in old_rankings.get(stat, []):
            nn = normalize_name(e["name"])
            norm_lookup[nn] = e["name"]

    # Build normalized ESPN name → box entry
    espn_norm = {}
    for espn_name, box in box_stats.items():
        fixed = ESPN_NAME_FIXES.get(espn_name, espn_name)
        nn = normalize_name(fixed)
        espn_norm[nn] = (espn_name, box)

    new_rankings = {}
    matched = 0
    for stat in STATS:
        entries = []
        for e in old_rankings.get(stat, []):
            new_entry = dict(e)
            name = e["name"]
            nn = normalize_name(name)

            # Try matching: normalized name, then name map reverse, then ESPN fixes
            box = None
            if nn in espn_norm:
                box = espn_norm[nn][1]
            if not box:
                alt = nm_reverse.get(name)
                if alt:
                    alt_nn = normalize_name(alt)
                    if alt_nn in espn_norm:
                        box = espn_norm[alt_nn][1]
            # Also try exact ESPN name
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

    print(f"  Matched {matched} snapshot players with box score PTS")
    return new_rankings


# ── MILESTONE DETECTION ──────────────────────────────────────
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
            if new_rank >= old_rank or gained <= 0:
                continue
            if new_rank > MAX_RANK:
                continue

            for passed_rank in range(new_rank, old_rank):
                passed_entry = old_by_rank.get(passed_rank)
                if not passed_entry or passed_entry["name"] == name:
                    continue
                display_name = nm.get(name, name)
                passed_name = nm.get(passed_entry["name"], passed_entry["name"])
                milestones.append({
                    "player": display_name, "player_raw": name,
                    "team_abbr": entry.get("team_abbr", ""),
                    "stat": stat, "label": STAT_LABELS[stat],
                    "new_rank": new_rank, "new_total": entry["total"],
                    "passed": passed_name, "passed_raw": passed_entry["name"],
                    "passed_total": passed_entry["total"],
                })

    milestones.sort(key=lambda m: (m["new_rank"], STATS.index(m["stat"])))
    return milestones


def combine_milestones(milestones):
    """Combine milestones where same player passed multiple people in same category.
    E.g. Kawhi Leonard / Steals / 69 / Muggsy Bogues + Ben Wallace → one row.
    """
    combined = {}
    for m in milestones:
        key = (m["player"], m["stat"])
        if key in combined:
            # Append passed name
            combined[key]["passed"] += ", " + m["passed"]
        else:
            combined[key] = dict(m)

    result = list(combined.values())
    result.sort(key=lambda m: (m["new_rank"], STATS.index(m["stat"])))
    return result


# ── OUTPUT ────────────────────────────────────────────────────
def save_milestones_csv(milestones, path):
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["PLAYER", "RAT", "PASSED", "CATEGORY", "RANK",
                     "STAT_TOTAL", "PASSED_TOTAL", "STAT_CODE", "LOGO_URL"])
        for m in milestones:
            logo = make_logo_url(m.get("team_abbr", ""))
            w.writerow([m["player"], "", m["passed"], m["label"], m["new_rank"],
                         m["new_total"], m["passed_total"], m["stat"], logo])
    print(f"  Milestones saved: {path} ({len(milestones)} entries)")


def print_milestones(milestones):
    if not milestones:
        print("\n  No milestones detected today.")
        return
    print(f"\n  ┌─ {len(milestones)} MILESTONE(S) DETECTED ──────────────────")
    for m in milestones:
        t = m.get("team_abbr", "???")
        print(f"  │ {t:>3} #{m['new_rank']:>3}  {m['player']:<28} {m['label']:<10} "
              f"({m['new_total']:,})  passed  {m['passed']} ({m['passed_total']:,})")
    print("  └─────────────────────────────────────────────")


# ── MAIN ─────────────────────────────────────────────────────
def main():
    import argparse
    parser = argparse.ArgumentParser(description="NBA All-Time Milestone Detector v3")
    parser.add_argument("--date", help="Game date YYYY-MM-DD (default: auto-detect)")
    parser.add_argument("--refresh", action="store_true",
                        help="Silent refresh: re-apply last 2 days of box scores to snapshot (no milestones)")
    args = parser.parse_args()

    et = timezone(timedelta(hours=-5))
    now = datetime.now(et)
    print("=" * 55)
    print("  NBA ALL-TIME MILESTONE DETECTOR v3 (ESPN)")
    print(f"  {now.strftime('%Y-%m-%d %H:%M')} ET")
    print("=" * 55)

    print("\n  Loading name mappings...")
    name_map = build_name_map()
    print(f"  Loaded {len(name_map)} translations")

    old_rankings = load_snapshot(SNAPSHOT_FILE)
    if not old_rankings:
        print(f"\n  ERROR: {SNAPSHOT_FILE} not found! Commit it to the repo.")
        sys.exit(1)

    total = sum(len(v) for v in old_rankings.values())
    print(f"  Loaded snapshot: {total} entries")

PROCESSED_GAMES_FILE = "processed_games.txt"


def load_processed_games():
    """Load set of already-processed ESPN game IDs."""
    if not os.path.exists(PROCESSED_GAMES_FILE):
        return set()
    with open(PROCESSED_GAMES_FILE, "r") as f:
        return {line.strip() for line in f if line.strip()}


def save_processed_games(game_ids_set):
    """Save processed game IDs."""
    with open(PROCESSED_GAMES_FILE, "w") as f:
        for gid in sorted(game_ids_set):
            f.write(gid + "\n")


# ── MAIN ─────────────────────────────────────────────────────
def main():
    import argparse
    parser = argparse.ArgumentParser(description="NBA All-Time Milestone Detector v3")
    parser.add_argument("--date", help="Game date YYYY-MM-DD (default: auto-detect)")
    parser.add_argument("--refresh", action="store_true",
                        help="Silent refresh: catch missed games from last 2 days")
    args = parser.parse_args()

    et = timezone(timedelta(hours=-5))
    now = datetime.now(et)
    print("=" * 55)
    print("  NBA ALL-TIME MILESTONE DETECTOR v3 (ESPN)")
    print(f"  {now.strftime('%Y-%m-%d %H:%M')} ET")
    print("=" * 55)

    print("\n  Loading name mappings...")
    name_map = build_name_map()
    print(f"  Loaded {len(name_map)} translations")

    old_rankings = load_snapshot(SNAPSHOT_FILE)
    if not old_rankings:
        print(f"\n  ERROR: {SNAPSHOT_FILE} not found! Commit it to the repo.")
        sys.exit(1)

    total = sum(len(v) for v in old_rankings.values())
    print(f"  Loaded snapshot: {total} entries")

    processed = load_processed_games()
    print(f"  Processed games on file: {len(processed)}")

    # First run with tracking: seed recent game IDs already in snapshot
    # to prevent double-counting on refresh. Only seed PAST days, not today.
    if not processed and not args.refresh:
        print("  First run — seeding processed games from recent days...")
        for days_ago in [4, 3, 2, 1]:
            d = (now - timedelta(days=days_ago)).strftime("%Y-%m-%d")
            try:
                gids = fetch_game_ids_espn(d)
                for e, s, n in gids:
                    if s == "STATUS_FINAL":
                        processed.add(e)
            except Exception:
                pass
        save_processed_games(processed)
        print(f"  Seeded {len(processed)} game IDs (will not re-process these)")

    # ── REFRESH MODE: catch any missed games from last 2 days
    if args.refresh:
        print("\n  REFRESH MODE: checking last 2 days for missed games...")
        new_games = 0
        for days_ago in [2, 1]:
            d = (now - timedelta(days=days_ago)).strftime("%Y-%m-%d")
            print(f"\n  Checking {d}...")
            try:
                gids = fetch_game_ids_espn(d)
                final = [(e, s, n) for e, s, n in gids if s == "STATUS_FINAL"]
                # Only process games not already in processed set
                new_final = [(e, s, n) for e, s, n in final if e not in processed]
                if not new_final:
                    print(f"    All {len(final)} games already processed.")
                    continue
                print(f"    {len(new_final)} new games (of {len(final)} total)")
                box = fetch_box_scores_espn(new_final)
                old_rankings = update_rankings(old_rankings, box, name_map)
                for e, s, n in new_final:
                    processed.add(e)
                new_games += len(new_final)
            except Exception as e:
                print(f"    Failed: {e}")
        if new_games > 0:
            save_snapshot(old_rankings, SNAPSHOT_FILE)
            save_processed_games(processed)
            print(f"\n  ✓ Refresh done: {new_games} new games added to snapshot")
        else:
            print("\n  ✓ Refresh done: no new games found")
        return

    # ── DETECT MODE: find milestones
    if args.date:
        game_date = args.date
    else:
        # Auto-detect: try today first (for manual/evening runs),
        # fall back to yesterday (for cron at 1:30 AM ET)
        today = now.strftime("%Y-%m-%d")
        yesterday = (now - timedelta(days=1)).strftime("%Y-%m-%d")
        print(f"\n  Checking today ({today}) for completed games...")
        try:
            today_ids = fetch_game_ids_espn(today)
            today_final = [g for g in today_ids if g[1] == "STATUS_FINAL"]
            if today_final:
                game_date = today
                print(f"    Found {len(today_final)} completed games today — using {today}")
            else:
                game_date = yesterday
                print(f"    No completed games today — falling back to {yesterday}")
        except Exception:
            game_date = yesterday
            print(f"    Could not check today — falling back to {yesterday}")

    print(f"\n  Fetching ESPN box scores for {game_date}...")
    game_ids = fetch_game_ids_espn(game_date)
    final = [(e, s, n) for e, s, n in game_ids if s == "STATUS_FINAL"]

    # Filter out games already processed (prevents double-counting on re-runs)
    new_final = [(e, s, n) for e, s, n in final if e not in processed]
    if len(new_final) < len(final):
        print(f"  Skipping {len(final) - len(new_final)} already-processed games")
    final = new_final

    if not final:
        print(f"  No completed games on {game_date}.")
        save_milestones_csv([], OUTPUT_FILE)
        return

    box_stats = fetch_box_scores_espn(final)
    active = sum(1 for v in box_stats.values() if any(v.get(s, 0) > 0 for s in STATS))
    print(f"\n  Box scores: {len(box_stats)} players, {active} with counted stats")

    print("  Updating career totals...")
    new_rankings = update_rankings(old_rankings, box_stats, name_map)

    print("  Detecting milestones...")
    milestones = detect_milestones(old_rankings, new_rankings, name_map)
    milestones = combine_milestones(milestones)
    print_milestones(milestones)

    save_milestones_csv(milestones, OUTPUT_FILE)
    save_snapshot(new_rankings, SNAPSHOT_FILE)

    # Track processed game IDs
    for e, s, n in final:
        processed.add(e)
    save_processed_games(processed)

    print(f"\n  ✓ Done: {len(final)} games, {len(milestones)} milestones")


if __name__ == "__main__":
    main()
