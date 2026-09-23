# Kunnskapsbase — treningscoach

Strukturert referanse for agenten og William. Innholdet er **sammendrag og anvendt kunnskap** med kildehenvisninger — ikke erstatning for lege/fysioterapeut ved skade.

## Indeks

| Mappe | Innhold |
|-------|---------|
| [ernaring/](ernaring/) | Daglig ernæring, fueling, tri-spesifikke situasjoner |
| [skader/](skader/) | Belastning, ACWR, forebygging, løp/sykkel/svøm |
| [svom/](svom/) | Teknikk, volum, svak svømmer → tri, åpent vann/kulde |
| [sykkel/](sykkel/) | Zoner, intervaller, rulle, landevei, terreng |
| [lop/](lop/) | Oppbygging, skadefri volum, intervaller, fjell |
| [utstyr/](utstyr/) | Tri-pakke, sykkel, våtdrakt, Trøndelag/vinter |
| [triathlon/](triathlon/) | Brick, Lofoten Half Extreme, periodisering mot 2027 |
| [restitusjon/](restitusjon/) | Søvn, stress, recovery |
| [mental/](mental/) | Kontinuitet, motivasjon (sykkel vs løp) |
| [kilder/](kilder/) | Lenker og nedlastede arkiv |
| [load-and-intensity.md](load-and-intensity.md) | TSS, soner, ukestruktur (eksisterende) |

## Nedlastede arkiv (`external/`)

| Fil | Kilde |
|-----|--------|
| `ioc-load-injury-consensus-2016.pdf` | IOC/BJSM — belastning og skaderisiko |
| `mso-open-water-swimming-safety.pdf` | Masters Swimming Ontario — OWS sikkerhet |

Oppdater arkiv:

```bash
./scripts/fetch_knowledge_archives.sh
```

## Hvordan agenten skal bruke dette

1. Ved **planlegging**: `triathlon/periodisering-mot-2027.md` + `load-and-intensity.md` + `docs/athlete/profile.md`
2. Ved **svøm**: `svom/` + `triathlon/lofoten-half-extreme.md` (1,9 km havn)
3. Ved **skadefrihet**: `skader/belastningsstyring-acwr.md` før volumøkning mot 750–800 t/år
4. Ved **utstyr/kulde**: `utstyr/` + `svom/apent-vann-kulde.md`

William: Half Extreme **2027** — bruk Lofoten-dokumentet som **distansespesifikasjon**, ikke nødvendigvis årets dato.
