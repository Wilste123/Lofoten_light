# Anti-patterns — hva vi ikke gjør

Lært fra xtri / xtri-pondus. Hold MVP enkelt.

## Forbudt i MVP

| Anti-pattern | Hvorfor | Gjør i stedet |
|--------------|---------|---------------|
| **Import av Pondus `coach_bot`** | Orchestrator, intent-router, tool-spam | Én chat-handler: kontekst → **ett** LLM-kall → svar |
| **Slack som primærflate** | Ops, webhooks, proaktiv støy | Mobilvennlig web |
| **Tool-loop / multi-agent chat** | LLM A ↔ LLM B | Deterministisk `partner_slots` (fase 3) |
| **Intent-router + mange tools** | Uforutsigbar, dyr | Trimmet prompt + bekreftet lagring av avtaler |
| **Auto-scrape hele chat til «minne»** | Hallusinert kontekst | Bruker bekrefter «Lagre som avtale/notat» |
| **Diagnostisere IBS/cøliaki i chat** | Medisinsk overtramp | GI-felter i profil; tilpass råd; henvis fagperson |
| **Hardkod William-fakta for alle** | Feil for andre atleter | Alltid `profile.md` + SQLite |
| **Supabase «fordi vi kanskje trenger det»** | Postgres/Auth/RLS for 1–2 piloter | SQLite + Fly volume |
| **Kalenderklone av Intervals** | Dupliserer SoT | Lenke «Åpne Intervals» + kort overblikk |
| **Proaktiv cron i v1** | Støy før chat er stabil | Fase 5 |

## Tillatt gjenbruk

- `scripts/intervals_lib.py` som bibliotek for lese-path (fase 2)
- `knowledge/coach/` og `knowledge/ernaring/` som prompt-snippets
- Git-planer og ZWO forblir i repo

## Sjekkliste før PR-merge til main

- [ ] Ingen `coach_bot` / Slack-avhengighet i `apps/` eller `services/coach-api/`
- [ ] `/v1/chat` = én LLM-tur per request
- [ ] Profil + GI-felter i onboarding; ingen diagnose-tone i chat
- [ ] SQLite som eneste datastore (ingen Supabase-dep)
