# Plan — månedskalender

**Branch:** `supabase` · Plan-fanen

## UX

- Månedsgrid (man–søn) med prikker = antall `planned_sessions` per dag.
- Klikk dag → liste + **Sync uke → Intervals** / **Sync måned → Intervals**.
- **Sync uke → TP β** bruker samme `start`/`end` mot `/v1/athlete/me/trainingpeaks/beta/calendar/*`.
- Global «Sync til Intervals» under kalenderen = hele nærvindu (som før).

## API

`POST …/intervals/calendar/preview` og TP beta preview tar valgfritt:

```json
{ "start": "2026-10-05", "end": "2026-10-11", "op": "push", "include_notes": false }
```

Filtrerer `planned_sessions` og events til perioden (ikke bare 2-ukers ICU-vindu når dato er satt).
