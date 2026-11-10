# EuroLeague Fantasy Optimizer

A step-by-step guide to installing and running the lineup optimizer.

## 1. Prerequisites

- Python 3.10 or newer (tested on Python 3.12.10)
- `pip`

Check your version:

```powershell
python --version
python -m pip --version
```

## 2. Open the project folder

```powershell
cd "C:\Users\strva\Documents\Euroleague Project"
```

All commands below assume you are in this folder.

## 3. Install dependencies

```powershell
python -m pip install -r requirements.txt
```

If you also want to run the tests, install the dev dependencies instead:

```powershell
python -m pip install -r requirements-dev.txt
```

## 4. Check the data file

The app reads `players_stats.csv` from the project root (or any path passed with `--csv`).

Expected columns:

```
ID, Name, Surname, Active, Position, Team, FPT, Quotation
```

Head-coach rows use the same file and add `Position = Head Coach`, the margin
buckets (`Win 1-10`, `Win 11-20`, `Win 20`, `Win ot`, `Loss 1-10`,
`Loss 11-20`, `Loss 20`, `Loss ot`) and `Plus`.

The player loader automatically:

- Keeps only `Active = 1` and `Position` in `Guard`, `Forward`, `Center`
- Drops footer rows, coaches, and rows with a missing/invalid `ID`
- Drops rows with invalid `FPT` or `Quotation <= 0`
- Warns when the file is older than 14 days

The coach loader keeps only `Active = 1` head coaches, builds their full names,
and requires exactly one coach per team. Coaches are handled separately so the
team and coach selections stay independent.

## 5. Run the web app (Streamlit)

The friendly, point-and-click version lives in `app.py`:

```powershell
streamlit run app.py
```

Streamlit opens `http://localhost:8501` in your browser. Use the **Section**
switch in the sidebar to choose between the **Team optimizer** (budget, per-team
limit, number of lineups, exclusions, downloadable results) and the **Head
coach** matchup tools.

## 6. Run the optimizer (CLI)

### Interactive (prompts for budget)

```powershell
python main.py
```

### With a budget flag

```powershell
python main.py --budget 100
```

### All options

```powershell
python main.py --help
```

| Option | Description | Default |
| --- | --- | --- |
| `-b`, `--budget` | Total credits available | prompts interactively |
| `--csv` | Path to the player CSV | `players_stats.csv` |
| `--max-per-team` | Max players from one club | `4` |
| `--exclude` | Player ID or name to exclude (repeatable) | none |
| `--top-n` | Number of alternative lineups to produce | `1` |
| `--output` | Save lineup(s) to a file (CSV or JSON) | none |
| `--log` | Append a summary row to a history CSV | none |

### Examples

Use a different data file:

```powershell
python main.py --budget 100 --csv "C:\path\to\players_stats.csv"
```

Exclude one or more players by ID or name:

```powershell
python main.py --budget 100 --exclude 9846
python main.py --budget 100 --exclude 9846 "Elijah Bryant" "Theo Maledon"
```

Change the per-team limit:

```powershell
python main.py --budget 100 --max-per-team 3
```

Get three alternative lineups:

```powershell
python main.py --budget 100 --top-n 3
```

Save lineup(s) to a file (CSV or JSON based on extension):

```powershell
python main.py --budget 100 --output lineup.csv
python main.py --budget 100 --top-n 3 --output lineup.json
```

Track results over time with a history log:

```powershell
python main.py --budget 100 --log lineup_history.csv
```

## 7. Head coach selection (Streamlit)

The app has a separate **Head coach** section in the sidebar. Coach credits are
ignored for now; the goal is to pick the coach whose club has the best matchup.

Coach points come from the final margin, using the official scoring table:

| Result | Points |
| --- | --- |
| Win by 20+ | +25 |
| Win by 11-20 | +20 |
| Win by 1-10, or in overtime | +10 |
| Loss by 1-10, or in overtime | -5 |
| Loss by 11-20 | -10 |
| Loss by 20+ | -20 |

The `Win 1-10`-style columns in the CSV are per-game frequencies, not points.
The app turns each team's margin profile into a strength rating and predicts a
margin for the next matchup with a league-wide spread of about 10 points. It
assumes a neutral venue.

Two views are available:

- **Matchup calculator** — choose your coach and the next opponent, then see
  expected points, win probability, blowout-win probability, heavy-loss
  probability and the full outcome breakdown.
- **Rank coaches for an opponent** — choose the opponent and see every
  available coach ranked by predicted points for that matchup.

Overall coach quality is computed as a **round-robin against every other team**
in `coaches.py`, but it is intentionally not shown in the Streamlit UI. You can
access it privately from the command line:

```powershell
python coaches.py quality
python coaches.py matchup "Zeljko Obradovic" OLY
python coaches.py rank KBA
```

## 8. Read the output

```text
==================================================
OPTIMAL LINEUP (Max FPT)
==================================================
          Full Name Position Team  FPT  Quotation  Value per Credit
      Elijah Bryant    Guard  HTA 25.8       17.4          1.482759
      ...
--------------------------------------------------
Total FPT Score    : 178.00
Total Credits Used : 99.4 / 100.0
Lineup value       : 1.79 FPT per credit
```

- `FPT` is the projected fantasy score used by the optimizer.
- `Value per Credit` is `FPT / Quotation`.
- The roster is always exactly **4 Guards, 4 Forwards, 2 Centers**.

## 9. Run the tests

```powershell
python -m pytest -q
```

Expected result:

```text
22 passed
```

## 10. Deploy so friends can use it (Streamlit Community Cloud)

This gives your friends a public URL they can open on any device, for free.

### Step 1 — Push the project to GitHub

The folder is not a git repository yet. Create one and push it:

```powershell
git init
git add .
git commit -m "EuroLeague Fantasy Optimizer"
```

Then create an empty repository on GitHub and connect it (replace the URL):

```powershell
git remote add origin https://github.com/<your-username>/<repo-name>.git
git branch -M main
git push -u origin main
```

`.gitignore` is already set up, so caches, virtualenvs and secrets are excluded.
The bundled `players_stats.csv` **is** committed, because the app needs it.

### Step 2 — Deploy on Streamlit Community Cloud

1. Go to <https://share.streamlit.io> and sign in with GitHub.
2. Click **Create app** → **Deploy a public app from GitHub** (or your own repo).
3. Fill in:
   - **Repository:** `<your-username>/<repo-name>`
   - **Branch:** `main`
   - **Main file path:** `app.py`
4. Open **Advanced settings** → set **Python version** to **3.12** (the pinned
   `numpy`/`scipy` wheels require Python 3.11+).
5. Click **Deploy**. Your app gets a URL like
   `https://<app-name>.streamlit.app` — send that to your friends.

### Updating the player data each week

The app reads `players_stats.csv` from the repo. To refresh it, replace that file
with the new week's data, then commit and push:

```powershell
git add players_stats.csv
git commit -m "Update player stats"
git push
```

Streamlit re-deploys automatically after each push.

> **Notes**
> - Free apps sleep after a period of inactivity; the first visit wakes them up
>   (it may take ~30 seconds).
> - Friends can also upload their own CSV in the sidebar, so they can use a fresh
>   file without you pushing anything.
> - Never put API keys or passwords in the repo. Use Streamlit "Secrets" instead
>   (`.streamlit/secrets.toml` is gitignored); this app does not need any.

## 11. Troubleshooting

**`Could not find players_stats.csv`**
Make sure the CSV is in the project folder, or pass its full path with `--csv`.

**`budget too low. Minimum feasible cost is X credits`**
The cheapest valid 10-player roster costs more than your budget. Increase `--budget` or loosen `--max-per-team`.

**`not enough Guards/Forwards/Centers available`**
The data file has too few active players at that position (after exclusions). Check the file or remove some `--exclude` filters.

**`no feasible lineup exists with the current pool and constraints`**
The position and per-team constraints cannot be satisfied together. Try a larger `--max-per-team`.

**`Warning: ... is N days old`**
The CSV is older than 14 days. Download fresh data so prices and FPT reflect the current week.

**`Warning: --exclude 'X' matched no players`**
The ID or name did not match anyone. Check spelling or use the numeric player ID.
