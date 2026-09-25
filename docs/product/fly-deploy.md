# Fly.io — coach-web (telefon-test)

Én Fly-app serverer **API + web** (samme origin). SQLite på volume `/data`. William-seed kjører ved boot.

**Branch:** `cursor/web-coach-mvp-42ac` · app-navn i `fly.toml`: `lofoten-coach` · region `arn` (Stockholm).

Cloud-agenten har **ikke** Fly-login — du kjører deploy fra egen PC (eller limer inn `FLY_API_TOKEN` senere).

## Første gang (fra laptop)

```bash
# 1) Branch + tools
git checkout cursor/web-coach-mvp-42ac
git pull
# installer flyctl: https://fly.io/docs/hands-on/install-flyctl/
fly auth login

# 2) Opprett app (hopp over hvis den finnes)
fly apps create lofoten-coach --org personal   # eller ditt org-navn

# 3) Volume for SQLite + profilfiler
fly volumes create coach_data --app lofoten-coach --region arn --size 1

# 4) Secrets (chat)
fly secrets set OPENAI_API_KEY=sk-... --app lofoten-coach
# valgfritt:
# fly secrets set OPENAI_MODEL=gpt-4o-mini --app lofoten-coach
# fly secrets set ADMIN_SEED_TOKEN=velg-en-lang-streng --app lofoten-coach

# 5) Deploy
fly deploy --app lofoten-coach
```

URL: **https://lofoten-coach.fly.dev** (eller `fly status` / `fly apps open`).

## På telefon

1. Åpne https://lofoten-coach.fly.dev  
2. Trykk **«Bruk seedet William-profil»** på onboarding — eller bookmark  
   `https://lofoten-coach.fly.dev/?athlete=william-lofoten`
3. Intervals: **Du**-fanen (nøkkel lagres på Fly-volume, ikke i telefonen).

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
