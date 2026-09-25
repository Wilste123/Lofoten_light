# Lofoten coach produkt — kanonisk plan

**Branch:** `cursor/web-coach-mvp-42ac` · **Repo:** [Lofoten_light](https://github.com/Wilste123/Lofoten_light) · **PR:** https://github.com/Wilste123/Lofoten_light/pull/13

## Produktfokus

1. Chat med personlig trener (forutsigbar, ett LLM-kall)
2. Kjapt overblikk (ikke erstatte Intervals)
3. App eier: mål, avtaler, skade, test-FTP, profilfil
4. Intervals eier: økter, kalenderdetaljer
5. Treningspar (fase 3): to trenere, samkjørte tid/sted-vinduer

## Onboarding → profilfil

Ved fullført onboarding **skriver API en profilfil** per atlet (markdown), f.eks. `data/athletes/{id}/profile.md` (speil av `docs/athlete/profile.md`-mal).

Innhold fra onboarding + Du:

- Visningsnavn, tidssone
- Trenernavn, personlighet, aksentfarge
- Mål / race / dato
- Skade / begrensninger (generelt)
- Testet FTP (+ dato), vekt, alder (for senere VO₂)
- Ukens fokus, avtaler (etter hvert)

Profilfilen er det treneren (LLM + Cursor) leser for **andre personer** — ikke bare William. Oppdateres når Du-fanen lagres.

**Ikke i onboarding:** IBS, gluten, detaljert ernæring (se knowledge).

## Ernæring / IBS — knowledge, ikke onboarding

Utvid `knowledge/ernaring/` med bl.a.:

- IBS: praktiske råd under trening (FODMAP-bevissthet, timing vs økt, hva coach kan spørre om)
- Gluten / cøliaki / intoleranse: trygge råd uten diagnose
- Generell tri-ernæring (eksisterende filer beholdes)

Chat kan **referere knowledge** og spørre naturlig («har du begrensninger rundt mat?») — lagring av svar går som **avtale/notat i profil** via «Lagre», ikke egne onboarding-steg.

## Datalagring

SQLite + Fly volume i MVP. Ikke Supabase før scale-triggere. Tabeller: athletes, secrets, messages, invites; senere training_pairs, coordinated_sessions. Se [data-storage.md](data-storage.md).

## Smarte estimater

Gate ≥ 5 sykkeløkter med watt (eller ICU-historikk). MMP-basert FTP; VO₂ strengere (vekt+HR). Se [form-estimates.md](form-estimates.md).

## Faser

| Fase | Innhold |
|------|---------|
| 0 | Branch + product docs |
| 1 | Onboarding → profilfil + chat + Du (uten ICU) |
| 2 | ICU les + overview + form_estimates |
| 3 | Invite + training_pair (samboer) |
| 4 | Valgfri Intervals-write |
| 5 | Proaktiv post-MVP |

## Anti

Ingen Pondus coach_bot-import, ingen Slack i MVP, ingen intent/orchestrator-tool-spam, ingen ernæring/IBS-wizard i onboarding. Se [anti-patterns.md](anti-patterns.md).

## Relaterte docs

- [mvp-scope.md](mvp-scope.md) · [partner-sync.md](partner-sync.md) · [README.md](README.md)
