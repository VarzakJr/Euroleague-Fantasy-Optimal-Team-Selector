import pandas as pd
import pytest

from coaches import COACH_BUCKETS, COACH_POINTS, CoachSelector
from fetcher import COACH_POSITION, load_coaches_csv

COLUMNS = [
    "ID", "Name", "Surname", "Active", "Position", "Team", "FPT", "Quotation", "Plus",
    *COACH_BUCKETS,
]


def make_coach(full_name, team, fpt, buckets):
    row = {
        "Full Name": full_name,
        "Team": team,
        "FPT": fpt,
        "Quotation": 5.0,
        "Plus": 0.0,
    }
    row.update(dict(zip(COACH_BUCKETS, buckets)))
    return row


def make_coaches():
    return pd.DataFrame(
        [
            make_coach(
                "Alpha Coach", "AAA", 12.0,
                [0.5, 0.3, 0.1, 0.0, 0.1, 0.0, 0.0, 0.0],
            ),
            make_coach(
                "Bravo Coach", "BBB", 4.0,
                [0.3, 0.1, 0.0, 0.0, 0.4, 0.1, 0.1, 0.0],
            ),
            make_coach(
                "Charlie Coach", "CCC", -4.0,
                [0.1, 0.0, 0.0, 0.0, 0.5, 0.2, 0.2, 0.0],
            ),
        ]
    )


def write_csv(tmp_path, rows):
    path = tmp_path / "stats.csv"
    pd.DataFrame(rows, columns=COLUMNS).to_csv(path, index=False)
    return path


def coach_row(name, surname, active, team, buckets):
    row = {c: "" for c in COLUMNS}
    row.update(
        {
            "ID": "-",
            "Name": name,
            "Surname": surname,
            "Active": active,
            "Position": COACH_POSITION,
            "Team": team,
            "FPT": 5.0,
            "Quotation": 5.0,
            "Plus": 0.0,
        }
    )
    row.update(dict(zip(COACH_BUCKETS, buckets)))
    return row


def test_load_coaches_keeps_only_active_coaches(tmp_path):
    path = write_csv(
        tmp_path,
        [
            coach_row(
                "Alpha", "Coach", 1, "AAA",
                [0.5, 0.3, 0.1, 0.0, 0.1, 0.0, 0.0, 0.0],
            ),
            coach_row(
                "Inactive", "Coach", 0, "BBB",
                [0.2, 0.2, 0.2, 0.0, 0.2, 0.2, 0.0, 0.0],
            ),
        ],
    )

    coaches = load_coaches_csv(path)

    assert len(coaches) == 1
    assert coaches.loc[0, "Full Name"] == "Alpha Coach"
    assert coaches.loc[0, "Team"] == "AAA"
    assert list(coaches.columns) == [
        "Full Name", "Team", "FPT", "Quotation", "Plus", *COACH_BUCKETS
    ]


def test_load_coaches_missing_bucket_raises(tmp_path):
    path = tmp_path / "stats.csv"
    pd.DataFrame([coach_row("Alpha", "Coach", 1, "AAA", [0] * 8)]).drop(
        columns=["Win 20"]
    ).to_csv(path, index=False)

    with pytest.raises(ValueError, match="Missing expected coach columns"):
        load_coaches_csv(path)


def test_load_coaches_duplicate_team_raises(tmp_path):
    path = write_csv(
        tmp_path,
        [
            coach_row(
                "Alpha", "Coach", 1, "AAA",
                [0.5, 0.3, 0.1, 0.0, 0.1, 0.0, 0.0, 0.0],
            ),
            coach_row(
                "Other", "Coach", 1, "AAA",
                [0.2, 0.2, 0.2, 0.0, 0.2, 0.2, 0.0, 0.0],
            ),
        ],
    )

    with pytest.raises(ValueError, match="Multiple head coaches"):
        load_coaches_csv(path)


def test_official_scoring_table():
    assert COACH_POINTS == {
        "Win 1-10": 10.0,
        "Win 11-20": 20.0,
        "Win 20": 25.0,
        "Win ot": 10.0,
        "Loss 1-10": -5.0,
        "Loss 11-20": -10.0,
        "Loss 20": -20.0,
        "Loss ot": -5.0,
    }


def test_prediction_probabilities_and_expected_points():
    selector = CoachSelector(make_coaches())

    prediction = selector.predict("AAA", "BBB")
    outcomes = prediction["outcomes"]

    assert outcomes["Probability"].sum() == pytest.approx(1.0)
    assert prediction["expected_points"] == pytest.approx(
        (outcomes["Probability"] * outcomes["Points"]).sum()
    )
    assert prediction["win_probability"] == pytest.approx(
        outcomes.loc[outcomes["Result"].str.startswith("Win"), "Probability"].sum()
    )


def test_win_probability_is_complementary():
    selector = CoachSelector(make_coaches())

    forward = selector.predict("AAA", "BBB")["win_probability"]
    reverse = selector.predict("BBB", "AAA")["win_probability"]

    assert forward + reverse == pytest.approx(1.0, abs=1e-9)


def test_stronger_team_scores_more():
    selector = CoachSelector(make_coaches())

    strong = selector.predict("AAA", "CCC")["expected_points"]
    weak = selector.predict("CCC", "AAA")["expected_points"]

    assert strong > weak


def test_coach_cannot_face_own_team():
    selector = CoachSelector(make_coaches())

    with pytest.raises(ValueError, match="own team"):
        selector.predict("AAA", "AAA")


def test_unknown_coach_raises():
    selector = CoachSelector(make_coaches())

    with pytest.raises(ValueError, match="Unknown coach or team"):
        selector.predict("Nobody", "AAA")


def test_rank_vs_opponent_excludes_opponent_and_sorts():
    selector = CoachSelector(make_coaches())

    table = selector.rank_vs_opponent("BBB")

    assert "BBB" not in set(table["Team"])
    assert len(table) == 2
    assert table["Expected Points"].tolist() == sorted(
        table["Expected Points"].tolist(), reverse=True
    )


def test_round_robin_quality_shape_and_sort():
    selector = CoachSelector(make_coaches())

    table = selector.round_robin_quality()

    assert len(table) == 3
    assert table["PVP Expected Points"].tolist() == sorted(
        table["PVP Expected Points"].tolist(), reverse=True
    )
    assert (table["PVP Win %"] >= 0).all()
    assert (table["PVP Win %"] <= 100).all()
