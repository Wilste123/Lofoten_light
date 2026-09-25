# Gap-analyse — plan vs levert (`cursor/web-coach-mvp-42ac`)

**Kildeplan:** [PRODUCT-PLAN.md](PRODUCT-PLAN.md) + søsterdocs · **HEAD ved analyse:** `aa8701a` · **PR:** [#13](https://github.com/Wilste123/Lofoten_light/pull/13) · **Fly:** `lofoten-coach` → https://lofoten-coach.fly.dev (deploy kjøres lokalt; se [fly-deploy.md](fly-deploy.md))

## Verdict

Dette er en **brukbar telefon-pilot**, ikke et ferdig produkt. Chat, Du, seed, Fly-stack og Overblikk med ekte Intervals-volum (når nøkkel er lagret) er på plass. Det som fortsatt skiller fra planen er **form_estimates matet fra ICU**, partner-sync, Intervals-write og proaktiv coach — pluss noen UX-/auth-rester.

## Landed

- [x] **Onboarding** → SQLite + `profile.md` (navn, trener, aksent, mål, skade, GI, FTP, vekt/alder)
- [x] **Chat** — ett LLM-kall, kontekst fra profil + overview-stub (`POST /v1/chat`)
- [x] **Du** — mål, sesongvolum, avtaler, skade, GI, FTP, plan-blokker CRUD
- [x] **Intervals Lagre/verify** — `PUT` + soft-verify; nøkkel kun server (`athlete_secrets`)
- [x] **Overblikk progress/compliance** — deterministisk `completed/target`; live ICU når credentials; Demo / Henting feilet-merker (`aa8701a`)
- [x] **Grovplan-strip** — current/next `plan_blocks` + dager til race
- [x] **Seed William** — CLI + `SEED_ON_BOOT` + valgfri admin-API; knapp «Bruk seedet William-profil»
- [x] **Fly** — `fly.toml` (`lofoten-coach`, `ams`, volume `/data`, port 8080, `min_machines_running=1`); runbook i [fly-deploy.md](fly-deploy.md)
- [x] **UX-grunnlag** — Space Grotesk/Syne, aksent, gradient-bakgrunn, tab-bar Coach / Overblikk / Du
- [x] **Anti holdt** — ingen Pondus/Slack/kalenderklone/Supabase i MVP-kode ([anti-patterns.md](anti-patterns.md))

## Partial / fragile

| Område | Status |
|--------|--------|
| **form_estimates** | Modul + tester finnes; overview kaller `compute_form_estimates([])` — gate aldri åpen fra ICU. Ingen `POST /v1/form/recompute`. UI viser disclaimer / testet FTP. |
| **UX-polish (2c)** | Mye landet (`680c0f7`); fortsatt enkel SPA, ikke «ferdig» polish-pass. |
| **Intervals Lagre** | Hang fikset (`efc80b3`); avhengig av soft-verify-timeout (~5–10 s). |
| **Fly live** | Kode + docs klare; agent har ikke Fly-login — William må `fly deploy` for å bekrefte prod. Cold start dempet med warm machine. |
| **Auth** | `POST /v1/session/login` + profil-ID i `localStorage`; valgfri invite-token. Ingen passord/OAuth. Se [returning-login.md](returning-login.md). |
| **last_session / load** | Alltid `null` i overview — ikke plan-kritisk. |
| **Compliance** | Kun `completed/target`; on-pace og sessions_planned er bevisst «ikke MVP» ([progress-compliance.md](progress-compliance.md)). |
| **partner_slots** | Alltid `[]` i API. |
| **Secrets** | Intervals-nøkkel i klartekst i SQLite (plan: krypter med `SECRETS_KEY` senere). |

## Missing vs plan

| Fase | Plan | Gap |
|------|------|-----|
| **2c** | UX leftovers | Små polish-pass; ikke blokkerende for pilot |
| **2→neste** | `form_estimates` fra ICU watt (≥5 økter) | **Hovedgap:** ingen power/MMP fra activities → lagrede estimater ([form-estimates.md](form-estimates.md)) |
| **2→neste** | On-pace compliance | Dokumentert som senere — ikke implementert |
| **3** | Invite + `training_pair` + `partner_slots` | Schema tom; ingen API/UI ([partner-sync.md](partner-sync.md)) |
| **4** | Valgfri Intervals-write | Ingen write/push |
| **5** | Proaktiv post-MVP | Ingen cron/push |
| — | Rate limit på `/v1/chat` | Ikke sett i kode |
| — | Aktivitets-cache (90 d power) på disk | Kun in-memory progress-cache (~2 min) |

## Recommended next slices

Ordnet for **William på telefon** (høyest verdi først):

1. **Bekreft Fly** — `fly deploy --app lofoten-coach`; seed-knapp + chat på https://lofoten-coach.fly.dev
2. **Koble Intervals i Du** — verifiser Overblikk-badge **Intervals** + ekte timer (ikke Demo)
3. **Wire form_estimates** — hent sykkel+power fra ICU (90 d), persist `ftp_estimated`, vis på Overblikk når gate ≥5
4. **Sesongmål-sanity i Du** — juster seed-fordeling vs opplevd YTD; sjekk progress-barer
5. **Plan-blokker på mobil** — rediger B0/neste under Du; strip skal speile
6. **Chat-smoke** — spør avtaler/rygg/uke; svar skal speile seedet `profile.md`
7. **Fase 3 invite-skisse** (etter 1–6) — pair-kode + `partner_slots` i overview (før Intervals-write)

## Relaterte docs

[mvp-scope.md](mvp-scope.md) · [periodization-overview.md](periodization-overview.md) · [data-storage.md](data-storage.md) · [import-from-repo.md](import-from-repo.md) · [README.md](README.md)
