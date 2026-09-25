# Lofoten coach produkt — kanonisk plan

**Branch:** `cursor/web-coach-mvp-42ac` · **Repo:** [Lofoten_light](https://github.com/Wilste123/Lofoten_light) · **PR:** https://github.com/Wilste123/Lofoten_light/pull/13

## Produktfokus

1. Chat med personlig trener (forutsigbar, ett LLM-kall)
2. Kjapt overblikk (ikke erstatte Intervals) — inkl. **fremskritt / compliance**
3. App eier: mål, avtaler, skade, test-FTP, profilfil, **grovplan / periodisering / bulk**
4. Intervals eier: økter, kalenderdetaljer (ikke makro/bulk-oversikt)
5. Treningspar (fase 3): to trenere, samkjørte tid/sted-vinduer
6. **UX:** litt mer moderne flate (tydelig aksent, knapper, spacing) — fortsatt enkel, ikke dashboard-monster

## Det Intervals ikke gir — appens oversikt

### Grovplan / periodisering / bulk

Appen viser **makro- og meso-nivå** som Intervals ikke gjør godt. Se [periodization-overview.md](periodization-overview.md).

| Objekt | Eksempel | Lagring |
|--------|----------|---------|
| **Sesong / makro** | «Mot Lofoten 2027», faser (base → bygg → peak) | SQLite `plan_blocks` + valgfri markdown under `data/athletes/{id}/plan/` |
| **Bulk / blokk** | 4-ukers bulk med tema og uketimer | Samme |
| **Grovplan-oversikt** | Én skjerm: nåværende blokk, neste blokk, dager til race | Overblikk (read-first; rediger i Du) |

Ikke full kalenderklone. Lenke «detaljer i Intervals» for dagsøkter.

### Fremskritt og compliance

Deterministiske tall på Overblikk (Python, ikke LLM). Se [progress-compliance.md](progress-compliance.md).

| Metrikk | Eksempel | Kilde |
|---------|----------|--------|
| **Volummål** | Sykkel **175 / 500 t** (sesong) | ICU activities + mål på atlet |
| **Compliance** | Sykkel **35 %** (`completed / target`) | Samme formel som progress-bar |
| Per disiplin | Svøm / sykkel / løp / styrke | Samme |
| Progress bar | Visuell 175/500 | UI |

Uten Intervals-credentials: **demo/stub**-tall merket tydelig «Demo».

## Onboarding → profilfil

Ved fullført onboarding **skriver API** `data/athletes/{id}/profile.md`. Oppdateres fra Du.

**Ikke i onboarding-wizard:** dypt IBS/ernæring-kurs — knowledge i `knowledge/ernaring/`; matbegrensninger kan ligge i profil/Du.

GI-felter (IBS/gluten/laktose) samles i onboarding/Du → SQLite + `profile.md`. Chat diagnostiserer aldri.

## Datalagring

SQLite + Fly volume. Secrets: OpenAI i `.env`; Intervals ID+nøkkel i Du → `athlete_secrets`. Se [data-storage.md](data-storage.md).

Sesongmål (`season_*_hours_target`) og `plan_blocks` lever i SQLite — appens SoT for makro.

## Smarte estimater

Gate ≥ 5 sykkeløkter med watt. Se [form-estimates.md](form-estimates.md).

## Faser (oppdatert)

| Fase | Innhold |
|------|---------|
| 0–1 | ~~Docs + onboarding + chat + Du + Intervals-settings~~ (landet på PR #13) |
| 2 | ICU les + overview + form_estimates + **fremskritt/compliance bars** |
| 2b | **Grovplan / periodisering / bulk-oversikt** (read-first; mål-timer per disiplin) |
| 2c | **UX-polish** (knapper, farger, overblikk-layout) |
| 3 | Invite + training_pair |
| 4 | Valgfri Intervals-write |
| 5 | Proaktiv post-MVP |

## Anti

Ingen Pondus-import, ingen Slack i MVP, ingen tool-spam-chat, ingen full kalender-UI. Se [anti-patterns.md](anti-patterns.md).

## Relaterte docs

[mvp-scope.md](mvp-scope.md) · [progress-compliance.md](progress-compliance.md) · [periodization-overview.md](periodization-overview.md) · [athlete-profile.md](athlete-profile.md) · [partner-sync.md](partner-sync.md) · [README.md](README.md)
