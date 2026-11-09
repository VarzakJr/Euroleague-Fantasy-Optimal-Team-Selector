import logging
import os
import time

import pandas as pd

DATA_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "players_stats.csv")
VALID_POSITIONS = ["Guard", "Forward", "Center"]
STALE_DAYS = 14

logger = logging.getLogger(__name__)


def _warn_if_stale(filepath, stale_days):
    age_days = (time.time() - os.path.getmtime(filepath)) / 86400
    if age_days > stale_days:
        logger.warning(
            "%s is %.1f days old (threshold %d). Prices may be out of date.",
            filepath,
            age_days,
            stale_days,
        )


def load_players_csv(filepath=DATA_FILE, stale_days=STALE_DAYS):
    """
    Loads, validates and cleans the player stats CSV.

    Expected columns: ID, Name, Surname, Active, Position, Team, FPT, Quotation (+ other stats).
    Returns a DataFrame with only active players in valid positions (coaches etc. are dropped).
    """
    if not os.path.exists(filepath):
        raise FileNotFoundError(f"Could not find {filepath}")

    _warn_if_stale(filepath, stale_days)

    df = pd.read_csv(filepath)
    df.columns = [str(c).strip() for c in df.columns]

    required_cols = ["ID", "Name", "Surname", "Active", "Position", "Team", "FPT", "Quotation"]
    missing = [c for c in required_cols if c not in df.columns]
    if missing:
        raise ValueError(f"Missing expected columns in {filepath}: {missing}")

    df = df.dropna(how="all")
    df["Position"] = df["Position"].astype(str).str.strip().str.capitalize()

    active_mask = pd.to_numeric(df["Active"], errors="coerce") == 1
    position_mask = df["Position"].isin(VALID_POSITIONS)
    players_df = df[active_mask & position_mask].copy()
    if players_df.empty:
        raise ValueError(f"No active players found in {filepath}")

    ids = pd.to_numeric(players_df["ID"], errors="coerce")
    valid_id_mask = ids.notna() & (ids % 1 == 0)
    dropped_ids = int((~valid_id_mask).sum())
    if dropped_ids:
        logger.warning(
            "Dropped %d active player rows with a missing or non-numeric ID.",
            dropped_ids,
        )
    players_df = players_df[valid_id_mask].copy()
    players_df["ID"] = ids[valid_id_mask].astype(int)

    duplicate_ids = players_df["ID"].duplicated(keep=False)
    if duplicate_ids.any():
        duplicates = sorted(players_df.loc[duplicate_ids, "ID"].unique())
        raise ValueError(f"Duplicate player IDs in {filepath}: {duplicates}")

    players_df["Full Name"] = (
        players_df["Name"].astype(str).str.strip()
        + " "
        + players_df["Surname"].astype(str).str.strip()
    ).str.strip()
    players_df["Team"] = players_df["Team"].astype(str).str.strip()

    players_df["FPT"] = pd.to_numeric(players_df["FPT"], errors="coerce")
    players_df["Quotation"] = pd.to_numeric(players_df["Quotation"], errors="coerce")
    before = len(players_df)
    players_df = players_df.dropna(subset=["FPT", "Quotation"])
    players_df = players_df[players_df["Quotation"] > 0]
    dropped_values = before - len(players_df)
    if dropped_values:
        logger.warning(
            "Dropped %d active players with invalid FPT or non-positive Quotation.",
            dropped_values,
        )

    players_df["Value per Credit"] = players_df["FPT"] / players_df["Quotation"]

    return players_df[
        ["ID", "Full Name", "Position", "Team", "FPT", "Quotation", "Value per Credit"]
    ].reset_index(drop=True)


def exclude_players(players_df, tokens):
    """
    Removes players matching any exclusion token.

    A token matches when it equals a player's ID or appears (case-insensitively)
    in the player's full name. Returns (filtered_df, matched, unmatched).
    """
    if not tokens:
        return players_df.copy(), [], []

    ids = players_df["ID"].astype(str)
    names = players_df["Full Name"].str.lower()
    excluded_mask = pd.Series(False, index=players_df.index)
    matched, unmatched = [], []

    for token in tokens:
        token = str(token).strip()
        if not token:
            continue
        match = (ids == token) | names.str.contains(token.lower(), regex=False)
        if match.any():
            excluded_mask |= match
            matched.append(token)
        else:
            unmatched.append(token)

    return players_df[~excluded_mask].copy(), matched, unmatched
