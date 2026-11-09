import pandas as pd
import pytest

from fetcher import exclude_players, load_players_csv


COLUMNS = ["ID", "Name", "Surname", "Active", "Position", "Team", "FPT", "Quotation"]


def write_csv(tmp_path, rows):
    path = tmp_path / "players.csv"
    pd.DataFrame(rows, columns=COLUMNS).to_csv(path, index=False)
    return path


def test_load_cleans_rows_and_adds_value_per_credit(tmp_path):
    path = write_csv(
        tmp_path,
        [
            {"ID": 1, "Name": "Alice", "Surname": "Smith", "Active": 1,
             "Position": "guard", "Team": " AAA ", "FPT": 20, "Quotation": 10},
            {"ID": 2, "Name": "Bob", "Surname": "Jones", "Active": 1,
             "Position": "Center", "Team": "BBB", "FPT": 8, "Quotation": 4},
            {"ID": "-", "Name": "Coach", "Surname": "One", "Active": 1,
             "Position": "Head Coach", "Team": "CCC", "FPT": 5, "Quotation": 5},
            {"ID": "-", "Name": "Zero", "Surname": "Minutes", "Active": 1,
             "Position": "Guard", "Team": "DDD", "FPT": 0, "Quotation": 4},
            {"ID": 3, "Name": "Zero", "Surname": "Price", "Active": 1,
             "Position": "Forward", "Team": "EEE", "FPT": 5, "Quotation": 0},
            {"ID": 4, "Name": "Inactive", "Surname": "Guy", "Active": 0,
             "Position": "Guard", "Team": "FFF", "FPT": 5, "Quotation": 5},
            dict.fromkeys(COLUMNS),
        ],
    )

    players = load_players_csv(path)

    assert list(players.columns) == [
        "ID", "Full Name", "Position", "Team", "FPT", "Quotation", "Value per Credit"
    ]
    assert set(players["ID"]) == {1, 2}
    assert set(players["Full Name"]) == {"Alice Smith", "Bob Jones"}
    assert set(players["Position"]) == {"Guard", "Center"}
    assert players.loc[players["ID"] == 1, "Team"].iloc[0] == "AAA"
    value = players.loc[players["ID"] == 1, "Value per Credit"].iloc[0]
    assert value == pytest.approx(2.0)


def test_duplicate_ids_raise(tmp_path):
    path = write_csv(
        tmp_path,
        [
            {"ID": 1, "Name": "Alice", "Surname": "Smith", "Active": 1,
             "Position": "Guard", "Team": "AAA", "FPT": 10, "Quotation": 5},
            {"ID": 1, "Name": "Bob", "Surname": "Jones", "Active": 1,
             "Position": "Center", "Team": "BBB", "FPT": 10, "Quotation": 5},
        ],
    )

    with pytest.raises(ValueError, match="Duplicate player IDs"):
        load_players_csv(path)


def test_missing_file_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_players_csv(tmp_path / "missing.csv")


def test_exclude_matches_ids_and_names():
    players = pd.DataFrame(
        [
            {"ID": 1, "Full Name": "Alice Smith", "Position": "Guard",
             "Team": "AAA", "FPT": 10.0, "Quotation": 5.0},
            {"ID": 2, "Full Name": "Bob Jones", "Position": "Center",
             "Team": "BBB", "FPT": 10.0, "Quotation": 5.0},
        ]
    )

    filtered, matched, unmatched = exclude_players(players, ["2", "alice", "nobody"])

    assert filtered.empty
    assert matched == ["2", "alice"]
    assert unmatched == ["nobody"]
