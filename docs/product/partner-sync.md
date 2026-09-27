# Treningspar — to trenere, samkjørte vinduer

**Kjernescenario:** William + samboer. Hver person har egen profil, egen trener (navn/personlighet/farge), egen Intervals-konto og egen chat.

Det som **deles** er **når og hvor** dere vil trene sammen — **ikke** samme øktinnhold.

## Modell

| Begrep | Betydning |
|--------|-----------|
| **`training_pair`** | Kobling mellom to `athlete_id` (begge godtar invite/pair-kode) |
| **Egen trener** | `coach_display_name`, personlighet, aksent per atlet |
| **Delingsnivå** | `schedule_windows` — disiplin + start/slutt + sted (f.eks. «basseng») |
| **Ikke delt** | Skadehistorikk, chat, FTP, avtaler, full øktbeskrivelse |

## Hvordan «trenerne snakker sammen»

**Ikke:** to LLM-er som chatter med hverandre.

**Ja:** begge coaches får samme deterministiske **`partner_slots`** i overview/chat-snapshot:

- Partner planlagt: `tir 19:00–20:00 · svøm · basseng` (kort tittel, ikke sett/reps)
- Egne preferanser: «foretrekker basseng tir/tor kveld»

Når William spør «kan vi svømme sammen i kveld?», foreslår Rocky **samme vindu**, **forskjellig økt**. Partneren spør sin trener — konsistent tidsluke.

## Samkjør-økt (valgfri)

Rad i `coordinated_sessions`: `pair_id`, `starts_at`, `venue`, `discipline`, `athlete_a_workout_note`, `athlete_b_workout_note`. Hver trener skriver kun *sin* note; tid/sted er felles. Begge bekrefter.

## Faseplassering

- **Fase 1–2:** én atlet — schema klar for `training_pairs` (tom).
- **Fase 3:** invite + pair + `partner_slots` i overview/chat — før generisk «mange venner».

## Bevisst utenfor scope

- Felles Intervals-kalender  
- Én chat for begge  
- Automatisk omskriving av partners plan uten bekreftelse  
- «Coach summit» (LLM A ↔ LLM B)  
