# Lofoten coach produkt — kanonisk plan

**Branch:** `cursor/web-coach-mvp-42ac` · **Repo:** [Lofoten_light](https://github.com/Wilste123/Lofoten_light) · **PR:** https://github.com/Wilste123/Lofoten_light/pull/13

## Produktfokus

1. Chat med personlig trener (forutsigbar, ett LLM-kall)
2. Kjapt overblikk (ikke erstatte Intervals)
3. App eier: mål, avtaler, skade, **ernæring/GI**, test-FTP, profilfil
4. Intervals eier: økter, kalenderdetaljer
5. Treningspar (fase 3): to trenere, samkjørte tid/sted-vinduer

## Onboarding → profilfil

Ved fullført onboarding **skriver API en profilfil** per atlet: `data/athletes/{id}/profile.md` (se [athlete-profile.md](athlete-profile.md)).

Innhold fra onboarding + Du:

- Visningsnavn, sport, tidssone, tilgjengelighet
- Trenernavn, personlighet, aksentfarge
- Mål / race, skade / begrensninger
- Testet FTP (+ dato), vekt, alder (for senere VO₂)
- Ukens fokus, avtaler
- **Ernæring / GI:** IBS, gluten, laktose, andre restriksjoner, fri tekst

Profilfilen er det treneren (LLM + Cursor) leser for **andre personer** — ikke bare William. Oppdateres når Du-fanen lagres.

## Ernæring / IBS — onboarding + knowledge

- Onboarding/Du samler GI-felter i SQLite + `profile.md`.
- Chat refererer `knowledge/ernaring/` (inkl. `ibs-og-gluten.md`) — **aldri diagnostiser**.
- Fri chat-svar kan fortsatt lagres som avtale/notat via «Lagre».

## Datalagring

SQLite + Fly volume i MVP. Ikke Supabase før scale-triggere. Se [data-storage.md](data-storage.md).

## Smarte estimater

Gate ≥ 5 sykkeløkter med watt. Se [form-estimates.md](form-estimates.md).

## Faser

| Fase | Innhold |
|------|---------|
| 0 | Branch + product docs |
| 1 | Onboarding → profilfil (+ GI) + chat + Du (uten ICU) |
| 2 | ICU les + overview + form_estimates |
| 3 | Invite + training_pair |
| 4 | Valgfri Intervals-write |
| 5 | Proaktiv post-MVP |

## Anti

Ingen Pondus `coach_bot`, Slack, intent/tool-loop, eller medisinsk diagnose i chat. Se [anti-patterns.md](anti-patterns.md).

## Relaterte docs

[mvp-scope.md](mvp-scope.md) · [athlete-profile.md](athlete-profile.md) · [partner-sync.md](partner-sync.md) · [README.md](README.md)
