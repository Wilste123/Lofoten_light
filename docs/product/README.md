# Coach web — produktdokumentasjon

**Arbeidsbranch:** `cursor/web-coach-mvp-42ac` (ikke merge til `main` før pilot er grønn).  
**PR:** https://github.com/Wilste123/Lofoten_light/pull/13

## Indeks

| Fil | Innhold |
|-----|---------|
| [PRODUCT-PLAN.md](PRODUCT-PLAN.md) | Kanonisk produktplan (faser, prinsipper, onboarding → profilfil) |
| [mvp-scope.md](mvp-scope.md) | MVP-suksess: chat + overblikk; non-goals |
| [anti-patterns.md](anti-patterns.md) | Ingen Pondus `coach_bot`, Slack, tool-loop chat |
| [data-storage.md](data-storage.md) | SQLite + Fly volume; schema inkl. fremtidige `training_pairs` |
| [form-estimates.md](form-estimates.md) | 5-økt-gate, MMP-FTP, VO₂-regler + kilder |
| [partner-sync.md](partner-sync.md) | To trenere, delte tid/sted-vinduer (ikke delte økter) |

## Kode

| Sti | Rolle |
|-----|--------|
| `apps/coach-web/` | Vite-frontend (Coach / Overblikk / Du) |
| `services/coach-api/` | FastAPI + SQLite |
| `data/athletes/{id}/profile.md` | Profilfil skrevet ved onboarding / Du-lagring |
| `knowledge/ernaring/` | Ernæring inkl. IBS/gluten — **ikke** onboarding-wizard |

## Hurtigstart

Se root `README.md` og `services/coach-api/README.md` / `apps/coach-web/README.md`.
