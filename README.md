# Xtri training coach (Cursor agent)

A **knowledge + workflow repo** for talking to a Cursor agent about cycling and triathlon training: building workouts, planning blocks, preparing TrainingPeaks imports, and analyzing exported training data.

The “agent” is **Cursor itself**, guided by `AGENTS.md` and `.cursor/rules/`. You chat in the IDE or a Cloud Agent with this repo open; the agent reads your athlete profile, zones, goals, and (when synced) background from the Xtri project.

## Quick start

1. Open this folder in Cursor (or start a Cloud Agent on this repo).
2. Fill in [`docs/athlete/profile.md`](docs/athlete/profile.md) (zones, schedule, goals, injury history).
3. **TrainingPeaks import-filer:** [`docs/trainingpeaks/imports/`](docs/trainingpeaks/imports/) (ukenotater + 4-ukers CSV).
3. Optional: pull background docs from your Xtri repo:
   ```bash
   export XTRI_REPO_URL='https://github.com/you/xtri-pondus.git'
   ./scripts/sync_xtri_docs.sh
   ```
4. Export a CSV from TrainingPeaks (calendar or summary) into `data/trainingpeaks/exports/` and ask the agent to run analysis:
   ```bash
   python3 scripts/analyze_tp_export.py data/trainingpeaks/exports/your-file.csv
   ```

## TrainingPeaks: what’s realistic

| Goal | In this repo | Notes |
|------|----------------|-------|
| Design workouts & plans | Yes | Structured steps, TSS targets, periodization in `plans/` |
| Import **planned** workouts | Partial | Generate **ZWO** (and notes) for upload/builder; full calendar API needs **partner** access |
| Import **completed** files | Partial | You can upload `.fit` / `.tcx` in the TP UI; API upload is partner-gated |
| Analyze progress | Yes | From TP **CSV exports** + optional wellness notes in `data/` |

TrainingPeaks does not offer a public API for personal hobby projects. This repo focuses on **files and exports** that work without partner credentials. If you later get API access, `docs/trainingpeaks-api.md` describes the integration path.

## Repo layout

```
docs/athlete/          Your profile, zones, constraints (source of truth)
docs/xtri/             Synced copies of Xtri project docs (after sync script)
docs/trainingpeaks/    Import/export how-tos
knowledge/             Stable coaching reference (load, intensity, tri balance)
plans/                 Meso/micro cycles (markdown)
workouts/zwo/          Workout library (ZWO: bike, swim, run, strength, brick)
scripts/               sync, export, analysis
data/                  Local exports only (not committed; see .gitignore)
```

## Talking to the coach

Example prompts:

- “Build a 4-week bike base block around 8 h/week; I can train Tue/Thu/Sat/Sun.”
- “Add a 5×8 min run threshold session to `workouts/planned/run/` and update `workouts/index.md`.”
- “Analyze my last 12 weeks of TP export and flag CTL drift and intensity distribution.”
- “After reading `docs/xtri/`, align my weekly plan with the Xtri pondus phase goals.”

## Requirements

- Python 3.10+ for scripts (`pip install -r scripts/requirements.txt` — stdlib only today).
