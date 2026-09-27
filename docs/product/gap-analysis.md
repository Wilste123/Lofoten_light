# Gap-analyse — plan vs levert (`cursor/web-coach-mvp-42ac`)

> **Oppdatert:** Se [gap-analysis-2026-09-27.md](gap-analysis-2026-09-27.md) for fersk scan (HEAD `5cfb32f`, Fly health OK, dashboard/øktbibliotek som neste).

**Kildeplan:** [PRODUCT-PLAN.md](PRODUCT-PLAN.md) + søsterdocs · **PR:** [#13](https://github.com/Wilste123/Lofoten_light/pull/13) · **Fly:** `lofoten-coach` → https://lofoten-coach.fly.dev (se [fly-deploy.md](fly-deploy.md))

## Verdict

Telefon-pilot med chat, Du, seed, Fly, Overblikk + **Plan/Compliance-faner**, **form_estimates fra ICU**, og **Intervals sync (preview→confirm)**. Partner-sync, proaktiv coach og Supabase er fortsatt ute.

## Landed

- [x] **Onboarding** → SQLite + `profile.md` (navn, trener, aksent, mål, skade, GI, FTP, vekt/alder)
- [x] **Chat** — ett LLM-kall, kontekst fra profil + overview-stub (`POST /v1/chat`)
- [x] **Du** — mål, sesongvolum, avtaler, skade, GI, FTP (plan-blokker flyttet til Plan-fane)
- [x] **Intervals Lagre/verify** — `PUT` + soft-verify; nøkkel kun server (`athlete_secrets`)
- [x] **Overblikk progress/compliance** — deterministisk `completed/target`; live ICU; Demo / Henting feilet
- [x] **form_estimates fra ICU** — sykkel+power 90d, gate ≥5, power-curve MMP, persist `ftp_estimated`, `POST /v1/form/recompute`, vist på Overblikk/Compliance
- [x] **On-pace compliance** — `expected = target × elapsed/season`; note «På plan / Foran / Bak» ([progress-compliance.md](progress-compliance.md))
- [x] **Plan- + Compliance-faner** — egen nav; Overblikk kort; Plan = grovplan + sync; Compliance = barer + sesongmål
- [x] **Intervals calendar sync** — Sync / Oppdater / Fjern med preview + Ja/Avbryt; `pending_actions` i SQLite; `ll-coach-…` noter
- [x] **Grovplan-strip** — current/next `plan_blocks` + dager til race
- [x] **Seed William** — CLI + `SEED_ON_BOOT` + valgfri admin-API
- [x] **Fly** — `fly.toml` (`lofoten-coach`, `ams`, volume `/data`, port 8080)
- [x] **UX** — Space Grotesk/Syne, mørk UI, 5-faners nav, sync confirm-kort
- [x] **Returning login** — profil-ID + valgfri invite (`POST /v1/session/login`)
- [x] **Anti holdt** — ingen Pondus/Slack/kalenderklone/Supabase

## Partial / fragile

| Område | Status |
|--------|--------|
| **UX-polish** | Bedre Plan/Compliance; fortsatt SPA-pilot. |
| **Intervals Lagre** | Soft-verify-timeout (~5–10 s). |
| **Fly live** | William må `fly deploy` for prod. |
| **Auth** | `POST /v1/session/login` + profil-ID i `localStorage`; valgfri invite-token. Se [returning-login.md](returning-login.md). |
| **VO₂** | Gate krever steady HR — fortsatt `null` uten segment. |
| **Sync** | Noter for meso-blokker, ikke full ukeplan/ZWO fra CSV. |
| **last_session / load** | Alltid `null` i overview. |
| **partner_slots** | Alltid `[]`. |
| **Secrets** | Intervals-nøkkel i klartekst i SQLite. |


## Missing vs plan (out of scope denne runden)

| Fase | Gap |
|------|-----|
| **3** | Invite + `training_pair` + `partner_slots` |
| **5** | Proaktiv coach |
| — | Rate limit `/v1/chat`; disk-cache 90d power (in-memory TTL finnes) |

## Closed this pass

1. Wire `form_estimates` (ikke lenger `compute_form_estimates([])`)
2. On-pace + tydelig compliance %
3. Plan / Compliance egne faner + UX-løft
4. Intervals push/status/delete med confirm UI

## Relaterte docs

[mvp-scope.md](mvp-scope.md) · [periodization-overview.md](periodization-overview.md) · [form-estimates.md](form-estimates.md) · [progress-compliance.md](progress-compliance.md) · [fly-deploy.md](fly-deploy.md)
