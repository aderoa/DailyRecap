#!/usr/bin/env python3
"""
NBA All-Time Milestone Detector
Compares career totals day-to-day to find players who passed others
in the all-time rankings for PTS, REB, AST, STL, BLK.

Usage:
  python milestones.py                    # detect milestones, output CSV
  python milestones.py --init             # first run: create baseline snapshot
  python milestones.py --snapshot-only    # update snapshot without detecting

Data flow:
  1. Reads previous snapshot from Google Sheet (published CSV)
  2. Fetches fresh career totals from nba_api AllTimeLeadersGrids
  3. Compares old vs new rankings → detects who passed whom
  4. Outputs milestones to milestones_today.csv
  5. Outputs new snapshot to snapshot_new.csv (paste into Sheet)

Google Sheet setup:
  - Tab "Snapshot": previous day's all-time rankings (5 cols per stat)
  - Tab "Milestones": today's milestones (read by Daily Recap)
"""
import csv, io, os, sys, time, json
from datetime import datetime, timezone, timedelta

# ── CONFIG ────────────────────────────────────────────────────
# Google Sheet published CSV for the SNAPSHOT tab
# Replace with your actual Sheet ID and GID after creating the tab
SNAPSHOT_SHEET_URL = os.environ.get(
    "SNAPSHOT_URL",
    "https://docs.google.com/spreadsheets/d/e/YOUR_SHEET_ID/pub?gid=SNAPSHOT_GID&single=true&output=csv"
)

# nba_api parameters
TOP_X = 500  # how deep to fetch in each category
STATS = ["PTS", "REB", "AST", "STL", "BLK"]
STAT_LABELS = {"PTS": "Scoring", "REB": "Rebounds", "AST": "Assists", "STL": "Steals", "BLK": "Blocks"}

# Result set names returned by AllTimeLeadersGrids
RESULT_SET_MAP = {
    "PTS": "PTSLeaders",
    "REB": "REBLeaders",
    "AST": "ASTLeaders",
    "STL": "STLLeaders",
    "BLK": "BLKLeaders",
}

# Browser-mimicking headers (required for stats.nba.com)
NBA_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
    "x-nba-stats-origin": "stats",
    "x-nba-stats-token": "true",
    "Referer": "https://www.nba.com/",
    "Origin": "https://www.nba.com",
}

# Name mapping: some nba_api names differ from HoopsHype names
# Add entries as needed: "NBA_API_NAME": "HOOPSHYPE_NAME"
NAME_MAP_URL = os.environ.get(
    "NAME_MAP_URL",
    "https://docs.google.com/spreadsheets/d/e/2PACX-1vS2iZj3avZ_-CAWKu-f_pxZkf38M0quXQwMbyTXmHsN6-c9V8vU1l_sNaxg0y8dl07dqraU3_5Z3b8D/pub?gid=1197809522&single=true&output=csv"
)


# ── FETCH HELPERS ─────────────────────────────────────────────
def fetch_csv(url):
    """Fetch CSV with cache-busting and forced UTF-8."""
    import requests
    url += f"&_cb={int(time.time())}"
    r = requests.get(url, timeout=30, headers={"Cache-Control": "no-cache"})
    r.encoding = "utf-8"
    return r.text


def build_name_map():
    """Build NBA API name → HoopsHype name map."""
    nm = {}
    try:
        text = fetch_csv(NAME_MAP_URL)
        reader = csv.reader(io.StringIO(text))
        next(reader, None)  # skip header
        for row in reader:
            if len(row) < 13:
                continue
            nba, hh = row[11].strip(), row[12].strip()
            if nba and hh:
                nm[nba] = hh
    except Exception as e:
        print(f"  Warning: could not load name map: {e}")
    return nm


# ── FETCH ALL-TIME LEADERS FROM NBA API ──────────────────────
def fetch_alltime_leaders():
    """
    Fetch all-time career totals from nba_api.
    Returns: {stat: [{name, total, rank, active}, ...]}
    """
    from nba_api.stats.endpoints import alltimeleadersgrids

    print(f"  Fetching AllTimeLeadersGrids (top {TOP_X})...")
    leaders = alltimeleadersgrids.AllTimeLeadersGrids(
        topx=TOP_X,
        per_mode_simple="Totals",
        season_type="Regular Season",
        headers=NBA_HEADERS,
    )
    data = leaders.get_dict()
    time.sleep(1)  # be nice to the API

    rankings = {}
    for stat in STATS:
        rs_name = RESULT_SET_MAP[stat]
        rs = next((r for r in data["resultSets"] if r["name"] == rs_name), None)
        if not rs:
            print(f"  Warning: result set '{rs_name}' not found")
            rankings[stat] = []
            continue

        headers = rs["headers"]
        rows = rs["rowSet"]

        # Find column indices dynamically
        id_col = headers.index("PLAYER_ID") if "PLAYER_ID" in headers else 0
        name_col = headers.index("PLAYER_NAME") if "PLAYER_NAME" in headers else 1
        # The stat total column name matches the stat abbreviation
        total_col = headers.index(stat) if stat in headers else 2
        active_col = headers.index("IS_ACTIVE_FLAG") if "IS_ACTIVE_FLAG" in headers else None

        entries = []
        for i, row in enumerate(rows):
            name = row[name_col]
            total = int(row[total_col]) if row[total_col] is not None else 0
            active = bool(row[active_col]) if active_col is not None else False
            entries.append({
                "player_id": row[id_col],
                "name": name,
                "total": total,
                "rank": i + 1,
                "active": active,
            })
        rankings[stat] = entries
        print(f"    {stat}: {len(entries)} players (top: {entries[0]['name']} = {entries[0]['total']:,})")

    return rankings


# NBA team ID → 3-letter abbreviation (same as generate_recap.py)
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


def fetch_player_teams():
    """Fetch active player → team_id mapping. Returns {player_id: team_id_str}."""
    from nba_api.stats.endpoints import commonallplayers
    print("  Fetching player-team mapping...")
    try:
        players = commonallplayers.CommonAllPlayers(
            is_only_current_season=1, league_id="00", season="2025-26",
            headers=NBA_HEADERS,
        )
        data = players.get_dict()
        time.sleep(1)
        rs = data["resultSets"][0]
        hdrs = rs["headers"]
        pid_col = hdrs.index("PERSON_ID") if "PERSON_ID" in hdrs else 0
        tid_col = hdrs.index("TEAM_ID") if "TEAM_ID" in hdrs else 7
        team_map = {}
        for row in rs["rowSet"]:
            pid, tid = row[pid_col], row[tid_col]
            if pid and tid and tid != 0:
                team_map[pid] = str(tid)
        print(f"    Loaded {len(team_map)} player-team mappings")
        return team_map
    except Exception as e:
        print(f"  Warning: could not fetch player teams: {e}")
        return {}


def make_logo_url(team_id):
    """Build NBA CDN logo URL from team_id (used by generate_recap.py for team abbr)."""
    return f"https://cdn.nba.com/logos/nba/{team_id}/primary/L/logo.svg" if team_id else ""


# ── SNAPSHOT I/O ──────────────────────────────────────────────
def load_snapshot_from_sheet():
    """
    Load previous snapshot from Google Sheet published CSV.
    CSV format: STAT,RANK,PLAYER_NAME,TOTAL,ACTIVE
    Returns: {stat: [{name, total, rank, active}, ...]}
    """
    print("  Loading previous snapshot from Sheet...")
    try:
        text = fetch_csv(SNAPSHOT_SHEET_URL)
    except Exception as e:
        print(f"  Warning: could not load snapshot: {e}")
        return None

    rankings = {s: [] for s in STATS}
    reader = csv.DictReader(io.StringIO(text))
    for row in reader:
        stat = row.get("STAT", "").strip()
        if stat not in rankings:
            continue
        rankings[stat].append({
            "name": row.get("PLAYER_NAME", "").strip(),
            "total": int(row.get("TOTAL", 0)),
            "rank": int(row.get("RANK", 0)),
            "active": row.get("ACTIVE", "").strip().upper() in ("TRUE", "1", "Y"),
        })
    total = sum(len(v) for v in rankings.values())
    print(f"    Loaded {total} entries across {len(STATS)} stats")
    return rankings if total > 0 else None


def load_snapshot_from_csv(path):
    """Load snapshot from local CSV file."""
    if not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8") as f:
        text = f.read()
    rankings = {s: [] for s in STATS}
    reader = csv.DictReader(io.StringIO(text))
    for row in reader:
        stat = row.get("STAT", "").strip()
        if stat not in rankings:
            continue
        rankings[stat].append({
            "name": row.get("PLAYER_NAME", "").strip(),
            "total": int(row.get("TOTAL", 0)),
            "rank": int(row.get("RANK", 0)),
            "active": row.get("ACTIVE", "").strip().upper() in ("TRUE", "1", "Y"),
        })
    return rankings if sum(len(v) for v in rankings.values()) > 0 else None


def save_snapshot_csv(rankings, path):
    """Save snapshot to CSV file."""
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["STAT", "RANK", "PLAYER_NAME", "TOTAL", "ACTIVE"])
        for stat in STATS:
            for entry in rankings.get(stat, []):
                w.writerow([
                    stat,
                    entry["rank"],
                    entry["name"],
                    entry["total"],
                    "TRUE" if entry.get("active") else "FALSE",
                ])
    print(f"  Snapshot saved: {path} ({os.path.getsize(path) / 1024:.1f} KB)")


# ── MILESTONE DETECTION ──────────────────────────────────────
def detect_milestones(old_rankings, new_rankings, name_map=None):
    """
    Compare two ranking snapshots.
    Returns list of milestones: [{player, stat, label, new_rank, passed, team_logo}]

    Logic:
    - For each stat, compare old rank → new rank for every player
    - If a player's rank improved (lower number = better), they passed someone
    - The "passed" player is whoever held the new rank in the old snapshot
    - Only report when rank actually changes (not just total increase without passing)
    """
    nm = name_map or {}
    milestones = []

    for stat in STATS:
        old_list = old_rankings.get(stat, [])
        new_list = new_rankings.get(stat, [])

        if not old_list or not new_list:
            continue

        # Build lookup: name → {rank, total} for old
        old_by_name = {e["name"]: e for e in old_list}
        # Build lookup: rank → name for old (to find who was passed)
        old_by_rank = {e["rank"]: e for e in old_list}

        for entry in new_list:
            name = entry["name"]
            new_rank = entry["rank"]
            new_total = entry["total"]

            # Must be in old snapshot to detect change
            old_entry = old_by_name.get(name)
            if not old_entry:
                continue

            old_rank = old_entry["rank"]
            old_total = old_entry["total"]

            # Must have improved rank
            if new_rank >= old_rank:
                continue

            # Must have actually gained stats (not just a re-ranking from someone retiring/correction)
            if new_total <= old_total:
                continue

            # Find all players who were passed (ranks between new_rank and old_rank-1)
            for passed_rank in range(new_rank, old_rank):
                passed_entry = old_by_rank.get(passed_rank)
                if not passed_entry:
                    continue
                if passed_entry["name"] == name:
                    continue  # can't pass yourself

                # Translate names to HoopsHype names if mapping exists
                display_name = nm.get(name, name)
                passed_name = nm.get(passed_entry["name"], passed_entry["name"])

                milestones.append({
                    "player": display_name,
                    "player_raw": name,
                    "player_id": entry.get("player_id"),
                    "stat": stat,
                    "label": STAT_LABELS[stat],
                    "new_rank": new_rank,
                    "new_total": new_total,
                    "passed": passed_name,
                    "passed_raw": passed_entry["name"],
                    "passed_total": passed_entry["total"],
                })

    # Sort: lowest rank first (most impressive), then by stat
    milestones.sort(key=lambda m: (m["new_rank"], STATS.index(m["stat"])))
    return milestones


# ── OUTPUT ────────────────────────────────────────────────────
def save_milestones_csv(milestones, path, player_teams=None):
    """Save milestones to CSV for the Recap sheet.
    Includes LOGO_URL column so generate_recap.py can resolve team abbreviation."""
    pt = player_teams or {}
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["PLAYER", "RAT", "PASSED", "CATEGORY", "RANK",
                     "STAT_TOTAL", "PASSED_TOTAL", "STAT_CODE", "LOGO_URL"])
        for m in milestones:
            pid = m.get("player_id")
            tid = pt.get(pid, "") if pid else ""
            logo = make_logo_url(tid)
            w.writerow([
                m["player"],
                "",  # RAT column (unused for milestones)
                m["passed"],
                m["label"],
                m["new_rank"],
                m["new_total"],
                m["passed_total"],
                m["stat"],
                logo,
            ])
    print(f"  Milestones saved: {path} ({len(milestones)} entries)")


def print_milestones(milestones):
    """Pretty-print milestones to console."""
    if not milestones:
        print("\n  No milestones detected today.")
        return
    print(f"\n  ┌─ {len(milestones)} MILESTONE(S) DETECTED ──────────────────")
    for m in milestones:
        print(f"  │ #{m['new_rank']:>3}  {m['player']:<28} {m['label']:<10} "
              f"({m['new_total']:,})  passed  {m['passed']} ({m['passed_total']:,})")
    print(f"  └─────────────────────────────────────────────")


# ── RECAP INTEGRATION ─────────────────────────────────────────
def format_for_recap_sheet(milestones):
    """
    Format milestones as rows ready to paste into the Recap Google Sheet.
    Matches the MILESTONES section format expected by generate_recap.py:
    Col 0: Player name
    Col 1: (empty - RAT)
    Col 2: Passed player name
    Col 3: Category label (Scoring, Rebounds, etc.)
    Col 4: Rank number
    Col 11: Team logo URL (filled by Sheet lookup)
    """
    rows = []
    for m in milestones:
        rows.append([
            m["player"],       # col 0: name
            "",                # col 1: RAT (empty)
            m["passed"],       # col 2: passed
            m["label"],        # col 3: category
            str(m["new_rank"]),  # col 4: rank
        ])
    return rows


# ── MAIN ─────────────────────────────────────────────────────
def main():
    import argparse
    parser = argparse.ArgumentParser(description="NBA All-Time Milestone Detector")
    parser.add_argument("--init", action="store_true", help="Create initial baseline snapshot")
    parser.add_argument("--snapshot-only", action="store_true", help="Update snapshot without detecting milestones")
    parser.add_argument("--snapshot-file", default="snapshot.csv", help="Local snapshot CSV path (default: snapshot.csv)")
    parser.add_argument("--output", default="milestones_today.csv", help="Output milestones CSV path")
    parser.add_argument("--use-local", action="store_true", help="Use local snapshot file instead of Google Sheet")
    args = parser.parse_args()

    et = timezone(timedelta(hours=-5))
    today = datetime.now(et).strftime("%Y-%m-%d")
    print("=" * 55)
    print("  NBA ALL-TIME MILESTONE DETECTOR")
    print(f"  {today} (ET)")
    print("=" * 55)

    # ── Step 1: Load name map
    print("\n  Loading name mappings...")
    name_map = build_name_map()
    print(f"  Loaded {len(name_map)} name translations")

    # ── Step 2: Fetch fresh all-time leaders
    print("\n  Fetching fresh all-time leaders from NBA API...")
    try:
        new_rankings = fetch_alltime_leaders()
    except Exception as e:
        print(f"\n  ERROR: Failed to fetch from NBA API: {e}")
        print("  Make sure you have nba_api installed: pip install nba_api")
        sys.exit(1)

    # ── Step 3: Save new snapshot
    snapshot_path = args.snapshot_file
    new_snapshot_path = snapshot_path.replace(".csv", "_new.csv")
    save_snapshot_csv(new_rankings, new_snapshot_path)

    if args.init:
        # First run: just save snapshot, no comparison
        save_snapshot_csv(new_rankings, snapshot_path)
        print(f"\n  ✓ Baseline snapshot created: {snapshot_path}")
        print("  Run again tomorrow (without --init) to detect milestones.")
        return

    if args.snapshot_only:
        save_snapshot_csv(new_rankings, snapshot_path)
        print(f"\n  ✓ Snapshot updated: {snapshot_path}")
        return

    # ── Step 4: Load previous snapshot
    if args.use_local:
        old_rankings = load_snapshot_from_csv(snapshot_path)
    else:
        old_rankings = load_snapshot_from_sheet()
        if not old_rankings:
            print("  Sheet snapshot not available, trying local file...")
            old_rankings = load_snapshot_from_csv(snapshot_path)

    if not old_rankings:
        print("\n  No previous snapshot found. Run with --init first to create baseline.")
        print("  Creating baseline now...")
        save_snapshot_csv(new_rankings, snapshot_path)
        print(f"  ✓ Baseline saved: {snapshot_path}")
        return

    # ── Step 5: Detect milestones
    print("\n  Detecting milestones...")
    milestones = detect_milestones(old_rankings, new_rankings, name_map)
    print_milestones(milestones)

    # ── Step 5b: Fetch player teams for logo URLs
    player_teams = {}
    if milestones:
        try:
            player_teams = fetch_player_teams()
        except Exception as e:
            print(f"  Warning: could not fetch teams: {e}")

    # ── Step 6: Save outputs
    if milestones:
        save_milestones_csv(milestones, args.output, player_teams)

        # Also print Recap-ready format
        recap_rows = format_for_recap_sheet(milestones)
        print("\n  Recap-ready rows (paste into Sheet):")
        for row in recap_rows:
            print(f"    {' | '.join(row)}")

    # ── Step 7: Rotate snapshot (new becomes current)
    save_snapshot_csv(new_rankings, snapshot_path)
    print(f"\n  ✓ Snapshot rotated: {snapshot_path}")

    # ── Summary
    total_entries = sum(len(v) for v in new_rankings.values())
    print(f"\n  Summary: {total_entries} rankings tracked, {len(milestones)} milestones found")
    print("  Done ✓")


if __name__ == "__main__":
    main()
