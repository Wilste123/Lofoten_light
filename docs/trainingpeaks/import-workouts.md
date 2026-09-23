# Getting workouts into TrainingPeaks (without partner API)

TrainingPeaks’ **OAuth API** is for approved partners, not personal scripts. This workflow works for most athletes.

## Planned workouts

### Option A — Workout Library + drag to calendar

1. In TrainingPeaks: **Workout Library** → **Build Workout** (or import file if supported).
2. Use the agent’s **structured workout text** (intervals with duration and % FTP or HR).
3. Drag the workout onto the calendar day.

### Option B — ZWO file (bike, smart trainer)

1. Agent generates: `workouts/generated/<name>.zwo` via `scripts/export_zwo.py`.
2. In TrainingPeaks: import into library (version-dependent) or open in **Zwift**/**TrainerRoad** if you use those bridges.
3. If TP does not accept ZWO directly, use the same file in Zwift and let TP sync completed activities from your connected device account.

### Option C — Copy structured steps

Ask the agent for a **TrainingPeaks builder checklist**: each step with `Duration`, `Intensity`, `Cadence` notes. Fast for one-off key sessions.

## Completed activities

- Upload `.fit` / `.tcx` from Garmin/Wahoo/cycle computer in TP **Upload**.
- Or sync via Garmin Connect / device integration.

## Calendar bulk import

- TP sometimes supports **iCal** subscribe/export for viewing; for **creating** many planned workouts, library + duplicate week is usually faster than fighting formats.
- For large blocks, ask the agent for a **week template** you duplicate in TP.

## When API access exists

See `docs/trainingpeaks/api.md` for `workouts:plan` and file upload endpoints (partner credentials required).
