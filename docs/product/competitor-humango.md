# Konkurrenter — HumanGO og lignende AI-utholdenhet

**Dato:** 2026-09-27 · **Vår posisjon:** Lofoten Coach på branch `cursor/web-coach-mvp-42ac` (`5cfb32f`) — tynn personlig coach + Intervals-companion, ikke full plan-/kalenderplattform.  
**Kilder:** offentlige produktsider / FAQ (HumanGO, TrainAsONE, Athletica) — ikke affiliate-review.

## Kort: hva vi er

| Vi | De (typisk) |
|----|-------------|
| Chat-trener med William-kontekst (profil, GI, skade, grovplan) | Adaptiv **daglig ukeplan** som eier kalenderen |
| Overblikk + compliance **regnet i appen** fra Intervals-aktiviteter | Plan-engine som også pusher hele økter til enheter |
| Intervals eier økter/detaljer; valgfri sync av **makro-noter** | Ofte egen workout-builder + wearable-økosystem |
| Én atlet (MVP); treningspar senere | HumanGO/Athletica: coach-modus / multi-athlete |

## Feature-tabell

| Feature-område | Lofoten Coach (nå) | HumanGO | TrainAsONE | Athletica |
|----------------|--------------------|---------|------------|-----------|
| **Adaptiv daglig plan** | Nei (grovplan-blokker) | Ja — Hugo tilpasser plan fortløpende | Ja — ML, kun løp | Ja — sports science + adaptasjon |
| **Chat / AI-coach** | Ja (ett LLM-kall + profil) | Ja (Hugo, flerspråklig) | Begrenset (feedback/recalc, ikke full chat-trener) | Ja (konversasjons-AI på data) |
| **Intervals.icu sync** | READ activities (+ form); WRITE valgfri plan-noter | Ikke kjent som ICU-first; TP Virtual sync | Garmin/Strava m.fl. | Ja — plan + wellness ↔ ICU |
| **TrainingPeaks** | Nei (Intervals-fokus) | TP Virtual connected account | Nei (primært run/wearables) | Nei (ICU-bro) |
| **Workout builder / bibliotek** | Nei | Ja (daglige økter, tester, race planner) | Ja (daglige løpøkter, watch-guidance) | Ja (Workout Wizard, bytt økt) |
| **Compliance / progress** | App-side `completed/target` + on-pace | Progress-tab (fitness, goals, activity) | ACWR / load-guardrails | Fitness/fatigue + compliance for coaches |
| **Body composition** | Kun `weight_kg` i profil; ingen fettanalyse | Markedsført i Progress (body composition m.fl.) | Ikke kjerne | Ikke kjerne (HRV/søvn mer sentralt) |
| **Sleep / wellness** | Ikke lest ennå | Søvn/HRV/RHR i readiness-narrativ | Markedsfører «slept poorly» → recalc; HRV ikke primær input | HRV + søvn brukt i adaptasjon; ICU wellness-sync |
| **Multi-athlete / coach** | Schema tom (`partner_slots: []`); fase 3 | Coach Mode (flere atleter) | Individuell løper | Coach-dashboard (gratis coach-konto) |
| **Race / periodisering** | Manuelle `plan_blocks` + dager til race | Mål, faser, race planner | Multi-race calendar | Sesong/periodisering i engine |
| **Produktform** | Mobil-vennlig web SPA + Fly | Native app + web | Web + iOS/Android + Garmin | Web-first (+ coach tools) |

## Honest gap — hvor vi ligger bak

1. **Plan-engine:** HumanGO / TrainAsONE / Athletica *eier* den daglige planen og tilpasser den. Vi viser makro og lar Intervals eie dagsøkter.
2. **Workout UX:** Ingen øktbibliotek, ingen guided intervals på klokke, ingen «swap this session».
3. **Wellness-loop:** Ingen søvn/HRV/BIA i appen ennå — konkurrenter selger readiness.
4. **Multi-athlete:** Coach-plattformer er bygget for roster; vi har én atlet + fremtidig treningspar.
5. **Polert produkt:** Native apps, onboarding-økter, race tools — vi er pilot.

## Hvor vi er foran / annerledes (bevisst)

1. **Intervals-first companion:** Athletica synker *inn* i ICU; vi antar ICU allerede er SoT for økter og legger chat + makro *utenpå*. Mindre «bytt plattform».
2. **Personlig trener-stemme:** OPV-inspirert, Lofoten 2027, GI/skade/avtaler i profil — smal, menneskelig coach, ikke generisk «Hugo».
3. **Compliance uten skriveplikt:** Tallene regnes lokalt fra aktiviteter; ingen stille overwrite av ICU-kalender (Sync er eksplisitt, kun noter).
4. **Tykkhet:** Lavere kompleksitet — William kan forstå hele stacken (SQLite + Fly + ett LLM-kall).
5. **Triathlon + ekstrem-kontekst:** TrainAsONE er løp-only; vi er tri/Half Extreme uten å late som Norseman-volum.

## Anbefalt strategisk holdning

Ikke konkurrer på «full AI plan platform». Konkurrer på:

- **Beste chat + kontekst** for William (og senere et treningspar)
- **Makro/periodisering + compliance** som Intervals ikke viser godt
- **Ærlig sync** (preview/confirm) når noe skal inn i ICU
- Senere: dashboard (søvn/vekt-toggle) + øktbibliotek som *speiler* ICU, ikke erstatter den

## Lenker (research)

- https://humango.ai/faqs · https://humango.ai/how-it-works/coaches  
- https://trainasone.com/features/adaptive-training-plan  
- https://www.athletica.ai/ · https://athletica.ai/blog/announcing-athleticas-integration-with-intervals-icu  
- TP Virtual ↔ HumanGO: Peaksware UserVoice (Mai 2025, markert Completed for Virtual)
