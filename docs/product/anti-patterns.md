# Anti-patterns — hva vi ikke gjør

Lært fra xtri / xtri-pondus. Hold MVP enkelt.

## Forbudt i MVP

| Anti-pattern | Hvorfor | Gjør i stedet |
|--------------|---------|---------------|
| **Import av Pondus `coach_bot`** | Orchestrator, intent-router, tool-spam — tung og uforutsigbar | Én chat-handler: kontekst → **ett** LLM-kall → svar |
| **Slack som primærflate** | Ops, webhooks, proaktiv støy | Mobilvennlig web (Coach / Overblikk / Du) |
| **Tool-loop / multi-agent chat** | «Coach summit», LLM A ↔ LLM B, agent-til-agent | Deterministisk `partner_slots` i snapshot (fase 3) |
| **Intent-router + mange tools per melding** | Uforutsigbar, dyr, vanskelig å debugge | Trimmet prompt + eventuell bekreftet lagring av avtaler |
| **Auto-scrape hele chat til «minne»** | Hallusinert kontekst | Bruker bekrefter «Lagre som avtale/notat» |
| **IBS/gluten-wizard i onboarding** | Scope-creep; medisinsk tone | Knowledge under `knowledge/ernaring/`; chat kan spørre |
| **Supabase «fordi vi kanskje trenger det»** | Postgres/Auth/RLS = Pondus-tunghet for 1–2 piloter | SQLite + Fly volume (`data-storage.md`) |
| **Kalenderklone av Intervals** | Dupliserer SoT | Lenke «Åpne Intervals» + kort overblikk |
| **Proaktiv cron i v1** | Støy før chat er stabil | Fase 5 |

## Tillatt gjenbruk

- `scripts/intervals_lib.py` som **bibliotek** for lese-path (overview) — ikke kopier hele Pondus-stacken.
- `knowledge/coach/` og `knowledge/ernaring/` som prompt-snippets (trimmet).
- Git-planer og ZWO forblir i repo; runtime speiler ikke hele `plans/` i appen.

## Sjekkliste før PR-merge til main

- [ ] Ingen `coach_bot` / Slack-avhengighet i `apps/` eller `services/coach-api/`
- [ ] `/v1/chat` = én LLM-tur per request (ingen tool-loop)
- [ ] Ingen ernæring-steg i onboarding-UI
- [ ] SQLite som eneste datastore (ingen Supabase-dep)
