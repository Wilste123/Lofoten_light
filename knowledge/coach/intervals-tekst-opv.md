# Intervals.icu — tekst som Ole Petter (OPV)

Kalenderbeskrivelser skal leses som **en trener som skriver til William**, ikke som en loggfil.

## Gjør

- Fullstendige setninger på norsk.
- Forklar **hvor** (3T vs hjemme), **hvordan** det skal føles (puls, rolig, ikke hero).
- Styrke: hele økta i beskrivelsen (push-script henter fra `workouts/planned/strength/*.txt` etter `---`).

Løp/svøm: **ikke** sykkel-ZWO til Intervals (viser watt). Bruk `workouts/planned/run|swim/*.txt` med `---intervals---` og syntaks som `- 40m 81-89% LTHR` / `- 500m 94% Pace`.

Sykkel: ZWO (% FTP) + coach-tekst fra `workouts/planned/bike/*.txt`.
- UKENOTE søndag 19:00: trening + kropp (vekt snitt, BIA) + **ett spørsmål** tilbake til coach.

## Ikke gjør

- Kryptiske forkortelser: «ST04+ST01», «TAK», «BIA push», «81–89% LTHR» uten å si «puls rolig ca. 134–147».
- «OPV UKE 3» som tittel i teksten — han vet hvem treneren er.
- Markere plan ferdig før økter har **full** beskrivelse og Intervals er oppdatert.

## Teknisk

```bash
python3 scripts/intervals_push_calendar.py --start 2026-09-28 --dry-run
```

Styrke-rader i CSV: `description` inneholder `workouts/planned/strength/….txt` — scriptet erstatter med brødtekst under `---`.
