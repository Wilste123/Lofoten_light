# Analyse — treningsbibliotek (Ole, 2026-09)

Lesing av `workouts/`, `knowledge/`, og første 4-ukersplan. **Ingen gjetting** om Williams nåværende FTP/CSS — anbefalinger er fasebaserte.

## Sterkt

1. **ID-system (B/S/R/ST)** koblet til ZWO og nå `workouts/catalog.md` + `workouts/sessions/`.
2. **Sykkelmanifest** gir konsistent % FTP og dekker Z2 → threshold → VO2 → langtur.
3. **Svøm/løp ZWO** på norsk med TP workaround dokumentert.
4. **Styrke** koblet til `forebygging-styrke-mobilitet.md` — kritisk for comeback.
5. **Første blokk** er konservativ (uke 1 ~5,6 t) — riktig mot MSK, ikke 2019.

## Svakheter (rettet i denne runden)

| Problem | Tiltak |
|---------|--------|
| Planer pekte på `workouts/swim/*.md` som ikke fantes | `workouts/sessions/*.md` + oppdaterte ukeplaner |
| S03 uten Plan B i filer | `S03b-aerob-3x400.zwo` |
| Recovery-løp bare R01 forkortet | `R14-recovery-30.zwo` |
| Ingen FTP-test i bibliotek | `B17` / `ftp-ramp-test.zwo` |
| Agent kunne «hallusinere» soner | `ole-grenser.md` + AGENTS/regel |

## Hull som gjenstår (krever William)

- **CSS / FTP 2026** — S05–S07 skal ikke brukes som pace-økter før test.
- **OWS** — S08 krever faktisk sjø/temperatur; se `apent-vann-kulde.md`.
- **B05/B13** — 4,5–5 t sykkel krever fueling-praksis og tid i kalender.
- **ACWR** — uten TP-eksport er trend usikker; legg CSV i `data/trainingpeaks/exports/`.

## Disiplin-dekning mot Half Extreme 2027

| Ben | Dekning nå | Neste utvidelse (fase) |
|-----|------------|-------------------------|
| Svøm | S01–S10, teknikk→aerob | S04 kontinuerlig nov; CSS des |
| Løp | R01–R05 easy + R08 bakke senere | R06 tempo etter LTHR-test |
| Sykkel | B01–B04 Z2 | B06 SS etter FTP; B12–B13 jun–jul |
| Brick | BR01–03 | BR01 etter 4+ uker stabil sykkel+løp |
| Styrke | ST01–03 | ST02 fra base solid |

## Rotasjonsprinsipp (build)

Maks **én** hard sykkel **og** **én** hard løp per uke — ikke samme uke som B15 + R11. Se `knowledge/sykkel/intervaller-og-sonearbeid.md` og `coach/feil-og-fixes.md`.

## Vedlikehold

Etter endring i `run_swim_zwo.py` eller `manifest.json`:

```bash
python3 scripts/build_zwo_library.py
./scripts/zip_zwo_library.sh
```

Oppdater `catalog.md` og `sessions/` når nye ID-er legges til.
