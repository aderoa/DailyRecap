#!/usr/bin/env python3
"""
NBA All-Time Milestone Detector (v2 — Box Score Update)

Architecture:
  1. ONE-TIME baseline: fetch AllTimeLeadersGrids top 500 per stat → snapshot.csv
  2. DAILY: fetch last night's box scores → update career totals → detect rank changes

Usage:
  python milestones.py --init             # First run: create baseline (retries on timeout)
  python milestones.py                    # Daily: update via box scores + detect milestones
  python milestones.py --date 2026-03-27  # Specific game date
"""
import csv, io, os, sys, time, json
from datetime import datetime, timezone, timedelta

# ── CONFIG ────────────────────────────────────────────────────
SNAPSHOT_FILE = "snapshot.csv"
OUTPUT_FILE = "milestones_today.csv"
TOP_X = 500
STATS = ["PTS", "REB", "AST", "STL", "BLK"]
STAT_LABELS = {"PTS": "Scoring", "REB": "Rebounds", "AST": "Assists", "STL": "Steals", "BLK": "Blocks"}

RESULT_SET_MAP = {
    "PTS": "PTSLeaders",
    "REB": "REBLeaders",
    "AST": "ASTLeaders",
    "STL": "STLLeaders",
    "BLK": "BLKLeaders",
}

NBA_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
    "x-nba-stats-origin": "stats",
    "x-nba-stats-token": "true",
    "Referer": "https://www.nba.com/",
    "Origin": "https://www.nba.com",
}

NAME_MAP_URL = os.environ.get(
    "NAME_MAP_URL",
    "https://docs.google.com/spreadsheets/d/e/2PACX-1vS2iZj3avZ_-CAWKu-f_pxZkf38M0quXQwMbyTXmHsN6-c9V8vU1l_sNaxg0y8dl07dqraU3_5Z3b8D/pub?gid=1197809522&single=true&output=csv"
)

TEAM_ABBR = {
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


def make_logo_url(team_id):
    return f"https://cdn.nba.com/logos/nba/{team_id}/primary/L/logo.svg" if team_id else ""


# ── FETCH HELPERS ─────────────────────────────────────────────
def fetch_csv(url):
    import requests
    url += f"&_cb={int(time.time())}"
    r = requests.get(url, timeout=30, headers={"Cache-Control": "no-cache"})
    r.encoding = "utf-8"
    return r.text


def build_name_map():
    nm = {}
    try:
        text = fetch_csv(NAME_MAP_URL)
        reader = csv.reader(io.StringIO(text))
        next(reader, None)
        for row in reader:
            if len(row) < 13:
                continue
            nba, hh = row[11].strip(), row[12].strip()
            if nba and hh:
                nm[nba] = hh
    except Exception as e:
        print(f"  Warning: could not load name map: {e}")
    return nm


# ── STEP 1: FETCH BASELINE ───────────────────────────────────
def fetch_baseline_with_retries(max_retries=4, timeout=90):
    from nba_api.stats.endpoints import alltimeleadersgrids
    for attempt in range(1, max_retries + 1):
        try:
            print(f"  Attempt {attempt}/{max_retries} (timeout={timeout}s)...")
            leaders = alltimeleadersgrids.AllTimeLeadersGrids(
                topx=TOP_X, per_mode_simple="Totals",
                season_type="Regular Season",
                headers=NBA_HEADERS, timeout=timeout,
            )
            data = leaders.get_dict()
            print("  Success!")
            return data
        except Exception as e:
            print(f"  Attempt {attempt} failed: {e}")
            if attempt < max_retries:
                wait = 15 * attempt
                print(f"  Retrying in {wait}s...")
                time.sleep(wait)
            else:
                raise


def parse_leaders(data):
    rankings = {}
    for stat in STATS:
        rs_name = RESULT_SET_MAP[stat]
        rs = next((r for r in data["resultSets"] if r["name"] == rs_name), None)
        if not rs:
            rankings[stat] = []
            continue
        hdrs = rs["headers"]
        id_col = hdrs.index("PLAYER_ID") if "PLAYER_ID" in hdrs else 0
        name_col = hdrs.index("PLAYER_NAME") if "PLAYER_NAME" in hdrs else 1
        total_col = hdrs.index(stat) if stat in hdrs else 2
        active_col = hdrs.index("IS_ACTIVE_FLAG") if "IS_ACTIVE_FLAG" in hdrs else None
        entries = []
        for i, row in enumerate(rs["rowSet"]):
            entries.append({
                "player_id": str(row[id_col]),
                "name": row[name_col],
                "total": int(row[total_col]) if row[total_col] is not None else 0,
                "rank": i + 1,
                "active": bool(row[active_col]) if active_col is not None else False,
            })
        rankings[stat] = entries
        print(f"    {stat}: {len(entries)} players (top: {entries[0]['name']} = {entries[0]['total']:,})")
    return rankings


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


# ── STEP 2: FETCH BOX SCORES ─────────────────────────────────
def fetch_game_ids(game_date, timeout=60):
    from nba_api.stats.endpoints import scoreboardv2
    print(f"  Fetching scoreboard for {game_date}...")
    sb = scoreboardv2.ScoreboardV2(
        game_date=game_date, league_id="00",
        headers=NBA_HEADERS, timeout=timeout,
    )
    data = sb.get_dict()
    time.sleep(0.5)
    rs = next((r for r in data["resultSets"] if r["name"] == "GameHeader"), None)
    if not rs:
        return []
    hdrs = rs["headers"]
    gid_col = hdrs.index("GAME_ID") if "GAME_ID" in hdrs else 0
    game_ids = [str(row[gid_col]) for row in rs["rowSet"]]
    print(f"    Found {len(game_ids)} games")
    return game_ids


def fetch_box_scores(game_ids, timeout=60):
    """Fetch box scores for all games. Returns {player_name: {PTS, REB, AST, STL, BLK, player_id, team_id}}."""
    from nba_api.stats.endpoints import boxscoretraditionalv2
    player_stats = {}

    for gid in game_ids:
        try:
            print(f"    Box score {gid}...", end=" ")
            box = boxscoretraditionalv2.BoxScoreTraditionalV2(
                game_id=gid,
                headers=NBA_HEADERS, timeout=timeout,
            )
            data = box.get_dict()
            time.sleep(0.6)

            # Find PlayerStats result set
            rs = next((r for r in data["resultSets"] if r["name"] == "PlayerStats"), None)
            if not rs:
                print("no PlayerStats")
                continue

            hdrs = rs["headers"]
            name_col = hdrs.index("PLAYER_NAME") if "PLAYER_NAME" in hdrs else 5
            pid_col = hdrs.index("PLAYER_ID") if "PLAYER_ID" in hdrs else 4
            tid_col = hdrs.index("TEAM_ID") if "TEAM_ID" in hdrs else 1

            def col_val(row, col_name):
                try:
                    return int(row[hdrs.index(col_name)] or 0)
                except (ValueError, IndexError):
                    return 0

            count = 0
            for row in rs["rowSet"]:
                name = str(row[name_col]).strip()
                if not name:
                    continue
                entry = {
                    "PTS": col_val(row, "PTS"),
                    "REB": col_val(row, "REB"),
                    "AST": col_val(row, "AST"),
                    "STL": col_val(row, "STL"),
                    "BLK": col_val(row, "BLK"),
                    "player_id": str(row[pid_col]),
                    "team_id": str(row[tid_col]),
                }
                if name in player_stats:
                    for s in STATS:
                        player_stats[name][s] += entry[s]
                else:
                    player_stats[name] = entry
                count += 1
            print(f"{count} players")
        except Exception as e:
            print(f"FAILED: {e}")
            time.sleep(2)

    return player_stats


# ── UPDATE RANKINGS ───────────────────────────────────────────
def update_rankings(old_rankings, box_stats, name_map):
    nm_reverse = {v: k for k, v in name_map.items()}
    new_rankings = {}

    for stat in STATS:
        entries = []
        for e in old_rankings.get(stat, []):
            new_entry = dict(e)
            name = e["name"]
            box = box_stats.get(name)
            if not box:
                alt = nm_reverse.get(name)
                if alt:
                    box = box_stats.get(alt)
            if not box and e.get("player_id"):
                for bname, bs in box_stats.items():
                    if bs.get("player_id") == e["player_id"]:
                        box = bs
                        break
            if box and box.get(stat, 0) > 0:
                new_entry["total"] = e["total"] + box[stat]
                new_entry["gained"] = box[stat]
                if box.get("team_id"):
                    new_entry["team_id"] = box["team_id"]
            entries.append(new_entry)

        entries.sort(key=lambda x: x["total"], reverse=True)
        for i, e in enumerate(entries):
            e["rank"] = i + 1
        new_rankings[stat] = entries

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
            for passed_rank in range(new_rank, old_rank):
                passed_entry = old_by_rank.get(passed_rank)
                if not passed_entry or passed_entry["name"] == name:
                    continue
                display_name = nm.get(name, name)
                passed_name = nm.get(passed_entry["name"], passed_entry["name"])
                milestones.append({
                    "player": display_name, "player_raw": name,
                    "player_id": entry.get("player_id"),
                    "team_id": entry.get("team_id", ""),
                    "stat": stat, "label": STAT_LABELS[stat],
                    "new_rank": new_rank, "new_total": entry["total"],
                    "passed": passed_name, "passed_raw": passed_entry["name"],
                    "passed_total": passed_entry["total"],
                })
    milestones.sort(key=lambda m: (m["new_rank"], STATS.index(m["stat"])))
    return milestones


# ── OUTPUT ────────────────────────────────────────────────────
def save_milestones_csv(milestones, path):
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["PLAYER", "RAT", "PASSED", "CATEGORY", "RANK",
                     "STAT_TOTAL", "PASSED_TOTAL", "STAT_CODE", "LOGO_URL"])
        for m in milestones:
            logo = make_logo_url(m.get("team_id", ""))
            w.writerow([m["player"], "", m["passed"], m["label"], m["new_rank"],
                         m["new_total"], m["passed_total"], m["stat"], logo])
    print(f"  Milestones saved: {path} ({len(milestones)} entries)")


def print_milestones(milestones):
    if not milestones:
        print("\n  No milestones detected today.")
        return
    print(f"\n  ┌─ {len(milestones)} MILESTONE(S) DETECTED ──────────────────")
    for m in milestones:
        print(f"  │ #{m['new_rank']:>3}  {m['player']:<28} {m['label']:<10} "
              f"({m['new_total']:,})  passed  {m['passed']} ({m['passed_total']:,})")
    print("  └─────────────────────────────────────────────")


# ── MAIN ─────────────────────────────────────────────────────
def main():
    import argparse
    parser = argparse.ArgumentParser(description="NBA All-Time Milestone Detector v2")
    parser.add_argument("--init", action="store_true", help="Create baseline from AllTimeLeadersGrids")
    parser.add_argument("--date", help="Game date YYYY-MM-DD (default: yesterday ET)")
    parser.add_argument("--timeout", type=int, default=90, help="API timeout seconds (default: 90)")
    parser.add_argument("--retries", type=int, default=4, help="Max retries for baseline (default: 4)")
    args = parser.parse_args()

    et = timezone(timedelta(hours=-5))
    now = datetime.now(et)
    print("=" * 55)
    print("  NBA ALL-TIME MILESTONE DETECTOR v2")
    print(f"  {now.strftime('%Y-%m-%d')} (ET)")
    print("=" * 55)

    print("\n  Loading name mappings...")
    name_map = build_name_map()
    print(f"  Loaded {len(name_map)} name translations")

    # ── INIT: fetch full leaderboard with retries
    if args.init:
        print(f"\n  Fetching AllTimeLeadersGrids (top {TOP_X})...")
        data = fetch_baseline_with_retries(args.retries, args.timeout)
        rankings = parse_leaders(data)
        save_snapshot(rankings, SNAPSHOT_FILE)
        total = sum(len(v) for v in rankings.values())
        print(f"\n  ✓ Baseline created: {SNAPSHOT_FILE} ({total} entries)")
        print("  Run without --init tomorrow to detect milestones.")
        return

    # ── DAILY: load snapshot → fetch box scores → update → detect
    old_rankings = load_snapshot(SNAPSHOT_FILE)
    if not old_rankings:
        print(f"\n  No {SNAPSHOT_FILE} found. Creating baseline...")
        data = fetch_baseline_with_retries(args.retries, args.timeout)
        rankings = parse_leaders(data)
        save_snapshot(rankings, SNAPSHOT_FILE)
        print(f"  ✓ Baseline created. Run again tomorrow.")
        return

    print(f"\n  Loaded snapshot: {sum(len(v) for v in old_rankings.values())} entries")

    game_date = args.date or (now - timedelta(days=1)).strftime("%Y-%m-%d")
    print(f"\n  Fetching box scores for {game_date}...")

    try:
        game_ids = fetch_game_ids(game_date, args.timeout)
    except Exception as e:
        print(f"  Scoreboard failed: {e}. Retrying...")
        time.sleep(10)
        try:
            game_ids = fetch_game_ids(game_date, args.timeout + 30)
        except Exception as e2:
            print(f"  FAILED: {e2}")
            save_milestones_csv([], OUTPUT_FILE)
            sys.exit(1)

    if not game_ids:
        print(f"  No games on {game_date}.")
        save_milestones_csv([], OUTPUT_FILE)
        return

    box_stats = fetch_box_scores(game_ids, args.timeout)
    active = sum(1 for v in box_stats.values() if any(v.get(s, 0) > 0 for s in STATS))
    print(f"\n  Box scores: {len(box_stats)} players, {active} with stats")

    print("  Updating career totals...")
    new_rankings = update_rankings(old_rankings, box_stats, name_map)

    print("  Detecting milestones...")
    milestones = detect_milestones(old_rankings, new_rankings, name_map)
    print_milestones(milestones)

    save_milestones_csv(milestones, OUTPUT_FILE)
    save_snapshot(new_rankings, SNAPSHOT_FILE)

    print(f"\n  ✓ Done: {len(game_ids)} games, {len(milestones)} milestones")


if __name__ == "__main__":
    main()
