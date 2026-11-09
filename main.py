import argparse
import logging
import math
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from fetcher import DATA_FILE, exclude_players, load_players_csv
from optimizer import EuroLeagueFantasyOptimizer


REQUIRED = {'Guard': 4, 'Forward': 4, 'Center': 2}
POSITION_ORDER = {'Guard': 0, 'Forward': 1, 'Center': 2}


def get_budget():
    """Ask the user for their available budget (credits)."""
    while True:
        raw = input("Enter your total budget (credits): ").strip()
        try:
            budget = float(raw)
        except ValueError:
            print(f"'{raw}' is not a valid number. Try e.g. 100")
            continue
        if budget <= 0:
            print("Budget must be positive. Try again.")
            continue
        return budget


def build_parser():
    parser = argparse.ArgumentParser(
        description="Optimize a EuroLeague Fantasy lineup for maximum FPT."
    )
    parser.add_argument(
        "-b", "--budget", type=float, default=None,
        help="Total credits available. Prompts interactively when omitted."
    )
    parser.add_argument(
        "--csv", default=DATA_FILE,
        help=f"Path to the player stats CSV (default: {DATA_FILE})."
    )
    parser.add_argument(
        "--max-per-team", type=int, default=4,
        help="Maximum players from the same club (default: 4)."
    )
    parser.add_argument(
        "--exclude", action="append", nargs="+", default=[], metavar="ID_OR_NAME",
        help="Player ID or name to exclude. Repeatable; accepts multiple values."
    )
    parser.add_argument(
        "--top-n", type=int, default=1, metavar="N",
        help="Number of alternative lineups to produce (default: 1)."
    )
    parser.add_argument(
        "--output", metavar="FILE",
        help="Save lineup(s) to a file. CSV or JSON (based on extension)."
    )
    parser.add_argument(
        "--log", metavar="FILE",
        help="Append a summary row for this run to a history CSV."
    )
    return parser


def sort_lineup(lineup):
    """Sort a lineup by position (Guard → Forward → Center), then FPT descending."""
    return (
        lineup
        .assign(_pos_order=lineup['Position'].map(POSITION_ORDER))
        .sort_values(['_pos_order', 'FPT'], ascending=[True, False])
        .drop(columns='_pos_order')
    )


def save_output(lineups, filepath):
    """Save lineup(s) to CSV or JSON based on file extension."""
    path = Path(filepath)
    frames = []
    for rank, (lineup, _total_fpt) in enumerate(lineups, 1):
        frame = sort_lineup(lineup).copy()
        frame.insert(0, 'Lineup', rank)
        frames.append(frame)
    combined = pd.concat(frames, ignore_index=True)

    if path.suffix.lower() == '.json':
        combined.to_json(path, orient='records', indent=2)
    else:
        combined.to_csv(path, index=False)
    print(f"\nLineup(s) saved to {path}")


def append_log(lineups, budget, filepath):
    """Append a summary row for this run to a history CSV."""
    path = Path(filepath)
    lineup, total_fpt = lineups[0]  # log the best lineup
    total_cost = float(lineup['Quotation'].sum())
    ids = ';'.join(str(i) for i in sorted(lineup['ID']))
    row = {
        'timestamp': datetime.now(timezone.utc).isoformat(),
        'budget': budget,
        'total_fpt': round(total_fpt, 2),
        'total_cost': round(total_cost, 2),
        'fpt_per_credit': round(total_fpt / total_cost, 4),
        'player_ids': ids,
    }
    write_header = not path.exists()
    pd.DataFrame([row]).to_csv(path, mode='a', header=write_header, index=False)
    print(f"Run logged to {path}")


def main(argv=None):
    logging.basicConfig(
        level=logging.WARNING,
        format="Warning: %(message)s",
        stream=sys.stdout,
    )
    args = build_parser().parse_args(argv)

    # 1. Load Data (active players only, coaches already filtered out)
    print("Loading player data...", flush=True)
    try:
        players = load_players_csv(args.csv)
    except (FileNotFoundError, ValueError) as exc:
        print(f"Error loading data: {exc}")
        return 1

    exclude_tokens = [token for group in args.exclude for token in group]
    players, matched, unmatched = exclude_players(players, exclude_tokens)
    if matched:
        print(f"Excluded by filter(s): {', '.join(matched)}")
    for token in unmatched:
        print(f"Warning: --exclude '{token}' matched no players.")
    if players.empty:
        print("Error: no players left after applying exclusions.")
        return 1

    # Debug: Check if we have enough players for each position
    pos_counts = players['Position'].value_counts()
    print(f"Available Players:\n{pos_counts}")

    for pos, need in REQUIRED.items():
        available = int(pos_counts.get(pos, 0))
        if available < need:
            print(f"Error: not enough {pos}s available ({available} < {need}).")
            return 1

    # 2. Ask user for budget (player values change week to week)
    budget = args.budget
    if budget is None:
        budget = get_budget()
    if budget <= 0:
        print("Error: budget must be positive.")
        return 1

    # 3. Initialize Optimizer with the given budget (max 4 per team)
    try:
        optimizer = EuroLeagueFantasyOptimizer(
            players_df=players,
            budget=budget,
            max_per_team=args.max_per_team
        )
    except ValueError as exc:
        print(f"Error: {exc}")
        return 1

    minimum_cost = optimizer.min_cost()
    if math.isinf(minimum_cost):
        print("Error: no feasible lineup exists with the current pool and constraints.")
        return 1
    if budget + 1e-9 < minimum_cost:
        print(
            f"Error: budget too low. Minimum feasible cost is "
            f"{minimum_cost:.1f} credits (you entered {budget:.1f})."
        )
        return 1

    # 4. Solve
    top_n = args.top_n
    label = 'optimal lineup' if top_n == 1 else f'top {top_n} lineups'
    print(f"\nSolving for {label}...")
    try:
        lineups = optimizer.solve_top_n(top_n)
    except RuntimeError as exc:
        print(f"Error during optimization: {exc}")
        return 1

    if len(lineups) < top_n:
        print(f"(found {len(lineups)} of {top_n} requested lineups)")

    # 5. Display Results
    display_cols = ['Full Name', 'Position', 'Team', 'FPT', 'Quotation', 'Value per Credit']
    best_fpt = lineups[0][1]

    for rank, (lineup, total_fpt) in enumerate(lineups, 1):
        lineup = sort_lineup(lineup)

        print("\n" + "=" * 50)
        if len(lineups) == 1:
            print("OPTIMAL LINEUP (Max FPT)")
        else:
            tag = "Best" if rank == 1 else f"\u2212{best_fpt - total_fpt:.2f} FPT"
            print(f"LINEUP {rank} OF {len(lineups)}  ({tag})")
        print("=" * 50)

        print(lineup[display_cols].to_string(index=False))

        total_cost = lineup['Quotation'].sum()
        print("-" * 50)
        print(f"Total FPT Score    : {total_fpt:.2f}")
        print(f"Total Credits Used : {total_cost:.1f} / {budget:.1f}")
        print(f"Lineup value       : {total_fpt / total_cost:.2f} FPT per credit")

    # 6. Save output
    if args.output:
        save_output(lineups, args.output)

    # 7. Append to log
    if args.log:
        append_log(lineups, budget, args.log)

    return 0


if __name__ == "__main__":
    sys.exit(main())
