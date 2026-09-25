# Returning user — logg inn uten passord

Problem: tømmer du nettleser / `localStorage`, eller bytter enhet, mistes `lofoten_athlete_id`. Uten login så man bare **ny onboarding** og mistet tilgang til eksisterende profil (f.eks. seedet `william-lofoten`).

## Hvordan logge inn

1. Startskjerm: **«Jeg har allerede profil»**
2. Lim inn **profil-ID** (`william-lofoten` eller UUID fra Du)
3. Valgfritt: **invite-token** hvis du har fått én (valideres mot `invites`-tabellen)
4. Appen kaller `POST /v1/session/login` → setter `localStorage` → Coach / Overblikk / Du

**Ny bruker** går fortsatt via vanlig onboarding (`POST /v1/onboarding`).

## Snarveier (samme login-sti)

| Snarvei | Effekt |
|---------|--------|
| `?athlete=william-lofoten` | Login med den ID-en |
| Knapp **«Bruk seedet William-profil»** | Login med `william-lofoten` |

## Finn / lagre ID

Under **Du → Din profil-ID** kan du kopiere ID-en. Lagre den (notes, passordmanager, bookmark med `?athlete=…`).

## API

```http
POST /v1/session/login
{ "athlete_id": "william-lofoten", "invite_token": "…" }
```

- **200** — `{ athlete, needs_onboarding: false }` (oppretter aldri ny utøver)
- **404** — ukjent ID (norsk feilmelding)
- **401** — invite-token sendt men ugyldig

`POST /v1/session/bootstrap` finnes fortsatt (mild «needs_onboarding»); UI bruker **login** for reconnect.

## Bevisst ikke

Ingen OAuth, passord eller Supabase i MVP. Invite-flow for treningspar er fase 3 — token-feltet er klar for det.
