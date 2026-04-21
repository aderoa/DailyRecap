#!/usr/bin/env python3
"""
NBA Milestone Recovery — April 20, 2026

Rebuilds snapshot.csv / snapshot_live.csv from authoritative NBA Stats API data
and detects April 20 milestones that the normal ESPN pipeline missed.

WHAT IT DOES
1. Pulls top-200 all-time playoff leaders for PTS/REB/AST/STL/BLK from NBA Stats API
   (AllTimeLeadersGrids with season_type='Playoffs'). This becomes the new
   post-April-20 baseline — the single source of truth.
2. For each April 20 game, pulls the box score via BoxScoreTraditionalV2.
3. Computes pre-April-20 = post - box_score per player (only for players who played).
4. Runs rank-based milestone detection: same logic as milestones.py detect_milestones.
5. Writes updated snapshot_live.csv and snapshot.csv.
6. Appends milestones to milestones_today.csv (deduping against existing rows).

USAGE
    python recovery_april20.py

Runs against files in current directory. Backs up each file before overwriting.

CONFIG
- GAME_DATE controls which date to recover. Set to 2026-04-20 by default.
- TOP_N controls how many leaders to fetch per stat (200 to match MAX_RANK).
"""

import csv
import json
import os
import shutil
import sys
import time
from datetime import datetime
from zoneinfo import ZoneInfo

# ── CONFIG ────────────────────────────────────────────────────
GAME_DATE = "2026-04-20"          # date being recovered (ET)
SEASON = "2025-26"                # NBA season string for API
TOP_N = 200                       # matches MAX_RANK in milestones.py
STATS = ["PTS", "REB", "AST", "STL", "BLK"]
STAT_LABELS = {"PTS": "Scoring", "REB": "Rebounds", "AST": "Assists",
               "STL": "Steals", "BLK": "Blocks"}
SNAPSHOT_FILE = "snapshot.csv"
SNAPSHOT_LIVE = "snapshot_live.csv"
MILESTONES_FILE = "milestones_today.csv"
PROCESSED_FILE = "processed_games.txt"
API_DELAY = 1.2

# Name-map URL matches milestones.py so player display names stay consistent
NAME_MAP_URL = os.environ.get(
    "NAME_MAP_URL",
    "https://docs.google.com/spreadsheets/d/e/2PACX-1vS2iZj3avZ_-CAWKu-f_pxZkf38M0quXQwMbyTXmHsN6-c9V8vU1l_sNaxg0y8dl07dqraU3_5Z3b8D/pub?gid=1197809522&single=true&output=csv"
)

# ── IMPORTS ───────────────────────────────────────────────────
try:
    from nba_api.stats.endpoints import (
        AllTimeLeadersGrids,
        ScoreboardV2,
        BoxScoreTraditionalV2,
    )
except ImportError:
    print("ERROR: nba_api not installed. Run: pip install nba_api")
    sys.exit(1)

try:
    import requests
except ImportError:
    print("ERROR: requests not installed. Run: pip install requests")
    sys.exit(1)


# ── NBA API HEADERS ───────────────────────────────────────────
NBA_HEADERS = {
    'Host': 'stats.nba.com',
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:136.0) Gecko/20100101 Firefox/136.0',
    'Accept': 'application/json, text/plain, */*',
    'Accept-Language': 'en-US,en;q=0.5',
    'Accept-Encoding': 'gzip, deflate, br',
    'x-nba-stats-origin': 'stats',
    'x-nba-stats-token': 'true',
    'Origin': 'https://www.nba.com',
    'Connection': 'keep-alive',
    'Referer': 'https://www.nba.com/',
}


def api_call(endpoint_class, **kwargs):
    """Call an nba_api endpoint with retries and rate limiting."""
    for attempt in range(4):
        try:
            time.sleep(API_DELAY)
            return endpoint_class(headers=NBA_HEADERS, timeout=45, **kwargs)
        except Exception as e:
            wait = (attempt + 1) * 8
            print(f"    API error (try {attempt + 1}/4): {str(e)[:60]} — retry in {wait}s")
            time.sleep(wait)
    raise RuntimeError(f"API call failed after 4 attempts: {endpoint_class.__name__}")


# ── NAME MAP ──────────────────────────────────────────────────
def load_name_map():
    """HoopsHype translation layer — matches milestones.py behavior."""
    try:
        r = requests.get(NAME_MAP_URL, timeout=20)
        if r.status_code != 200:
            return {}
        reader = csv.reader(r.text.splitlines())
        name_map = {}
        for row in reader:
            if len(row) > 12:
                nba_name = row[11].strip()
                hh_name = row[12].strip()
                if nba_name and hh_name and nba_name != "NBA NAME" and not nba_name.lower().startswith("season"):
                    name_map[nba_name] = hh_name
        return name_map
    except Exception as e:
        print(f"  Name map fetch failed (non-fatal): {e}")
        return {}


# ── AUTHORITATIVE POST-DATE TOTALS ────────────────────────────
def fetch_alltime_leaders():
    """
    Pull top-TOP_N playoff leaders for each stat from NBA's AllTimeLeadersGrids.
    Returns dict: {stat: [{rank, player_id, name, total}, ...]}
    Note: This endpoint returns a separate frame per stat. We take the PO version.
    """
    result = {}
    print(f"\n  Fetching all-time playoff leaders (top {TOP_N}) from NBA Stats API...")
    endpoint = api_call(
        AllTimeLeadersGrids,
        league_id='00',
        per_mode_simple='Totals',
        season_type='Playoffs',
        topx=TOP_N,
    )
    # AllTimeLeadersGrids returns multiple frames, one per stat category.
    # The exact frame order is documented as: PTS, AST, STL, BLK, ..., REB, ...
    # We'll match by inspecting each frame's columns and value range.
    frames = endpoint.get_data_frames()
    
    # Map stat → frame by detecting which numeric column holds the stat value
    # Each frame has: PLAYER_ID, PLAYER_NAME, <STAT>, <STAT>_RANK
    stat_to_frame = {}
    for i, df in enumerate(frames):
        if len(df) == 0:
            continue
        cols = list(df.columns)
        # Look for PTS, REB, AST, STL, BLK columns
        for s in STATS:
            if s in cols and f"{s}_RANK" in cols:
                stat_to_frame[s] = df
                print(f"    Frame {i} → {s} ({len(df)} rows)")
                break
    
    missing = [s for s in STATS if s not in stat_to_frame]
    if missing:
        print(f"  ⚠ Missing frames for: {missing}")
        print(f"  Available frames shapes: {[df.shape for df in frames]}")
        raise RuntimeError(f"Could not identify frames for {missing}")
    
    for stat, df in stat_to_frame.items():
        rows = []
        for _, r in df.iterrows():
            try:
                total = int(r[stat])
                rank = int(r[f"{stat}_RANK"])
                pid = str(r["PLAYER_ID"])
                name = str(r["PLAYER_NAME"]).strip()
                rows.append({"rank": rank, "player_id": pid, "name": name, "total": total})
            except (ValueError, TypeError):
                continue
        rows.sort(key=lambda x: x["rank"])
        result[stat] = rows[:TOP_N]
    
    for s, rows in result.items():
        if rows:
            print(f"    {s}: top = {rows[0]['name']} ({rows[0]['total']:,})")
    return result


# ── APRIL 20 BOX SCORES ───────────────────────────────────────
def fetch_game_ids_for_date(date_str):
    """Get GAME_IDs for NBA games on a given date."""
    # date_str is YYYY-MM-DD. ScoreboardV2 wants MM/DD/YYYY
    dt = datetime.strptime(date_str, "%Y-%m-%d")
    mmddyyyy = dt.strftime("%m/%d/%Y")
    print(f"\n  Fetching scoreboard for {date_str} ({mmddyyyy})...")
    sb = api_call(ScoreboardV2, game_date=mmddyyyy, league_id='00')
    frames = sb.get_data_frames()
    # First frame is usually GameHeader
    gh = frames[0]
    game_ids = []
    for _, r in gh.iterrows():
        gid = str(r.get("GAME_ID", "")).strip()
        status = str(r.get("GAME_STATUS_TEXT", "")).strip()
        if gid:
            game_ids.append((gid, status))
    print(f"    Found {len(game_ids)} games: {[g[0] for g in game_ids]}")
    return game_ids


def fetch_box_score(game_id):
    """Pull per-player stats for a single game. Returns {player_id: {PTS, REB, AST, STL, BLK}}."""
    print(f"    Box score {game_id}...", end=" ")
    ep = api_call(BoxScoreTraditionalV2, game_id=game_id)
    frames = ep.get_data_frames()
    ps = frames[0]  # PlayerStats frame
    stats = {}
    for _, r in ps.iterrows():
        pid = str(r.get("PLAYER_ID", "")).strip()
        name = str(r.get("PLAYER_NAME", "")).strip()
        if not pid:
            continue
        # Skip DNPs
        mins = r.get("MIN")
        if mins is None or (isinstance(mins, str) and mins.strip() in ("", "None")):
            continue
        try:
            entry = {
                "PTS": int(r.get("PTS") or 0),
                "REB": int(r.get("REB") or 0),
                "AST": int(r.get("AST") or 0),
                "STL": int(r.get("STL") or 0),
                "BLK": int(r.get("BLK") or 0),
                "name": name,
                "team_abbr": str(r.get("TEAM_ABBREVIATION") or ""),
            }
            stats[pid] = entry
        except (ValueError, TypeError):
            continue
    print(f"{len(stats)} players")
    return stats


# ── DETECT MILESTONES ─────────────────────────────────────────
def build_pre_rankings(post_rankings, all_boxes):
    """
    Given post-date rankings and {player_id: {STAT: gained}}, derive pre-date rankings
    by subtracting. Re-ranks after subtraction.
    """
    pre = {}
    for stat in STATS:
        post_list = post_rankings.get(stat, [])
        entries = []
        for e in post_list:
            pid = e["player_id"]
            gained = 0
            box = all_boxes.get(pid)
            if box:
                gained = box.get(stat, 0) or 0
            entries.append({
                "player_id": pid,
                "name": e["name"],
                "total": e["total"] - gained,
                "gained": gained,
            })
        # Re-rank pre-state
        entries.sort(key=lambda x: x["total"], reverse=True)
        for i, e in enumerate(entries):
            e["rank"] = i + 1
        pre[stat] = entries
    return pre


def detect_milestones(pre_rankings, post_rankings, name_map):
    """
    Mirror milestones.py detect_milestones — find rank crossings within top-TOP_N.
    """
    milestones = []
    for stat in STATS:
        old_list = pre_rankings.get(stat, [])
        new_list = post_rankings.get(stat, [])
        if not old_list or not new_list:
            continue
        old_by_pid = {e["player_id"]: e for e in old_list}
        old_by_rank = {e["rank"]: e for e in old_list}
        for entry in new_list:
            pid = entry["player_id"]
            new_rank = entry["rank"]
            old_entry = old_by_pid.get(pid)
            if not old_entry:
                continue
            gained = old_entry.get("gained", 0)
            old_rank = old_entry["rank"]
            if new_rank >= old_rank or gained <= 0 or new_rank > TOP_N:
                continue
            # For each intermediate rank, that player was passed
            for pr in range(new_rank, old_rank):
                pe = old_by_rank.get(pr)
                if not pe or pe["player_id"] == pid:
                    continue
                display = name_map.get(entry["name"], entry["name"])
                passed = name_map.get(pe["name"], pe["name"])
                milestones.append({
                    "player": display,
                    "player_raw": entry["name"],
                    "stat": stat,
                    "label": STAT_LABELS[stat],
                    "new_rank": new_rank,
                    "new_total": entry["total"],
                    "passed": passed,
                    "passed_raw": pe["name"],
                    "passed_total": pe["total"],
                })
    milestones.sort(key=lambda m: (m["new_rank"], STATS.index(m["stat"])))
    return milestones


def combine_milestones(milestones):
    """Group multiple-pass milestones by (player, stat)."""
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


# ── SNAPSHOT I/O ──────────────────────────────────────────────
def write_snapshot(path, rankings):
    """Write rankings to CSV matching the existing format."""
    with open(path, "w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["STAT", "RANK", "PLAYER_ID", "PLAYER_NAME", "TOTAL", "ACTIVE"])
        for stat in STATS:
            for e in rankings.get(stat, []):
                w.writerow([stat, e["rank"], e["player_id"], e["name"], e["total"], "FALSE"])
    print(f"  Wrote {path}")


def make_logo_url(team_abbr):
    """Mirror milestones.py make_logo_url — use NBA CDN logos."""
    TEAM_IDS = {
        "ATL": "1610612737", "BOS": "1610612738", "CLE": "1610612739",
        "NOP": "1610612740", "CHI": "1610612741", "DAL": "1610612742",
        "DEN": "1610612743", "GSW": "1610612744", "HOU": "1610612745",
        "LAC": "1610612746", "LAL": "1610612747", "MIA": "1610612748",
        "MIL": "1610612749", "MIN": "1610612750", "BKN": "1610612751",
        "NYK": "1610612752", "ORL": "1610612753", "IND": "1610612754",
        "PHI": "1610612755", "PHX": "1610612756", "POR": "1610612757",
        "SAC": "1610612758", "SAS": "1610612759", "OKC": "1610612760",
        "TOR": "1610612761", "UTA": "1610612762", "MEM": "1610612763",
        "WAS": "1610612764", "DET": "1610612765", "CHA": "1610612766",
    }
    tid = TEAM_IDS.get(team_abbr.upper())
    return f"https://cdn.nba.com/logos/nba/{tid}/global/L/logo.svg" if tid else ""


def append_milestones_to_csv(milestones, path, all_boxes, post_rankings):
    """Append new milestone rows to milestones_today.csv, deduping against existing entries."""
    # Load existing rows
    existing = set()
    existing_rows = []
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8", newline="") as fh:
            reader = csv.reader(fh)
            for i, row in enumerate(reader):
                existing_rows.append(row)
                if i == 0:
                    continue  # header
                if len(row) >= 8:
                    # dedup key: (player, stat_code)
                    existing.add((row[0], row[7]))
    
    # Write header if missing
    if not existing_rows:
        existing_rows.append([
            "PLAYER", "RAT", "PASSED", "CATEGORY", "RANK",
            "STAT_TOTAL", "PASSED_TOTAL", "STAT_CODE", "LOGO_URL"
        ])
    
    # Build team abbr lookup from boxes → player_id → team
    pid_to_team = {pid: box.get("team_abbr", "") for pid, box in all_boxes.items()}
    # Also build name → team for fallback
    name_to_pid = {}
    for stat, rows in post_rankings.items():
        for e in rows:
            name_to_pid.setdefault(e["name"], e["player_id"])
    
    added = 0
    new_rows = []
    for m in milestones:
        key = (m["player"], m["stat"])
        if key in existing:
            continue
        pid = name_to_pid.get(m["player_raw"], "")
        team = pid_to_team.get(pid, "")
        logo = make_logo_url(team)
        row = [
            m["player"], "", m["passed"], m["label"], m["new_rank"],
            m["new_total"], m["passed_total"], m["stat"], logo,
        ]
        new_rows.append(row)
        added += 1
    
    if new_rows:
        with open(path, "a", encoding="utf-8", newline="") as fh:
            w = csv.writer(fh)
            # If file is new (we wrote header above), write header first
            if len(existing_rows) == 1 and not os.path.getsize(path):
                w.writerow(existing_rows[0])
            for r in new_rows:
                w.writerow(r)
    
    print(f"  Appended {added} new milestone(s) to {path} (skipped {len(milestones) - added} duplicates)")


def print_milestones(milestones):
    if not milestones:
        print("\n  No milestones detected.")
        return
    print(f"\n  ┌─ {len(milestones)} MILESTONE(S) ──────────────────────────")
    for m in milestones:
        print(f"  │ #{m['new_rank']:>3}  {m['player']:<30} {m['label']:<10} "
              f"({m['new_total']:,})  passed  {m['passed']} ({m['passed_total']:,})")
    print("  └─────────────────────────────────────────────")


# ── MAIN ─────────────────────────────────────────────────────
def main():
    print("=" * 60)
    print(f"  MILESTONE RECOVERY — {GAME_DATE}")
    print(f"  {datetime.now(ZoneInfo('America/New_York')).strftime('%Y-%m-%d %H:%M')} ET")
    print("=" * 60)

    # Back up everything before touching
    print("\n  Backing up existing files...")
    for f in [SNAPSHOT_FILE, SNAPSHOT_LIVE, MILESTONES_FILE]:
        if os.path.exists(f):
            shutil.copy2(f, f + ".bak")
            print(f"    {f} → {f}.bak")

    # 1. Name map
    print("\n  Loading name map...")
    name_map = load_name_map()
    print(f"    Loaded {len(name_map)} translations")

    # 2. Authoritative post-GAME_DATE totals
    post_rankings = fetch_alltime_leaders()

    # 3. April 20 games + box scores
    game_ids = fetch_game_ids_for_date(GAME_DATE)
    finals = [gid for gid, status in game_ids if "Final" in status or status.startswith("F")]
    # ScoreboardV2 status often shows "Final" or "Final/OT" for completed games
    # Fall back: try all games if none marked final
    if not finals:
        print("  No games explicitly marked Final — trying all listed games anyway.")
        finals = [gid for gid, _ in game_ids]
    
    all_boxes = {}
    for gid in finals:
        try:
            box = fetch_box_score(gid)
            all_boxes.update(box)
        except Exception as e:
            print(f"    ⚠ Box score {gid} failed: {e}")
    active_count = sum(1 for b in all_boxes.values() if any(b.get(s, 0) > 0 for s in STATS))
    print(f"\n  Box scores total: {len(all_boxes)} players ({active_count} with stats)")

    # 4. Derive pre-GAME_DATE rankings
    print("\n  Deriving pre-April-20 rankings by subtracting box scores...")
    pre_rankings = build_pre_rankings(post_rankings, all_boxes)

    # 5. Detect milestones
    print("  Detecting milestones...")
    milestones = detect_milestones(pre_rankings, post_rankings, name_map)
    milestones = combine_milestones(milestones)
    print_milestones(milestones)

    # 6. Write updated snapshots (authoritative post-state)
    print("\n  Writing updated snapshots...")
    write_snapshot(SNAPSHOT_LIVE, post_rankings)
    write_snapshot(SNAPSHOT_FILE, post_rankings)

    # 7. Append to milestones_today.csv
    print("\n  Updating milestones_today.csv...")
    append_milestones_to_csv(milestones, MILESTONES_FILE, all_boxes, post_rankings)

    # 8. Ensure April 20 game IDs are in processed_games.txt
    if os.path.exists(PROCESSED_FILE):
        with open(PROCESSED_FILE, "r") as fh:
            processed = set(line.strip() for line in fh if line.strip())
    else:
        processed = set()
    # Convert NBA-style game IDs to ESPN-style? We don't have ESPN IDs here.
    # Just skip — milestones.py won't reprocess since the snapshot is already updated.
    
    print("\n" + "=" * 60)
    print(f"  DONE: {len(milestones)} milestone(s) detected")
    print(f"  Next: python generate_recap.py")
    print("=" * 60)


if __name__ == "__main__":
    main()
