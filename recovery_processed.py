"""
Recovery script for milestones pipeline.

Use case: a milestones run no-op'd because games were already in
processed_games.txt (likely from an earlier run that wiped milestones_today.csv
without recording them). This script removes the game IDs for specific dates
from processed_games.txt so the next milestones.py run will pick them up
again and re-detect milestones.

Usage:
  # Default: remove yesterday + today's games (the most common recovery)
  python recovery.py

  # Specific dates
  python recovery.py --date 2026-05-01 --date 2026-05-02

  # Dry run (show what would be removed without changing the file)
  python recovery.py --dry-run

After running this, manually trigger the "Generate NBA Daily Recap" workflow
on GitHub Actions and milestones should be detected.
"""

import argparse
import os
import sys
from datetime import datetime, timezone, timedelta

import requests

PROCESSED_FILE = "processed_games.txt"
ESPN_SCOREBOARD = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/scoreboard"


def fetch_game_ids_for_date(game_date: str) -> list[str]:
    """Return all ESPN game IDs for the given YYYY-MM-DD date."""
    date_str = game_date.replace("-", "")
    url = f"{ESPN_SCOREBOARD}?dates={date_str}"
    r = requests.get(url, timeout=30)
    r.raise_for_status()
    data = r.json()
    return [ev.get("id", "") for ev in data.get("events", []) if ev.get("id")]


def load_processed() -> set[str]:
    if not os.path.exists(PROCESSED_FILE):
        return set()
    with open(PROCESSED_FILE, "r") as f:
        return {line.strip() for line in f if line.strip()}


def save_processed(ids: set[str]) -> None:
    # Match the original script's format: sorted, one per line
    with open(PROCESSED_FILE, "w") as f:
        for gid in sorted(ids):
            f.write(gid + "\n")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Remove game IDs for specific dates from processed_games.txt"
    )
    parser.add_argument(
        "--date",
        action="append",
        help="Game date to remove (YYYY-MM-DD). Can be repeated. "
             "Defaults to yesterday + today (ET) if not provided.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be removed without writing the file",
    )
    args = parser.parse_args()

    # Default to yesterday + today (ET) — same window the nightly run uses
    if not args.date:
        et = timezone(timedelta(hours=-5))
        now = datetime.now(et)
        yesterday = (now - timedelta(days=1)).strftime("%Y-%m-%d")
        today = now.strftime("%Y-%m-%d")
        dates = [yesterday, today]
    else:
        dates = args.date

    print(f"Recovery target dates: {', '.join(dates)}")
    print()

    # Fetch the game IDs for those dates from ESPN
    ids_to_remove: set[str] = set()
    for d in dates:
        try:
            ids = fetch_game_ids_for_date(d)
            print(f"  {d}: {len(ids)} games found on ESPN")
            for gid in ids:
                ids_to_remove.add(gid)
        except Exception as ex:
            print(f"  {d}: FETCH FAILED — {ex}")
            return 1

    print()

    # Load current processed file
    if not os.path.exists(PROCESSED_FILE):
        print(f"ERROR: {PROCESSED_FILE} not found in current directory.")
        print("Run this script from the same directory as the milestones pipeline.")
        return 1

    processed = load_processed()
    print(f"Current {PROCESSED_FILE}: {len(processed)} entries")

    # Compute what'd actually change
    overlap = processed & ids_to_remove
    print(f"Overlap with target dates: {len(overlap)} entries to remove")
    if overlap:
        print("  IDs being removed:")
        for gid in sorted(overlap):
            print(f"    {gid}")

    if not overlap:
        print()
        print("Nothing to remove — those games aren't in processed_games.txt.")
        print("(Either already cleared, or never registered.)")
        return 0

    if args.dry_run:
        print()
        print("DRY RUN — no changes written.")
        return 0

    # Write the trimmed file
    new_processed = processed - ids_to_remove
    save_processed(new_processed)
    print()
    print(f"✓ Wrote {PROCESSED_FILE} ({len(new_processed)} entries, "
          f"{len(overlap)} removed)")
    print()
    print("Next steps:")
    print("  1. Commit and push processed_games.txt")
    print("  2. Manually trigger 'Generate NBA Daily Recap' workflow")
    print("  3. Verify milestones_today.csv now has entries")

    return 0


if __name__ == "__main__":
    sys.exit(main())
