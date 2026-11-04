# Intervals.icu data

- **Committed dumps:** `exports/YYYY-MM-DD/` + mirror `exports/latest/` — maximal CSV (wellness, activities, events, laps).
- **Refresh:** `python3 scripts/export_intervals_maximal.py` (needs `INTERVALS_API` / `INTERVALS_API_KEY`).
- **Schema / ranges:** `exports/README.md` and `exports/latest/README.md`.
- **Quick fetch (not committed):** `scripts/fetch_intervals_activities.py`, `scripts/fetch_intervals_wellness.py` → `pack-*.csv` (gitignored).
- **TB-Score:** `scripts/compute_readiness.py` — `docs/athlete/readiness-totalbelastning.md`
- **Plan-push:** `docs/trainingpeaks/intervals-push-verified.md`
- Never commit API keys.
