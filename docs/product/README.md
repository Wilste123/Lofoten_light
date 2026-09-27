# Coach web — produktdokumentasjon

**Arbeidsbranch:** `cursor/web-coach-mvp-42ac` (ikke merge til `main` før pilot er grønn).  
**PR:** https://github.com/Wilste123/Lofoten_light/pull/13

## Indeks

| Fil | Innhold |
|-----|---------|
| [PRODUCT-PLAN.md](PRODUCT-PLAN.md) | Kanonisk produktplan (faser, dashboard, øktbibliotek, UX) |
| [gap-analysis-2026-09-27.md](gap-analysis-2026-09-27.md) | Fersk gap vs branch HEAD `5cfb32f` + Fly health |
| [competitor-humango.md](competitor-humango.md) | HumanGO / TrainAsONE / Athletica — feature-tabell |
| [gap-analysis.md](gap-analysis.md) | Eldre gap (pre-dashboard-plan); se 2026-09-27 for aktuell |
| [progress-compliance.md](progress-compliance.md) | Volummål, formler, demo vs Intervals |
| [dashboard-okter.md](dashboard-okter.md) | Dashboard, Økter, kropp-toggle, øktlogg |
| [periodization-overview.md](periodization-overview.md) | App vs Intervals; `plan_blocks` |
| [mvp-scope.md](mvp-scope.md) | MVP-suksess: chat + Dashboard + Økter; non-goals |
| [anti-patterns.md](anti-patterns.md) | Pondus, tool-loop, diagnose — hva vi unngår |
| [data-storage.md](data-storage.md) | SQLite + Fly volume; schema inkl. `training_pairs` |
| [athlete-profile.md](athlete-profile.md) | Profilfil-felter inkl. IBS/gluten/laktose |
| [form-estimates.md](form-estimates.md) | 5-økt-gate, MMP-FTP, VO₂ |
| [partner-sync.md](partner-sync.md) | To trenere, delte tid/sted-vinduer |
| [import-from-repo.md](import-from-repo.md) | Seed William fra `docs/athlete/` + `plans/` |
| [fly-deploy.md](fly-deploy.md) | Fly.io deploy + secrets + telefon-test |
| [returning-login.md](returning-login.md) | Reconnect: **username** (mål) + athlete-id; uten passord |
| [onboarding-setup.md](onboarding-setup.md) | AI-samtale + knowledge → plan-preview → confirm; restart/logout |

## Kode

| Sti | Rolle |
|-----|--------|
| `apps/coach-web/` | Vite-frontend (Coach / Dashboard / Plan / Økter / Du) |
| `services/coach-api/` | FastAPI + SQLite |
| `data/athletes/{id}/profile.md` | Profilfil ved onboarding / Du-lagring |
| `knowledge/ernaring/` | Ernæringskunnskap for chat (inkl. IBS/gluten) |

## Hurtigstart

Se root `README.md` og `services/coach-api/README.md` / `apps/coach-web/README.md`.
