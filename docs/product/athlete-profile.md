# Athlete profile — fil + SQLite

Hver utøver får en **egen profil** slik at coach (app + Cursor) tilpasser seg *den* personen — ikke William-only antakelser.

## Lagring

| Lag | Sti / tabell |
|-----|----------------|
| Markdown-speil | `data/athletes/{athlete_id}/profile.md` (runtime; gitignore OK) |
| App SoT | SQLite `athletes` |
| William fasit i git | `docs/athlete/profile.md` — **kun William** |

## Felter (MVP)

Visningsnavn, sport, mål, schedule, skade, testet FTP (+ dato), vekt/alder, trener (navn/personlighet/aksent), timezone, ukens fokus, avtaler.

**Treningsavtaler:** `athlete_type`, `allowed_disciplines` (`run`/`bike`/`swim`/`strength`), `sessions_per_week`.

**Ernæring / GI:** `nutrition_ibs` (`no`/`yes`/`unsure`), `nutrition_gluten` (`none`/`sensitive`/`celiac`), `nutrition_lactose`, `nutrition_other_restrictions`, `nutrition_notes`.

## Chat-regler

1. Les GI-felter inn i kontekst (via profile.md).
2. Trekk på `knowledge/ernaring/`.
3. Respekter restriksjoner.
4. Ingen medisinsk diagnose.
