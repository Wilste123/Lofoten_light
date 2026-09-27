# Returning user — logg inn uten passord

Problem: tømmer du nettleser / `localStorage`, eller bytter enhet, mistes `lofoten_athlete_id`. Uten login så man bare **ny onboarding** og mistet tilgang til eksisterende profil (f.eks. seedet William med brukernavn `william`).

## Hvordan logge inn

1. Startskjerm: **«Jeg har allerede profil»**
2. Skriv **brukernavn** (f.eks. `william` — vises under **Du**)
3. Valgfritt (Avansert): **profil-ID** (`william-lofoten` / UUID) og/eller **invite-token**
4. Appen kaller `POST /v1/session/login` → setter `localStorage` → Coach / Overblikk / Du

**Ny bruker** går via onboarding (`POST /v1/onboarding`) og **må velge unikt brukernavn** (foreslås fra visningsnavn).

| Felt | Rolle |
|------|--------|
| **`username`** | Primær login (lowercase slug, f.eks. `william`) — unik |
| **`athlete_id`** | Avansert / bookmarks (`william-lofoten`, UUID) |
| **invite-token** | Valgfritt (fase 3-klar) |

## Snarveier (samme login-sti)

| Snarvei | Effekt |
|---------|--------|
| `?user=william` | Login med brukernavn |
| `?athlete=william-lofoten` | Login med intern profil-ID |
| Knapp **«Bruk seedet William-profil»** | Login med brukernavn `william` |

## Finn / lagre brukernavn

Under **Du → Brukernavn** kan du kopiere. Lagre det (notes, passordmanager, bookmark med `?user=…`). Profil-ID ligger under Avansert — trengs sjelden.

## API

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
- **404** — ukjent brukernavn / ID (norsk feilmelding)
- **401** — invite-token sendt men ugyldig
- **422** — verken `username` nor `athlete_id`

`POST /v1/session/bootstrap` finnes fortsatt (mild «needs_onboarding»); UI bruker **login** for reconnect.

## Bevisst ikke

Ingen OAuth, passord eller Supabase i MVP. Invite-flow for treningspar er fase 3 — token-feltet er klar for det.
