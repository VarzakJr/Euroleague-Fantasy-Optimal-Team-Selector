import math

import numpy as np
import pandas as pd
from scipy.optimize import LinearConstraint, milp


class EuroLeagueFantasyOptimizer:
    def __init__(self, players_df: pd.DataFrame, budget=100.0, max_per_team=4):
        """
        Args:
            players_df: DataFrame with columns [ID, Full Name, Position, Team, FPT, Quotation]
                        Positions must be 'Guard', 'Forward', 'Center'
            budget: Total credits available (Quotation cap, default 100)
            max_per_team: Max players from the same club (default 4)

        Uses scipy.optimize.milp (bundled HiGHS solver).
        """
        if budget <= 0:
            raise ValueError("Budget must be positive.")
        if max_per_team < 1:
            raise ValueError("max_per_team must be at least 1.")

        self.players = players_df.copy().reset_index(drop=True)
        self.budget = budget
        self.max_per_team = max_per_team

        # Roster requirements: exactly 4 Guards, 4 Forwards, 2 Centers (10 total)
        self.roster_reqs = {
            'Guard': 4,
            'Forward': 4,
            'Center': 2
        }

    def _build_constraints(self, include_budget=True):
        n = len(self.players)
        quotation = self.players['Quotation'].to_numpy(dtype=float)
        positions = self.players['Position'].to_numpy()
        teams = self.players['Team'].to_numpy()

        A_rows, lbs, ubs = [], [], []

        if include_budget:
            A_rows.append(quotation)
            lbs.append(-np.inf)
            ubs.append(self.budget)

        for pos, count in self.roster_reqs.items():
            A_rows.append((positions == pos).astype(float))
            lbs.append(count)
            ubs.append(count)

        for team in np.unique(teams):
            A_rows.append((teams == team).astype(float))
            lbs.append(-np.inf)
            ubs.append(self.max_per_team)

        return np.vstack(A_rows), np.array(lbs), np.array(ubs)

    def _solve(self, c, include_budget=True, no_good_cuts=None):
        n = len(self.players)
        A, lb, ub = self._build_constraints(include_budget=include_budget)

        if no_good_cuts:
            roster_size = sum(self.roster_reqs.values())
            cut_A = np.vstack(no_good_cuts)
            A = np.vstack([A, cut_A])
            lb = np.concatenate([lb, np.full(len(no_good_cuts), -np.inf)])
            ub = np.concatenate([ub, np.full(len(no_good_cuts), roster_size - 1)])

        constraint = LinearConstraint(A, lb=lb, ub=ub)
        return milp(
            c=c,
            constraints=constraint,
            integrality=np.ones(n),
            bounds=(0, 1)
        )

    def min_cost(self):
        """
        Returns the minimum achievable cost for a valid roster (ignoring the
        budget cap), or math.inf if no roster satisfies the constraints.
        """
        quotation = self.players['Quotation'].to_numpy(dtype=float)
        result = self._solve(quotation, include_budget=False)
        if not result.success:
            return math.inf
        return float(result.fun)

    def solve(self):
        """
        Solves the optimization problem.
        Returns: (lineup_df, total_fpt)
        """
        fpt = self.players['FPT'].to_numpy(dtype=float)

        # Objective: maximize total FPT  ->  minimize -FPT (milp minimizes)
        result = self._solve(-fpt, include_budget=True)

        if not result.success:
            raise RuntimeError(
                f"Optimization failed: {result.message}. "
                "Try a larger --budget or a looser --max-per-team."
            )

        selected = np.where(result.x > 0.5)[0]
        lineup_df = self.players.iloc[selected].copy()
        total_fpt = float(lineup_df['FPT'].sum())

        return lineup_df, total_fpt

    def solve_top_n(self, n=1):
        """
        Return up to *n* distinct lineups, best first, using no-good cuts.

        Each iteration re-solves after forbidding every previously found
        roster.  Returns a list of ``(lineup_df, total_fpt)`` tuples.  The
        list may be shorter than *n* if fewer feasible lineups exist.
        """
        fpt = self.players['FPT'].to_numpy(dtype=float)
        results = []
        no_good_cuts = []

        for _ in range(n):
            result = self._solve(-fpt, include_budget=True,
                                 no_good_cuts=no_good_cuts or None)
            if not result.success:
                break

            selected = np.where(result.x > 0.5)[0]
            lineup_df = self.players.iloc[selected].copy()
            total_fpt = float(lineup_df['FPT'].sum())
            results.append((lineup_df, total_fpt))

            # Forbid this exact roster in subsequent solves.
            cut = np.zeros(len(self.players))
            cut[selected] = 1.0
            no_good_cuts.append(cut)

        if not results:
            raise RuntimeError(
                "Optimization failed. "
                "Try a larger --budget or a looser --max-per-team."
            )

        return results
