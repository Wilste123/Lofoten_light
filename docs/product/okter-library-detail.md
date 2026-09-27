# Økter library + detail

Short product note for the workout library / detail redesign (PR #13 branch).

## UX

1. **Bibliotek** (default) — one card per distinct workout; date chips for occurrences.
2. **Kommende** — chronological today / upcoming / recent (previous list).
3. Tap card → **detail**:
   - **Struktur** — Oppvarming / Hoveddel / Nedkjøling (parsed from Intervals-steg)
   - Redigerbare felter (coach-økter) → Forhåndsvis → bekreft
   - **Sticky chat-composer** (alltid synlig over bunnfaner på mobil)
   - Knowledge-grounded coach-svar for sport/økt-type
   - Logg completion

## API

- `GET /v1/sessions` → adds `library[]`, `view_modes`, `default_view`
- `GET /v1/sessions/{id}` → detail (`steps`, `structure.phases`, `coach_block`, `editable_fields` inkl. warmup/main/cooldown)
- `POST /v1/chat` → optional `session_id` → `focused_session` + **mode=session knowledge** (sport packs under `knowledge/sykkel|lop|svom/…`)
  - Response includes `knowledge: { mode, discipline, paths }`
- `POST /v1/sessions/{id}/edit/preview` → pending `workout_push` (same confirm as chat)

No Pondus. ICU writes only after confirm.

## Deploy verify

```bash
fly deploy --app lofoten-coach
```

1. Logg inn → **Økter** — Bibliotek viser unike økter (ikke én kort per dag).
2. Toggle **Kommende** — kronologisk liste.
3. Åpne økt — struktur (warmup/main/cooldown), sticky chat-input synlig, Logg.
4. Chat i detalj: «kan vi kutte hovedsettet?» → forslag (knowledge for sport) → Forhåndsvis → Avbryt.
5. Coach-økt: Rediger oppvarming/hoveddel/nedkjøling → Forhåndsvis endring → Avbryt.
