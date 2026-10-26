# Daglig bruk — context pack (default)

**Default denne uka:** bygg pack → `@data/context/context-pack.md` i Cursor Agent-modus.

```bash
git checkout rethink && git pull
# INTERVALS_API eller INTERVALS_API_KEY i env (samme som øvrige Intervals-scripts)
python3 scripts/build_context_pack.py --fetch-icu --days 14
```

I Agent-chat: `@data/context/context-pack.md` + f.eks. «Sjekk uka / i morgen — referer TB/ICU eller si mangler.»

Uten nøkkel: dropp `--fetch-icu` (athlete + ukeplan + nøkkeløkter fortsatt med).

Full brainstorm (prosjekt): `rethink-bruk.md` hos coordinator. Se også [README.md](README.md).
