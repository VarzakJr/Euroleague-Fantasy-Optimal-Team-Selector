"""
Head-coach scoring and matchup model for the EuroLeague Fantasy Optimizer.

Coach fantasy points are awarded on the margin of the club's result, so a
coach's scoring is heavily driven by the quality of the opponent.  This module
turns each team's historical margin profile into a strength rating and uses it
to predict coach points for a specific next opponent.

Overall coach quality (a round-robin against every other team) is intentionally
kept out of the Streamlit UI; use it from this module or the CLI:

    python coaches.py quality
    python coaches.py matchup "Zeljko Obradovic" OLY
    python coaches.py rank OLY
"""

import argparse
import sys

import numpy as np
import pandas as pd
from scipy.stats import norm

from fetcher import COACH_BUCKETS, DATA_FILE, load_coaches_csv

COACH_POINTS = {
    "Win 1-10": 10.0,
    "Win 11-20": 20.0,
    "Win 20": 25.0,
    "Win ot": 10.0,
    "Loss 1-10": -5.0,
    "Loss 11-20": -10.0,
    "Loss 20": -20.0,
    "Loss ot": -5.0,
}

COACH_MIDPOINTS = {
    "Win 1-10": 5.5,
    "Win 11-20": 15.5,
    "Win 20": 24.5,
    "Win ot": 1.0,
    "Loss 1-10": -5.5,
    "Loss 11-20": -15.5,
    "Loss 20": -24.5,
    "Loss ot": -1.0,
}

DEFAULT_SIGMA = 10.0

_MODEL_BUCKETS = [
    "Win 1-10",
    "Win 11-20",
    "Win 20",
    "Loss 1-10",
    "Loss 11-20",
    "Loss 20",
]
_MODEL_POINTS = np.array([COACH_POINTS[b] for b in _MODEL_BUCKETS], dtype=float)


class CoachSelector:
    """Predict coach points for matchups and build a round-robin quality view."""

    def __init__(self, coaches_df, league_sigma=None):
        required = ["Full Name", "Team", "FPT", "Quotation", *COACH_BUCKETS]
        missing = [c for c in required if c not in coaches_df.columns]
        if missing:
            raise ValueError(f"Missing expected coach columns: {missing}")

        self.coaches = coaches_df.copy().reset_index(drop=True)
        if self.coaches.empty:
            raise ValueError("No coaches available for selection.")

        probs = self.coaches[COACH_BUCKETS].to_numpy(dtype=float)
        row_sums = probs.sum(axis=1)
        if np.any(row_sums <= 0):
            bad = self.coaches.loc[row_sums <= 0, "Team"].tolist()
            raise ValueError(f"Coach margin buckets sum to zero for team(s): {bad}")
        probs = probs / row_sums[:, None]

        midpoints = np.array([COACH_MIDPOINTS[b] for b in COACH_BUCKETS], dtype=float)
        quality = probs @ midpoints

        self._teams = self.coaches["Team"].tolist()
        self._quality_by_team = dict(zip(self._teams, quality))
        self._probs_by_team = {team: probs[i] for i, team in enumerate(self._teams)}
        self._rows_by_team = {
            row["Team"]: row for _, row in self.coaches.iterrows()
        }

        if league_sigma is None:
            variance = np.clip((probs @ (midpoints ** 2)) - quality ** 2, 0, None)
            self.sigma = float(np.sqrt(variance.mean())) if len(variance) else DEFAULT_SIGMA
            if not np.isfinite(self.sigma) or self.sigma <= 0:
                self.sigma = DEFAULT_SIGMA
        else:
            if league_sigma <= 0:
                raise ValueError("league_sigma must be positive.")
            self.sigma = float(league_sigma)

    @property
    def teams(self):
        return list(self._teams)

    @property
    def quality(self):
        return dict(self._quality_by_team)

    def _resolve_team(self, value):
        if value in self._quality_by_team:
            return value

        text = str(value).strip()
        lowered = text.lower()

        team_matches = [t for t in self._teams if t.lower() == lowered]
        if len(team_matches) == 1:
            return team_matches[0]

        name_matches = [
            row["Team"]
            for _, row in self.coaches.iterrows()
            if row["Full Name"].lower() == lowered
        ]
        if len(name_matches) == 1:
            return name_matches[0]

        partial = [
            row["Team"]
            for _, row in self.coaches.iterrows()
            if lowered in row["Full Name"].lower()
        ]
        if len(partial) == 1:
            return partial[0]
        if len(partial) > 1:
            names = [
                f"{self._rows_by_team[t]['Full Name']} ({t})" for t in partial
            ]
            raise ValueError(f"'{value}' is ambiguous; matches: {', '.join(names)}")

        raise ValueError(f"Unknown coach or team: '{value}'")

    def _bucket_probabilities(self, margin_mean):
        """Bucket probabilities for a Normal margin. OT is folded into 1-10."""
        mu, sigma = margin_mean, self.sigma
        cdf = lambda x: norm.cdf(x, mu, sigma)
        tie_band = cdf(0.5) - cdf(-0.5)

        return np.array(
            [
                cdf(10.5) - cdf(0.5) + 0.5 * tie_band,
                cdf(19.5) - cdf(10.5),
                1.0 - cdf(19.5),
                cdf(-0.5) - cdf(-10.5) + 0.5 * tie_band,
                cdf(-10.5) - cdf(-19.5),
                cdf(-19.5),
            ],
            dtype=float,
        )

    def predict(self, coach, opponent, home_advantage=0.0):
        coach_team = self._resolve_team(coach)
        opponent_team = self._resolve_team(opponent)
        if coach_team == opponent_team:
            raise ValueError("A coach cannot face their own team.")

        margin_mean = (
            self._quality_by_team[coach_team]
            - self._quality_by_team[opponent_team]
            + home_advantage
        )
        probabilities = self._bucket_probabilities(margin_mean)
        contributions = probabilities * _MODEL_POINTS

        outcomes = pd.DataFrame(
            {
                "Result": _MODEL_BUCKETS,
                "Probability": probabilities,
                "Points": _MODEL_POINTS,
                "Contribution": contributions,
            }
        )

        return {
            "coach": self._rows_by_team[coach_team]["Full Name"],
            "team": coach_team,
            "opponent_team": opponent_team,
            "opponent_coach": self._rows_by_team[opponent_team]["Full Name"],
            "margin_mean": float(margin_mean),
            "sigma": float(self.sigma),
            "expected_points": float(contributions.sum()),
            "win_probability": float(probabilities[:3].sum()),
            "blowout_win_probability": float(probabilities[2]),
            "heavy_loss_probability": float(probabilities[5]),
            "outcomes": outcomes,
        }

    def rank_vs_opponent(self, opponent, home_advantage=0.0):
        opponent_team = self._resolve_team(opponent)
        rows = []
        for team in self._teams:
            if team == opponent_team:
                continue
            prediction = self.predict(team, opponent_team, home_advantage)
            row = self._rows_by_team[team]
            rows.append(
                {
                    "Coach": row["Full Name"],
                    "Team": team,
                    "Quotation": float(row["Quotation"]),
                    "Season FPT": float(row["FPT"]),
                    "Expected Points": prediction["expected_points"],
                    "Win %": prediction["win_probability"] * 100.0,
                    "P(+20 Win)": prediction["blowout_win_probability"] * 100.0,
                    "P(-20 Loss)": prediction["heavy_loss_probability"] * 100.0,
                }
            )

        return (
            pd.DataFrame(rows)
            .sort_values("Expected Points", ascending=False)
            .reset_index(drop=True)
        )

    def round_robin_quality(self):
        rows = []
        for team in self._teams:
            expected, wins, blowouts, heavy_losses = [], [], [], []
            for opponent in self._teams:
                if opponent == team:
                    continue
                prediction = self.predict(team, opponent)
                expected.append(prediction["expected_points"])
                wins.append(prediction["win_probability"])
                blowouts.append(prediction["blowout_win_probability"])
                heavy_losses.append(prediction["heavy_loss_probability"])

            row = self._rows_by_team[team]
            rows.append(
                {
                    "Coach": row["Full Name"],
                    "Team": team,
                    "Quality (margin)": float(self._quality_by_team[team]),
                    "PVP Expected Points": float(np.mean(expected)),
                    "PVP Win %": float(np.mean(wins)) * 100.0,
                    "PVP Blowout Win %": float(np.mean(blowouts)) * 100.0,
                    "PVP Heavy Loss %": float(np.mean(heavy_losses)) * 100.0,
                    "Season FPT": float(row["FPT"]),
                }
            )

        return (
            pd.DataFrame(rows)
            .sort_values("PVP Expected Points", ascending=False)
            .reset_index(drop=True)
        )


def _build_parser():
    parser = argparse.ArgumentParser(
        description="Head-coach matchup predictor and overall-quality report."
    )
    parser.add_argument(
        "--csv", default=DATA_FILE, help=f"Path to the stats CSV (default: {DATA_FILE})."
    )
    parser.add_argument(
        "--sigma", type=float, default=None,
        help="Override the league margin standard deviation.",
    )

    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("quality", help="Print the round-robin overall coach quality table.")

    matchup = sub.add_parser("matchup", help="Predict a coach's points vs an opponent.")
    matchup.add_argument("coach", help="Coach name or team abbreviation.")
    matchup.add_argument("opponent", help="Opponent team abbreviation or coach name.")
    matchup.add_argument(
        "--home-advantage", type=float, default=0.0,
        help="Margin adjustment for the coach's team (default 0).",
    )

    rank = sub.add_parser("rank", help="Rank all coaches against one opponent.")
    rank.add_argument("opponent", help="Opponent team abbreviation or coach name.")
    rank.add_argument(
        "--home-advantage", type=float, default=0.0,
        help="Margin adjustment for every candidate coach (default 0).",
    )
    return parser


def main(argv=None):
    args = _build_parser().parse_args(argv)

    try:
        coaches = load_coaches_csv(args.csv)
        selector = CoachSelector(coaches, league_sigma=args.sigma)
    except (FileNotFoundError, ValueError) as exc:
        print(f"Error: {exc}")
        return 1

    if args.command == "quality":
        table = selector.round_robin_quality()
        print(f"League margin sigma: {selector.sigma:.2f}")
        print(table.to_string(index=False, float_format=lambda x: f"{x:.2f}"))
        return 0

    if args.command == "matchup":
        try:
            prediction = selector.predict(
                args.coach, args.opponent, home_advantage=args.home_advantage
            )
        except ValueError as exc:
            print(f"Error: {exc}")
            return 1

        print(
            f"{prediction['coach']} ({prediction['team']}) vs "
            f"{prediction['opponent_coach']} ({prediction['opponent_team']})"
        )
        print(f"Expected margin : {prediction['margin_mean']:+.2f}")
        print(f"Expected points : {prediction['expected_points']:.2f}")
        print(f"Win probability : {prediction['win_probability'] * 100:.1f}%")
        print(
            "Blowout win     : "
            f"{prediction['blowout_win_probability'] * 100:.1f}%"
        )
        print(
            "Heavy loss      : "
            f"{prediction['heavy_loss_probability'] * 100:.1f}%"
        )
        print()
        print(
            prediction["outcomes"].to_string(
                index=False, float_format=lambda x: f"{x:.3f}"
            )
        )
        return 0

    if args.command == "rank":
        try:
            table = selector.rank_vs_opponent(
                args.opponent, home_advantage=args.home_advantage
            )
        except ValueError as exc:
            print(f"Error: {exc}")
            return 1

        print(f"Coaches ranked against {args.opponent}:")
        print(table.to_string(index=False, float_format=lambda x: f"{x:.2f}"))
        return 0

    return 1


if __name__ == "__main__":
    sys.exit(main())
