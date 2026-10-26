# Rethink-spor — context pack (agent-modus tree)

Grein **`rethink`** basert på **`cursor/uke1-bakke-5x2-tor-634c`** — samme rike coach-kontekst som Agent modus-chatten (pilot-docs, plans, TB/readiness, R-HILL-5x2, Intervals-scripts).

*Ikke* tynn `main`. *Ikke* `supabase`.

## Hvorfor denne basen

| | |
|--|--|
| Parent | `cursor/uke1-bakke-5x2-tor-634c` (~45 commits foran `origin/main`) |
| Innhold William peker på | Agent modus pilot, `plans/`, workouts (inkl. `R-HILL-5x2`), TB/readiness-scripts, athlete docs, Intervals-tooling |
| `main` | For tynn — mangler pilot/TB/rike økter |

PR-base: **`cursor/uke1-bakke-5x2-tor-634c`** (diff = kun rethink-scaffold).

## First slice

```bash
python3 scripts/build_context_pack.py
python3 scripts/build_context_pack.py --fetch-icu --days 14
python3 scripts/build_context_pack.py --json
```

Output (gitignored): `data/context/context-pack.md`

Packen leser bl.a.:

1. `docs/athlete/*` (profil, mål, TB-config, plager)
2. `docs/coach/agent-modus-pilot-2026-10.md`
3. Nyeste `plans/*uke*`
4. Nøkkeløkter (`R-HILL-5x2`, myr, elghufs) + `workouts/index.md`
5. ICU CSV 7–14d + `compute_readiness` TB-Score når data finnes

## Anbefaling

**Context pack først** — ikke RAG/MCP. Se prosjekt-memo `docs/context-rethink.md`.
