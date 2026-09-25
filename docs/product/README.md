# Coach web — produktdokumentasjon

**Arbeidsbranch:** `cursor/web-coach-mvp-42ac` (ikke merge til `main` før pilot er grønn).  
**PR:** https://github.com/Wilste123/Lofoten_light/pull/13

## Indeks

| Fil | Innhold |
|-----|---------|
| [PRODUCT-PLAN.md](PRODUCT-PLAN.md) | Kanonisk produktplan (faser, fremskritt, grovplan, UX) |
| [progress-compliance.md](progress-compliance.md) | Volummål, formler, demo vs Intervals |
| [periodization-overview.md](periodization-overview.md) | App vs Intervals; `plan_blocks` |
| [mvp-scope.md](mvp-scope.md) | MVP-suksess: chat + overblikk; non-goals |
| [anti-patterns.md](anti-patterns.md) | Pondus, tool-loop, diagnose — hva vi unngår |
| [data-storage.md](data-storage.md) | SQLite + Fly volume; schema inkl. `training_pairs` |
| [athlete-profile.md](athlete-profile.md) | Profilfil-felter inkl. IBS/gluten/laktose |
| [form-estimates.md](form-estimates.md) | 5-økt-gate, MMP-FTP, VO₂ |
| [partner-sync.md](partner-sync.md) | To trenere, delte tid/sted-vinduer |
| [import-from-repo.md](import-from-repo.md) | Seed William fra `docs/athlete/` + `plans/` |

## Kode

| Sti | Rolle |
|-----|--------|
| `apps/coach-web/` | Vite-frontend (Coach / Overblikk / Du) |
| `services/coach-api/` | FastAPI + SQLite |
| `data/athletes/{id}/profile.md` | Profilfil ved onboarding / Du-lagring |
| `knowledge/ernaring/` | Ernæringskunnskap for chat (inkl. IBS/gluten) |

## Hurtigstart

Se root `README.md` og `services/coach-api/README.md` / `apps/coach-web/README.md`.
