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

1. Hent aktiviteter for `[season_start_date … i dag]` via  
   `GET https://intervals.icu/api/v1/athlete/{id}/activities?oldest=&newest=&limit=100&fields=…`  
   (Basic auth `API_KEY:{nøkkel}`). Implementasjon: `services/coach-api/progress_compliance.py`.
2. **Paginering:** hvis en side returnerer `limit` rader, hent eldre sider (`newest` = dagen før eldste `start_date_local` i siden) til vinduet er dekket. Dedup på `id`.
3. **Cache:** kort TTL (~2 min) per atlet+vindu så Overblikk-fanen ikke hammerer ICU.
4. Map `type` → disiplin:

| Intervals `type` (eksempler) | Disiplin |
|------------------------------|----------|
| Swim, SwimWorkout | `swim` |
| Ride, VirtualRide, GravelRide, MountainBikeRide | `bike` |
| Run, VirtualRun, TrailRun | `run` |
| WeightTraining, Workout, Strength | `strength` |

5. Varighet: foretrekk `moving_time`, ellers `elapsed_time` / `duration` (sekunder → timer). Verdier &lt; 15 tolkes som allerede timer (CSV-quirk).

Hvis `season_start_date` er **i fremtiden**: ingen ICU-kall; `source: "intervals"`, `season_not_started: true`, completed = 0.

### Uten credentials

Stub/demo-tall returneres med `source: "demo"` og UI-merke **Demo**. Tallene er faste illustrasjoner — ikke ekte trening.

### Credentials men fetch feilet

`source: "demo"`, `fetch_error: true`, **completed = 0** (ikke fake demo-timer). UI: **Henting feilet**.

## Formler

Én definisjon — hold den stabil:

```
completed_h   = sum(duration_hours for discipline in window)
target_h      = season_{discipline}_hours_target
progress_pct  = 0 if target_h <= 0 else min(100, 100 * completed_h / target_h)
compliance_pct = progress_pct   # «fullført av sesongmål»
```

Visning: «Sykkel **175 / 500 t**» + progress-bar + «**35 %**» compliance.

### On-pace (når `season_start_date` + `goal_race_date` finnes)

```
elapsed_days = max(1, (today − season_start).days + 1)   # capped to season_days
season_days  = max(1, (goal_race − season_start).days)
expected_h   = target_h * elapsed_days / season_days
on_pace_pct  = 100 * completed_h / expected_h            # ikke capped
on_pace      = on_pace_pct >= 95
on_pace_note = «På plan» | «Foran plan (+N %)» | «Bak plan (−N %)»
```

Implementasjon: `progress_compliance.on_pace_metrics` · vist under Compliance-fanen og kompakt på Overblikk.

### Senere

- `sessions_done / sessions_planned` siste 4 uker (krever planlagte events fra Intervals).

## API-felt (overview)

```json
{
  "progress": {
    "window": { "start": "2026-01-01", "end": "2026-09-25" },
    "source": "intervals" | "demo",
    "estimate": false,
    "season_not_started": false,
    "activity_count": 42,
    "formula": "completed_hours / season_target_hours (capped 100%)",
    "fetch_error": false,
    "disciplines": [
      {
        "id": "bike",
        "label": "Sykkel",
        "completed_hours": 175.0,
        "target_hours": 500.0,
        "progress_pct": 35.0,
        "compliance_pct": 35.0,
        "session_count": 40,
        "expected_hours": 180.0,
        "on_pace_pct": 97.2,
        "on_pace": true,
        "on_pace_note": "På plan"
      }
    ]
  }
}
```

## Merker

| Merke | Når |
|-------|-----|
| **Demo** | Ingen Intervals-nøkkel |
| **Henting feilet** | Credentials finnes, men ICU-kall feilet → 0 t |
| **Intervals** | Ekte summer fra aktiviteter |
| **Estimat** | Data tynn (&lt; 3 økter i vinduet) — fortsatt reell sum, men usikker |
