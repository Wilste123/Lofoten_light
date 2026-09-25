# Fly.io — coach-web (telefon-test)

Én Fly-app serverer **API + web** (samme origin). SQLite på volume `/data`. William-seed kjører ved boot.

**Branch:** `cursor/web-coach-mvp-42ac` · app-navn i `fly.toml`: `lofoten-coach` · region `ams` (eksisterende app; bytt til `arn` senere om du vil).

Cloud-agenten har **ikke** Fly-login — du kjører deploy fra egen PC (eller limer inn `FLY_API_TOKEN` senere).

## Første gang (fra laptop)

```bash
# 1) Branch + tools — MÅ stå i repo-roten (cd ~/Lofoten_light)
git checkout cursor/web-coach-mvp-42ac
git pull
# installer flyctl: https://fly.io/docs/hands-on/install-flyctl/
fly auth login

# 2) App finnes ofte allerede — ignorer "Name has already been taken"
fly apps list   # skal vise lofoten-coach

# 3) Volume i SAMME region som maskinen (sjekk: fly status -a lofoten-coach)
fly volumes list -a lofoten-coach
# Hvis maskin er i ams og volume mangler der:
fly volumes create coach_data --app lofoten-coach --region ams --size 1

# 4) Secrets — BRUK ANFØRSELSTEGN; lim aldri nøkkel i Slack/Cursor-chat
fly secrets set OPENAI_API_KEY='sk-...' --app lofoten-coach

# 5) Deploy
fly deploy --app lofoten-coach
```

Hvis deploy sier `ams=1` mangler volume: opprett volume i **ams**, ikke arn.
## På telefon

1. Åpne https://lofoten-coach.fly.dev  
2. **«Jeg har allerede profil»** → lim inn `william-lofoten` (eller Din profil-ID fra Du),  
   eller **«Bruk seedet William-profil»**, eller bookmark  
   `https://lofoten-coach.fly.dev/?athlete=william-lofoten`
3. Intervals: **Du**-fanen (nøkkel lagres på Fly-volume, ikke i telefonen).
4. Lagre **Din profil-ID** under Du — trengs etter tømt nettleser. Se [returning-login.md](returning-login.md).

## Oppdater etter kodeendring

```bash
fly deploy --app lofoten-coach
```

Seed er idempotent (`SEED_ON_BOOT=1`). Volume beholdes.

## Secrets vs git

| Hemmelighet | Hvor |
|-------------|------|
| `OPENAI_API_KEY` | `fly secrets set` |
| Intervals ID + nøkkel | App **Du** → SQLite på volume |
| `.env` | aldri commit / ikke nødvendig på Fly |

## Feilsøk

```bash
fly logs --app lofoten-coach
fly ssh console --app lofoten-coach
# inne: ls /data && ls /data/athletes
```

## Kostnad

`min_machines_running = 0` + auto-stop → billig hobby. Første request etter pause kan ta noen sekunder (cold start).
