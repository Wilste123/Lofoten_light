# Gap-analyse — 2026-09-27

**Branch:** `cursor/web-coach-mvp-42ac` · **HEAD ved kode-scan:** `5cfb32f` · **docs-push:** `5617a00`+ · **PR:** [#13](https://github.com/Wilste123/Lofoten_light/pull/13)  
**Fly:** https://lofoten-coach.fly.dev — `/health` → `{"status":"ok"}` (HTTP 200, sjekket 2026-09-27)  
**Kode skannet:** `apps/coach-web`, `services/coach-api`, `docs/product/*`, `fly.toml`  
**Plan:** [lofoten-coach-produkt-plan.md](lofoten-coach-produkt-plan.md) (inkl. **username-login**-krav)

## Verdict

Telefon-pilot er **brukbar og live på Fly**. Chat, Du, Overblikk, Plan, Compliance, form_estimates fra ICU, og **valgfri Sync av grovplan-noter** til Intervals er på plass. Åpne produktgap: **username login** (nå kun athlete-id — egen worker), **Dashboard**, **øktbibliotek**, wellness/søvn, BIA med av-toggle, partner-sync, proaktiv coach.

Vi er fortsatt en **tynn coach + Intervals-companion** — ikke TrainingPeaks-/HumanGO-erstatning.

## Compliance: les vs skriv (viktig)

| Hva | Retning | Status |
|-----|---------|--------|
| **Compliance / sesongvolum** | **App-side READ** fra Intervals `activities` + sesongmål i SQLite | Landet (`progress_compliance.py` → Overblikk + Compliance-fane) |
| **On-pace** | App-side beregning (`completed / expected`) | Landet |
| **form_estimates (FTP)** | App-side READ sykkel+power 90d → persist i SQLite | Landed (`form_from_intervals.py`, `POST /v1/form/recompute`) |
| Sync til Intervals | **WRITE** — grovplan-NOTE + bibliotek-WORKOUT (CLI-bygger / ZWO) via preview→confirm | Landet (Plan + setup) |
| Compliance skrevet til Intervals | Nei | **Ikke** — tallene lever kun i appen |
| Full ukeplan / ZWO-push | Nei | Ikke (CLI `intervals_push_calendar.py`) |

Compliance er altså **ikke** «synced into Intervals». Den regnes i appen fra ICU-aktiviteter. Skriving til Intervals skjer kun når brukeren aktivt bekrefter (plan-noter eller chat-øktforslag).

## Landed (vs eldre gap `aa8701a` / store `gap-analysis-branch.md`)

- [x] Onboarding → SQLite + `profile.md`
- [x] **Veiledet setup** — AI-samtale + adaptive knowledge → periodisering-preview → confirm; Intervals how-to; Du restart (dobbelt) + Logg ut — [onboarding-setup.md](onboarding-setup.md)
- [x] Chat (`POST /v1/chat`, ett LLM-kall) — **+ Intervals sessions-snapshot** i kontekst
- [x] Du — mål, sesongvolum, avtaler, skade, GI, FTP, vekt/alder, Intervals Lagre/verify
- [x] Returning login via **athlete-id** (`POST /v1/session/login` + profil-ID) — `6ce6872`
- [x] Overblikk — progress/compliance bars, form-kort, grovplan-strip
- [x] **Plan-fane** — plan_blocks CRUD + Sync panel
- [x] **Compliance-fane** — fullførte timer, on-pace, sesongmål-oppsummering
- [x] **form_estimates fra ICU** (gate ≥5) — ikke lenger `compute_form_estimates([])`
- [x] Intervals calendar sync: preview → confirm → push/delete/status
- [x] Chat → Intervals WORKOUT: foreslå → forhåndsvis → sync (`ll-coach-w-…`; ingen ZWO)
- [x] Seed William (CLI + `SEED_ON_BOOT` + admin-API)
- [x] Fly stack (`lofoten-coach`, `ams`, volume `/data`, port 8080, warm machine) — **health OK**
- [x] UX-grunnlag — mørk SPA, 5 faner (Coach / Overblikk / Plan / Compliance / Du)
- [x] Anti holdt — ingen Pondus/Slack/kalenderklone/Supabase

## Partial / fragile

| Område | Status |
|--------|--------|
| **Username login** | Landet på branch (login med `username`) — verifiser etter Fly deploy |
| UX-polish | Bedre enn tidlig MVP; fortsatt enkel SPA |
| **Auth** | Username + profil-ID + valgfri invite-token — ingen passord |
| VO₂ | Gate krever steady HR — ofte `null` |
| Sync | Meso-noter + enkle WORKOUT-beskrivelser; **ikke** full ukeplan/ZWO fra chat |
| `partner_slots` | Alltid `[]` |
| Secrets | Intervals-nøkkel klartekst i SQLite |
| Fly vs docs | `fly.toml` har `min_machines_running = 1`; `fly-deploy.md` kostnadsavsnitt nevner fortsatt `0` |
| Sessions planned | Ikke implementert (`sessions_done / sessions_planned`) |

## Missing (ønsket produkt + faseplan)

| Område | Gap |
|--------|-----|
| **Username login (2d+)** | Unik `username`-slug på athlete; login med brukernavn (f.eks. `william`); onboarding velger username; Du viser username + profil-ID; `POST /v1/session/login` → `{ username }` **eller** `{ athlete_id }` |
| **Dashboard-side** | Ingen dedikert training-status-side med timer + søvn + vekt/fett samlet (Overblikk er kompakt, ikke full dashboard) |
| **Søvnanalyse** | Ingen ICU wellness-fetch; ingen søvn-UI |
| **Vekt + body-fat** | Kun `weight_kg` i profil; ingen BIA/fettanalyse; ingen toggle OFF i Du |
| **Workout builder / øktbibliotek** | Ingen side for økter, coach-spørsmål om økt, completion + reason |
| **Fase 3** | Invite + `training_pair` + `partner_slots` |
| **Fase 5** | Proaktiv coach (cron/push) |
| — | Rate limit `/v1/chat`; disk-cache 90d power (kun in-memory TTL) |

## Recommended next slices

1. **Username login** (egen worker) — deretter telefon-smoke med `william` i stedet for bare `william-lofoten`
2. Telefon-smoke på https://lofoten-coach.fly.dev (seed → Intervals → Overblikk Live → Sync preview)
3. **Dashboard v1** — status + timer (gjenbruk progress) + søvn fra ICU wellness hvis tilgjengelig
4. **Vekt/fett** — app-analyse av wellness/BIA med **toggle OFF** i Du
5. **Øktbibliotek** — list planned/completed; chat om økt; completion + reason
6. Fase 3 invite / training_pair

## Referanser

`docs/product/PRODUCT-PLAN.md` · `returning-login.md` · `progress-compliance.md` · `form-estimates.md` · `fly-deploy.md` · store: [lofoten-coach-produkt-plan.md](lofoten-coach-produkt-plan.md) · [competitor-humango.md](competitor-humango.md)
