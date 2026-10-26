"""TrainingPeaks calendar sync (beta, unofficial tpapi).

Inspired by tp2intervals (GPLv3) — reimplemented in Python; do not copy their sources.
"""

from trainingpeaks_beta.sync import (
    icu_workout_events_for_tp,
    preview_tp_push,
    push_tp_workouts,
    tp_public_status,
)

__all__ = [
    "icu_workout_events_for_tp",
    "preview_tp_push",
    "push_tp_workouts",
    "tp_public_status",
]
