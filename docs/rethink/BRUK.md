# Daglig bruk — context pack (default)

**Hard priority:** råd skal bygge på **info om William** + **`knowledge/`** — ikke internett / generisk web-coaching.

| Tillatt | Forbudt |
|---------|---------|
| `knowledge/`, `docs/athlete/`, `plans/`, `workouts/`, `data/context/context-pack.md`, Intervals-fetch | Web search, usiterte internett-påstander om trening |

**Default denne uka:** bygg pack → `@data/context/context-pack.md` (+ ev. `@knowledge/coach/…`) i Cursor Agent-modus. Svar uten kilde i repo = si «mangler».

```bash
git checkout rethink && git pull
# INTERVALS_API eller INTERVALS_API_KEY i env (samme som øvrige Intervals-scripts)
python3 scripts/build_context_pack.py --fetch-icu --days 14
```

I Agent-chat: `@data/context/context-pack.md` + f.eks. «Sjekk uka / i morgen — bruk pack + knowledge; ingen web.»

Uten nøkkel: dropp `--fetch-icu` (athlete + ukeplan + knowledge + nøkkeløkter fortsatt med).

Se [README.md](README.md). Full brainstorm: prosjekt-`rethink-bruk.md`.
