import math

import pandas as pd
import pytest

from optimizer import EuroLeagueFantasyOptimizer


def make_players(quotation=10.0, team="A"):
    rows = []
    player_id = 1
    for position, count in (("Guard", 6), ("Forward", 6), ("Center", 4)):
        for i in range(count):
            rows.append(
                {
                    "ID": player_id,
                    "Full Name": f"{position} {i}",
                    "Position": position,
                    "Team": team,
                    "FPT": 10.0 + i,
                    "Quotation": quotation,
                }
            )
            player_id += 1
    return pd.DataFrame(rows)


def test_selects_required_positions_within_budget():
    players = make_players(quotation=4.0)
    players["Team"] = [f"T{i}" for i in range(len(players))]
    optimizer = EuroLeagueFantasyOptimizer(players, budget=40.0, max_per_team=4)

    lineup, total_fpt = optimizer.solve()

    assert len(lineup) == 10
    assert lineup["Position"].value_counts().to_dict() == {
        "Guard": 4,
        "Forward": 4,
        "Center": 2,
    }
    assert lineup["Quotation"].sum() <= 40.0 + 1e-9
    assert total_fpt == pytest.approx(lineup["FPT"].sum())


def test_respects_max_per_team():
    high = make_players(quotation=5.0, team="A")
    low_b = make_players(quotation=5.0, team="B")
    low_c = make_players(quotation=5.0, team="C")
    low_b["ID"] += 100
    low_c["ID"] += 200
    players = pd.concat([high, low_b, low_c], ignore_index=True)
    players.loc[players["Team"] == "A", "FPT"] += 100

    optimizer = EuroLeagueFantasyOptimizer(players, budget=1000.0, max_per_team=4)
    lineup, _ = optimizer.solve()

    assert (lineup["Team"] == "A").sum() == 4
    assert lineup["Team"].value_counts().max() <= 4


def test_min_cost_and_low_budget_failure():
    players = make_players(quotation=10.0)
    players["Team"] = [f"T{i}" for i in range(len(players))]
    optimizer = EuroLeagueFantasyOptimizer(players, budget=50.0, max_per_team=4)

    assert optimizer.min_cost() == pytest.approx(100.0)
    with pytest.raises(RuntimeError):
        optimizer.solve()


def test_min_cost_infinite_when_roster_infeasible():
    players = make_players(quotation=10.0, team="A")
    optimizer = EuroLeagueFantasyOptimizer(players, budget=1000.0, max_per_team=4)

    assert math.isinf(optimizer.min_cost())


def test_rejects_nonpositive_budget():
    players = make_players()
    with pytest.raises(ValueError):
        EuroLeagueFantasyOptimizer(players, budget=0)


def test_solve_top_n_returns_distinct_lineups():
    players = make_players(quotation=4.0)
    players["Team"] = [f"T{i}" for i in range(len(players))]
    optimizer = EuroLeagueFantasyOptimizer(players, budget=100.0, max_per_team=4)

    results = optimizer.solve_top_n(3)

    assert len(results) >= 2
    for lineup, total_fpt in results:
        assert len(lineup) == 10
        assert lineup["Position"].value_counts().to_dict() == {
            "Guard": 4, "Forward": 4, "Center": 2,
        }
        assert total_fpt == pytest.approx(lineup["FPT"].sum())

    # Best first (FPT non-increasing)
    fpts = [fpt for _, fpt in results]
    assert fpts == sorted(fpts, reverse=True)

    # All lineups are distinct
    id_sets = [frozenset(lineup["ID"]) for lineup, _ in results]
    assert len(set(id_sets)) == len(id_sets)


def test_solve_top_n_one_matches_solve():
    players = make_players(quotation=4.0)
    players["Team"] = [f"T{i}" for i in range(len(players))]
    optimizer = EuroLeagueFantasyOptimizer(players, budget=40.0, max_per_team=4)

    _single_lineup, single_fpt = optimizer.solve()
    top_results = optimizer.solve_top_n(1)

    assert len(top_results) == 1
    assert top_results[0][1] == pytest.approx(single_fpt)
