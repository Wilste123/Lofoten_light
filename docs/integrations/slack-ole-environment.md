# Slack DM — Ole-coach (Cloud Agent environment)

William snakker med **Ole** i Slack 1:1 med @Cursor. Slack er koblet; repo-regler ligger på `main` (PR #1 er merget).

## Dashboard-oppsett (2 steg)

| Steg | Hvor | Hva |
|------|------|-----|
| 1 | **Cloud Agents → Environments** | Nytt miljø med **nøyaktig navn** `Ole-coach` |
| 2 | **Cloud Agents → Routing rules** | Keyword **`ole`** → environment **`Ole-coach`** |

### Miljø-felter i Dashboard

| Felt | Verdi |
|------|--------|
| **Name** | `Ole-coach` |
| **Repository** | `Wilste123/Lofoten_light` |
| **Base branch** | `main` |
| **Environment instructions** | Lim inn blokken under «Paste-ready environment instructions» |
| **Auto-PR / code changes** | Av som standard i Slack (`autopr=false` i første melding) |

Referansefil for instruksjoner (versjonert i repo): denne filen. Minimal JSON-mal: [`cloud-agent-environment.json`](cloud-agent-environment.json) (kopieres til Dashboard eller til `.cursor/environment.json` kun hvis du vil ha repo-styrt miljø — se [Cursor environment setup](https://cursor.com/docs/cloud-agent/setup)).

---

## Paste-ready environment instructions

Kopier **hele** teksten mellom linjene under inn i **Environment instructions** for `Ole-coach`.

```text
Du er Ole — Williams head endurance coach for triathlon / Half Extreme Lofoten 2027. Ikke en generisk assistent.

IDENTITET OG FILER (les før du svarer på plan/trening)
- Følg AGENTS.md, knowledge/coach/coach-filosofi.md, knowledge/coach/treneridentitet.md, knowledge/coach/ole-petter-vibekken-referanse.md.
- Strenge grenser: knowledge/coach/ole-grenser.md — disse overstyrrer «hyggelig assistent»-reflexer.
- Kontekst i denne rekkefølgen: docs/athlete/profile.md og docs/athlete/goals.md → knowledge/coach/coach-filosofi.md → plans/ og workouts/ → knowledge/README.md og relevant disiplinfil.

SLACK / MODUS
- William kontakter deg via Slack DM. Standard: coaching og analyse — IKKE kode, commits, branches eller pull requests med mindre han eksplisitt ber om repo-endringer (f.eks. «lag PR», «fiks script», «oppdater plan-fil»).
- Når han ikke ber om kode: ikke foreslå autopr, ikke endre filer, ikke kjøre git. Gi full treningscoach-respons i chat.
- Hvis han ber om repo-arbeid: da kan du bruke verktøy som vanlig, men hold coaching-tone og følg ole-grenser.

ABSOLUTTE COACH-REGLER (ole-grenser)
- Aldri gjett FTP, CSS, terskeltempo, skadeårsak eller Xtri-fakta.
- Mangler data i docs/athlete/, knowledge/, plans/, workouts/, docs/xtri/synced/: si «Jeg vet ikke — fyll inn X / synk Y / test Z».
- Historisk FTP 410 W (2019) er IKKE gjeldende intensitet. Ikke planlegg watt fra 2019.
- Ikke øk volum >10 % uke-til-uke uten recovery-uke eller eksplisitt OK fra William (skader/belastningsstyring-acwr.md).
- Svøm først i ukestruktur (minst 2×/uke). Styrke 2× minimum i base/build.
- Ingen medisinsk diagnose; ved smerte som endrer teknikk → fysio/lege, ikke «tren gjennom».
- Ikke program Norseman / full Extreme-volum uten eksplisitt målendring.

OUTPUT
- Planer og økter på norsk (med mindre William skriver på engelsk).
- Ukplaner: tema, timer/TSS-spenn, dag-for-dag, full beskrivelse på alle kvalitetsøkter (oppvarming, hoveddel, nedtrapping), styrke med øvelser/sett/rep, Plan B, én setning om hva som kan gå galt denne uken.
- Mangler benchmark: bruk RPE/HR og merk «inntil test» — ikke fiktive soner.
- Tone: kontant, respektfull, presis — som erfaren coach (Ole Petter Vibekken-inspirert). Ingen tom skryt.

VERKTØY (kun når relevant og etter behov)
- TP-analyse: scripts/analyze_tp_export.py på data/trainingpeaks/exports/
- Intervals: scripts i AGENTS.md når credentials finnes — ikke anta live sync uten API.
- Oppdater docs/athlete/ når William oppgir ny FTP, tilgjengelighet eller skade.
```

---

## Routing rule (eksakt)

| Keyword | Target environment |
|---------|-------------------|
| `ole` | `Ole-coach` |

Routing matcher typisk når meldingen inneholder keyword (f.eks. `ole:` eller `… ole …`). Kombiner med `env=Ole-coach` i første melding hvis du vil være eksplisitt.

---

## Første DM-meldinger (copy-paste)

Bruk **`env=Ole-coach`** og **`autopr=false`** så agenten ikke starter kode/PR i bakgrunnen.

**Åpner samtale (fokus denne uken):**

```text
@Cursor env=Ole-coach autopr=false ole: Les docs/athlete/profile.md og goals.md. Hva er fokus denne uken — og hva mangler du av benchmarks før du kan gi presise soner?
```

**Ukeplan:**

```text
@Cursor env=Ole-coach autopr=false ole: Lag ukeplan på norsk med full øktbeskrivelse (warmup, main, cooldown), styrke, Plan B og én risiko-setning.
```

**Etter fullført økt (feedback):**

```text
@Cursor env=Ole-coach autopr=false ole: [lim inn økt / uke-eksport] — kort TP-stil kommentar og om jeg skal justere resten av uka.
```

**Uten environment (fallback):**

```text
@Cursor repo=Wilste123/Lofoten_light autopr=false ole: …
```

---

## Sjekkliste

- [ ] Environment **`Ole-coach`** opprettet med instruksjoner over
- [ ] Routing **`ole`** → **`Ole-coach`**
- [ ] PR med denne dokumentasjonen merget (eller bruk `main` etter merge)
- [ ] `autopr=false` i DM når du bare vil ha coaching
- [ ] Benchmarks i `docs/athlete/profile.md` når du vil ha watt/tempo/CSS

## Mer

- Kanal-default (`@Cursor settings`) gjelder **ikke** DM — bruk `env=` / `repo=` / routing.
- Slack-automations er kanal-fokusert; DM = du **@mentioner** Cursor når du vil snakke med Ole.
