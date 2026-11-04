# Intervals.icu — svøm fra agent-kalender

**Regel (William, okt 2026):** Svøm-WORKOUTs som pushes med `intervals_push_calendar.py` skal **ikke** ha strukturerte intervaller i Intervals (ingen `12m` / meter-blokker i builder).

| Felt | Innhold |
|------|---------|
| **Varighet** | `duration_minutes` fra CSV → `moving_time` |
| **Load** | `tss` fra CSV → `icu_training_load` |
| **Beskrivelse** | Kun **trenernotat** fra `workouts/planned/swim/*.txt` (tekst etter YAML `---`, **uten** `---intervals---`-delen) |

Repo-filer beholder `---intervals---` for TP/ZWO og dokumentasjon; push-scriptet stripper det for svøm.

Sykkel: ZWO/struktur som før. Løp: coach + ev. Intervals-syntax der det er definert.
