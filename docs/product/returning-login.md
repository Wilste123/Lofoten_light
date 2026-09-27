# Returning user — logg inn uten passord

Problem: tømmer du nettleser / `localStorage`, eller bytter enhet, mistes `lofoten_athlete_id`. Uten login så man bare **ny onboarding** og mistet tilgang til eksisterende profil (f.eks. seedet `william-lofoten`).

## Mål (kanonisk plan)

Login skal støtte **brukernavn** — ikke bare rå athlete-id:

| Felt | Rolle |
|------|--------|
| **`username`** | Primær login (slug, f.eks. `william`) — unik per atlet |
| **`athlete_id`** | Valgfritt for power users / bookmarks (`william-lofoten`, UUID) |
| **invite-token** | Valgfritt (fase 3-klar) |

- Onboarding: velg unik **brukernavn**-slug (lagres på athlete)
- Seed: `william-lofoten` speiles som brukernavn `william` (eller liknende)
- Under **Du**: vis **brukernavn** + profil-ID (begge kopierbare)
- `POST /v1/session/login` aksepterer `{ "username": "…" }` **eller** `{ "athlete_id": "…" }`

## Status

| Del | Status |
|-----|--------|
| Login med **athlete-id** / profil-ID | Landet (`6ce6872`) |
| Login med **username** + onboarding-slug | **I arbeid** (egen worker) — se PRODUCT-PLAN fase **2d+** |

## Hvordan logge inn (nå / snart)

1. Startskjerm: **«Jeg har allerede profil»**
2. Skriv **brukernavn** (mål) — midlertidig fortsatt **profil-ID** til 2d+ lander
3. Valgfritt: lim inn athlete-id eller **invite-token**
4. Appen kaller `POST /v1/session/login` → setter `localStorage` → Coach / Overblikk / Du

**Ny bruker** går fortsatt via vanlig onboarding (`POST /v1/onboarding`) — skal også samle username.

## Snarveier

| Snarvei | Effekt |
|---------|--------|
| `?athlete=william-lofoten` | Login med den ID-en (beholdes) |
| Knapp **«Bruk seedet William-profil»** | Login med seedet profil |
| Senere: `?user=william` | Valgfri username-snarvei |

## Finn / lagre

Under **Du**: kopier **brukernavn** (primært) og **profil-ID** (backup). Bookmark med `?athlete=…` fungerer fortsatt.

## API (mål)

```http
POST /v1/session/login
{ "username": "william" }
```

eller

```http
POST /v1/session/login
{ "athlete_id": "william-lofoten", "invite_token": "…" }
```

- **200** — `{ athlete, needs_onboarding: false }` (oppretter aldri ny utøver)
- **404** — ukjent username / ID
- **401** — invite-token sendt men ugyldig

`POST /v1/session/bootstrap` finnes fortsatt (mild «needs_onboarding»); UI bruker **login** for reconnect.

## Bevisst ikke

Ingen OAuth, passord eller Supabase i MVP. Invite-flow for treningspar er fase 3 — token-feltet er klar for det.
