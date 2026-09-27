# Kunnskapsbase — treningscoach (utvidet)

Referanse for **topp-coach**-agenten og web-MVP (setup / plan / session-chat).
Alt skal kunne brukes til **konkrete ukeplaner** — evidensbasert der det er vitenskapelige påstander.

**Vedlikehold:** Utvid **eksisterende** filer fremfor nye overlappende docs. Nye filer kun ved klart gap uten naturlig hjem (nå: `coach/maalrealisme.md`, `lop/maraton-periodisering.md`).

**Evidensmarkering** (lett): *konsensus* · *sterk* · *moderat* · *praksis* (heuristikk).

## Start her (agent / retrieval)

1. `coach/coach-filosofi.md` — tone, nybegynner vs trent, «hvorfor uka», økt-chat, planjustering  
2. `coach/maalrealisme.md` — **mål × dose × tid** (setup alltid)  
3. `coach/treneridentitet.md` + `ole-petter-vibekken-referanse.md`  
4. `docs/athlete/profile.md` + `goals.md`  
5. `load-and-intensity.md` — soner, 80/20, periodisering base→taper, deload  
6. `coach/ukemaler.md` / `lop/ukeplaner-lav-frekvens.md` / disiplinfiler  

Retrieval: `services/coach-api/knowledge_ctx.py` (CORE_* + CONDITIONAL_PACKS).

## Indeks

<<<<<<< HEAD
| Mappe / fil | Innhold |
|-------------|---------|
| **[coach/](coach/)** | Filosofi, OPV, ukemaler, feil/fixes, generell kondis, **maalrealisme** |
| [load-and-intensity.md](load-and-intensity.md) | TSS, polarisert/pyramidal, periodisering, deload |
| [ernaring/](ernaring/) | Daglig, fueling, IBS/gluten |
| [skader/](skader/) | ACWR, styrke+concurrent, løp, oversikt + load-begrensninger |
| [svom/](svom/) | Faser, OWS |
| [sykkel/](sykkel/) | Langtur, intervall |
| [lop/](lop/) | Oppbygging, **HM**, **maraton**, lav-frekvens (inkl. 5–6 økter), styrke+løp |
| [triathlon/](triathlon/) | Periodisering (inkl. langdistanse-intro), brick, Lofoten |
| [restitusjon/](restitusjon/) | Søvn, stress, deload-triggers |
| [mental/](mental/) | Kontinuitet |
| [utstyr/](utstyr/) | Race / vinter |
| [kilder/](kilder/) | Referanser + PDF |
=======
| Mappe | Innhold |
|-------|---------|
| **[coach/](coach/)** | Filosofi, treneridentitet (OPV-modell), `opv-nokkelokter.md`, ukemaler, typiske feil |
| [ernaring/](ernaring/) | Daglig, fueling, race |
| [skader/](skader/) | ACWR, styrkeprogram, løp, oversikt |
| [svom/](svom/) | Faser 0–3, øktbibliotek, OWS/kulde |
| [sykkel/](sykkel/) | Langtur, motivasjon, intervall-presets |
| [lop/](lop/) | Oppbygging, **HM-periodisering**, lav/middels frekvens (2–5) ukeplaner, styrke+løp, nybegynner, intervall, terreng |
| [coach/ukeplaner-generell-utholdenhet.md](coach/ukeplaner-generell-utholdenhet.md) | Ikke-tri / generell kondis — 2–4 økter |
| [utstyr/](utstyr/) | Race checklist, sykkel, vinter |
| [triathlon/](triathlon/) | Brick, Lofoten, periodisering |
| [restitusjon/](restitusjon/) | Søvn, sykdom, stress |
| [mental/](mental/) | Kontinuitet, motivasjon |
| [kilder/](kilder/) | Lenker + PDF |
| [load-and-intensity.md](load-and-intensity.md) | TSS, soner, CTL |
>>>>>>> origin/cursor/fix-sessions-per-week-sync-006e

## PDF-arkiv

`external/` — IOC belastning/skade, OWS. `./scripts/fetch_knowledge_archives.sh`

## Vedlikehold

Når William får nye tester/skader: oppdater `docs/athlete/profile.md` **og** ev. relevant `knowledge/`-avsnitt.
