# Fremskritt og compliance

Deterministisk Python på Overblikk — **ikke** LLM. Tallene er lesbare i API (`GET /v1/overview`) og UI.

## Volummål (sesong)

Lagret på atlet (SQLite-kolonner):

| Felt | Disiplin | Eksempel |
|------|----------|----------|
| `season_swim_hours_target` | Svøm | 100 |
| `season_bike_hours_target` | Sykkel | 500 |
| `season_run_hours_target` | Løp | 150 |
| `season_strength_hours_target` | Styrke | 50 |
| `season_start_date` | Sesongstart (ISO) | `2026-09-01` |
| `goal_race_date` | Race / mål-dato | `2027-08-20` |

Redigeres under **Du → Sesongmål**. Tomt felt = ingen rad / ingen target for den disiplinen (UI viser «Sett mål i Du»).

## Fullførte timer

### Med Intervals-credentials

1. Hent aktiviteter for `[season_start_date … i dag]` (default: sesongstart = 1. jan inneværende år hvis felt mangler).
2. Map `type` → disiplin:

| Intervals `type` (eksempler) | Disiplin |
|------------------------------|----------|
| Swim, SwimWorkout | `swim` |
| Ride, VirtualRide, GravelRide, MountainBikeRide | `bike` |
| Run, VirtualRun, TrailRun | `run` |
| WeightTraining, Workout, Strength | `strength` |

3. Varighet: foretrekk `moving_time`, ellers `elapsed_time` / `duration` (sekunder → timer). Verdier &lt; 15 tolkes som allerede timer (CSV-quirk).

### Uten credentials

Stub/demo-tall returneres med `source: "demo"` og UI-merke **Demo**. Tallene er faste illustrasjoner — ikke ekte trening.

## Formler (MVP)

Én definisjon — hold den stabil:

```
completed_h   = sum(duration_hours for discipline in window)
target_h      = season_{discipline}_hours_target
progress_pct  = 0 if target_h <= 0 else min(100, 100 * completed_h / target_h)
compliance_pct = progress_pct   # MVP: samme ratio
```

Visning: «Sykkel **175 / 500 t**» + progress-bar fylt til `progress_pct` + «**35 %**» compliance.

### Senere (ikke MVP)

Valgfritt alternativ dokumentert her for historikk — **ikke implementert**:

- `sessions_done / sessions_planned` siste 4 uker (krever planlagte events fra Intervals).
- On-pace: `completed / (target * elapsed_days / season_days)`.

## API-felt (overview)

```json
{
  "progress": {
    "window": { "start": "2026-01-01", "end": "2026-09-25" },
    "source": "intervals" | "demo",
    "disciplines": [
      {
        "id": "bike",
        "label": "Sykkel",
        "completed_hours": 175.0,
        "target_hours": 500.0,
        "progress_pct": 35.0,
        "compliance_pct": 35.0
      }
    ]
  }
}
```

## Merker

| Merke | Når |
|-------|-----|
| **Demo** | Ingen Intervals-nøkkel, eller fetch feilet → stub |
| **Estimat** | Data tynn (&lt; 3 økter i vinduet) — fortsatt reell sum, men usikker |
