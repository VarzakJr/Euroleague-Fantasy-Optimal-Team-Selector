"""
Streamlit GUI for the EuroLeague Fantasy Optimizer.

Launch with:  streamlit run app.py
"""

import math
import tempfile

import pandas as pd
import streamlit as st

from fetcher import DATA_FILE, exclude_players, load_players_csv
from optimizer import EuroLeagueFantasyOptimizer

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
POSITION_ORDER = {"Guard": 0, "Forward": 1, "Center": 2}
REQUIRED = {"Guard": 4, "Forward": 4, "Center": 2}
POS_EMOJI = {"Guard": "🏃", "Forward": "💪", "Center": "🗼"}

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def sort_lineup(lineup):
    """Sort by position (Guard → Forward → Center), then FPT descending."""
    return (
        lineup.assign(_pos=lineup["Position"].map(POSITION_ORDER))
        .sort_values(["_pos", "FPT"], ascending=[True, False])
        .drop(columns="_pos")
    )


@st.cache_data(show_spinner=False)
def load_default_csv():
    """Load and validate the bundled CSV (cached across reruns)."""
    return load_players_csv(DATA_FILE)


@st.cache_data(show_spinner=False)
def load_uploaded_csv(raw_bytes: bytes):
    """Write uploaded bytes to a temp file, then load through the normal pipeline."""
    with tempfile.NamedTemporaryFile(suffix=".csv", delete=False, mode="wb") as f:
        f.write(raw_bytes)
        tmp = f.name
    return load_players_csv(tmp, stale_days=999_999)


LINEUP_COL_CONFIG = {
    "FPT": st.column_config.NumberColumn(format="%.1f"),
    "Quotation": st.column_config.NumberColumn("Cost", format="%.1f"),
    "Value per Credit": st.column_config.NumberColumn("Value / Credit", format="%.2f"),
}
DISPLAY_COLS = ["Full Name", "Position", "Team", "FPT", "Quotation", "Value per Credit"]

# ---------------------------------------------------------------------------
# Page config
# ---------------------------------------------------------------------------
st.set_page_config(page_title="EuroLeague Fantasy Optimizer", page_icon="🏀", layout="wide")

st.title("🏀 EuroLeague Fantasy Optimizer")
st.caption("Build the highest-scoring fantasy lineup that fits your budget.")

# ---------------------------------------------------------------------------
# Sidebar — settings
# ---------------------------------------------------------------------------
with st.sidebar:
    st.header("Settings")

    uploaded = st.file_uploader(
        "Player stats CSV",
        type=["csv"],
        help="Upload a fresh CSV, or leave empty to use the default file.",
    )

    st.divider()

    budget = st.number_input(
        "Budget (credits)",
        min_value=10.0,
        max_value=500.0,
        value=100.0,
        step=0.5,
        help="Total credits you can spend on your lineup.",
    )

    max_per_team = st.slider(
        "Max players per team",
        min_value=1,
        max_value=10,
        value=4,
        help="Limits how many players you can pick from any single club.",
    )

    top_n = st.slider(
        "Number of lineups",
        min_value=1,
        max_value=10,
        value=1,
        help="Generate multiple alternative lineups ranked by total FPT.",
    )

# ---------------------------------------------------------------------------
# Load data
# ---------------------------------------------------------------------------
try:
    with st.spinner("Loading player data…"):
        if uploaded is not None:
            players_raw = load_uploaded_csv(uploaded.getvalue())
        else:
            players_raw = load_default_csv()
except (FileNotFoundError, ValueError) as exc:
    st.error(f"**Could not load data:** {exc}")
    st.stop()

# Sidebar — player exclusion (populated from loaded data)
with st.sidebar:
    st.divider()
    player_names = sorted(players_raw["Full Name"].tolist())
    excluded_names = st.multiselect(
        "Exclude players",
        options=player_names,
        help="Remove specific players before optimizing.",
    )

players = players_raw.copy()
if excluded_names:
    players, _matched, _unmatched = exclude_players(players, excluded_names)

# ---------------------------------------------------------------------------
# Player-pool overview (expandable)
# ---------------------------------------------------------------------------
with st.expander(f"📋 Player pool  —  {len(players)} players", expanded=False):
    cols = st.columns(3)
    for i, (pos, need) in enumerate(REQUIRED.items()):
        count = int((players["Position"] == pos).sum())
        cols[i].metric(f"{POS_EMOJI[pos]}  {pos}s", count, help=f"Need exactly {need}")

    st.dataframe(
        players[["ID", "Full Name", "Position", "Team", "FPT", "Quotation", "Value per Credit"]],
        column_config={
            "ID": st.column_config.NumberColumn(format="%d"),
            **LINEUP_COL_CONFIG,
        },
        width="stretch",
        hide_index=True,
    )

# ---------------------------------------------------------------------------
# Pre-flight validation
# ---------------------------------------------------------------------------
pos_counts = players["Position"].value_counts()
for pos, need in REQUIRED.items():
    if int(pos_counts.get(pos, 0)) < need:
        st.error(f"Not enough **{pos}s** in the pool (need {need}).")
        st.stop()

# ---------------------------------------------------------------------------
# Optimize button
# ---------------------------------------------------------------------------
st.divider()
btn_label = "🚀  Find Optimal Lineup" if top_n == 1 else f"🚀  Find Top {top_n} Lineups"
optimize_clicked = st.button(btn_label, type="primary", width="stretch")

if optimize_clicked:
    # Build optimizer
    try:
        optimizer = EuroLeagueFantasyOptimizer(
            players_df=players, budget=budget, max_per_team=max_per_team,
        )
    except ValueError as exc:
        st.error(str(exc))
        st.stop()

    # Feasibility check
    min_cost = optimizer.min_cost()
    if math.isinf(min_cost):
        st.error(
            "No feasible lineup exists with the current constraints. "
            "Try increasing **Max players per team** or removing some exclusions."
        )
        st.stop()
    if budget + 1e-9 < min_cost:
        st.error(
            f"Budget too low — the cheapest valid lineup costs **{min_cost:.1f}** credits. "
            f"Increase your budget or loosen constraints."
        )
        st.stop()

    # Solve
    with st.spinner("Optimizing…"):
        try:
            lineups = optimizer.solve_top_n(top_n)
        except RuntimeError as exc:
            st.error(f"Optimization failed: {exc}")
            st.stop()

    if len(lineups) < top_n:
        st.info(
            f"Found **{len(lineups)}** of {top_n} requested lineups "
            f"(not enough distinct feasible rosters)."
        )

    # Store in session so results survive sidebar tweaks
    st.session_state["lineups"] = lineups
    st.session_state["solve_budget"] = budget

# ---------------------------------------------------------------------------
# Display results (from session state so they persist across reruns)
# ---------------------------------------------------------------------------
if "lineups" in st.session_state:
    lineups = st.session_state["lineups"]
    solve_budget = st.session_state["solve_budget"]
    best_fpt = lineups[0][1]

    # Use tabs when showing multiple lineups
    if len(lineups) > 1:
        medals = {1: "🥇", 2: "🥈", 3: "🥉"}
        tab_labels = [f"{medals.get(i, '  ')} Lineup {i}" for i in range(1, len(lineups) + 1)]
        containers = st.tabs(tab_labels)
    else:
        containers = [st.container()]

    for rank, ((lineup, total_fpt), container) in enumerate(
        zip(lineups, containers), 1
    ):
        lineup = sort_lineup(lineup)
        total_cost = float(lineup["Quotation"].sum())

        with container:
            if len(lineups) == 1:
                st.subheader("🏆 Optimal Lineup")
            else:
                diff = best_fpt - total_fpt
                if rank > 1:
                    st.caption(f"−{diff:.2f} FPT vs. best")

            # Metric cards
            m1, m2, m3 = st.columns(3)
            m1.metric("Total FPT", f"{total_fpt:.1f}")
            m2.metric("Credits Used", f"{total_cost:.1f} / {solve_budget:.1f}")
            m3.metric("Value", f"{total_fpt / total_cost:.2f} FPT / credit")

            # Lineup table
            st.dataframe(
                lineup[DISPLAY_COLS],
                column_config=LINEUP_COL_CONFIG,
                width="stretch",
                hide_index=True,
            )

    # ---- Download buttons ----
    st.divider()
    frames = []
    for rank, (lineup, _) in enumerate(lineups, 1):
        frame = sort_lineup(lineup).copy()
        frame.insert(0, "Lineup", rank)
        frames.append(frame)
    combined = pd.concat(frames, ignore_index=True)

    dl1, dl2 = st.columns(2)
    with dl1:
        st.download_button(
            "📥  Download CSV",
            data=combined.to_csv(index=False),
            file_name="euroleague_lineup.csv",
            mime="text/csv",
            width="stretch",
        )
    with dl2:
        st.download_button(
            "📥  Download JSON",
            data=combined.to_json(orient="records", indent=2),
            file_name="euroleague_lineup.json",
            mime="application/json",
            width="stretch",
        )
