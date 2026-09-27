# Grovplan / periodisering / bulk

Appen eier **makro- og meso-nivå**. Intervals eier **mikro** (dagsøkter, kalender, grafer).

## Ansvarsfordeling

| Lag | App (coach-web) | Intervals.icu |
|-----|-----------------|---------------|
| Makro / sesong | Mål-race, sesongvindu, volummål per disiplin | — |
| Meso / bulk | `plan_blocks`: tittel, tema, start–slutt, uketimer | — |
| Mikro / uke | Plan-sync: første 1–2 uker bibliotek-WORKOUT + noter; chat: valgfri økt-sync | Kalender, ZWO, TSS, formkurver |
| Chat-kontekst | Leser blokk + mål + **kommende/siste økter** inn i prompt-stub | — |

**Valgfri sync:**
- Plan / setup: første 1–2 uker som WORKOUT via CLI-byggeren (`build_workout_event` → planned/ZWO) + grovplan-noter — `/v1/athlete/me/intervals/calendar/*` (preview→confirm).
- Coach-chat: enkle WORKOUT-events når utøveren ber om økt — `/v1/athlete/me/intervals/workouts/preview` → samme confirm.
- Full 4-ukers CSV-push er fortsatt CLI `scripts/intervals_push_calendar.py` (samme builder).

## Datamodell

### SQLite `plan_blocks`

| Kolonne | Type | Beskrivelse |
|---------|------|-------------|
| `id` | TEXT PK | UUID |
| `athlete_id` | TEXT FK | Utøver |
| `title` | TEXT | f.eks. «Base 1» |
| `theme` | TEXT | f.eks. «Aerob + svømteknikk» |
| `start_date` | TEXT | ISO `YYYY-MM-DD` |
| `end_date` | TEXT | ISO |
| `weekly_hours` | REAL | Mål timer/uke i blokken |
| `sort_order` | INTEGER | Stabil rekkefølge |
| `created_at` / `updated_at` | TEXT | UTC ISO |

Valgfri speiling: `data/athletes/{id}/plan/blocks.md` (senere) — MVP skriver kun SQLite.

### Relaterte atlet-felter

- `goal_race_date` — dager til mål på Overblikk
- `season_start_date` — start for compliance-vindu
- `weekly_focus` — ukens tekst (mikro-hint, ikke en blokk)

## Overblikk-UI (strip)

1. **Nåværende blokk** — tittel, tema, uke-range (`start`–`end`), uketimer
2. **Neste blokk** — teaser (tittel + startdato) eller «Ingen neste blokk»
3. **Dager til mål** — `goal_race_date − i dag` (eller «Sett racedato i Du»)

Tom state: seed én tom/redigerbar blokk fra Du, eller tom strip med CTA «Legg til blokk under Du».

## Redigering (Du)

Enkel liste: legg til / oppdater / slett blokker. Ingen kalendergrid. Sortert på `start_date` deretter `sort_order`.

## «Current» / «next»-logikk

```
today = date.today()
current = first block where start_date <= today <= end_date
         else nearest past block ending before today (fallback)
         else first upcoming block
next    = first block with start_date > today
          (if current exists: first with start_date > current.end_date)
```

William vs andre:

- William: blokker kan speile `plans/` i repo manuelt (coach limer inn) eller seed.
- Andre: **veiledet setup** genererer adaptive `plan_blocks` (knowledge + AI) med preview før lagring — se [onboarding-setup.md](onboarding-setup.md). Redigerbart i Plan/Du etterpå.
