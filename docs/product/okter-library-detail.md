# Økter library + detail

Short product note for the workout library / detail redesign (PR #13 branch).

## UX

1. **Bibliotek** (default) — one card per distinct workout; date chips for occurrences.
2. **Kommende** — chronological today / upcoming / recent (previous list).
3. Tap card → **detail**: title, sport, «Fra treneren» steps, dates, status, Logg, edit (coach workouts), in-view chat.

## API

- `GET /v1/sessions` → adds `library[]`, `view_modes`, `default_view`
- `GET /v1/sessions/{id}` → structured detail (`steps`, `coach_block`, `editable_fields`, occurrences)
- `POST /v1/chat` → optional `session_id` → `focused_session` in LLM context
- `POST /v1/sessions/{id}/edit/preview` → pending `workout_push` (same confirm as chat)

No Pondus. Knowledge-grounded via existing `build_system_prompt`. ICU writes only after confirm.

## Deploy verify

```bash
fly deploy --app lofoten-coach
```

1. Logg inn → **Økter** — Bibliotek viser unike økter (ikke én kort per dag).
2. Toggle **Kommende** — kronologisk liste.
3. Åpne økt — steg / beskrivelse, datoer, Logg.
4. Chat i detalj: «kan vi kutte hovedsettet?» → forslag → Forhåndsvis → Avbryt (ingen stille sync).
5. Coach-økt: Rediger felter → Forhåndsvis endring → Avbryt.
