# EuroLeague Fantasy — Future Roadmap

Modeling ideas for evolving the optimizer from a **momentum strategy** (pick last week's best scorers within budget) to one that optimizes *predicted* outcomes under uncertainty. Ordered roughly by impact.

---

## 1. Add a forecasting layer (the biggest lever)

The optimizer is only as good as its inputs. Instead of using raw FPT, predict **next week's** FPT per player:

- **Baseline first**: `expected = α·player_last_week + (1−α)·season_avg` — surprisingly hard to beat
- **Then regression / gradient boosting** with features like:
  - Form trend (exponentially weighted last 5–8 games, not just last week)
  - Minutes per game trend (rising = rotation upgrade → upside)
  - Opponent strength (see #4)
  - Rest days since last game / back-to-back flag
  - Injury history & return-from-injury pattern (first game back is usually a discount)
- **Validate weekly**: track MAE out-of-sample. If your model can't beat "last week's FPT" as a predictor, no fancy optimizer will save you — this tells you where the real edge lives.

## 2. Predict distributions, not point estimates

Once you have a forecaster, upgrade it to output **mean + variance** (quantile regression, or Bayesian model). This unlocks everything below and directly addresses variable budgets: a cheap player with high variance is a different animal than an expensive stable one.

## 3. Risk-aware objectives (builds directly on the existing MILP)

With per-player distributions, replace `max Σ FPT` with:

- **Mean–variance**: `max E[FPT] − λ·σ²(lineup)` — expose a "safe / balanced / aggressive" mode via λ
- **CVaR** (more robust than variance, handles the left tail from injuries): maximize expected score of your worst 10% of scenarios
- **Chance constraints**: `P(total FPT ≥ target) ≥ 90%`

The cleanest implementation is a **scenario-based MILP**: sample ~200–500 scenarios from player distributions, add one variable per (player, scenario), and optimize the CVaR formulation. Same structure as the current model — just bigger. `scipy.optimize.milp` handles it fine at this scale.

## 4. Matchup & schedule modeling

EuroLeague has a public schedule, so this is very tractable:

- **Team ratings** (Elo or simple win/loss-adjusted rating) → adjust each player's expected output by opponent strength
- **Fatigue factors**: back-to-backs, 4-games-in-9-days streaks → small multiplicative discount
- **Matchup-specific features** if detailed box scores can be scraped: e.g., guards vs. weak perimeter defenses, centers vs. weak rim protection

This is where a "cheap player facing the league's worst defense" edge comes from — pure price/FPT models miss it entirely.

## 5. Model the market (Quotation as implied expectation)

Quotations are essentially the platform's *implied forecast*. That reframes the whole problem:

- **Alpha = your predicted FPT − market-implied expectation**
- Track `value per credit` over time and look for systematic mispricings: e.g., prices that don't drop fast enough after a slump, or players whose price lags a rotation upgrade
- This turns the optimizer from "pick best value" into "exploit where *your* model disagrees with *theirs*" — which is the only durable edge in these games

## 6. Multi-period / portfolio view (fits variable budgets)

Since the budget changes week to week, think of the **season as a portfolio**, not isolated weeks:

- Track cumulative expected points and variance across weeks; occasionally it's optimal to *underperform* one week to preserve flexibility
- If transfers exist: this becomes a genuine multi-stage stochastic program (or at least a rollout heuristic) — but even without transfers, a "diversify risk over time" constraint is easy to add
- Season-long objective: maximize expected total points subject to weekly budget paths

## 7. Backtesting infrastructure (what makes it real)

None of the above is trustworthy without this:

- **Walk-forward test**: for each past week, predict → optimize → compare against baselines (top-FPT lineup, random picks, median player pool)
- Metrics that matter: win rate vs. field median, **points per credit** (ROI), and consistency (variance of weekly results)
- Ablate features to see what actually adds value — a simple rest-day flag can contribute more than expected

---

## Suggested path

1. **Historical data pipeline first** (per-game box scores + price snapshots in SQLite/Parquet) — everything else depends on it, and without historical *prices* you can't backtest #5
2. **Forecaster (#1)** with weekly validation
3. **Scenario-based CVaR optimizer (#3)** — reuses the existing MILP structure
4. **Backtesting loop (#7)** to prove it beats momentum

---

## Quick wins (from earlier discussion, still pending)

- ~~CLI arguments via `argparse` (`--budget`, `--csv`, `--max-per-team`, `--exclude`)~~ ✅
- ~~Feasibility pre-check with a clear error when budget is below the minimum possible cost~~ ✅
- ~~Injury/exclusion support (`--exclude 1234 "John Smith"`)~~ ✅
- ~~Log results to CSV/JSON for season-long tracking~~ ✅ (`--output`, `--log`)
- ~~Top-N alternative lineups (re-solve with a no-good cut)~~ ✅ (`--top-n`)
- ~~Head-coach selection: separate app section, next-opponent matchup predictor and backend round-robin quality metrics~~ — (`coaches.py`)
- Budget sensitivity curve (FPT vs. budget, find the kinks)
- Pin dependencies in `requirements.txt` (`pandas`, `numpy`, `scipy>=1.9`) — pulp is no longer used
- ~~Small pytest suite for constraint logic~~ ✅
- ~~Data validation in `fetcher.py` (duplicate IDs, non-positive Quotation, stale file check) + a "value per credit" column in output~~ ✅
