# Supabase vs comercial (branch-status)

**Oppdatert:** 2026-10-02

| Branch | Rolle |
|--------|--------|
| **`supabase`** | Aktiv utvikling: Postgres/Supabase, coach-api, two-tier plan, ICU push (preview→confirm), beta forecasts, ticker/e-post. |
| **`comercial`** | Eldre tip — **merge-base = siste commit på comercial**; alt fra comercial ligger allerede i `supabase` + 6 commits foran. |
| **`main`** | Coach-repo (planer/scripts) uten `apps/` / `services/`. |

Ingen merge fra `comercial` nødvendig med mindre noen har pushet unike commits kun til comercial senere. Sjekk med:

```bash
git fetch origin supabase comercial
git log --oneline origin/comercial..origin/supabase
git log --oneline origin/supabase..origin/comercial
```
