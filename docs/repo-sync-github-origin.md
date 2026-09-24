# Synk Cursor/Origin ↔ GitHub (uten lokal terminal)

Dette repoet ble **primært pushet til Origin** (`origin.cursor.com/.../Lofoten_Light_agent`).  
Et **duplikat på GitHub** oppdateres ikke automatisk. Du trenger **ikke** programvare på PC — kun secrets i Cursor + én Cloud Agent-kjøring.

## Anbefalt «source of truth»

| Etter sep 2026 | Primær |
|----------------|--------|
| Plan, Intervals, coach-filer | **Origin `main`** (Cursor Cloud Agent) |
| GitHub | Speil / backup / Actions secrets (`INTERVALS_API`) |

## Steg 1 — GitHub token (én gang)

1. GitHub → **Settings** → **Developer settings** → **Fine-grained personal access token** (eller classic PAT).
2. Repository access: **kun** `Lofoten_Light_agent`.
3. Permissions: **Contents** → Read and write.
4. Cursor → **Dashboard** → **Cloud Agents** → **Environments** → ditt miljø → **Secrets**:
   - Legg til **`GITHUB_TOKEN`** = tokenet (ikke committes i repo).

`INTERVALS_API` kan ligge i GitHub repo secrets *og* i Cursor secrets — det er greit.

## Steg 2 — Be Cloud Agent merge (chat)

Skriv f.eks.: «Synk GitHub og Origin — kjør repo-sync».

Agenten kjører da (med begge remotes):

```bash
git remote add github "https://x-access-token:${GITHUB_TOKEN}@github.com/william-berg-steffenak/Lofoten_Light_agent.git" 2>/dev/null || true
git fetch origin main
git fetch github main
git checkout main
# Se hva som er forskjellig:
git log --oneline --left-right main...github/main | head -40
# Merge begge veier inn i én main (typisk):
git merge github/main -m "Merge GitHub main into unified main"
# Løs evt. konflikter i agenten, deretter:
git push origin main
git push github main
```

Hvis **GitHub bare er bak** (ingen unike commits der): kan bruke `git push github main` uten merge (overskriver GitHub med Origin).

## Steg 3 — Fremover (unngå duplikat-problemet)

- Kjør **Cloud Agent på repoet som er koblet til Origin**, og la agenten **pushe til begge** etter endringer (`origin` + `github`).
- Eller: koble **samme** GitHub-repo i Cursor-prosjektinnstillinger slik at IDE/cloud skriver til GitHub — avklar én primær forge med teamet.

## Uten token (kun nød-løsning)

- Last ned **ZIP** av `main` fra Origin/Cursor (hvis UI tilbyr det) og **Last opp filer** på GitHub web — **ikke** anbefalt for hele repo (mange filer, ingen git-historikk).
- **GitHub Codespaces** i nettleseren (ingen install på PC): clone GitHub-repo, legg til Origin-remote med token, merge, push — samme git-kommandoer som over, men i browser-IDE.

## Relatert

- [`IMPORT-INTERVALS.md`](../IMPORT-INTERVALS.md) — plan på Intervals (kun på Origin `main` til GitHub er synket).
