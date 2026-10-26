import {
  renderAcwrRiskBar,
  renderBetaLoadTrajectory,
  renderDisciplineBars,
  renderLoadLines,
  renderVolumeBars,
  volumeBucketTitle,
} from './charts.js'
import {
  SETUP_STEPS,
  applyExtractedToDraft,
  draftPayload,
  emptySetupDraft,
  readSetupForm,
  renderSetupWizard,
} from './setup.js'
import {
  addMonths,
  buildMonthGrid,
  calendarDotsHtml,
  defaultMonthKeyForSessions,
  monthKeyFromDate,
  monthLabelNb,
  monthRange,
  sessionIsoDate,
  sessionsByDate,
  toIsoDate,
  weekRangeFromDate,
} from './plan-calendar.js'

const API = import.meta.env.VITE_API_URL || ''
const STORAGE_KEY = 'lofoten_athlete_id'

const ACCENTS = ['#1a6b4a', '#c45c26', '#1e4d6b', '#6b3a1e', '#3d5a1e', '#5a2a4a']

const PERSONALITIES = [
  { id: 'direkte', label: 'Direkte' },
  { id: 'støttende', label: 'Støttende' },
  { id: 'teknisk', label: 'Teknisk' },
  { id: 'opv', label: 'OPV-stil' },
]

const state = {
  athlete: null,
  /** null = logged in; entry | login | onboarding before session */
  gate: null,
  login: {
    username: '',
    athlete_id: '',
    invite_token: '',
  },
  tab: 'coach',
  messages: [],
  overview: null,
  dashboard: null,
  dashboardPeriod: {
    preset: '14d',
    from: '',
    to: '',
  },
  sessions: null,
  /** library | chronological */
  sessionsView: 'library',
  sessionDetail: null,
  sessionChat: {
    messages: [],
    draft: '',
    busy: false,
    error: '',
  },
  /** Visual øktbygger steps (warmup/work/recover/cooldown) */
  builderSteps: [],
  /** Edit form open by default for coach-editable sessions */
  sessionEditOpen: true,
  chatDraft: '',
  planBlocks: [],
  /** Full app plan horizon (planned_sessions) — Plan tab */
  plannedSessions: {
    sessions: [],
    total: 0,
    plan_horizon_weeks: null,
    goal_race_date: null,
    error: '',
  },
  planCalendar: {
    month: monthKeyFromDate(),
    selectedDate: null,
    syncScopeLabel: '',
    sourceFilter: 'all', // all | coach | agent | manual | app
  },
  tpSync: {
    busy: false,
    pending: null,
    message: '',
    error: '',
  },
  intervals: {
    connected: false,
    intervals_athlete_id: '',
    api_key_hint: null,
    form_athlete_id: '',
    form_api_key: '',
  },
  sync: {
    status: null,
    statusError: '',
    busy: false,
    pending: null,
    message: '',
    error: '',
  },
  /** Chat → Intervals workout proposal (preview → confirm) */
  workoutProposal: null,
  workoutRemoval: null,
  athleteTypeProposal: null,
  /** Chat → negotiated training agreements (confirm → PATCH Du) */
  agreementsProposal: null,
  /** Sunday ukesopp prompt (questions only — no auto write) */
  ukesopp: null,
  ukesoppAnswerDrafts: {},
  ukesoppSaveMessage: '',
  ukesoppSaveError: '',
  /** Deterministic week check card (load / TB / Plan B — no Intervals write) */
  weekCheck: null,
  /** Du → plan adjust preview (local blocks; Intervals only after Sync confirm) */
  planAdjust: null,
  /** Selected ids when weekly cap requires replace */
  replaceSessionIds: [],
  profileSavedForCoach: false,
  workoutSync: {
    pending: null,
    busy: false,
    message: '',
    error: '',
  },
  /** Guided setup (new user or restart) — conversation-first */
  setup: {
    mode: 'new',
    step: 'account',
    draft: emptySetupDraft({ accent_color: ACCENTS[0] }),
    messages: [],
    chatDraft: '',
    readyForPlan: false,
    preview: null,
    prepareIntervals: false,
  },
  /** Du → restart setup: 0 idle, 1 first confirm, 2 type SLETT */
  resetConfirm: 0,
  resetDeleteIcu: false,
  /** Coach ticker — athlete_events unread strip */
  ticker: {
    events: [],
    unread_count: 0,
    error: '',
  },
  /** Beta forecasts (experimental) */
  beta: null,
  betaError: '',
  busy: false,
  intervalsBusy: false,
  intervalsStatus: '',
  error: '',
  intervalsError: '',
  planError: '',
}

const app = document.getElementById('app')

function getAthleteId() {
  return localStorage.getItem(STORAGE_KEY)
}

function setAthleteId(id) {
  localStorage.setItem(STORAGE_KEY, id)
}

function clearAthleteId() {
  localStorage.removeItem(STORAGE_KEY)
}

/** Wipe all client session state so account switches cannot leak athlete facts. */
function clearSessionLocal() {
  clearAthleteId()
  state.athlete = null
  state.messages = []
  state.overview = null
  state.dashboard = null
  state.sessions = null
  state.sessionDetail = null
  state.sessionChat = { messages: [], draft: '', busy: false, error: '' }
  state.sessionEditOpen = true
  state.planBlocks = []
  state.workoutProposal = null
  state.workoutRemoval = null
  state.athleteTypeProposal = null
  state.agreementsProposal = null
  state.planAdjust = null
  state.profileSavedForCoach = false
  state.chatDraft = ''
  state.sync = {
    status: null,
    statusError: '',
    busy: false,
    pending: null,
    message: '',
    error: '',
  }
  state.workoutSync = {
    pending: null,
    busy: false,
    message: '',
    error: '',
  }
  state.intervals = {
    connected: false,
    intervals_athlete_id: '',
    api_key_hint: null,
    form_athlete_id: '',
    form_api_key: '',
  }
  state.setup = {
    mode: 'new',
    step: 'account',
    draft: emptySetupDraft({ accent_color: ACCENTS[0] }),
    messages: [],
    chatDraft: '',
    readyForPlan: false,
    preview: null,
    prepareIntervals: false,
  }
  state.login = {
    username: '',
    athlete_id: '',
    invite_token: '',
  }
  state.resetConfirm = 0
  state.resetDeleteIcu = false
  state.ticker = { events: [], unread_count: 0, error: '' }
  state.error = ''
  state.intervalsError = ''
  state.planError = ''
  state.intervalsStatus = ''
  state.busy = false
  state.intervalsBusy = false
}

/** Fresh commercial onboarding — never reuse previous localStorage athlete id. */
function startNewUserSetup() {
  clearSessionLocal()
  state.setup = {
    mode: 'new',
    step: 'account',
    draft: emptySetupDraft({ accent_color: ACCENTS[0] }),
    messages: [],
    chatDraft: '',
    readyForPlan: false,
    preview: null,
    prepareIntervals: false,
  }
  state.gate = 'onboarding'
  state.error = ''
  setAccent(ACCENTS[0])
  render()
}

function logoutLocal() {
  clearSessionLocal()
  state.gate = 'entry'
  toast('Logget ut')
  render()
}

async function api(path, { method = 'GET', body, athleteId, timeoutMs } = {}) {
  const headers = { 'Content-Type': 'application/json' }
  // undefined → session localStorage; null/'' → omit header (new-user setup must
  // NEVER reuse a previous account's id via ?? nullish coalesce).
  const id =
    athleteId === undefined ? getAthleteId() : athleteId || null
  if (id) headers['X-Athlete-Id'] = id
  // Default timeout so a wedged API (bad DATABASE_URL hang) cannot leave the
  // UI on a blank/#app forever — bootstrap and login always fail-fast.
  const ms =
    typeof timeoutMs === 'number' ? timeoutMs : DEFAULT_API_TIMEOUT_MS
  const ctrl = ms > 0 ? new AbortController() : null
  const timer =
    ctrl && ms > 0 ? setTimeout(() => ctrl.abort(), ms) : null
  let res
  try {
    res = await fetch(`${API}${path}`, {
      method,
      headers,
      body: body ? JSON.stringify(body) : undefined,
      signal: ctrl?.signal,
    })
  } catch (err) {
    if (err?.name === 'AbortError') {
      throw new Error(
        'Tidsavbrudd mot API — sjekk at tjenesten svarer (/health) og DATABASE_URL/sslmode.',
      )
    }
    throw err
  } finally {
    if (timer) clearTimeout(timer)
  }
  const data = await res.json().catch(() => ({}))
  if (!res.ok) {
    const detail = data.detail
    const msg =
      typeof detail === 'string'
        ? detail
        : Array.isArray(detail)
          ? detail.map((d) => d.msg || d).join('; ')
          : typeof detail === 'object' && detail && detail.message
            ? String(detail.message)
            : data.message || data.error || `Feil ${res.status}`
    const err = new Error(msg)
    err.detail = typeof detail === 'object' && detail && !Array.isArray(detail) ? detail : data
    throw err
  }
  return data
}

/** Client wall budget for Intervals save/verify — must exceed server soft-verify (~5s). */
const INTERVALS_CLIENT_TIMEOUT_MS = 10000
/** Default fetch budget — prevents infinite spinner when Fly/API/DB is wedged. */
const DEFAULT_API_TIMEOUT_MS = 15000
/** Slightly longer for reconnect bootstrap (login + enterApp fan-out). */
const BOOTSTRAP_API_TIMEOUT_MS = 20000

function setAccent(color) {
  document.documentElement.style.setProperty('--accent', color || ACCENTS[0])
}

function toast(msg) {
  let el = document.querySelector('.toast')
  if (!el) {
    el = document.createElement('div')
    el.className = 'toast'
    document.body.appendChild(el)
  }
  el.textContent = msg
  el.classList.add('show')
  setTimeout(() => el.classList.remove('show'), 2200)
}

function escapeHtml(s) {
  return String(s)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
}

async function enterApp(athlete, { welcome } = {}) {
  const prevId = state.athlete?.id || getAthleteId()
  const switched = Boolean(prevId && prevId !== athlete.id)
  if (switched) {
    // Drop prior account's in-memory UI — server data is scoped by header id
    state.messages = []
    state.overview = null
    state.dashboard = null
    state.sessions = null
    state.sessionDetail = null
    state.sessionChat = { messages: [], draft: '', busy: false, error: '' }
    state.planBlocks = []
    state.workoutProposal = null
    state.workoutRemoval = null
    state.athleteTypeProposal = null
    state.agreementsProposal = null
    state.planAdjust = null
    state.sync.pending = null
    state.workoutSync = { pending: null, busy: false, message: '', error: '' }
    state.chatDraft = ''
  }
  state.athlete = athlete
  state.gate = null
  state.error = ''
  state.busy = false
  setAccent(athlete.accent_color)
  setAthleteId(athlete.id)
  if (welcome) {
    state.messages = [{ role: 'assistant', content: welcome }]
  } else if (switched) {
    state.messages = []
  }
  await Promise.all([
    refreshOverview(),
    refreshIntervals(),
    refreshPlanBlocks(),
    refreshPlannedSessions(),
    refreshDashboard(),
    refreshSessions(),
    refreshTicker(),
  ])
  render()
}

function slugifyUsername(raw) {
  const text = String(raw || '')
    .normalize('NFKD')
    .replace(/[\u0300-\u036f]/g, '')
    .toLowerCase()
  const slug = text.replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '')
  return (slug || 'utover').slice(0, 32)
}

/**
 * Reconnect to existing athlete via POST /v1/session/login.
 * Does not create profiles. Prefer username; athlete_id is advanced fallback.
 * @returns {{ athlete: object, needs_setup: boolean }}
 */
async function loginSession({ username, athleteId, inviteToken } = {}) {
  const uname = String(username || '').trim().toLowerCase()
  const id = String(athleteId || '').trim()
  if (!uname && !id) {
    throw new Error('Skriv inn brukernavn')
  }
  const body = {}
  if (uname) body.username = uname
  else body.athlete_id = id
  const token = String(inviteToken || '').trim()
  if (token) body.invite_token = token
  const data = await api('/v1/session/login', {
    method: 'POST',
    body,
    athleteId: null,
    timeoutMs: BOOTSTRAP_API_TIMEOUT_MS,
  })
  if (!data.athlete) {
    throw new Error(
      uname
        ? 'Ukjent brukernavn. Sjekk stavemåte, eller opprett ny bruker.'
        : 'Ukjent profil-ID. Sjekk at ID er riktig, eller opprett ny bruker.',
    )
  }
  return {
    athlete: data.athlete,
    needs_setup: Boolean(data.needs_setup),
  }
}

/** @deprecated use loginSession — kept name for call-site clarity with id/query */
async function loginWithId(athleteId, inviteToken) {
  return loginSession({ athleteId, inviteToken })
}

/** After login: completed athletes enter the app; incomplete get AI setup. */
async function enterAfterLogin(session, { welcome } = {}) {
  const athlete = session.athlete
  if (session.needs_setup) {
    setAthleteId(athlete.id)
    state.athlete = athlete
    startRestartSetup()
    toast('Fullfør veiledet setup')
    return
  }
  await enterApp(athlete, { welcome })
}

async function bootstrap() {
  const params = new URLSearchParams(location.search)
  const fromUser = params.get('user')
  const fromQuery = params.get('athlete')
  if (fromUser || fromQuery) {
    state.busy = true
    state.error = ''
    state.gate = 'login'
    render()
    try {
      const session = fromUser
        ? await loginSession({ username: fromUser })
        : await loginWithId(fromQuery)
      await enterAfterLogin(session, {
        welcome: `Hei ${session.athlete.display_name}. Jeg er ${session.athlete.coach_display_name}. Velkommen tilbake.`,
      })
      // Drop query so refresh uses localStorage
      if (location.search) {
        history.replaceState({}, '', location.pathname)
      }
    } catch (err) {
      clearAthleteId()
      state.athlete = null
      state.gate = 'login'
      if (fromUser) state.login.username = fromUser
      if (fromQuery) state.login.athlete_id = fromQuery
      state.error = err.message || 'Kunne ikke logge inn'
      state.busy = false
      render()
    }
    return
  }

  const id = getAthleteId()
  if (!id) {
    state.athlete = null
    state.gate = 'entry'
    render()
    return
  }

  // Show a real gate immediately — blank #app looked like an infinite spinner
  // when /v1/session/login hung on a wedged Postgres lifespan.
  state.busy = true
  state.error = ''
  state.gate = 'login'
  state.login.athlete_id = id
  render()
  try {
    const session = await loginWithId(id)
    await enterAfterLogin(session)
  } catch (err) {
    clearAthleteId()
    state.athlete = null
    state.gate = 'login'
    state.login.athlete_id = id
    state.error = err.message || 'Ukjent profil'
    state.busy = false
    render()
  }
}

async function refreshOverview() {
  try {
    state.overview = await api('/v1/overview')
  } catch {
    state.overview = null
  }
}

async function refreshDashboard() {
  try {
    const p = state.dashboardPeriod || { preset: '14d' }
    const qs = new URLSearchParams()
    if (p.preset === 'custom' && p.from && p.to) {
      qs.set('period', 'custom')
      qs.set('from', p.from)
      qs.set('to', p.to)
    } else {
      qs.set('period', p.preset || '14d')
    }
    state.dashboard = await api(`/v1/dashboard?${qs.toString()}`)
  } catch {
    state.dashboard = null
  }
}

async function refreshSessions() {
  try {
    state.sessions = await api('/v1/sessions')
  } catch {
    state.sessions = null
  }
}

async function refreshTicker({ refresh = true } = {}) {
  try {
    const qs = new URLSearchParams({
      limit: '12',
      refresh: refresh ? 'true' : 'false',
    })
    const data = await api(`/v1/athlete/me/events?${qs.toString()}`)
    state.ticker = {
      events: data.events || [],
      unread_count: data.unread_count || 0,
      error: '',
      email_notify: data.email_notify || null,
    }
  } catch (err) {
    state.ticker = {
      ...(state.ticker || { events: [], unread_count: 0 }),
      error: err.message || 'Ticker feilet',
    }
  }
}

async function refreshPlanBlocks() {
  try {
    const data = await api('/v1/athlete/me/plan-blocks')
    state.planBlocks = data.blocks || []
  } catch {
    state.planBlocks = []
  }
}

async function refreshPlannedSessions() {
  try {
    const data = await api(
      '/v1/athlete/me/planned-sessions?merge_intervals=true',
    )
    const sessions = (data.sessions || []).map((s) => ({
      ...s,
      session_date: sessionIsoDate(s),
    }))
    const total = data.total ?? sessions.length
    const monthKey = defaultMonthKeyForSessions(sessions)
    if (monthKey) {
      state.planCalendar.month = monthKey
      if (!state.planCalendar.selectedDate) {
        const today = toIsoDate(new Date())
        const upcoming = sessions
          .map((s) => sessionIsoDate(s))
          .filter((d) => d >= today)
          .sort()
        if (upcoming.length) state.planCalendar.selectedDate = upcoming[0]
      }
    }
    state.plannedSessions = {
      sessions,
      total,
      plan_horizon_weeks: data.plan_horizon_weeks ?? null,
      goal_race_date: data.goal_race_date || null,
      sync_summary: data.sync_summary || null,
      intervals_connected: data.intervals_connected ?? null,
      error: '',
    }
  } catch (err) {
    state.plannedSessions = {
      sessions: [],
      total: 0,
      plan_horizon_weeks: null,
      goal_race_date: null,
      error: err.message || 'Kunne ikke hente planlagte økter',
    }
  }
}

async function refreshBeta() {
  try {
    state.beta = await api('/v1/beta/forecasts?lookback_days=90&horizon_days=28')
    state.betaError = ''
  } catch (err) {
    state.beta = null
    state.betaError = err.message || 'Beta-prognoser feilet'
  }
}

async function refreshIntervals() {
  try {
    const data = await api('/v1/athlete/me/intervals')
    state.intervals.connected = !!data.connected
    state.intervals.intervals_athlete_id = data.intervals_athlete_id || ''
    state.intervals.api_key_hint = data.api_key_hint || null
    state.intervals.form_athlete_id = data.intervals_athlete_id || ''
    // Never put the real key in state — leave blank for re-entry
    state.intervals.form_api_key = ''
  } catch {
    state.intervals.connected = false
    state.intervals.intervals_athlete_id = ''
    state.intervals.api_key_hint = null
  }
}

function render() {
  if (!state.athlete) {
    if (state.gate === 'login') {
      app.innerHTML = renderLogin()
      bindLogin()
      return
    }
    if (state.gate === 'onboarding') {
      app.innerHTML = renderOnboarding()
      bindOnboarding()
      return
    }
    app.innerHTML = renderEntry()
    bindEntry()
    return
  }
  const a = state.athlete
  const initial = (a.coach_display_name || 'T').trim().charAt(0).toUpperCase()
  setAccent(a.accent_color)
  app.innerHTML = `
    <header class="app-header">
      <div class="coach-avatar" aria-hidden="true">${escapeHtml(initial)}</div>
      <div>
        <h1>${escapeHtml(a.coach_display_name || 'Trener')}</h1>
        <p>Hei ${escapeHtml(a.display_name)} — Lofoten-coach</p>
      </div>
    </header>
    ${renderTickerStrip()}
    <main>
      <section class="panel ${state.tab === 'coach' ? 'active' : ''}" data-panel="coach">
        ${renderChat()}
      </section>
      <section class="panel ${state.tab === 'dashboard' ? 'active' : ''}" data-panel="dashboard">
        ${renderDashboard()}
      </section>
      <section class="panel ${state.tab === 'plan' ? 'active' : ''}" data-panel="plan">
        ${renderPlanTab()}
      </section>
      <section class="panel ${state.tab === 'okter' ? 'active' : ''}" data-panel="okter">
        ${renderOkterTab()}
      </section>
      <section class="panel ${state.tab === 'beta' ? 'active' : ''}" data-panel="beta">
        ${renderBetaTab()}
      </section>
      <section class="panel ${state.tab === 'du' ? 'active' : ''}" data-panel="du">
        ${renderDu()}
      </section>
    </main>
    <nav class="tabs tabs-six" aria-label="Hovedfaner">
      <button type="button" data-tab="coach" class="${state.tab === 'coach' ? 'active' : ''}">Coach</button>
      <button type="button" data-tab="dashboard" class="${state.tab === 'dashboard' ? 'active' : ''}">Dashboard</button>
      <button type="button" data-tab="plan" class="${state.tab === 'plan' ? 'active' : ''}">Plan</button>
      <button type="button" data-tab="okter" class="${state.tab === 'okter' ? 'active' : ''}">Økter</button>
      <button type="button" data-tab="beta" class="${state.tab === 'beta' ? 'active' : ''}">Beta</button>
      <button type="button" data-tab="du" class="${state.tab === 'du' ? 'active' : ''}">Du</button>
    </nav>
  `
  bindApp()
}

function renderTickerStrip() {
  const t = state.ticker || { events: [], unread_count: 0 }
  const unread = (t.events || []).filter((e) => e && e.unread)
  if (!unread.length && !t.error) {
    return ''
  }
  const items = (unread.length ? unread : t.events || [])
    .slice(0, 4)
    .map((e) => {
      const kind = escapeHtml(e.kind || '')
      const title = escapeHtml(e.title || e.kind || 'Hendelse')
      return `
        <button type="button" class="ticker-item" data-ticker-id="${escapeHtml(e.id || '')}" data-ticker-kind="${kind}">
          <span class="ticker-kind">${kind}</span>
          <span class="ticker-title">${title}</span>
        </button>`
    })
    .join('')
  return `
    <div class="ticker-strip" role="region" aria-label="Coach-varsler">
      <div class="ticker-head">
        <span class="ticker-label">Varsler${t.unread_count ? ` · ${t.unread_count}` : ''}</span>
        <button type="button" class="ticker-dismiss" id="ticker-read-all">Merk lest</button>
      </div>
      <div class="ticker-items">${items}</div>
      ${t.error ? `<p class="error tight">${escapeHtml(t.error)}</p>` : ''}
      <p class="muted tight ticker-hint">Trykk åpner bekreft/plan — aldri auto-apply eller auto-sync.</p>
    </div>
  `
}

function renderEntry() {
  return `
    <div class="onboarding entry-gate">
      <p class="brand-mark">Lofoten coach</p>
      <h1>Velkommen</h1>
      <p class="lead">Ny her, eller tilbake etter ny enhet / tømt nettleser?</p>
      ${state.error ? `<p class="error">${escapeHtml(state.error)}</p>` : ''}
      <div class="entry-actions">
        <button type="button" class="btn btn-primary" id="gate-new" ${state.busy ? 'disabled' : ''}>
          Ny bruker
        </button>
        <button type="button" class="btn" id="gate-returning" ${state.busy ? 'disabled' : ''}>
          Jeg har allerede profil
        </button>
      </div>
      <p class="muted" style="margin-top:1.5rem">Allerede seedet fra repo (Fly / lokal)?</p>
      <button type="button" class="btn secondary" id="use-seed-william" ${state.busy ? 'disabled' : ''}>
        Bruk seedet William-profil
      </button>
    </div>
  `
}

function bindEntry() {
  document.getElementById('gate-new')?.addEventListener('click', () => {
    startNewUserSetup()
  })
  document.getElementById('gate-returning')?.addEventListener('click', () => {
    state.gate = 'login'
    state.error = ''
    render()
  })
  document.getElementById('use-seed-william')?.addEventListener('click', () => {
    void runSeedWilliamLogin()
  })
}

function renderLogin() {
  const L = state.login
  const advancedOpen = !!(L.athlete_id || L.invite_token)
  return `
    <div class="onboarding">
      <p class="brand-mark">Lofoten coach</p>
      <h1>Logg inn</h1>
      <p class="lead">Skriv brukernavnet ditt (f.eks. <code>william</code>). Ingen passord.</p>
      <form id="login-form">
        <div class="field">
          <label for="login_username">Brukernavn</label>
          <input id="login_username" name="username" autocomplete="username"
            value="${escapeHtml(L.username)}"
            placeholder="william" ${state.busy ? 'disabled' : ''} />
        </div>
        <details class="login-advanced" ${advancedOpen ? 'open' : ''}>
          <summary>Avansert — profil-ID / invite</summary>
          <div class="field">
            <label for="login_athlete_id">Profil-ID</label>
            <input id="login_athlete_id" name="athlete_id" autocomplete="off"
              value="${escapeHtml(L.athlete_id)}"
              placeholder="william-lofoten eller UUID" ${state.busy ? 'disabled' : ''} />
          </div>
          <div class="field">
            <label for="login_invite_token">Invite-token (valgfritt)</label>
            <input id="login_invite_token" name="invite_token" autocomplete="off"
              value="${escapeHtml(L.invite_token)}"
              placeholder="Kun hvis du har fått token" ${state.busy ? 'disabled' : ''} />
          </div>
        </details>
        ${state.error ? `<p class="error">${escapeHtml(state.error)}</p>` : ''}
        <button class="btn btn-primary" type="submit" ${state.busy ? 'disabled' : ''}>
          ${state.busy ? 'Logger inn…' : 'Fortsett'}
        </button>
      </form>
      <p class="muted" style="margin-top:1.25rem">
        <button type="button" class="linkish" id="login-back">Tilbake</button>
        ·
        <button type="button" class="linkish" id="login-to-onboard">Ny bruker</button>
      </p>
      <p class="muted" style="margin-top:1rem">Snarvei:</p>
      <button type="button" class="btn secondary" id="use-seed-william" ${state.busy ? 'disabled' : ''}>
        Bruk seedet William-profil
      </button>
    </div>
  `
}

function bindLogin() {
  document.getElementById('login-back')?.addEventListener('click', () => {
    state.gate = 'entry'
    state.error = ''
    render()
  })
  document.getElementById('login-to-onboard')?.addEventListener('click', () => {
    startNewUserSetup()
  })
  document.getElementById('use-seed-william')?.addEventListener('click', () => {
    void runSeedWilliamLogin()
  })
  document.getElementById('login-form')?.addEventListener('submit', async (e) => {
    e.preventDefault()
    const fd = new FormData(e.target)
    const username = String(fd.get('username') || '').trim().toLowerCase()
    const athleteId = String(fd.get('athlete_id') || '').trim()
    const inviteToken = String(fd.get('invite_token') || '').trim()
    state.login.username = username
    state.login.athlete_id = athleteId
    state.login.invite_token = inviteToken
    if (!username && !athleteId) {
      state.error = 'Skriv inn brukernavn (eller profil-ID under Avansert)'
      render()
      return
    }
    state.busy = true
    state.error = ''
    render()
    try {
      // Prefer username when both filled
      const session = username
        ? await loginSession({ username, inviteToken })
        : await loginSession({ athleteId, inviteToken })
      await enterAfterLogin(session, {
        welcome: `Hei ${session.athlete.display_name}. Jeg er ${session.athlete.coach_display_name}. Velkommen tilbake — spør om mål, skade eller ukens fokus.`,
      })
      if (!session.needs_setup) toast('Innlogget')
    } catch (err) {
      state.error = err.message || 'Kunne ikke logge inn'
      state.busy = false
      render()
    }
  })
}

async function runSeedWilliamLogin() {
  state.busy = true
  state.error = ''
  render()
  try {
    const session = await loginSession({ username: 'william' })
    if (session.needs_setup) {
      throw new Error(
        'William-profil mangler setup_completed — kjør seed på nytt (SEED_ON_BOOT).',
      )
    }
    await enterAfterLogin(session, {
      welcome: `Hei ${session.athlete.display_name}. Jeg er ${session.athlete.coach_display_name}. Profilen er seedet fra repo — spør om avtaler, rygg eller ukens fokus.`,
    })
    toast('Seedet William lastet')
  } catch (err) {
    state.error =
      err.message ||
      'Fant ikke brukernavn william. Kjør seed / fly deploy med SEED_ON_BOOT=1.'
    state.busy = false
    if (!state.gate) state.gate = 'login'
    render()
  }
}

function renderOnboarding() {
  setAccent(state.setup.draft.accent_color)
  return renderSetupWizard({
    state,
    accents: ACCENTS,
    personalities: PERSONALITIES,
    escapeHtml,
  })
}

function startRestartSetup() {
  const a = state.athlete || {}
  const aid = a.id || getAthleteId()
  if (aid) setAthleteId(aid)
  state.setup = {
    mode: 'restart',
    step: 'chat',
    draft: emptySetupDraft({
      display_name: a.display_name,
      username: a.username,
      coach_display_name: a.coach_display_name,
      coach_personality: a.coach_personality,
      coach_style_note: a.coach_style_note,
      accent_color: a.accent_color || ACCENTS[0],
    }),
    messages: [
      {
        role: 'assistant',
        content: `Hei ${a.display_name || ''}. Vi nullstiller planen og bygger på nytt. Fortell mål, erfaring og begrensninger — jeg tilpasser (ikke én mal for alle).`,
      },
    ],
    chatDraft: '',
    readyForPlan: false,
    preview: null,
    prepareIntervals: false,
  }
  state.athlete = null
  state.gate = 'onboarding'
  state.resetConfirm = 0
  state.error = ''
  state.tab = 'coach'
  render()
}

async function runSetupReset() {
  state.busy = true
  state.error = ''
  render()
  try {
    const data = await api('/v1/athlete/me/setup/reset', {
      method: 'POST',
      body: {
        acknowledge_wipe: true,
        confirm_phrase: 'SLETT',
        delete_intervals_coach_events: Boolean(state.resetDeleteIcu),
        acknowledge_intervals_delete: Boolean(state.resetDeleteIcu),
      },
    })
    startRestartSetup()
    toast(data.message || 'Setup nullstilt')
  } catch (err) {
    state.error = err.message || 'Kunne ikke nullstille'
    state.busy = false
    state.resetConfirm = 0
    state.resetDeleteIcu = false
    render()
  }
}

async function generateSetupPreview() {
  state.busy = true
  state.error = ''
  render()
  try {
    const data = await api('/v1/setup/plan/preview', {
      method: 'POST',
      body: draftPayload(state.setup.draft),
      athleteId: null,
    })
    state.setup.preview = data
    state.busy = false
    render()
  } catch (err) {
    state.error = err.message || 'Kunne ikke generere plan'
    state.busy = false
    render()
  }
}

async function confirmSetupPlan() {
  state.busy = true
  state.error = ''
  render()
  try {
    const preview = state.setup.preview
    const draft = state.setup.draft
    const payload = {
      ...draftPayload(draft),
      plan_blocks: preview.plan_blocks || [],
      athlete_patch: preview.athlete_patch || {},
      prepare_intervals_sync: Boolean(state.setup.prepareIntervals),
    }
    if (state.setup.mode === 'restart') {
      payload.athlete_id = getAthleteId()
    }
    const data = await api('/v1/setup/confirm', {
      method: 'POST',
      body: payload,
      athleteId: state.setup.mode === 'restart' ? getAthleteId() : null,
    })
    const welcome =
      state.setup.mode === 'restart'
        ? `Planen er satt opp på nytt. Jeg er ${data.athlete.coach_display_name}. Si ifra om noe skal justeres.`
        : `Hei ${data.athlete.display_name}. Jeg er ${data.athlete.coach_display_name}. Grovplanen er lagret — spør gjerne om første uke.`
    await enterApp(data.athlete, { welcome })
    if (data.intervals_prep_error) {
      state.error = data.intervals_prep_error
    }
    if (data.intervals_pending) {
      state.tab = 'plan'
      state.sync.pending = data.intervals_pending
      state.sync.message = data.intervals_pending.message || ''
      render()
    }
    toast(data.message || 'Plan lagret')
  } catch (err) {
    state.error = err.message || 'Kunne ikke lagre setup'
    state.busy = false
    render()
  }
}

function bindOnboarding() {
  document.getElementById('setup-to-login')?.addEventListener('click', () => {
    state.gate = 'login'
    state.error = ''
    render()
  })
  document.getElementById('setup-back')?.addEventListener('click', () => {
    const idx = SETUP_STEPS.indexOf(state.setup.step)
    if (idx <= 0) {
      state.gate = 'entry'
      state.error = ''
      render()
      return
    }
    if (state.setup.step === 'preview') state.setup.preview = null
    state.setup.step = SETUP_STEPS[idx - 1]
    state.error = ''
    render()
  })

  const form = document.getElementById('setup-form')
  document.querySelectorAll('#setup-swatches .swatch, .setup-flow .swatch').forEach((btn) => {
    btn.addEventListener('click', () => {
      if (form) state.setup.draft = readSetupForm(form, state.setup.draft)
      state.setup.draft.accent_color = btn.dataset.color
      setAccent(btn.dataset.color)
      render()
    })
  })
  const nameInput = document.getElementById('display_name')
  const userInput = document.getElementById('username')
  nameInput?.addEventListener('input', () => {
    state.setup.draft.display_name = nameInput.value
    if (!state.setup.draft.username_touched && userInput && state.setup.mode === 'new') {
      const suggested = slugifyUsername(nameInput.value)
      state.setup.draft.username = suggested
      userInput.value = suggested
    }
  })
  userInput?.addEventListener('input', () => {
    state.setup.draft.username_touched = true
    state.setup.draft.username = userInput.value
  })
  form?.querySelector('[name=skip_intervals]')?.addEventListener('change', () => {
    state.setup.draft = readSetupForm(form, state.setup.draft)
    render()
  })

  form?.addEventListener('submit', async (e) => {
    e.preventDefault()
    state.setup.draft = readSetupForm(form, state.setup.draft)
    const step = state.setup.step
    const draft = state.setup.draft
    if (step === 'account') {
      if (!draft.display_name.trim()) {
        state.error = 'Skriv inn navnet ditt'
        render()
        return
      }
      if (state.setup.mode === 'new') {
        let username = (draft.username || '').trim().toLowerCase()
        if (!username) username = slugifyUsername(draft.display_name)
        draft.username = username
        if (username.length < 2) {
          state.error = 'Brukernavn må være minst 2 tegn'
          render()
          return
        }
      }
      state.setup.step = 'chat'
      if (!(state.setup.messages || []).length) {
        state.setup.messages = [
          {
            role: 'assistant',
            content: `Hei ${draft.display_name}. Jeg er ${draft.coach_display_name}. Fortell om mål og bakgrunn — nybegynner, comeback, skade, lite tid, eller noe annet. Vi lager planen etterpå med forhåndsvisning.`,
          },
        ]
      }
      state.error = ''
      render()
      return
    }
    if (step === 'intervals') {
      if (!draft.skip_intervals) {
        const hasId = Boolean((draft.intervals_athlete_id || '').trim())
        const hasKey = Boolean((draft.intervals_api_key || '').trim())
        if ((hasId && !hasKey) || (!hasId && hasKey)) {
          state.error = 'Fyll inn både athlete ID og API-nøkkel, eller huk av «Hopp over».'
          render()
          return
        }
      }
      state.setup.step = 'preview'
      state.setup.preview = null
      state.error = ''
      render()
      void generateSetupPreview()
    }
  })

  document.getElementById('setup-to-intervals')?.addEventListener('click', () => {
    state.setup.step = 'intervals'
    state.error = ''
    render()
  })
  document.getElementById('setup-gen-preview')?.addEventListener('click', () => {
    void generateSetupPreview()
  })
  document.getElementById('prepare_intervals_sync')?.addEventListener('change', (e) => {
    state.setup.prepareIntervals = e.target.checked
  })
  document.getElementById('setup-confirm-plan')?.addEventListener('click', () => {
    const box = document.getElementById('prepare_intervals_sync')
    if (box) state.setup.prepareIntervals = box.checked
    void confirmSetupPlan()
  })

  const chatForm = document.getElementById('setup-chat-form')
  chatForm?.addEventListener('submit', async (e) => {
    e.preventDefault()
    const input = document.getElementById('setup-chat-input')
    const text = (input?.value || '').trim()
    if (!text || state.busy) return
    state.setup.chatDraft = ''
    state.setup.messages = [...(state.setup.messages || []), { role: 'user', content: text }]
    state.busy = true
    state.error = ''
    render()
    try {
      const data = await api('/v1/setup/chat', {
        method: 'POST',
        body: {
          message: text,
          draft: draftPayload(state.setup.draft),
          history: (state.setup.messages || []).slice(0, -1).map((m) => ({
            role: m.role,
            content: m.content,
          })),
        },
        athleteId: null,
      })
      state.setup.draft = applyExtractedToDraft(
        { ...state.setup.draft, ...(data.draft || {}) },
        data.extracted || {},
      )
      // Keep account fields
      if (data.draft?.goal_text) state.setup.draft.goal_text = data.draft.goal_text
      state.setup.readyForPlan = Boolean(data.ready_for_plan)
      state.setup.messages = [
        ...(state.setup.messages || []),
        { role: 'assistant', content: data.reply || '…' },
      ]
      state.busy = false
      render()
      const log = document.getElementById('setup-chat-log')
      if (log) log.scrollTop = log.scrollHeight
    } catch (err) {
      state.error = err.message || 'Samtale feilet'
      state.busy = false
      render()
    }
  })
}

function renderChatBubbles(messages, emptyHtml) {
  const bubbles = (messages || [])
    .map((m) => `<div class="bubble ${m.role}">${escapeHtml(m.content)}</div>`)
    .join('')
  return bubbles || emptyHtml || ''
}

function renderChatComposer({
  formId = 'chat-form',
  inputId = 'chat-input',
  draft = '',
  busy = false,
  placeholder = 'Spør treneren…',
  sticky = false,
  ariaLabel = 'Chat med treneren',
} = {}) {
  return `
    <form class="chat-form${sticky ? ' chat-composer-sticky' : ''}" id="${escapeHtml(formId)}" aria-label="${escapeHtml(ariaLabel)}">
      <input id="${escapeHtml(inputId)}" autocomplete="off" placeholder="${escapeHtml(placeholder)}" value="${escapeHtml(draft)}" ${busy ? 'disabled' : ''} />
      <button class="btn btn-primary" type="submit" ${busy ? 'disabled' : ''}>Send</button>
    </form>`
}

function applyChatResponse(data, { mirrorToMain = false, userText = '' } = {}) {
  if (data.workout_proposal?.workouts?.length) {
    state.workoutProposal = data.workout_proposal
    state.workoutRemoval = null
    if (data.workout_proposal.replace_required) {
      state.replaceSessionIds = [
        ...(data.workout_proposal.replace_session_ids ||
          data.workout_replace_proposal?.replace_session_ids ||
          []),
      ]
    }
    if (data.proposal_hint) toast(data.proposal_hint)
  }
  if (data.workout_replace_proposal?.workouts?.length && !data.workout_proposal?.workouts?.length) {
    state.workoutProposal = {
      workouts: data.workout_replace_proposal.workouts,
      replace_required: true,
      replace_candidates: data.workout_replace_proposal.replace_candidates || [],
      replace_session_ids: data.workout_replace_proposal.replace_session_ids || [],
    }
    state.replaceSessionIds = [...(data.workout_replace_proposal.replace_session_ids || [])]
    if (data.proposal_hint || data.workout_replace_proposal.message) {
      toast(data.proposal_hint || data.workout_replace_proposal.message)
    }
  }
  if (data.workout_removal) {
    state.workoutRemoval = data.workout_removal
    state.workoutProposal = null
    if (data.removal_hint) toast(data.removal_hint)
  }
  if (data.athlete_type_proposal) {
    state.athleteTypeProposal = data.athlete_type_proposal
  }
  if (data.agreements_proposal) {
    state.agreementsProposal = data.agreements_proposal
    if (data.agreements_hint) toast(data.agreements_hint)
  }
  if (data.ukesopp?.questions?.length) {
    state.ukesopp = data.ukesopp
    state.ukesoppAnswerDrafts = {}
    state.ukesoppSaveMessage = ''
    state.ukesoppSaveError = ''
  } else if (data.ukesopp === null) {
    state.ukesopp = null
  }
  if (data.week_check) {
    state.weekCheck = data.week_check
    state.ukesopp = null
  }
  const planProp = data.plan_roll || data.plan_proposal
  const planHasFull = Boolean(planProp?.plan_blocks?.length)
  const planHasWeek = planProp?.scope === 'week' && Array.isArray(planProp?.sessions)
  const planHasRoll =
    (planProp?.op === 'plan_roll' || planProp?.scope === 'detalj') &&
    Array.isArray(planProp?.sessions)
  const planHasError = Boolean(planProp?.error)
  if (planHasFull || planHasWeek || planHasRoll || planHasError) {
    state.planAdjust = planProp
    if (planHasFull || planHasWeek || planHasRoll) state.agreementsProposal = null
    if (data.plan_hint) toast(data.plan_hint)
  }
  // Existing plan → Intervals near-window sync (no new week inventing).
  // Keep Coach tab when possible so the confirm card appears in chat.
  if (data.intervals_pending) {
    state.sync.pending = data.intervals_pending
    state.sync.message = data.intervals_pending.message || data.sync_hint || ''
    state.sync.error = data.intervals_prep_error || ''
    state.workoutProposal = null
    state.planAdjust = null
    if (state.tab !== 'coach' && state.tab !== 'plan') state.tab = 'plan'
    if (data.sync_hint) toast(data.sync_hint)
  } else if (data.intervals_sync_intent && data.intervals_connect_hint) {
    toast(data.intervals_connect_hint)
  } else if (data.intervals_sync_intent && data.intervals_prep_error) {
    state.sync.error = data.intervals_prep_error
    toast(data.intervals_prep_error)
  }
  // Never toast «done» from prose-only writes — card or honest block only.
  if (data.write_blocked_no_card) {
    toast('Ingenting lagret — mangler bekreftelseskort')
  } else if (data.confirm_push_done || data.write_success) {
    const saved = data.planned_sessions_saved
    const pushed = data.pushed
    const msg =
      data.reply ||
      (saved
        ? `${saved} økt(er) lagret i planen${pushed ? ` · ${pushed} på Intervals` : ''}`
        : 'Bekreftet')
    toast(msg)
    state.workoutProposal = null
    state.workoutSync.pending = null
    state.workoutSync.message = msg
  } else if (
    data.pending_write_reopen &&
    !data.workout_proposal?.workouts?.length &&
    !planHasWeek &&
    !planHasFull &&
    !planHasRoll
  ) {
    toast('Ingenting oppdatert — bekreft via kortet eller gjenta forespørselen')
  }
  if (mirrorToMain && userText) {
    state.messages = [
      ...state.messages,
      { role: 'user', content: userText },
      data.message || { role: 'assistant', content: data.reply || '…' },
    ]
  }
}

async function sendCoachMessage(message, { sessionId = null } = {}) {
  const body = { message }
  if (sessionId) body.session_id = sessionId
  return api('/v1/chat', { method: 'POST', body })
}

function renderChat() {
  const draft = state.chatDraft || ''
  const empty = `<p class="muted">Skriv til ${escapeHtml(state.athlete.coach_display_name)} — eller åpne en økt under Økter. Spør f.eks. «hva har jeg denne uka?».</p>`
  const proposal = state.workoutProposal
  const removal = state.workoutRemoval
  const typeProp = state.athleteTypeProposal
  const agrProp = state.agreementsProposal
  const wPending = state.workoutSync.pending
  const syncPending = state.sync.pending
  let proposalCard = ''
  if (syncPending?.pending_id) {
    const sample = (syncPending.events || [])
      .slice(0, 8)
      .map((e) => {
        const cat =
          e.category === 'WORKOUT' ? 'Økt' : e.category === 'NOTE' ? 'Note' : e.category || ''
        const line =
          e.preview_no ||
          `${(e.day || e.start_date_local || '').toString().slice(0, 10)} · ${e.name || ''}`
        return `<li><span class="badge badge-off">${escapeHtml(cat)}</span> ${escapeHtml(line)}</li>`
      })
      .join('')
    const wc = syncPending.workouts_count
    const nc = syncPending.notes_count
    const meta =
      wc != null
        ? Number(nc) > 0
          ? `${wc} økter + ${nc} noter · nærvindu ${syncPending.weeks ?? 2} uker`
          : `${wc} økter fra planned_sessions · nærvindu ${syncPending.weeks ?? 2} uker (uten grovplan-noter)`
        : `${syncPending.count || 0} hendelser`
    proposalCard = `
      <div class="confirm-card" role="dialog" aria-label="Bekreft Intervals-sync">
        <p><strong>${escapeHtml(syncPending.message || 'Bekreft Sync til Intervals')}</strong></p>
        <p class="muted tight">${escapeHtml(meta)}</p>
        <ul class="sync-sample">${sample}</ul>
        ${syncPending.events_truncated ? `<p class="muted tight">+${syncPending.events_truncated} til</p>` : ''}
        <div class="sync-actions">
          <button type="button" class="btn btn-primary" id="sync-confirm-yes" ${state.sync.busy ? 'disabled' : ''}>Ja, sync</button>
          <button type="button" class="btn secondary" id="sync-confirm-no" ${state.sync.busy ? 'disabled' : ''}>Avbryt</button>
        </div>
        ${state.sync.error ? `<p class="error">${escapeHtml(state.sync.error)}</p>` : ''}
      </div>`
  } else if (wPending) {
    const sample = (wPending.events?.length ? wPending.events : wPending.sessions || [])
      .slice(0, 8)
      .map(
        (e) =>
          `<li><code>${escapeHtml(e.start_date_local || e.session_date || e.day || '')}</code> · ${escapeHtml(e.name || e.external_id || '')} <span class="dim">${escapeHtml(e.type || e.sport || e.category || '')}</span></li>`,
      )
      .join('')
    const isDelete = (wPending.op || '') === 'delete'
    const savedN = wPending.planned_sessions_count ?? wPending.count
    const icuN = wPending.intervals_event_count
    proposalCard = `
      <div class="confirm-card" role="dialog" aria-label="Bekreft økt">
        <p><strong>${escapeHtml(wPending.message || 'Bekreft lagring')}</strong></p>
        <p class="muted tight">${escapeHtml(wPending.op || 'workout_push')} · ${savedN} økt(er) i plan${
          icuN != null ? ` · ${icuN} Intervals` : ''
        }</p>
        <ul class="sync-sample">${sample}</ul>
        ${wPending.write_gap ? `<p class="muted tight">${escapeHtml(wPending.write_gap)}</p>` : ''}
        <div class="sync-actions">
          <button type="button" class="btn btn-primary" id="workout-confirm-yes" ${state.workoutSync.busy ? 'disabled' : ''}>${
            isDelete ? 'Ja, slett på Intervals' : 'Ja, lagre'
          }</button>
          <button type="button" class="btn secondary" id="workout-confirm-no" ${state.workoutSync.busy ? 'disabled' : ''}>Avbryt</button>
        </div>
        ${state.workoutSync.error ? `<p class="error">${escapeHtml(state.workoutSync.error)}</p>` : ''}
      </div>`
  } else if (removal) {
    proposalCard = `
      <div class="confirm-card workout-proposal-card" aria-label="Fjern økt">
        <p><strong>Foreslått fjerning av coach-økter</strong></p>
        <p class="muted tight">Kun ll-coach-* — forhåndsvis før sletting.</p>
        <ul class="sync-sample">
          ${(removal.external_ids || []).map((id) => `<li><code>${escapeHtml(id)}</code></li>`).join('')}
          ${(removal.dates || []).map((d) => `<li>dato ${escapeHtml(d)}</li>`).join('')}
          ${(removal.names || []).map((n) => `<li>${escapeHtml(n)}</li>`).join('')}
        </ul>
        <div class="sync-actions">
          <button type="button" class="btn btn-primary" id="workout-remove-preview-btn" ${state.workoutSync.busy || !state.intervals.connected ? 'disabled' : ''}>Forhåndsvis sletting</button>
          <button type="button" class="btn secondary" id="workout-dismiss-btn" ${state.workoutSync.busy ? 'disabled' : ''}>Avvis</button>
        </div>
        ${state.workoutSync.error ? `<p class="error">${escapeHtml(state.workoutSync.error)}</p>` : ''}
      </div>`
  } else if (typeProp) {
    proposalCard = `
      <div class="confirm-card workout-proposal-card" aria-label="Oppdater hovedprofil">
        <p><strong>Oppdater hovedprofil</strong></p>
        <p class="muted tight">${escapeHtml(typeProp.from_label || typeProp.from || '—')} → <strong>${escapeHtml(typeProp.to_label || typeProp.to || '')}</strong></p>
        ${typeProp.reason ? `<p class="tight">${escapeHtml(typeProp.reason)}</p>` : ''}
        <p class="muted tight">Typen er muterbar over tid. Bekreft før plan/økter følger ny type (plan skrives ikke stille om).</p>
        <div class="sync-actions">
          <button type="button" class="btn btn-primary" id="athlete-type-confirm-btn" ${state.busy ? 'disabled' : ''}>Bekreft ny type</button>
          <button type="button" class="btn secondary" id="athlete-type-dismiss-btn">Avvis</button>
        </div>
        ${state.workoutSync.error ? `<p class="error">${escapeHtml(state.workoutSync.error)}</p>` : ''}
      </div>`
  } else if (agrProp) {
    const agrLines = []
    if (agrProp.sessions_per_week != null) agrLines.push(`${agrProp.sessions_per_week} økter/uke`)
    if (agrProp.goal_race_date) agrLines.push(`Måldato ${agrProp.goal_race_date}`)
    if (agrProp.goal_text) agrLines.push(agrProp.goal_text)
    if (Array.isArray(agrProp.allowed_disciplines) && agrProp.allowed_disciplines.length) {
      agrLines.push('Disipliner: ' + agrProp.allowed_disciplines.join(' + '))
    }
    if (Array.isArray(agrProp.agreements)) {
      for (const a of agrProp.agreements.slice(0, 6)) agrLines.push(a)
    }
    const agrList = agrLines.map((l) => `<li>${escapeHtml(String(l))}</li>`).join('')
    proposalCard = `
      <div class="confirm-card workout-proposal-card" aria-label="Oppdater treningsavtaler">
        <p><strong>Oppdater treningsavtaler</strong></p>
        ${agrProp.reason ? `<p class="tight">${escapeHtml(agrProp.reason)}</p>` : ''}
        <ul class="sync-sample">${agrList}</ul>
        <p class="muted tight">Bekreft for å lagre til Du-fanen — ingen stille endring.</p>
        <div class="sync-actions">
          <button type="button" class="btn btn-primary" id="agreements-confirm-btn" ${state.busy ? 'disabled' : ''}>Bekreft avtaler</button>
          <button type="button" class="btn secondary" id="agreements-dismiss-btn">Avvis</button>
        </div>
        ${state.workoutSync.error ? `<p class="error">${escapeHtml(state.workoutSync.error)}</p>` : ''}
      </div>`
  } else if (
    state.planAdjust?.plan_blocks?.length ||
    (state.planAdjust?.scope === 'week' && state.planAdjust?.sessions) ||
    ((state.planAdjust?.op === 'plan_roll' || state.planAdjust?.scope === 'detalj') &&
      state.planAdjust?.sessions)
  ) {
    const pa = state.planAdjust
    const isWeek = pa.scope === 'week'
    const isRoll = pa.op === 'plan_roll' || pa.scope === 'detalj'
    const sync = pa.intervals_sync || {}
    const csum =
      pa.constraints_summary_nb ||
      sync.constraints_summary_nb ||
      ''
    const horizon =
      pa.workout_horizon_note_nb ||
      pa.horizon_note_nb ||
      (isWeek
        ? 'Kirurgisk ukejustering — resten av planen beholdes.'
        : isRoll
          ? 'Neste detaljvindu — grovplan beholdes. Intervals først etter Sync.'
          : 'App-plan til måldato; Intervals WORKOUT kun nærvindu.')
    const readiness = pa.readiness_hints || pa.readiness || {}
    const readyNote =
      pa.readiness_note_nb ||
      readiness.summary_nb ||
      ''
    const rows = isWeek || isRoll
      ? (pa.sessions || [])
          .slice(0, 12)
          .map(
            (s) =>
              `<li><strong>${escapeHtml(s.session_date || '')}</strong> · ${escapeHtml(s.name || '')} · ${escapeHtml(s.sport || '')}${
                s.duration_minutes != null ? ` · ${escapeHtml(String(s.duration_minutes))} min` : ''
              }</li>`,
          )
          .join('')
      : (pa.plan_blocks || [])
          .slice(0, 8)
          .map(
            (b) =>
              `<li><strong>${escapeHtml(b.title || '')}</strong> · ${escapeHtml(b.start_date || '')}–${escapeHtml(b.end_date || '')} · ${escapeHtml(b.theme || '')}</li>`,
          )
          .join('')
    const wprev = (sync.workouts_preview || [])
      .slice(0, 8)
      .map((e) => `<li>${escapeHtml(e.preview_no || e.name || '')}</li>`)
      .join('')
    const sessN = isWeek || isRoll ? pa.count || pa.planned_sessions_count : pa.planned_sessions_count
    const hzW = pa.plan_horizon_weeks
    const title = isWeek
      ? 'Foreslått ukejustering'
      : isRoll
        ? 'Rull videre — neste detaljplan'
        : 'Foreslått planjustering'
    const confirmLabel = isWeek ? 'Bekreft uke' : isRoll ? 'Bekreft neste detalj' : 'Bekreft ny plan'
    proposalCard = `
      <div class="confirm-card workout-proposal-card" aria-label="${escapeHtml(title)}">
        <p><strong>${escapeHtml(title)}</strong></p>
        <p class="muted tight">${escapeHtml(pa.confirm_hint || pa.message || (isWeek ? 'Bekreft for å erstatte kun denne uka.' : 'Bekreft for å lagre meso-blokker + økter til måldato lokalt — ikke auto-sync til Intervals.'))}</p>
        ${csum ? `<p class="muted tight">${escapeHtml(csum)}</p>` : ''}
        <p class="muted tight">${escapeHtml(horizon)}</p>
        ${isWeek && pa.week_start ? `<p class="muted tight">${escapeHtml(pa.week_start)}–${escapeHtml(pa.week_end || '')}${pa.ease_load ? ' · lett uke' : ''}.</p>` : ''}
        ${isRoll && pa.detalj_start ? `<p class="muted tight">${escapeHtml(pa.detalj_start)}–${escapeHtml(pa.detalj_end || '')} (~${escapeHtml(String(pa.detalj_weeks || 4))} uker).</p>` : ''}
        ${sessN != null ? `<p class="muted tight">${escapeHtml(String(sessN))} økter${isWeek ? ' i uka' : isRoll ? ' i neste detalj' : ` i app-plan${hzW != null ? ` (~${escapeHtml(String(hzW))} uker)` : ''}`}</p>` : ''}
        ${pa.unchanged_note_nb ? `<p class="muted tight">${escapeHtml(pa.unchanged_note_nb)}</p>` : ''}
        ${readyNote ? `<p class="muted tight">Readiness: ${escapeHtml(readyNote)}</p>` : ''}
        ${!isWeek && !isRoll && sync.workouts_count != null ? `<p class="muted tight">${escapeHtml(String(sync.workouts_count))} WORKOUT i Intervals-nærvindu (${escapeHtml(String(pa.icu_sync_weeks || sync.weeks || 2))} uker).</p>` : ''}
        <ul class="sync-sample">${rows}</ul>
        ${wprev ? `<p class="plan-kicker">Intervals nærvindu (WORKOUT)</p><ul class="sync-sample">${wprev}</ul>` : ''}
        ${
          state.intervals?.connected
            ? `<label class="muted tight prepare-sync-opt"><input type="checkbox" id="plan-prepare-icu-sync" /> Også forbered Sync til Intervals (valgfritt — ikke auto)</label>`
            : ''
        }
        <div class="sync-actions">
          <button type="button" class="btn btn-primary" id="plan-adjust-confirm-btn" ${state.busy ? 'disabled' : ''}>${escapeHtml(confirmLabel)}</button>
          <button type="button" class="btn secondary" id="plan-adjust-dismiss-btn">Avvis</button>
        </div>
        ${state.workoutSync.error ? `<p class="error">${escapeHtml(state.workoutSync.error)}</p>` : ''}
      </div>`
  } else if (proposal?.workouts?.length) {
    const rows = proposal.workouts
      .map(
        (w) =>
          `<li><strong>${escapeHtml(w.date || '')}</strong> · ${escapeHtml(w.name || '')} · ${escapeHtml(w.sport || '')}${
            w.duration_minutes != null ? ` · ${escapeHtml(String(w.duration_minutes))} min` : ''
          }</li>`,
      )
      .join('')
    const replaceNeeded = Boolean(proposal.replace_required)
    const candidates = proposal.replace_candidates || []
    const selected = new Set(state.replaceSessionIds || proposal.replace_session_ids || [])
    const replaceList = replaceNeeded
      ? `<p class="muted tight"><strong>Uka er full</strong> — velg økt(er) å erstatte (samme dato prioriteres):</p>
        <ul class="sync-sample replace-candidates">${candidates
          .map((c) => {
            const id = String(c.id || '')
            const checked = selected.has(id) ? 'checked' : ''
            return `<li><label class="replace-pick"><input type="checkbox" class="replace-session-cb" value="${escapeHtml(id)}" ${checked}/> <strong>${escapeHtml(c.session_date || '')}</strong> · ${escapeHtml(c.name || '')}${c.same_date ? ' · samme dato' : ''}</label></li>`
          })
          .join('') || '<li class="muted">Ingen kandidater denne uka</li>'}</ul>`
      : ''
    proposalCard = `
      <div class="confirm-card workout-proposal-card" aria-label="Foreslått økt">
        <p><strong>${replaceNeeded ? 'Erstatt økt i planen' : 'Foreslått økt til planen'}</strong></p>
        <p class="muted tight">Ingenting er lagret ennå — forhåndsvis, deretter bekreft. Lagrer i app-planen${
          state.intervals.connected
            ? '; «Bekreft og push» lagrer og synker samme økt til Intervals (CLI-struktur).'
            : ' (koble Intervals under Du for Sync).'
        }</p>
        ${replaceList}
        <ul class="sync-sample">${rows}</ul>
        ${
          state.intervals.connected && !replaceNeeded
            ? `<label class="muted tight prepare-sync-opt"><input type="checkbox" id="workout-prepare-icu-sync" /> Forbered Sync til Intervals i forhåndsvisning (valgfritt)</label>`
            : ''
        }
        <div class="sync-actions">
          <button type="button" class="btn btn-primary" id="workout-preview-btn" ${state.workoutSync.busy || (replaceNeeded && !(state.replaceSessionIds || []).length) ? 'disabled' : ''}>${replaceNeeded ? 'Forhåndsvis erstatning' : 'Forhåndsvis lagring'}</button>
          ${
            state.intervals.connected && !replaceNeeded
              ? `<button type="button" class="btn secondary" id="workout-confirm-push-btn" ${state.workoutSync.busy ? 'disabled' : ''}>Bekreft og push til Intervals</button>`
              : ''
          }
          <button type="button" class="btn secondary" id="workout-dismiss-btn" ${state.workoutSync.busy ? 'disabled' : ''}>Avvis</button>
        </div>
        ${state.workoutSync.error ? `<p class="error">${escapeHtml(state.workoutSync.error)}</p>` : ''}
        ${state.workoutSync.message ? `<p class="intervals-status is-ok">${escapeHtml(state.workoutSync.message)}</p>` : ''}
      </div>`
  } else if (state.weekCheck) {
    const w = state.weekCheck
    const tb = w.tb || {}
    const load = w.load || {}
    const tbLine =
      tb.available && tb.tb_score != null
        ? `<p><strong>TB-Score ${escapeHtml(String(tb.tb_score))}/100</strong> · ${escapeHtml(tb.band || '')}</p>`
        : `<p class="muted tight">TB-Score ikke tilgjengelig${tb.note ? ` (${escapeHtml(String(tb.note))})` : ''}.</p>`
    const loadLine =
      load.hours != null || load.load != null
        ? `<p class="muted tight">Belastning: ~${escapeHtml(String(load.hours ?? '—'))} t · load ~${escapeHtml(String(load.load ?? '—'))} (${escapeHtml(String(load.sessions ?? 0))} aktiviteter)</p>`
        : ''
    const planB = (w.plan_b || [])
      .slice(0, 3)
      .map((b) => `<li>${escapeHtml(String(b))}</li>`)
      .join('')
    const risk = (w.risk || [])
      .slice(0, 2)
      .map((b) => `<li>${escapeHtml(String(b))}</li>`)
      .join('')
    const presc = (w.prescriptions || [])
      .slice(0, 3)
      .map((block) => `<pre class="sync-sample week-check-presc">${escapeHtml(String(block))}</pre>`)
      .join('')
    const src =
      w.calendar_source === 'intervals'
        ? 'Kilde: Intervals-kalender + aktiviteter'
        : 'Kilde: app-plan'
    proposalCard = `
      <div class="confirm-card workout-proposal-card" aria-label="Ukesjekk">
        <p><strong>Ukesjekk ${escapeHtml(w.week_start || '')}–${escapeHtml(w.week_end || '')}</strong></p>
        <p class="muted tight">${escapeHtml(src)}. Ingen Intervals-push.</p>
        ${
          w.compliance_pct != null
            ? `<p class="muted tight">Compliance: ${escapeHtml(String(w.sessions_done ?? 0))}/${escapeHtml(String(w.sessions_planned ?? 0))} (${escapeHtml(String(w.compliance_pct))} %)</p>`
            : ''
        }
        ${tbLine}
        ${loadLine}
        ${planB ? `<p class="muted tight">Plan B</p><ul class="sync-sample">${planB}</ul>` : ''}
        ${risk ? `<p class="muted tight">Ukerisiko</p><ul class="sync-sample">${risk}</ul>` : ''}
        ${presc ? `<p class="muted tight">Kvalitetsøkter</p>${presc}` : ''}
        <div class="sync-actions">
          <button type="button" class="btn secondary" id="week-check-dismiss-btn">Skjul</button>
        </div>
      </div>`
  } else if (state.ukesopp?.questions?.length) {
    const u = state.ukesopp
    const drafts = state.ukesoppAnswerDrafts || {}
    const qs = (u.questions || [])
      .map(
        (q, i) => `<li>
          <label class="ukesopp-q-label"><strong>${i + 1}.</strong> ${escapeHtml(q)}</label>
          <textarea class="ukesopp-answer" data-ukesopp-i="${i}" rows="2" placeholder="Kort svar…">${escapeHtml(drafts[i] || '')}</textarea>
        </li>`,
      )
      .join('')
    const hint = u.completed_hint
      ? `<p class="muted tight">${escapeHtml(u.completed_hint)}</p>`
      : ''
    proposalCard = `
      <div class="confirm-card workout-proposal-card" aria-label="Ukesopp">
        <p><strong>Ukesopp ${escapeHtml(u.week_start || '')}–${escapeHtml(u.week_end || '')}</strong></p>
        <p class="muted tight">Lagre svar i appen (ikke Intervals-push).</p>
        ${u.planned_count != null ? `<p class="muted tight">${escapeHtml(String(u.planned_count))} planlagte økter i uka.</p>` : ''}
        ${hint}
        <ol class="sync-sample ukesopp-q">${qs}</ol>
        <div class="sync-actions">
          <button type="button" class="btn btn-primary" id="ukesopp-save-btn">Lagre svar</button>
          <button type="button" class="btn secondary" id="ukesopp-dismiss-btn">Skjul</button>
        </div>
        ${state.ukesoppSaveMessage ? `<p class="intervals-status is-ok">${escapeHtml(state.ukesoppSaveMessage)}</p>` : ''}
        ${state.ukesoppSaveError ? `<p class="error">${escapeHtml(state.ukesoppSaveError)}</p>` : ''}
      </div>`
  } else if (state.workoutSync.message) {
    proposalCard = `<p class="intervals-status is-ok">${escapeHtml(state.workoutSync.message)}</p>`
  }
  return `
    <div class="chat-log" id="chat-log">${renderChatBubbles(state.messages, empty)}</div>
    ${proposalCard}
    ${renderChatComposer({
      formId: 'chat-form',
      inputId: 'chat-input',
      draft,
      busy: state.busy,
      placeholder: 'Spør treneren…',
    })}
    ${state.error && state.tab === 'coach' ? `<p class="error">${escapeHtml(state.error)}</p>` : ''}
  `
}

function formatHours(n) {
  if (n == null || Number.isNaN(Number(n))) return '—'
  const v = Number(n)
  return Number.isInteger(v) ? String(v) : v.toFixed(1)
}

function renderProgressSection(o, { compact = false } = {}) {
  const progress = o.progress || {}
  const rows = progress.disciplines || []
  const source = progress.source || 'demo'
  const fetchFailed = Boolean(progress.fetch_error)
  const badge = fetchFailed
    ? `<span class="badge badge-demo">Henting feilet</span>`
    : source === 'demo'
      ? `<span class="badge badge-demo">Demo</span>`
      : progress.estimate
        ? `<span class="badge badge-est">Estimat</span>`
        : `<span class="badge badge-live">Intervals</span>`
  const windowLabel =
    progress.window?.start && progress.window?.end
      ? `${progress.window.start} – ${progress.window.end}`
      : ''
  const bars = rows
    .map((d) => {
      const pct = d.progress_pct != null ? d.progress_pct : 0
      const sessions =
        d.session_count != null && source === 'intervals'
          ? ` · ${d.session_count} økter`
          : ''
      const target =
        d.target_hours != null
          ? `${formatHours(d.completed_hours)} / ${formatHours(d.target_hours)} t`
          : `${formatHours(d.completed_hours)} t · sett mål i Du`
      const compliance =
        d.compliance_pct != null ? `${d.compliance_pct} %` : '—'
      const paceNote = d.on_pace_note
        ? `<span class="pace-note ${d.on_pace === false ? 'behind' : d.on_pace ? 'ok' : ''}">${escapeHtml(d.on_pace_note)}</span>`
        : ''
      const expected =
        !compact && d.expected_hours != null
          ? `<span class="dim">forventet ${formatHours(d.expected_hours)} t</span>`
          : ''
      return `
        <div class="progress-row">
          <div class="progress-meta">
            <span class="progress-label">${escapeHtml(d.label)}</span>
            <span class="progress-nums">${escapeHtml(target)}${escapeHtml(sessions)}</span>
            <span class="progress-pct">${escapeHtml(compliance)}</span>
          </div>
          <div class="progress-track" role="progressbar" aria-valuenow="${pct}" aria-valuemin="0" aria-valuemax="100" aria-label="${escapeHtml(d.label)}">
            <div class="progress-fill" style="width:${Math.min(100, Math.max(0, pct))}%"></div>
          </div>
          <div class="progress-sub">${paceNote}${expected}</div>
        </div>`
    })
    .join('')
  let blurb = 'Sesongvolum vs mål (fullført / mål).'
  if (fetchFailed) {
    blurb = `Kunne ikke hente Intervals — viser 0 t. ${progress.fetch_error_detail || ''} Prøv igjen snart.`
  } else if (source === 'demo') {
    blurb = 'Illustrasjonstall — koble Intervals under Du for ekte volum.'
  } else if (progress.season_not_started) {
    blurb = 'Sesongen er ikke startet ennå — volum er 0 til sesongstart.'
  } else if (progress.activity_count != null) {
    blurb = `Sesongvolum vs mål · ${progress.activity_count} aktiviteter i vinduet.`
  }
  const formula = compact
    ? ''
    : `<p class="muted tight dim formula-note">Compliance: completed / season_target (maks 100&nbsp;%). On-pace: completed / (target × elapsed/season).</p>`
  return `
    <section class="section-block">
      <div class="section-head">
        <h2>${compact ? 'Sesongvolum' : 'Fremskritt & compliance'}</h2>
        ${badge}
      </div>
      <p class="muted tight">${escapeHtml(blurb.trim())}${windowLabel ? ` <span class="dim">(${escapeHtml(windowLabel)})</span>` : ''}</p>
      <div class="progress-list">${bars || `<p class="muted">Ingen disipliner.</p>`}</div>
      ${formula}
    </section>`
}

function renderFormCard(o) {
  const q = o.qualifying_sessions
  const req = o.required_sessions || 5
  const gate = o.gate_open
  const ftpEst =
    o.ftp_estimated != null
      ? `${o.ftp_estimated} W${o.estimate_confidence ? ` · ${o.estimate_confidence}` : ''}`
      : o.estimate_disclaimer || `Estimat etter ${req} sykkeløkter med watt`
  const gateLabel =
    gate === true
      ? `<span class="badge badge-live">Gate åpen</span>`
      : `<span class="badge badge-off">${q != null ? `${q}/${req}` : '—'} økter</span>`
  return `
    <section class="section-block form-card">
      <div class="section-head">
        <h2>Form</h2>
        ${gateLabel}
      </div>
      <div class="stat-row"><span>Testet FTP</span><span>${o.ftp_tested != null ? `${o.ftp_tested} W` : '—'}</span></div>
      <div class="stat-row"><span>Estimert FTP</span><span>${escapeHtml(String(ftpEst))}</span></div>
      <div class="stat-row"><span>VO₂</span><span>${o.vo2_estimate != null ? o.vo2_estimate : '—'}</span></div>
      ${
        o.estimate_disclaimer && o.ftp_estimated != null
          ? `<p class="muted tight">${escapeHtml(o.estimate_disclaimer)}</p>`
          : ''
      }
    </section>`
}

function renderPlanStrip(o) {
  const p = o.periodization || {}
  const cur = p.current_block
  const next = p.next_block
  const days = p.days_to_goal
  const raceDate = p.goal_race_date
  const daysLabel =
    days == null
      ? 'Sett racedato i Du'
      : days < 0
        ? `${Math.abs(days)} dager siden mål`
        : `${days} dager til mål`
  const raceSub =
    raceDate && days != null
      ? `<p class="muted tight race-sub">${escapeHtml(raceDate)}</p>`
      : ''
  const curHtml = cur
    ? `<div class="plan-current">
        <p class="plan-kicker">Nåværende blokk</p>
        <h3>${escapeHtml(cur.title || 'Uten tittel')}</h3>
        <p class="plan-theme">${escapeHtml(cur.theme || '—')}</p>
        <p class="muted tight">${escapeHtml(cur.start_date || '?')} – ${escapeHtml(cur.end_date || '?')}${cur.weekly_hours != null ? ` · ${formatHours(cur.weekly_hours)} t/uke` : ''}</p>
        ${cur.plan_b ? `<p class="muted tight"><strong>Plan B:</strong> ${escapeHtml(cur.plan_b)}</p>` : ''}
        ${cur.weekly_risk ? `<p class="muted tight"><strong>Ukerisiko:</strong> ${escapeHtml(cur.weekly_risk)}</p>` : ''}
      </div>`
    : `<div class="plan-current">
        <p class="plan-kicker">Grovplan</p>
        <h3>Ingen blokk ennå</h3>
        <p class="muted tight">Legg til under Du — appen eier makro, Intervals eier dagsøkter.</p>
      </div>`
  const nextHtml = next
    ? `<div class="plan-next">
        <p class="plan-kicker">Neste</p>
        <p class="plan-next-title">${escapeHtml(next.title || 'Uten tittel')}</p>
        <p class="muted tight">fra ${escapeHtml(next.start_date || '?')}${next.theme ? ` · ${escapeHtml(next.theme)}` : ''}</p>
      </div>`
    : `<div class="plan-next">
        <p class="plan-kicker">Neste</p>
        <p class="muted tight">Ingen neste blokk</p>
      </div>`
  return `
    <section class="section-block plan-strip">
      <div class="section-head">
        <h2>Periodisering</h2>
        <div class="days-block">
          <span class="days-pill">${escapeHtml(daysLabel)}</span>
          ${raceSub}
        </div>
      </div>
      <div class="plan-grid">
        ${curHtml}
        ${nextHtml}
      </div>
      <p class="muted tight plan-footnote">Økter i kalenderen under — sync per uke/måned.</p>
    </section>`
}

function renderOverview() {
  const o = state.overview || {}
  return `
    <div class="overview-hero">
      <p class="brand-mark">Lofoten Coach</p>
      <h2>Kjapt overblikk</h2>
      <p class="muted">${escapeHtml(o.uplift_line || '')}</p>
    </div>
    ${renderPlanStrip(o)}
    ${renderFormCard(o)}
    ${renderProgressSection(o, { compact: true })}
    <section class="section-block">
      <h2>Kontekst</h2>
      <div class="stat-row"><span>Mål</span><span>${escapeHtml(o.goal_text || '—')}</span></div>
      <div class="stat-row"><span>Ukens fokus</span><span>${escapeHtml(o.weekly_focus || '—')}</span></div>
      <div class="stat-row"><span>Skade</span><span>${escapeHtml(o.injury_notes || '—')}</span></div>
    </section>
    <p class="muted tight jump-hint">Full grovplan under <strong>Plan</strong> · status under <strong>Dashboard</strong>.</p>
  `
}

function renderSleepCard(sleep, fetchError, detail, periodLabel) {
  if (!sleep) {
    return `<section class="section-block"><h2>Søvn</h2><p class="muted">Ingen data.</p></section>`
  }
  const badge = fetchError
    ? `<span class="badge badge-demo">Henting feilet</span>`
    : sleep.available
      ? `<span class="badge badge-live">Intervals</span>`
      : `<span class="badge badge-off">Mangler</span>`
  const snittLabel = periodLabel ? `Snitt (${periodLabel})` : 'Snitt'
  return `
    <section class="section-block">
      <div class="section-head"><h2>Søvn</h2>${badge}</div>
      ${fetchError && detail ? `<p class="error tight">${escapeHtml(detail)}</p>` : ''}
      <div class="stat-row"><span>${escapeHtml(snittLabel)}</span><span>${sleep.avg_hours != null ? `${sleep.avg_hours} t` : '—'}</span></div>
      <div class="stat-row"><span>Søvnscore</span><span>${sleep.avg_score != null ? sleep.avg_score : '—'}</span></div>
      <div class="stat-row"><span>Korte netter (&lt;6,5 t)</span><span>${sleep.short_nights ?? '—'}</span></div>
      <p class="muted tight">${escapeHtml(sleep.note || '')}</p>
    </section>`
}

function renderBodyCard(body, hidden) {
  // When show_body_metrics is off: omit the entire module (no «Skjult» placeholder).
  if (hidden) return ''
  if (!body) {
    return `<section class="section-block"><h2>Kropp</h2><p class="muted">Ingen data.</p></section>`
  }
  const badge = body.available
    ? `<span class="badge badge-live">Wellness</span>`
    : `<span class="badge badge-off">Mangler</span>`
  return `
    <section class="section-block" data-testid="body-metrics">
      <div class="section-head"><h2>Kropp</h2>${badge}</div>
      <div class="stat-row"><span>Siste vekt</span><span>${body.latest_weight_kg != null ? `${body.latest_weight_kg} kg` : '—'}</span></div>
      <div class="stat-row"><span>Fett %</span><span>${body.latest_body_fat_pct != null ? `${body.latest_body_fat_pct} %` : '—'}</span></div>
      <div class="stat-row"><span>Snitt vekt</span><span>${body.avg_weight_kg != null ? `${body.avg_weight_kg} kg` : '—'}</span></div>
      <p class="muted tight">${escapeHtml(body.note || '')}</p>
    </section>`
}

function periodLabelFromDash(dash) {
  const p = dash?.period || {}
  if (p.preset === 'custom' && p.start && p.end) {
    return `${p.start} – ${p.end}`
  }
  const map = { '7d': '7 d', '14d': '14 d', '30d': '30 d', '90d': '90 d' }
  return map[p.preset] || (p.days != null ? `${p.days} d` : 'periode')
}

function renderPeriodPicker(dash) {
  const p = state.dashboardPeriod || { preset: '14d', from: '', to: '' }
  const active = p.preset || '14d'
  const presets = [
    ['7d', '7 d'],
    ['14d', '14 d'],
    ['30d', '30 d'],
    ['90d', '90 d'],
    ['custom', 'Egen'],
  ]
  const chips = presets
    .map(
      ([id, lab]) =>
        `<button type="button" class="period-chip ${active === id ? 'active' : ''}" data-period="${id}" aria-pressed="${active === id ? 'true' : 'false'}">${lab}</button>`
    )
    .join('')
  const win = dash?.period
  const winLabel =
    win?.start && win?.end
      ? `<p class="muted tight period-window">${escapeHtml(win.start)} – ${escapeHtml(win.end)}${win.days != null ? ` · ${win.days} dager` : ''}</p>`
      : ''
  const custom =
    active === 'custom'
      ? `
      <div class="period-custom">
        <div class="field">
          <label for="period_from">Fra</label>
          <input type="date" id="period_from" value="${escapeHtml(p.from || '')}" />
        </div>
        <div class="field">
          <label for="period_to">Til</label>
          <input type="date" id="period_to" value="${escapeHtml(p.to || '')}" />
        </div>
        <button type="button" class="btn btn-sm btn-primary" id="period-apply">Vis</button>
      </div>`
      : ''
  return `
    <section class="section-block period-picker" aria-label="Velg periode">
      <div class="section-head"><h2>Periode</h2></div>
      <p class="muted tight">Treningsdata for valgt vindu — separat fra sesongmål.</p>
      <div class="period-chips" role="group">${chips}</div>
      ${custom}
      ${winLabel}
    </section>`
}

function renderLoadCard(dash) {
  const load = dash.load || {}
  const wl = load.from_wellness || {}
  const training = dash.training || dash.hours || {}
  const hours = dash.hours || training
  const charts = training.charts || {}
  const volume = charts.volume || { bars: [], bucket: 'day' }
  const volumePlanned = charts.volume_planned || null
  const discBars =
    charts.by_discipline ||
    (training.disciplines || hours.disciplines || []).map((d) => ({
      id: d.id,
      label: d.label,
      hours: d.hours != null ? d.hours : d.completed_hours,
    }))
  const loadSeries = load.series || {}
  const truthNote = charts.truth?.note_nb || load.note || training.note || ''
  const badge =
    training.source === 'intervals' || hours.source === 'intervals'
      ? `<span class="badge badge-live">Intervals</span>`
      : training.fetch_error || hours.fetch_error
        ? `<span class="badge badge-demo">Henting feilet</span>`
        : `<span class="badge badge-demo">Demo</span>`
  const total =
    training.total_hours != null
      ? training.total_hours
      : hours.total_hours != null
        ? hours.total_hours
        : null
  const actCount = training.activity_count ?? hours.activity_count
  const label = periodLabelFromDash(dash)
  const volTitle = volumeBucketTitle(volume.bucket)
  const plannedBlock =
    volumePlanned && (volumePlanned.bars || []).some((b) => Number(b.hours) > 0)
      ? `<section class="section-block chart-block" data-testid="chart-volume-planned" aria-label="Planlagt volum">
      <div class="section-head"><h2>Planlagt volum (fremover)</h2></div>
      ${renderVolumeBars({ ...volumePlanned, series_kind: 'planned' })}
    </section>`
      : ''
  return `
    <section class="section-block" data-testid="period-training">
      <div class="section-head"><h2>Trening (${escapeHtml(label)})</h2>${badge}</div>
      <div class="stat-row"><span>Totalt gjennomført</span><span>${total != null ? `${formatHours(total)} t` : '—'}${actCount != null ? ` · ${actCount} økter` : ''}</span></div>
      <div class="stat-row"><span>CTL</span><span>${wl.ctl != null ? wl.ctl : '—'}</span></div>
      <div class="stat-row"><span>ATL</span><span>${wl.atl != null ? wl.atl : '—'}</span></div>
      <div class="stat-row"><span>Readiness</span><span>${wl.readiness != null ? wl.readiness : '—'}</span></div>
      <p class="muted tight">${escapeHtml(truthNote)}</p>
    </section>
    <section class="section-block chart-block" data-testid="chart-volume" aria-label="${escapeHtml(volTitle)}">
      <div class="section-head"><h2>${escapeHtml(volTitle)} — gjennomført</h2></div>
      ${renderVolumeBars({ ...volume, series_kind: 'executed' })}
    </section>
    ${plannedBlock}
    <section class="section-block chart-block" data-testid="chart-discipline" aria-label="Timer per disiplin">
      <div class="section-head"><h2>Per disiplin (gjennomført)</h2></div>
      ${renderDisciplineBars(discBars)}
    </section>
    <section class="section-block chart-block" data-testid="chart-load" aria-label="Belastning CTL ATL">
      <div class="section-head"><h2>Belastning (CTL / ATL)</h2></div>
      <p class="muted tight">Kun Intervals wellness — ingen inventerte fremtidstall.</p>
      ${renderLoadLines(loadSeries)}
    </section>`
}

function renderDashboard() {
  const dash = state.dashboard
  const o = state.overview || {}
  if (!dash) {
    return `
      <div class="tab-hero">
        <p class="brand-mark">Dashboard</p>
        <h2>Treningsstatus</h2>
        <p class="muted">Laster… eller koble Intervals under Du.</p>
      </div>`
  }
  const progressForSection = { progress: dash.compliance || {} }
  const sleepLabel = periodLabelFromDash(dash)
  const sc4 = dash.session_compliance_4w
  const sc4Html =
    sc4 && sc4.sessions_planned != null
      ? `<div class="section-block compliance-week-block">
          <div class="section-head"><h2>Planlagt vs gjennomført</h2></div>
          <p class="muted tight">4-ukers økt-compliance: <strong>${sc4.sessions_done ?? 0} / ${sc4.sessions_planned}</strong> planlagte WORKOUT matchet til ICU-aktiviteter${
            sc4.compliance_pct != null ? ` (${sc4.compliance_pct} %)` : ''
          }.</p>
          <p class="muted tight">NOTE og planlagt uten aktivitet = ikke gjennomført. Spør Coach «sjekk uka mi» for ukesdetalj.</p>
        </div>`
      : `<div class="section-block compliance-week-block">
          <div class="section-head"><h2>Planlagt vs gjennomført</h2></div>
          <p class="muted tight">Koble Intervals under Du for ærlig økt-compliance (aktiviteter ≠ NOTES).</p>
        </div>`
  return `
    <div class="tab-hero">
      <p class="brand-mark">Dashboard</p>
      <h2>Treningsstatus</h2>
      <p class="muted">${escapeHtml(dash.uplift_line || 'Timer, søvn og sesongmål — app-beregnet.')}</p>
    </div>
    ${renderPeriodPicker(dash)}
    ${renderLoadCard(dash)}
    ${renderSleepCard(dash.sleep, dash.wellness_fetch_error, dash.wellness_fetch_error_detail, sleepLabel)}
    ${renderBodyCard(dash.body, dash.body_hidden || !dash.show_body_metrics)}
    ${sc4Html}
    <p class="compliance-banner" role="note">
      <strong>Sesongmål &amp; compliance</strong> er uavhengig av periodevalget over.
      Beregnes i appen (aktiviteter vs sesongmål) og <em>skrives ikke</em> til Intervals.
    </p>
    ${renderProgressSection(progressForSection)}
    ${renderFormCard({ ...(dash.form || {}), ...o })}
    ${renderPlanStrip(o)}
  `
}

function statusLabel(status) {
  const map = {
    completed: 'Gjennomført',
    matched_activity: 'Gjennomført (matchet)',
    planned: 'Planlagt',
    planned_not_done: 'Ikke gjennomført',
    note: 'Note (ikke trening)',
    skipped: 'Hoppet over',
    injured: 'Skade',
    tired: 'For sliten',
    sick: 'Syk',
    moved: 'Flyttet',
    cancelled: 'Avlyst',
    app_logged_completed: 'Logget (uten ICU-aktivitet)',
    other: 'Annet',
  }
  return map[status] || status || ''
}

function trainingStatusBadge(s) {
  const st = s.training_status || s.completion?.status || null
  if (!st) {
    if (s.kind === 'activity') {
      return `<span class="badge badge-live">Gjennomført</span>`
    }
    if (s.kind === 'event' && s.calendar_role === 'note') {
      return `<span class="badge badge-off">Note</span>`
    }
    if (s.kind === 'event') {
      return `<span class="badge badge-off">Planlagt</span>`
    }
    return `<span class="badge badge-off">Ulågget</span>`
  }
  const live = ['completed', 'matched_activity'].includes(st)
  return `<span class="badge ${live ? 'badge-live' : 'badge-off'}">${escapeHtml(statusLabel(st))}</span>`
}

function formatDateChips(dates, { max = 6 } = {}) {
  const list = (dates || []).filter(Boolean)
  if (!list.length) return `<span class="muted tight">Ingen datoer</span>`
  const shown = list.slice(0, max)
  const extra = list.length - shown.length
  const chips = shown
    .map((d) => `<span class="date-chip">${escapeHtml(d)}</span>`)
    .join('')
  return `${chips}${extra > 0 ? `<span class="date-chip more">+${extra}</span>` : ''}`
}

function renderSessionRow(s) {
  const statusBit = trainingStatusBadge(s)
  const dur =
    s.duration_hours != null ? ` · ${formatHours(s.duration_hours)} t` : ''
  const kindBit =
    s.kind === 'activity'
      ? ' · aktivitet'
      : s.calendar_role === 'note'
        ? ' · note'
        : s.kind === 'event'
          ? ' · planlagt'
          : ''
  return `
    <article class="session-row" data-open-detail="${escapeHtml(s.id)}" role="button" tabindex="0">
      <div class="session-main">
        <p class="session-date">${escapeHtml(s.date || '—')} · ${escapeHtml(s.discipline_label || s.type || '')}${escapeHtml(dur)}${escapeHtml(kindBit)}</p>
        <h3>${escapeHtml(s.name || 'Økt')}</h3>
        ${statusBit}
      </div>
      <div class="session-actions">
        <span class="btn btn-sm fake-btn">Åpne</span>
        <button type="button" class="btn btn-sm secondary" data-open-log="${escapeHtml(s.id)}">Logg</button>
      </div>
    </article>`
}

function renderLibraryCard(item) {
  const dates = item.dates || []
  const next = item.next_date || dates[0] || '—'
  const sid = item.sample_session_id || item.representative_id || ''
  const preview = item.description_preview
    ? `<p class="session-preview">${escapeHtml(item.description_preview)}</p>`
    : ''
  return `
    <article class="library-card" data-open-detail="${escapeHtml(sid)}" role="button" tabindex="0">
      <div class="library-card-top">
        <p class="session-date">${escapeHtml(item.discipline_label || item.type || '')}${
          item.occurrence_count > 1
            ? ` · ${item.occurrence_count} datoer`
            : next !== '—'
              ? ` · neste ${escapeHtml(next)}`
              : ''
        }</p>
        <h3>${escapeHtml(item.name || 'Økt')}</h3>
        ${preview}
      </div>
      <div class="date-chip-row" aria-label="Datoer">${formatDateChips(dates)}</div>
      <div class="session-actions">
        <span class="btn btn-sm fake-btn">Detaljer</span>
        <button type="button" class="btn btn-sm secondary" data-open-log="${escapeHtml(sid)}">Logg</button>
      </div>
    </article>`
}

function renderSessionProposalCard() {
  const proposal = state.workoutProposal
  const removal = state.workoutRemoval
  const wPending = state.workoutSync.pending
  if (wPending) {
    const sample = (wPending.events || [])
      .slice(0, 8)
      .map(
        (e) =>
          `<li><code>${escapeHtml(e.start_date_local || e.day || '')}</code> · ${escapeHtml(e.name || e.external_id || '')}</li>`,
      )
      .join('')
    const isDelete = (wPending.op || '') === 'delete'
    return `
      <div class="confirm-card" role="dialog" aria-label="Bekreft økt på Intervals">
        <p><strong>${escapeHtml(wPending.message || 'Bekreft økt-sync')}</strong></p>
        <p class="muted tight">${escapeHtml(wPending.op || 'workout_push')} · ${wPending.count} hendelse(r)</p>
        <ul class="sync-sample">${sample}</ul>
        <div class="sync-actions">
          <button type="button" class="btn btn-primary" id="workout-confirm-yes" ${state.workoutSync.busy ? 'disabled' : ''}>${
            isDelete ? 'Ja, slett på Intervals' : 'Ja, sync til Intervals'
          }</button>
          <button type="button" class="btn secondary" id="workout-confirm-no" ${state.workoutSync.busy ? 'disabled' : ''}>Avbryt</button>
        </div>
        ${state.workoutSync.error ? `<p class="error">${escapeHtml(state.workoutSync.error)}</p>` : ''}
      </div>`
  }
  if (removal) {
    return `
      <div class="confirm-card workout-proposal-card">
        <p><strong>Foreslått fjerning</strong></p>
        <div class="sync-actions">
          <button type="button" class="btn btn-primary" id="workout-remove-preview-btn" ${state.workoutSync.busy || !state.intervals.connected ? 'disabled' : ''}>Forhåndsvis sletting</button>
          <button type="button" class="btn secondary" id="workout-dismiss-btn">Avvis</button>
        </div>
      </div>`
  }
  if (proposal?.workouts?.length) {
    const rows = proposal.workouts
      .map(
        (w) =>
          `<li><strong>${escapeHtml(w.date || '')}</strong> · ${escapeHtml(w.name || '')} · ${escapeHtml(w.sport || '')}${
            w.duration_minutes != null ? ` · ${escapeHtml(String(w.duration_minutes))} min` : ''
          }</li>`,
      )
      .join('')
    return `
      <div class="confirm-card workout-proposal-card">
        <p><strong>Foreslått endring til Intervals</strong></p>
        <p class="muted tight">Ingenting er synct — forhåndsvis først.</p>
        <ul class="sync-sample">${rows}</ul>
        <div class="sync-actions">
          <button type="button" class="btn btn-primary" id="workout-preview-btn" ${state.workoutSync.busy || !state.intervals.connected ? 'disabled' : ''}>Forhåndsvis sync</button>
          <button type="button" class="btn secondary" id="workout-dismiss-btn">Avvis</button>
        </div>
        ${state.workoutSync.error ? `<p class="error">${escapeHtml(state.workoutSync.error)}</p>` : ''}
      </div>`
  }
  if (state.workoutSync.message) {
    return `<p class="intervals-status is-ok">${escapeHtml(state.workoutSync.message)}</p>`
  }
  return ''
}

function renderSessionStructure(structure, steps) {
  const phases = structure?.phases || []
  if (phases.length) {
    return phases
      .map((ph) => {
        const items = (ph.items || [])
          .map((it) => `<li>${escapeHtml(it)}</li>`)
          .join('')
        return `
          <div class="structure-phase" data-phase="${escapeHtml(ph.id || '')}">
            <h4 class="structure-phase-label">${escapeHtml(ph.label || ph.id || '')}</h4>
            <ol class="coach-steps structure-steps">${items}</ol>
          </div>`
      })
      .join('')
  }
  const flat = (steps || []).map((st) => `<li>${escapeHtml(st)}</li>`).join('')
  return flat ? `<ol class="coach-steps">${flat}</ol>` : ''
}

function renderSessionDetail() {
  const d = state.sessionDetail
  if (!d) return ''
  const s = d.session || {}
  const fields = d.editable_fields || {}
  const statuses = [
    ['completed', 'Gjennomført'],
    ['skipped', 'Hoppet over'],
    ['moved', 'Flyttet'],
    ['cancelled', 'Avlyst'],
    ['injured', 'Skade'],
    ['tired', 'For sliten'],
    ['sick', 'Syk'],
    ['other', 'Annet'],
  ]
  const opts = statuses
    .map(
      ([v, lab]) =>
        `<option value="${v}" ${s.completion?.status === v ? 'selected' : ''}>${lab}</option>`,
    )
    .join('')
  const structureHtml = renderSessionStructure(d.structure || d.coach_block?.structure, d.steps)
  const builderSteps = state.builderSteps || d.builder_steps || fields.builder_steps || []
  if (!state.builderSteps && builderSteps.length) {
    state.builderSteps = builderSteps.map((s, i) => ({ ...s, sort_order: i }))
  }
  const coachBody = d.coach_block?.body || d.description || ''
  const occChips = formatDateChips(d.dates || [])
  const chatBubbles = renderChatBubbles(
    state.sessionChat.messages,
    `<p class="muted">F.eks. «kan vi kutte hovedsettet?» eller «legg til 3×8 min Z3».</p>`,
  )
  const editOpen = state.sessionEditOpen
  const canEdit = Boolean(d.editable) || Boolean(s.app_planned)
  const sportOpts = [
    ['bike', 'Sykkel'],
    ['run', 'Løp'],
    ['swim', 'Svøm'],
    ['strength', 'Styrke'],
    ['other', 'Annet'],
  ]
    .map(
      ([v, lab]) =>
        `<option value="${v}" ${(fields.sport || s.discipline || '') === v ? 'selected' : ''}>${lab}</option>`,
    )
    .join('')
  const chips = [
    ['Kutt hovedsett', 'Kan vi kutte hovedsettet litt?'],
    ['Mer spesifikk', 'Gjør økten mer spesifikk for Lofoten'],
    ['Plan B', 'Foreslå Plan B hvis jeg er sliten'],
  ]
    .map(
      ([lab, msg]) =>
        `<button type="button" class="chip session-chat-chip" data-session-chip="${escapeHtml(msg)}">${escapeHtml(lab)}</button>`,
    )
    .join('')

  const stepTypeOpts = (selected) =>
    [
      ['warmup', 'Oppvarming'],
      ['work', 'Arbeid'],
      ['recover', 'Pause'],
      ['cooldown', 'Nedkjøling'],
    ]
      .map(
        ([v, lab]) =>
          `<option value="${v}" ${selected === v ? 'selected' : ''}>${lab}</option>`,
      )
      .join('')

  const liveSteps = state.builderSteps || []
  const liveTotal = liveSteps.reduce(
    (acc, st) => acc + (Number(st.duration_minutes) || 0),
    0,
  )
  const builderRows = liveSteps
    .map((st, i) => {
      return `
      <div class="builder-step" data-step-index="${i}">
        <select class="builder-type" data-field="type" aria-label="Stegtype">${stepTypeOpts(st.type || 'work')}</select>
        <input class="builder-dur" data-field="duration_minutes" type="number" min="0" placeholder="min" value="${
          st.duration_minutes != null ? escapeHtml(String(st.duration_minutes)) : ''
        }" aria-label="Varighet minutter" />
        <input class="builder-intensity" data-field="intensity" placeholder="RPE/sone" value="${escapeHtml(
          st.intensity || '',
        )}" aria-label="Intensitet" />
        <input class="builder-note" data-field="note" placeholder="Notat" value="${escapeHtml(
          st.note || '',
        )}" aria-label="Notat" />
        <button type="button" class="btn btn-sm secondary builder-remove" data-remove-step="${i}" aria-label="Fjern steg">×</button>
      </div>`
    })
    .join('')

  const builderPreview = liveSteps.length
    ? `<ol class="builder-preview">${liveSteps
        .map((st) => {
          const lab =
            { warmup: 'WU', work: 'Work', recover: 'Rec', cooldown: 'CD' }[st.type] ||
            st.type
          const bits = [
            lab,
            st.duration_minutes != null ? `${st.duration_minutes} min` : null,
            st.intensity || null,
            st.note || null,
          ].filter(Boolean)
          return `<li>${escapeHtml(bits.join(' · '))}</li>`
        })
        .join('')}</ol>
      <p class="muted tight">Sum: <strong>${liveTotal}</strong> min</p>`
    : `<p class="muted tight">Ingen steg ennå — legg til warmup/work/recover/cooldown.</p>`

  return `
    <div class="session-detail-view has-sticky-chat" id="session-detail">
      <div class="section-head">
        <button type="button" class="btn btn-sm secondary" id="close-session-detail">← Bibliotek</button>
        <span class="badge ${s.completion || ['completed', 'matched_activity'].includes(s.training_status) ? 'badge-live' : 'badge-off'}">${
          s.training_status
            ? escapeHtml(statusLabel(s.training_status))
            : s.completion
              ? escapeHtml(statusLabel(s.completion.status))
              : s.kind === 'activity'
                ? 'Gjennomført'
                : 'Planlagt'
        }</span>
      </div>
      <header class="detail-hero">
        <p class="brand-mark">${escapeHtml(s.discipline_label || s.type || 'Økt')}</p>
        <h2>${escapeHtml(s.name || 'Økt')}</h2>
        <p class="muted tight">${escapeHtml(s.date || '—')}${
          s.duration_hours != null ? ` · ${formatHours(s.duration_hours)} t` : ''
        }${s.editable ? ' · coach-økt' : ''}</p>
        <div class="date-chip-row detail-dates" aria-label="Planlagte datoer">${occChips}</div>
      </header>

      <section class="section-block coach-block">
        <h3>Struktur</h3>
        ${
          structureHtml
            ? `<div class="session-structure">${structureHtml}</div>`
            : coachBody
              ? `<pre class="coach-desc">${escapeHtml(coachBody)}</pre>`
              : `<p class="muted">Ingen steg lagret på denne økten ennå.</p>`
        }
        ${
          structureHtml && coachBody
            ? `<details class="coach-raw"><summary>Full beskrivelse</summary><pre class="coach-desc">${escapeHtml(coachBody)}</pre></details>`
            : ''
        }
      </section>

      ${
        canEdit
          ? `<section class="section-block builder-panel" id="oktbygger-section" aria-label="Øktbygger">
        <div class="section-head">
          <h3>Øktbygger</h3>
          <button type="button" class="btn btn-sm secondary" id="builder-add-step">+ Steg</button>
        </div>
        <p class="muted tight">Steg med type, varighet og intensitet (steps_json). Lagre i plan først — Sync til Intervals er valgfritt.</p>
        <div id="builder-steps" class="builder-steps">${builderRows || ''}</div>
        <div class="builder-live" aria-live="polite">
          <h4 class="tight">Forhåndsvis struktur</h4>
          ${builderPreview}
        </div>
        <div class="row-actions">
          <button type="button" class="btn btn-primary" id="builder-save-plan" ${state.workoutSync.busy ? 'disabled' : ''}>Lagre i plan</button>
        </div>
        <p class="muted tight">Human Coach: lagring i DB først. Intervals skrives først etter Sync-bekreftelse.</p>
      </section>
      <section class="section-block">
        <div class="section-head">
          <h3>Rediger økt</h3>
          <button type="button" class="btn btn-sm secondary" id="toggle-session-edit">${editOpen ? 'Skjul' : 'Åpne felter'}</button>
        </div>
        ${
          editOpen
            ? `<form id="session-edit-form" class="session-edit-form">
          <div class="field">
            <label for="edit_name">Tittel</label>
            <input id="edit_name" name="name" required value="${escapeHtml(fields.name || '')}" />
          </div>
          <div class="field-row">
            <div class="field">
              <label for="edit_date">Dato</label>
              <input id="edit_date" name="date" type="date" required value="${escapeHtml(fields.date || '')}" />
            </div>
            <div class="field">
              <label for="edit_sport">Sport</label>
              <select id="edit_sport" name="sport">${sportOpts}</select>
            </div>
          </div>
          <div class="field-row">
            <div class="field">
              <label for="edit_duration">Varighet (min)</label>
              <input id="edit_duration" name="duration_minutes" type="number" min="1" value="${
                fields.duration_minutes != null ? escapeHtml(String(fields.duration_minutes)) : ''
              }" />
            </div>
            <div class="field">
              <label for="edit_start">Start</label>
              <input id="edit_start" name="start_time" value="${escapeHtml(fields.start_time || '07:00')}" />
            </div>
          </div>
          <details class="coach-raw">
            <summary>Klassisk tekststeg (valgfritt)</summary>
            <div class="field">
              <label for="edit_warmup">Oppvarming</label>
              <textarea id="edit_warmup" name="warmup" rows="2">${escapeHtml(fields.warmup || '')}</textarea>
            </div>
            <div class="field">
              <label for="edit_main">Hoveddel</label>
              <textarea id="edit_main" name="main" rows="3">${escapeHtml(fields.main || '')}</textarea>
            </div>
            <div class="field">
              <label for="edit_cooldown">Nedkjøling</label>
              <textarea id="edit_cooldown" name="cooldown" rows="2">${escapeHtml(fields.cooldown || '')}</textarea>
            </div>
          </details>
          <details class="coach-raw">
            <summary>Rå beskrivelse (valgfri overstyring)</summary>
            <div class="field">
              <label for="edit_description" class="sr-only">Beskrivelse</label>
              <textarea id="edit_description" name="description" rows="4">${escapeHtml(fields.description || '')}</textarea>
            </div>
          </details>
          <input type="hidden" name="external_id" value="${escapeHtml(fields.external_id || '')}" />
          <div class="row-actions">
            <button type="submit" class="btn secondary" ${state.workoutSync.busy ? 'disabled' : ''}>Forhåndsvis Intervals</button>
          </div>
          <p class="muted tight">Intervals-forhåndsvisning krever tilkobling under Du.</p>
        </form>`
            : `<p class="muted tight">Endre tittel, dato, sport — eller bruk Øktbygger over.</p>`
        }
      </section>`
          : `<p class="muted tight">Aktiviteter fra Intervals er skrivebeskyttet her — logg status under.</p>`
      }

      ${renderSessionProposalCard()}

      <section class="section-block session-chat-block" id="session-chat-block">
        <h3>Spør coach om denne</h3>
        <p class="muted tight">Samme coach-chat som Coach-fanen — fokusert på denne økten (${escapeHtml(
          s.discipline_label || s.discipline || 'sport',
        )}). Endringer → forhåndsvis → bekreft.</p>
        <div class="chat-log session-chat-log" id="session-chat-log">${chatBubbles}</div>
        <div class="session-chat-chips" aria-label="Hurtigspørsmål">${chips}</div>
        ${state.sessionChat.error ? `<p class="error">${escapeHtml(state.sessionChat.error)}</p>` : ''}
      </section>

      <section class="section-block" id="session-log-block">
        <h3>Logg fullføring</h3>
        <form id="completion-form">
          <div class="field">
            <label for="completion_status">Status</label>
            <select id="completion_status" name="status" required>${opts}</select>
          </div>
          <div class="field">
            <label for="completion_reason">Grunn (valgfri)</label>
            <input id="completion_reason" name="reason" value="${escapeHtml(s.completion?.reason || '')}" placeholder="f.eks. for kort søvn" />
          </div>
          <div class="field">
            <label for="completion_note">Notat</label>
            <textarea id="completion_note" name="note" rows="2">${escapeHtml(s.completion?.note || '')}</textarea>
          </div>
          <div class="row-actions">
            <button type="submit" class="btn btn-primary" ${state.busy ? 'disabled' : ''}>Lagre logg</button>
          </div>
        </form>
        ${state.planError ? `<p class="error">${escapeHtml(state.planError)}</p>` : ''}
        <p class="muted tight">Lagres i appen — ikke i Intervals.</p>
      </section>

      ${renderChatComposer({
        formId: 'session-chat-form',
        inputId: 'session-chat-input',
        draft: state.sessionChat.draft || '',
        busy: state.sessionChat.busy,
        placeholder: 'Spør om denne økten…',
        sticky: true,
        ariaLabel: 'Chat om denne økten',
      })}
    </div>`
}

function renderBetaTab() {
  const b = state.beta
  if (state.betaError && !b) {
    return `
      <div class="tab-hero">
        <p class="brand-mark">Beta <span class="badge badge-demo">eksperimentell</span></p>
        <h2>Prognoser</h2>
        <p class="error">${escapeHtml(state.betaError)}</p>
      </div>`
  }
  if (!b) {
    return `
      <div class="tab-hero">
        <p class="brand-mark">Beta <span class="badge badge-demo">eksperimentell</span></p>
        <h2>Prognoser</h2>
        <p class="muted">Laster CTL/ATL/TSB og risikobånd…</p>
      </div>`
  }
  const load = b.load_now || {}
  const chart = b.charts?.ctl_atl_tsb || {}
  const bands = b.charts?.acwr_bands || {}
  const race = b.race_form || {}
  const vol = b.volume || {}
  const sc = b.scenario_ease
  const cites = b.citations || []
  const citeHtml = cites
    .map(
      (c) =>
        `<li><span class="cite-id">${escapeHtml(c.id || '')}</span> — ${escapeHtml(c.cite || '')}${
          c.note ? ` <em class="muted">(${escapeHtml(c.note)})</em>` : ''
        }</li>`
    )
    .join('')
  const scenarioHtml = sc
    ? `<section class="section-block" data-testid="beta-scenario">
        <div class="section-head"><h2>${escapeHtml(sc.title_nb || 'Scenario')}</h2></div>
        <p class="muted tight">${escapeHtml(sc.note_nb || '')}</p>
        <div class="stat-row"><span>CTL slutt (plan)</span><span>${sc.baseline_end?.ctl ?? '—'}</span></div>
        <div class="stat-row"><span>CTL slutt (−20 %)</span><span>${sc.eased_end?.ctl ?? '—'}</span></div>
        <p class="coach-note">Kun forslag. Trykk «Åpne i Coach» — ingen auto-omskrivning av plan.</p>
        <button type="button" class="btn secondary" id="beta-open-coach">Åpne i Coach</button>
      </section>`
    : ''
  return `
    <div class="tab-hero beta-hero">
      <p class="brand-mark">Beta <span class="badge badge-demo">eksperimentell</span></p>
      <h2>Avanserte prognoser</h2>
      <p class="lead tight">CTL/ATL/TSB, overload-risiko og race-form — evidensbaserte soft signals. Human Coach bekrefter før handling.</p>
    </div>
    <section class="section-block" data-testid="beta-load-now">
      <div class="section-head"><h2>Load nå</h2></div>
      <div class="stat-row"><span>CTL</span><span>${load.ctl != null ? load.ctl : '—'}</span></div>
      <div class="stat-row"><span>ATL</span><span>${load.atl != null ? load.atl : '—'}</span></div>
      <div class="stat-row"><span>TSB</span><span>${load.tsb != null ? load.tsb : '—'}</span></div>
      <div class="stat-row"><span>ATL:CTL</span><span>${load.acwr != null ? Number(load.acwr).toFixed(2) : '—'}</span></div>
      <p class="muted tight">${escapeHtml(b.truth?.note_nb || '')}</p>
    </section>
    <section class="section-block chart-block" data-testid="beta-chart-trajectory" aria-label="CTL ATL TSB">
      <div class="section-head"><h2>CTL / ATL / TSB</h2></div>
      ${renderBetaLoadTrajectory(chart)}
      <p class="muted tight">${escapeHtml(chart.note_nb || '')}</p>
    </section>
    <section class="section-block" data-testid="beta-acwr">
      <div class="section-head"><h2>Overload / akutt:kronisk</h2></div>
      ${renderAcwrRiskBar(bands)}
    </section>
    <section class="section-block" data-testid="beta-race-form">
      <div class="section-head"><h2>Race-form mot mål</h2></div>
      <div class="stat-row"><span>Måldato</span><span>${escapeHtml(race.goal_race_date || '—')}</span></div>
      <div class="stat-row"><span>Dager igjen</span><span>${race.days_to_goal != null ? race.days_to_goal : '—'}</span></div>
      <div class="stat-row"><span>Confidence</span><span>${escapeHtml(race.confidence || '—')}</span></div>
      <div class="stat-row"><span>Proj. CTL på mål</span><span>${race.projected_ctl_at_goal != null ? race.projected_ctl_at_goal : '—'}</span></div>
      <p class="coach-note">${escapeHtml(race.summary_nb || '')}</p>
      <p class="muted tight">${escapeHtml(race.confidence_band_nb || '')}</p>
    </section>
    <section class="section-block" data-testid="beta-volume">
      <div class="section-head"><h2>Volum: gjennomført vs planlagt</h2></div>
      <div class="stat-row"><span>Gjennomført (lookback)</span><span>${vol.executed_hours_lookback != null ? `${vol.executed_hours_lookback} t` : '—'}</span></div>
      <div class="stat-row"><span>Planlagt (horizon)</span><span>${vol.planned_hours_horizon != null ? `${vol.planned_hours_horizon} t` : '—'}</span></div>
      <p class="muted tight">${escapeHtml(vol.note_nb || '')}</p>
    </section>
    ${scenarioHtml}
    <section class="section-block beta-footnotes" data-testid="beta-citations">
      <div class="section-head"><h2>Kilder</h2></div>
      <p class="muted tight">${escapeHtml(b.coach_notes_nb || '')}</p>
      <ol class="cite-list">${citeHtml}</ol>
    </section>
  `
}

function renderOkterTab() {
  if (state.sessionDetail) {
    return renderSessionDetail()
  }
  const sess = state.sessions
  const linked = state.intervals.connected
  const view = state.sessionsView || 'library'
  let body = ''
  if (!sess) {
    body = `<p class="muted">Laster økter…</p>`
  } else if (sess.source === 'none') {
    body = `<p class="muted">Koble Intervals under Du for å se bibliotek og kommende økter.</p>`
  } else if (sess.fetch_error) {
    body = `<p class="error">Kunne ikke hente økter: ${escapeHtml(sess.fetch_error_detail || '')}</p>`
  } else if (view === 'chronological') {
    const today = (sess.today || []).map(renderSessionRow).join('')
    const upcoming = (sess.upcoming || []).map(renderSessionRow).join('')
    const recent = (sess.recent || []).map(renderSessionRow).join('')
    const missed = (sess.planned_not_done || []).map(renderSessionRow).join('')
    body = `
      ${today ? `<section class="section-block"><h2>I dag</h2><div class="session-list">${today}</div></section>` : ''}
      <section class="section-block">
        <h2>Kommende (planlagt)</h2>
        <div class="session-list">${upcoming || `<p class="muted">Ingen planlagte økter i vinduet.</p>`}</div>
      </section>
      <section class="section-block">
        <h2>Gjennomført (ICU-aktiviteter)</h2>
        <div class="session-list">${recent || `<p class="muted">Ingen aktiviteter i vinduet.</p>`}</div>
      </section>
      ${
        missed
          ? `<section class="section-block"><h2>Ikke gjennomført</h2><p class="muted tight">Planlagt WORKOUT uten matching aktivitet.</p><div class="session-list">${missed}</div></section>`
          : ''
      }`
  } else {
    const lib = (sess.library || []).map(renderLibraryCard).join('')
    body = `
      <section class="section-block">
        <h2>Bibliotek</h2>
        <p class="muted tight">Samme økt én gang — datoene den går på listes under.</p>
        <div class="library-list">${lib || `<p class="muted">Ingen økter i vinduet.</p>`}</div>
      </section>`
  }
  return `
    <div class="tab-hero">
      <p class="brand-mark">Økter</p>
      <h2>Bibliotek &amp; detalj</h2>
      <p class="muted">Trykk en økt for Øktbygger, steg, coach-chat og logg. Endringer til Intervals krever bekreftelse.</p>
    </div>
    <div class="view-toggle" role="tablist" aria-label="Visning">
      <button type="button" class="chip ${view === 'library' ? 'active' : ''}" data-sessions-view="library">Bibliotek</button>
      <button type="button" class="chip ${view === 'chronological' ? 'active' : ''}" data-sessions-view="chronological">Kommende</button>
    </div>
    <p class="compliance-banner muted tight">${escapeHtml(sess?.compliance_note || 'Compliance beregnes i appen, ikke i Intervals.')}</p>
    ${
      sess?.rolling_compliance_4w?.sessions_planned != null
        ? `<p class="muted tight">4 uker: ${sess.rolling_compliance_4w.sessions_done ?? 0} / ${sess.rolling_compliance_4w.sessions_planned} planlagte økter matchet til ICU-aktiviteter${
            sess.rolling_compliance_4w.compliance_pct != null
              ? ` (${sess.rolling_compliance_4w.compliance_pct} %)`
              : ''
          }.</p>`
        : ''
    }
    <p class="muted tight">${linked ? 'Intervals koblet.' : 'Ikke koblet ennå.'}</p>
    ${body}
  `
}

function renderSyncPanel() {
  const linked = state.intervals.connected
  const pending = state.sync.pending
  const status = state.sync.status
  let confirmHtml = ''
  if (pending) {
    const sample = (pending.events || [])
      .slice(0, 12)
      .map((e) => {
        const cat =
          e.category === 'WORKOUT' ? 'Økt' : e.category === 'NOTE' ? 'Note' : e.category || ''
        const line =
          e.preview_no ||
          `${(e.day || e.start_date_local || '').toString().slice(0, 10)} · ${e.name || ''}${
            e.has_zwo || e.filename ? ' · ZWO' : ''
          }${e.duration_minutes ? ` · ${e.duration_minutes} min` : ''}`
        return `<li><span class="badge badge-off">${escapeHtml(cat)}</span> ${escapeHtml(line)}</li>`
      })
      .join('')
    const wc = pending.workouts_count
    const nc = pending.notes_count
    const zc = pending.zwo_count
    const meta =
      wc != null
        ? Number(nc) > 0
          ? `${wc} økter${zc != null ? ` (${zc} ZWO)` : ''} + ${nc} noter`
          : `${wc} økter${zc != null ? ` (${zc} ZWO)` : ''} fra planned_sessions (uten grovplan-noter)`
        : `${pending.count} hendelser`
    confirmHtml = `
      <div class="confirm-card" role="dialog" aria-label="Bekreft Intervals-sync">
        <p><strong>${escapeHtml(pending.message || 'Bekreft handling')}</strong></p>
        <p class="muted tight">${escapeHtml(pending.op || '')} · ${escapeHtml(meta)}</p>
        <ul class="sync-sample">${sample}</ul>
        ${pending.events_truncated ? `<p class="muted tight">+${pending.events_truncated} til</p>` : ''}
        <div class="row-actions">
          <button type="button" class="btn btn-primary" id="sync-confirm-yes" ${state.sync.busy ? 'disabled' : ''}>Ja, sync</button>
          <button type="button" class="btn secondary" id="sync-confirm-no" ${state.sync.busy ? 'disabled' : ''}>Avbryt</button>
        </div>
      </div>`
  }
  const statusList = (status?.events || [])
    .slice(0, 8)
    .map(
      (e) =>
        `<li>${escapeHtml(e.category === 'WORKOUT' ? 'Økt' : e.category === 'NOTE' ? 'Note' : '')} ${escapeHtml(e.name || 'Hendelse')} · <span class="dim">${escapeHtml((e.start_date_local || '').slice(0, 10))}</span></li>`
    )
    .join('')
  return `
    <section class="section-block sync-panel">
      <div class="section-head">
        <h2>Sync til Intervals</h2>
        <span class="badge ${linked ? 'badge-live' : 'badge-off'}">${linked ? 'Koblet' : 'Ikke koblet'}</span>
      </div>
      <p class="muted tight">Pusher <strong>lagrede økter</strong> (planned_sessions) for første <strong>2 uker</strong> når de finnes — ellers bibliotek. Antall ≈ avtalt økter/uke × 2. Grovplan-noter kan dekke sesongen. Forhåndsvis → Ja/Avbryt. Upsert — sletter ikke andre kalenderhendelser.</p>
      <div class="sync-actions">
        <button type="button" class="btn btn-primary" id="sync-push" ${!linked || state.sync.busy ? 'disabled' : ''}>Sync til Intervals</button>
        <button type="button" class="btn secondary" id="sync-refresh" ${!linked || state.sync.busy ? 'disabled' : ''}>Oppdater status</button>
        <button type="button" class="btn secondary danger-outline" id="sync-delete" ${!linked || state.sync.busy ? 'disabled' : ''}>Fjern fra Intervals</button>
      </div>
      ${state.sync.message ? `<p class="intervals-status is-ok">${escapeHtml(state.sync.message)}</p>` : ''}
      ${state.sync.error ? `<p class="error">${escapeHtml(state.sync.error)}</p>` : ''}
      ${confirmHtml}
      <div class="sync-status-box">
        <p class="plan-kicker">På Intervals nå</p>
        ${
          state.sync.statusError
            ? `<p class="error">${escapeHtml(state.sync.statusError)}</p>`
            : status
              ? `<p class="muted tight">${status.count} agent-hendelser (${escapeHtml(status.window?.start || '')} – ${escapeHtml(status.window?.end || '')})</p>
                 <ul class="sync-sample">${statusList || '<li class="muted">Ingen</li>'}</ul>`
              : `<p class="muted tight">Trykk Oppdater for å hente status.</p>`
        }
      </div>
    </section>`
}

function renderPlanTab() {
  const o = state.overview || {}
  return `
    <div class="tab-hero">
      <p class="brand-mark">Grovplan</p>
      <h2>Plan &amp; Intervals</h2>
      <p class="muted">Makro/meso, økter til måldato, deretter Sync nærvindu.</p>
    </div>
    ${renderPlanStrip(o)}
    ${renderPlanBlocksEditor()}
    ${renderPlanMonthCalendar()}
    ${renderSyncPanel()}
  `
}

function renderPlanMonthCalendar() {
  const ps = state.plannedSessions || {}
  const sessions = ps.sessions || []
  const total = ps.total ?? sessions.length
  const monthKey = state.planCalendar.month || monthKeyFromDate()
  const byDate = sessionsByDate(sessions)
  const cells = buildMonthGrid(monthKey, byDate)
  const selected = state.planCalendar.selectedDate
  const sourceFilter = state.planCalendar.sourceFilter || 'all'
  const filterBySource = (list) =>
    sourceFilter === 'all'
      ? list
      : list.filter((s) => (s.source_kind || 'app') === sourceFilter)
  const selectedSessions = filterBySource(selected ? byDate.get(selected) || [] : [])
  const weekdays = ['Man', 'Tir', 'Ons', 'Tor', 'Fre', 'Lør', 'Søn']
  const head = weekdays.map((w) => `<div class="cal-dow">${w}</div>`).join('')
  const todayIso = toIsoDate(new Date())
  const grid = cells
    .map((c) => {
      const filtered = filterBySource(c.sessions)
      const n = filtered.length
      const sel = selected === c.iso ? ' cal-day-selected' : ''
      const out = c.inMonth ? '' : ' cal-day-out'
      const isToday = c.iso === todayIso ? ' cal-day-today' : ''
      const dots = n > 0 ? calendarDotsHtml(filtered) : ''
      return `<button type="button" class="cal-day${sel}${out}${isToday}" data-cal-day="${escapeHtml(c.iso)}" ${
        c.inMonth ? '' : 'tabindex="-1"'
      }>
        <span class="cal-day-num">${c.day}</span>${dots}
      </button>`
    })
    .join('')
  const selList = selectedSessions
    .map(
      (s) =>
        `<li>${escapeHtml(s.name || 'Økt')} · ${escapeHtml(s.sport || '')}${
          s.duration_minutes != null ? ` · ${s.duration_minutes} min` : ''
        }${
          s.source_kind_nb
            ? ` <span class="cal-source-tag cal-source-${escapeHtml(s.source_kind || 'app')}">${escapeHtml(s.source_kind_nb)}</span>`
            : ''
        }${
          s.sync_status_nb
            ? ` <span class="cal-sync-tag cal-sync-${escapeHtml(s.sync_status || 'unknown')}">${escapeHtml(s.sync_status_nb)}</span>`
            : ''
        }</li>`,
    )
    .join('')
  const weekQ = ps.week_quality || {}
  const planBBits = (weekQ.plan_b || []).map((t) => escapeHtml(t)).join('<br/>')
  const riskBits = (weekQ.weekly_risk || []).map((t) => escapeHtml(t)).join('<br/>')
  const weekQualityHtml =
    planBBits || riskBits
      ? `<div class="cal-week-quality">
          ${planBBits ? `<p class="muted tight"><strong>Plan B (uke)</strong><br/>${planBBits}</p>` : ''}
          ${riskBits ? `<p class="muted tight"><strong>Ukerisiko</strong><br/>${riskBits}</p>` : ''}
        </div>`
      : ''
  const sourceFilters = [
    ['all', 'Alle'],
    ['coach', 'Coach'],
    ['agent', 'Agent'],
    ['manual', 'Manuell'],
    ['app', 'App'],
  ]
    .map(
      ([id, label]) =>
        `<button type="button" class="btn btn-sm secondary cal-source-filter${
          sourceFilter === id ? ' is-active' : ''
        }" data-source-filter="${id}">${label}</button>`,
    )
    .join('')
  const metaBits = []
  if (total) metaBits.push(`${total} økter`)
  if (ps.plan_horizon_weeks) metaBits.push(`~${ps.plan_horizon_weeks} uker`)
  if (ps.goal_race_date) metaBits.push(`mål ${ps.goal_race_date}`)
  const scopeHint = state.planCalendar.syncScopeLabel
    ? `<p class="muted tight">Sync-vindu: <strong>${escapeHtml(state.planCalendar.syncScopeLabel)}</strong></p>`
    : ''
  const tpPending = state.tpSync.pending
  const tpConfirm =
    tpPending?.pending_id
      ? `<div class="confirm-card cal-sync-confirm">
          <p><strong>${escapeHtml(tpPending.message_nb || 'Bekreft TrainingPeaks (beta)')}</strong></p>
          <p class="muted tight">${escapeHtml(String(tpPending.workouts_count || 0))} økter</p>
          <div class="sync-actions">
            <button type="button" class="btn btn-primary" id="tp-sync-confirm-yes" ${state.tpSync.busy ? 'disabled' : ''}>Ja, push til TP</button>
            <button type="button" class="btn secondary" id="tp-sync-confirm-no" ${state.tpSync.busy ? 'disabled' : ''}>Avbryt</button>
          </div>
          ${state.tpSync.error ? `<p class="error">${escapeHtml(state.tpSync.error)}</p>` : ''}
        </div>`
      : ''
  return `
    <div class="section-block plan-month-calendar">
      <div class="section-head">
        <h2>Treningskalender</h2>
        <div class="cal-month-nav">
          <button type="button" class="btn btn-sm secondary" id="cal-prev-month" aria-label="Forrige måned">‹</button>
          <span class="cal-month-title">${escapeHtml(monthLabelNb(monthKey))}</span>
          <button type="button" class="btn btn-sm secondary" id="cal-next-month" aria-label="Neste måned">›</button>
        </div>
      </div>
      <p class="muted tight">App-plan + Intervals-WORKOUTs. <span class="cal-legend"><span class="cal-dot cal-dot-synced">•</span> synket</span> · <span class="cal-legend"><span class="cal-dot cal-dot-unsynced">•</span> ikke synket</span> · <span class="cal-legend"><span class="cal-dot cal-dot-icu">•</span> kun Intervals</span>. Kilde: coach / agent / manuell. Sync <strong>uke/måned</strong> pusher app → Intervals.</p>
      <div class="cal-source-filters" role="group" aria-label="Filtrer kilde">${sourceFilters}</div>
      ${metaBits.length ? `<p class="muted tight">${escapeHtml(metaBits.join(' · '))}</p>` : ''}
      ${
        !total && (state.planBlocks || []).length
          ? `<p class="muted tight">Grovplan finnes, men ingen lagrede økter ennå — bekreft planjustering eller «rull videre» i Coach.</p>`
          : ''
      }
      ${
        total && !cells.some((c) => c.inMonth && c.sessions.length)
          ? `<p class="muted tight">Ingen økter i denne måneden — bruk ‹ › for å bla til uker med plan.</p>`
          : ''
      }
      ${ps.error ? `<p class="error">${escapeHtml(ps.error)}</p>` : ''}
      ${scopeHint}
      ${weekQualityHtml}
      <div class="cal-grid" role="grid" aria-label="Månedskalender">
        ${head}
        ${grid}
      </div>
      <div class="cal-side">
        <p class="plan-kicker">${selected ? `Dag ${escapeHtml(selected)}` : 'Velg en dag'}</p>
        ${
          selected
            ? `<ul class="horizon-session-list">${selList || '<li class="muted">Ingen økter</li>'}</ul>`
            : '<p class="muted tight">Klikk en dag for økter og uke-sync.</p>'
        }
        <div class="sync-actions cal-scope-actions">
          <button type="button" class="btn btn-sm" id="cal-sync-week" ${
            !selected || !state.intervals.connected ? 'disabled' : ''
          }>Sync uke → Intervals</button>
          <button type="button" class="btn btn-sm secondary" id="cal-sync-month" ${
            !state.intervals.connected ? 'disabled' : ''
          }>Sync måned → Intervals</button>
          <button type="button" class="btn btn-sm secondary" id="cal-sync-week-tp" ${
            !selected ? 'disabled' : ''
          } title="Krever TP-cookie (beta API)">Sync uke → TP β</button>
        </div>
      </div>
      ${tpConfirm}
    </div>`
}

function renderPlanBlocksEditor() {
  const rows = (state.planBlocks || [])
    .map(
      (b, i) => `
      <div class="block-edit" data-block-id="${escapeHtml(b.id)}">
        <div class="grid-2">
          <div class="field"><label>Tittel</label><input name="title" value="${escapeHtml(b.title || '')}" /></div>
          <div class="field"><label>Uketimer</label><input name="weekly_hours" type="number" step="0.5" value="${b.weekly_hours ?? ''}" /></div>
        </div>
        <div class="field"><label>Tema</label><input name="theme" value="${escapeHtml(b.theme || '')}" /></div>
        <div class="field"><label>Plan B</label><input name="plan_b" value="${escapeHtml(b.plan_b || '')}" placeholder="Hvis sliten / vær / tid …" /></div>
        <div class="field"><label>Ukerisiko</label><input name="weekly_risk" value="${escapeHtml(b.weekly_risk || '')}" placeholder="Én setning — hva kan gå galt" /></div>
        <div class="grid-2">
          <div class="field"><label>Start</label><input name="start_date" type="date" value="${escapeHtml(b.start_date || '')}" /></div>
          <div class="field"><label>Slutt</label><input name="end_date" type="date" value="${escapeHtml(b.end_date || '')}" /></div>
        </div>
        <div class="row-actions">
          <button type="button" class="btn btn-sm" data-save-block="${escapeHtml(b.id)}">Lagre blokk</button>
          <button type="button" class="btn btn-sm secondary" data-delete-block="${escapeHtml(b.id)}">Slett</button>
        </div>
      </div>`
    )
    .join('')
  return `
    <div class="section-block">
      <div class="section-head">
        <h2>Grovplan / blokker</h2>
      </div>
      <p class="muted tight">Makro og meso — ikke ukeplan. Tom liste er OK for MVP.</p>
      ${rows || `<p class="muted">Ingen blokker ennå.</p>`}
      ${state.planError ? `<p class="error">${escapeHtml(state.planError)}</p>` : ''}
      <button type="button" class="btn secondary" id="add-plan-block" ${state.busy ? 'disabled' : ''}>Legg til blokk</button>
    </div>`
}

function renderDu() {
  const a = state.athlete
  const pers = PERSONALITIES.map(
    (p) => `<option value="${p.id}" ${a.coach_personality === p.id ? 'selected' : ''}>${p.label}</option>`
  ).join('')
  const swatches = ACCENTS.map(
    (c) =>
      `<button type="button" class="swatch ${a.accent_color === c ? 'selected' : ''}" data-color="${c}" style="background:${c}"></button>`
  ).join('')
  const agreements = (a.agreements || []).join('\n')
  return `
    <form id="du-form">
      <div class="section-block">
        <h2>Profil</h2>
        <div class="field profile-id-field">
          <label for="username_display">Brukernavn</label>
          <div class="profile-id-row">
            <input id="username_display" type="text" readonly value="${escapeHtml(a.username || '')}" />
            <button type="button" class="btn secondary" id="copy-username">Kopier</button>
          </div>
          <p class="muted tight">Lagre dette — brukes for «Jeg har allerede profil» på ny enhet.</p>
        </div>
        <details class="login-advanced profile-id-advanced">
          <summary>Profil-ID (avansert)</summary>
          <div class="field profile-id-field">
            <label for="profile_id_display">Intern profil-ID</label>
            <div class="profile-id-row">
              <input id="profile_id_display" type="text" readonly value="${escapeHtml(a.id || '')}" />
              <button type="button" class="btn secondary" id="copy-profile-id">Kopier</button>
            </div>
            <p class="muted tight">Teknisk ID — trengs sjelden når du har brukernavn.</p>
          </div>
        </details>
        <div class="field"><label>Navn</label><input name="display_name" value="${escapeHtml(a.display_name || '')}" /></div>
        <div class="field">
          <label for="du_email">E-post (valgfritt)</label>
          <input id="du_email" name="email" type="email" autocomplete="email"
            value="${escapeHtml(a.email || '')}"
            placeholder="deg@example.com" />
          <p class="muted tight">Brukes kun til sparsomme ticker-varsler (sync, roll, CTL) — aldri spam.</p>
        </div>
        <div class="field">
          <label class="toggle-label">
            <input type="checkbox" name="notify_email" ${a.notify_email ? 'checked' : ''} />
            E-postvarsler (opt-in)
          </label>
          <p class="muted tight">Krever e-post + Fly-secret <code>RESEND_API_KEY</code>. Uten nøkkel lagres valget, men sendes ikke.</p>
        </div>
        <div class="grid-2">
          <div class="field"><label>Trener</label><input name="coach_display_name" value="${escapeHtml(a.coach_display_name || '')}" /></div>
          <div class="field"><label>Personlighet</label><select name="coach_personality">${pers}</select></div>
        </div>
        <div class="field"><label>Aksentfarge</label><div class="swatches" id="du-swatches">${swatches}</div></div>
      </div>
      <div class="section-block">
        <h2>Mål & avtaler</h2>
        <div class="field"><label>Mål</label><textarea name="goal_text" rows="2">${escapeHtml(a.goal_text || '')}</textarea></div>
        <div class="field"><label>Ukens fokus</label><input name="weekly_focus" value="${escapeHtml(a.weekly_focus || '')}" /></div>
        <div class="field"><label>Skade / begrensninger</label><textarea name="injury_notes" rows="2">${escapeHtml(a.injury_notes || '')}</textarea></div>
        <div class="field"><label>Avtaler (én per linje)</label><textarea name="agreements" rows="3" placeholder="f.eks. Ingen langløp denne uka">${escapeHtml(agreements)}</textarea></div>
        <div class="field"><label>Notater</label><textarea name="notes" rows="2">${escapeHtml(a.notes || '')}</textarea></div>
        <div class="field"><label>Form (setup)</label><textarea name="fitness_notes" rows="2" placeholder="f.eks. Form OK — trener allerede 4×/uke">${escapeHtml(a.fitness_notes || '')}</textarea></div>
        <div class="grid-2">
          <div class="field"><label>Økter / uke</label><input name="sessions_per_week" type="number" min="2" max="8" value="${a.sessions_per_week ?? ''}" placeholder="4" /></div>
          <div class="field"><label>Disipliner (kommaseparert)</label><input name="allowed_disciplines" value="${escapeHtml((a.allowed_disciplines || []).join(', '))}" placeholder="run, strength" /></div>
        </div>
      </div>
      <div class="section-block">
        <h2>Sesongmål (timer)</h2>
        <p class="muted tight">Volummål for fremskritt / compliance på Dashboard.</p>
        <div class="grid-2">
          <div class="field"><label>Svøm (t)</label><input name="season_swim_hours_target" type="number" step="1" min="0" value="${a.season_swim_hours_target ?? ''}" placeholder="100" /></div>
          <div class="field"><label>Sykkel (t)</label><input name="season_bike_hours_target" type="number" step="1" min="0" value="${a.season_bike_hours_target ?? ''}" placeholder="500" /></div>
          <div class="field"><label>Løp (t)</label><input name="season_run_hours_target" type="number" step="1" min="0" value="${a.season_run_hours_target ?? ''}" placeholder="150" /></div>
          <div class="field"><label>Styrke (t)</label><input name="season_strength_hours_target" type="number" step="1" min="0" value="${a.season_strength_hours_target ?? ''}" placeholder="50" /></div>
        </div>
        <div class="grid-2">
          <div class="field"><label>Sesongstart</label><input name="season_start_date" type="date" value="${escapeHtml(a.season_start_date || '')}" /></div>
          <div class="field"><label>Racedato / mål</label><input name="goal_race_date" type="date" value="${escapeHtml(a.goal_race_date || '')}" /></div>
        </div>
      </div>
      <div class="section-block">
        <h2>Ernæring / GI</h2>
        <div class="field">
          <label>IBS</label>
          <select name="nutrition_ibs">
            <option value="no" ${a.nutrition_ibs === 'no' ? 'selected' : ''}>Nei</option>
            <option value="yes" ${a.nutrition_ibs === 'yes' ? 'selected' : ''}>Ja</option>
            <option value="unsure" ${a.nutrition_ibs === 'unsure' ? 'selected' : ''}>Usikker</option>
          </select>
        </div>
        <div class="field">
          <label>Gluten</label>
          <select name="nutrition_gluten">
            <option value="none" ${a.nutrition_gluten === 'none' ? 'selected' : ''}>Ingen</option>
            <option value="sensitive" ${a.nutrition_gluten === 'sensitive' ? 'selected' : ''}>Sensitivitet</option>
            <option value="celiac" ${a.nutrition_gluten === 'celiac' ? 'selected' : ''}>Cøliaki</option>
          </select>
        </div>
        <div class="field">
          <label><input type="checkbox" name="nutrition_lactose" ${a.nutrition_lactose ? 'checked' : ''} /> Laktoseproblemer</label>
        </div>
        <div class="field"><label>Andre restriksjoner</label><textarea name="nutrition_other_restrictions" rows="2">${escapeHtml(a.nutrition_other_restrictions || '')}</textarea></div>
        <div class="field"><label>Ernæringsnotater</label><textarea name="nutrition_notes" rows="2">${escapeHtml(a.nutrition_notes || '')}</textarea></div>
      </div>
      <div class="section-block">
        <h2>Personvern / visning</h2>
        <div class="field">
          <label class="toggle-label">
            <input type="checkbox" name="show_body_metrics" ${a.show_body_metrics ? 'checked' : ''} />
            Vis vekt og fett% på Dashboard
          </label>
          <p class="muted tight">Slå på for å vise kroppsmål fra wellness/BIA. Standard: av (personvern).</p>
        </div>
      </div>
      <div class="section-block">
        <h2>Form</h2>
        <div class="grid-2">
          <div class="field"><label>Testet FTP</label><input name="ftp_tested" type="number" value="${a.ftp_tested ?? ''}" /></div>
          <div class="field"><label>FTP-dato</label><input name="ftp_tested_at" type="date" value="${escapeHtml(a.ftp_tested_at || '')}" /></div>
        </div>
        <div class="grid-2">
          <div class="field"><label>Vekt kg</label><input name="weight_kg" type="number" value="${a.weight_kg ?? ''}" /></div>
          <div class="field"><label>Alder</label><input name="age_years" type="number" value="${a.age_years ?? ''}" /></div>
        </div>
      </div>
      ${state.error && state.tab === 'du' ? `<p class="error">${escapeHtml(state.error)}</p>` : ''}
      <div class="sync-actions" style="margin-top:0.75rem">
        <button class="btn btn-primary" type="submit" ${state.busy ? 'disabled' : ''}>Lagre profil</button>
        <button type="button" class="btn secondary" id="du-talk-coach-btn" ${state.busy ? 'disabled' : ''}>
          Snakk med treneren om endringene
        </button>
      </div>
      ${
        state.profileSavedForCoach
          ? `<p class="muted tight">Profil lagret. Trykk «Snakk med treneren…» for foreslått planjustering (forhåndsvis → bekreft — ingen stille Intervals-skriving).</p>`
          : `<p class="muted tight">Etter lagring kan du be treneren foreslå planjustering ut fra nye mål/avtaler.</p>`
      }
    </form>
    <form id="intervals-form" class="section-block intervals-section">
      <div class="section-head">
        <h2>Intervals</h2>
        <span class="badge ${state.intervals.connected ? 'badge-live' : 'badge-off'}" id="intervals-status-badge">
          ${state.intervals.connected ? 'Koblet' : 'Ikke koblet'}
        </span>
      </div>
      <p class="muted tight">
        ${
          state.intervals.connected
            ? `ID ${escapeHtml(state.intervals.intervals_athlete_id || '—')}${
                state.intervals.api_key_hint
                  ? ` · nøkkel ${escapeHtml(state.intervals.api_key_hint)}`
                  : ''
              }. Nøkkel lagres kun på server.`
            : 'Hent nøkkel under Intervals → Settings → Developer Settings. Lagres kun på server.'
        }
      </p>
      <div class="field">
        <label for="intervals_athlete_id">Athlete ID</label>
        <input id="intervals_athlete_id" name="intervals_athlete_id" autocomplete="off"
          inputmode="text" enterkeyhint="next"
          value="${escapeHtml(state.intervals.form_athlete_id || '')}"
          placeholder="f.eks. i123456" required ${state.intervalsBusy ? 'disabled' : ''} />
      </div>
      <div class="field">
        <label for="intervals_api_key">API-nøkkel</label>
        <input id="intervals_api_key" name="intervals_api_key" type="password" autocomplete="off"
          enterkeyhint="done"
          value="${escapeHtml(state.intervals.form_api_key || '')}"
          placeholder="${
            state.intervals.api_key_hint
              ? `Lagret ${escapeHtml(state.intervals.api_key_hint)} — tomt = behold`
              : 'Lim inn API-nøkkel'
          }"
          ${state.intervals.connected ? '' : 'required'}
          ${state.intervalsBusy ? 'disabled' : ''} />
      </div>
      ${
        state.intervalsStatus
          ? `<p class="intervals-status ${state.intervalsError ? 'is-warn' : 'is-ok'}">${escapeHtml(state.intervalsStatus)}</p>`
          : ''
      }
      ${state.intervalsError ? `<p class="error">${escapeHtml(state.intervalsError)}</p>` : ''}
      <div class="intervals-actions">
        <button class="btn btn-primary" type="submit" ${state.intervalsBusy ? 'disabled' : ''}>
          ${state.intervalsBusy ? 'Lagrer…' : 'Lagre'}
        </button>
        <button class="btn secondary" type="button" id="intervals-test"
          ${state.intervalsBusy || !state.intervals.connected ? 'disabled' : ''}>
          Test tilkobling
        </button>
      </div>
    </form>
    <div class="section-block settings-danger">
      <h2>Innstillinger / sesjon</h2>
      <p class="muted tight">Logg ut tømmer lokal sesjon på denne enheten. Nullstill setup sletter grovplan og mål (krever dobbelt bekreftelse).</p>
      <div class="setup-nav" style="margin-top:0.75rem">
        <button type="button" class="btn secondary" id="btn-logout" ${state.busy ? 'disabled' : ''}>Logg ut</button>
        <button type="button" class="btn secondary danger-outline" id="btn-restart-setup" ${state.busy ? 'disabled' : ''}>
          Start setup på nytt
        </button>
      </div>
      ${
        state.resetConfirm === 1
          ? `<div class="confirm-card" role="dialog" aria-label="Bekreft nullstilling steg 1">
              <p><strong>Steg 1/2:</strong> Dette sletter grovplan-blokker, sesongmål, avtaler, utøvertype og chat-historikk for profilen.</p>
              <label class="field tight"><input type="checkbox" id="reset-delete-icu" ${state.resetDeleteIcu ? 'checked' : ''} />
                Slett også coach-økter på Intervals (<code>ll-coach-*</code> / <code>ll-coach-w-*</code> — ikke hele kalenderen)
              </label>
              <div class="sync-actions">
                <button type="button" class="btn btn-primary" id="reset-confirm-1">Ja, fortsett</button>
                <button type="button" class="btn secondary" id="reset-cancel">Avbryt</button>
              </div>
            </div>`
          : ''
      }
      ${
        state.resetConfirm === 2
          ? `<div class="confirm-card" role="dialog" aria-label="Bekreft nullstilling steg 2">
              <p><strong>Steg 2/2:</strong> Skriv <code>SLETT</code> for å bekrefte.
              ${
                state.resetDeleteIcu
                  ? ' Coach-hendelser på Intervals slettes også (dobbelt bekreftet via avhuking + SLETT).'
                  : ' Intervals-kalenderen røres ikke.'
              }</p>
              <div class="field">
                <input id="reset-phrase" autocomplete="off" placeholder="SLETT" ${state.busy ? 'disabled' : ''} />
              </div>
              <div class="sync-actions">
                <button type="button" class="btn btn-primary" id="reset-confirm-2" ${state.busy ? 'disabled' : ''}>Nullstill nå</button>
                <button type="button" class="btn secondary" id="reset-cancel" ${state.busy ? 'disabled' : ''}>Avbryt</button>
              </div>
            </div>`
          : ''
      }
      ${state.error && state.tab === 'du' && state.resetConfirm ? `<p class="error">${escapeHtml(state.error)}</p>` : ''}
    </div>
  `
}

function bindApp() {
  document.querySelectorAll('.tabs button').forEach((btn) => {
    btn.addEventListener('click', async () => {
      state.tab = btn.dataset.tab
      state.error = ''
      state.intervalsError = ''
      state.intervalsStatus = ''
      state.planError = ''
      state.sync.error = ''
      state.sync.message = ''
      if (state.tab === 'dashboard') {
        await refreshOverview()
        await refreshDashboard()
        await refreshTicker({ refresh: true })
      }
      if (state.tab === 'coach') {
        await refreshTicker({ refresh: false })
      }
      if (state.tab === 'plan') {
        await refreshOverview()
        await refreshPlanBlocks()
        await refreshPlannedSessions()
        await refreshIntervals()
      }
      if (state.tab === 'okter') {
        await refreshIntervals()
        await refreshSessions()
      }
      if (state.tab === 'beta') {
        await refreshBeta()
      }
      if (state.tab === 'du') {
        await refreshIntervals()
      }
      render()
    })
  })

  document.getElementById('beta-open-coach')?.addEventListener('click', () => {
    const sc = state.beta?.scenario_ease
    const draft =
      sc?.note_nb ||
      'Beta-scenario: vurdere å lette ~20 % neste 2 uker. Kun forslag — bekreft før lagring.'
    state.tab = 'coach'
    state.chatDraft = draft
    state.error = ''
    render()
  })

  document.getElementById('ticker-read-all')?.addEventListener('click', async () => {
    try {
      await api('/v1/athlete/me/events/read-all', { method: 'POST', body: {} })
      await refreshTicker({ refresh: false })
    } catch (err) {
      state.ticker = {
        ...(state.ticker || { events: [], unread_count: 0 }),
        error: err.message || 'Kunne ikke merke lest',
      }
    }
    render()
  })

  document.querySelectorAll('[data-ticker-id]').forEach((btn) => {
    btn.addEventListener('click', async () => {
      const id = btn.dataset.tickerId
      const kind = btn.dataset.tickerKind || ''
      const ev = (state.ticker?.events || []).find((e) => e.id === id)
      const action = ev?.payload?.action || ''
      try {
        if (id) {
          await api(`/v1/athlete/me/events/${encodeURIComponent(id)}/read`, {
            method: 'POST',
            body: {},
          })
        }
      } catch {
        /* soft */
      }
      // Open confirm/plan surfaces — never auto-apply / auto-sync
      if (action === 'open_plan' || kind === 'sessions_saved' || kind === 'sync_ok') {
        state.tab = 'plan'
        await refreshPlannedSessions()
      } else if (
        action === 'open_roll' ||
        action === 'open_ease' ||
        action === 'open_coach' ||
        kind === 'roll_forward_due' ||
        kind === 'ctl_overload' ||
        kind === 'weekly_cap_replace' ||
        kind === 'sync_fail' ||
        kind === 'readiness_soft'
      ) {
        state.tab = 'coach'
        // Tap opens a real proposal card when possible (Human Coach preview — not apply).
        let seed = ''
        if (kind === 'ctl_overload' || action === 'open_ease') {
          seed = 'lette denne uka'
        } else if (kind === 'roll_forward_due' || action === 'open_roll') {
          seed = 'rull videre'
        } else if (kind === 'weekly_cap_replace') {
          seed = 'legg inn økt i morgen'
        } else if (ev?.payload?.message) {
          toast(ev.payload.message)
        }
        if (seed && !state.busy) {
          state.chatDraft = ''
          state.messages.push({ role: 'user', content: seed })
          state.busy = true
          render()
          try {
            const data = await sendCoachMessage(seed)
            state.messages.push({ role: 'assistant', content: data.reply || '…' })
            applyChatResponse(data, { mirrorToMain: false })
            toast(
              kind === 'roll_forward_due' || action === 'open_roll'
                ? 'Roll-forslag åpnet — bekreft kortet (ingen auto-apply).'
                : kind === 'weekly_cap_replace'
                  ? 'Ukeskap — erstatningskort åpnet (forhåndsvis → bekreft).'
                  : 'Lett-uke-forslag åpnet — bekreft kortet (ingen auto-apply).',
            )
          } catch (err) {
            state.messages.pop()
            state.chatDraft = seed
            toast(err.message || 'Kunne ikke åpne forslag — send meldingen manuelt.')
          } finally {
            state.busy = false
          }
        }
      } else {
        state.tab = 'coach'
      }
      await refreshTicker({ refresh: false })
      render()
    })
  })

  document.querySelectorAll('[data-period]').forEach((btn) => {
    btn.addEventListener('click', async () => {
      const preset = btn.dataset.period
      if (!preset || state.busy) return
      state.dashboardPeriod = {
        ...(state.dashboardPeriod || {}),
        preset,
      }
      if (preset !== 'custom') {
        state.busy = true
        render()
        await refreshDashboard()
        state.busy = false
        render()
        return
      }
      // Custom: show date fields; apply on Vis
      const today = new Date()
      const iso = (d) => {
        const y = d.getFullYear()
        const m = String(d.getMonth() + 1).padStart(2, '0')
        const day = String(d.getDate()).padStart(2, '0')
        return `${y}-${m}-${day}`
      }
      if (!state.dashboardPeriod.from || !state.dashboardPeriod.to) {
        const end = iso(today)
        const start = new Date(today)
        start.setDate(start.getDate() - 13)
        state.dashboardPeriod.from = iso(start)
        state.dashboardPeriod.to = end
      }
      render()
    })
  })

  document.getElementById('period-apply')?.addEventListener('click', async () => {
    const fromEl = document.getElementById('period_from')
    const toEl = document.getElementById('period_to')
    const from = (fromEl?.value || '').trim()
    const to = (toEl?.value || '').trim()
    if (!from || !to) {
      state.planError = 'Velg både fra- og tildato.'
      render()
      return
    }
    state.dashboardPeriod = { preset: 'custom', from, to }
    state.planError = ''
    state.busy = true
    render()
    await refreshDashboard()
    state.busy = false
    render()
  })

  document.getElementById('copy-username')?.addEventListener('click', async () => {
    const username = state.athlete?.username || ''
    if (!username) return
    try {
      await navigator.clipboard.writeText(username)
      toast('Brukernavn kopiert')
    } catch {
      const input = document.getElementById('username_display')
      if (input) {
        input.select()
        toast('Marker brukernavn og kopier manuelt')
      }
    }
  })

  document.getElementById('copy-profile-id')?.addEventListener('click', async () => {
    const id = state.athlete?.id || ''
    if (!id) return
    try {
      await navigator.clipboard.writeText(id)
      toast('Profil-ID kopiert')
    } catch {
      const input = document.getElementById('profile_id_display')
      if (input) {
        input.select()
        toast('Marker ID og kopier manuelt')
      }
    }
  })

  const chatForm = document.getElementById('chat-form')
  chatForm?.addEventListener('submit', async (e) => {
    e.preventDefault()
    const input = document.getElementById('chat-input')
    const message = (input?.value || '').trim()
    if (!message || state.busy) return
    state.chatDraft = ''
    state.workoutProposal = null
    state.workoutRemoval = null
    state.athleteTypeProposal = null
    state.agreementsProposal = null
    state.ukesopp = null
    state.weekCheck = null
    state.workoutSync.pending = null
    state.workoutSync.error = ''
    state.workoutSync.message = ''
    state.messages.push({ role: 'user', content: message })
    state.busy = true
    state.error = ''
    render()
    const log = document.getElementById('chat-log')
    if (log) log.scrollTop = log.scrollHeight
    try {
      const data = await sendCoachMessage(message)
      state.messages.push({ role: 'assistant', content: data.reply })
      applyChatResponse(data, { mirrorToMain: false })
    } catch (err) {
      state.error = err.message || 'Chat feilet'
      state.messages.pop()
    } finally {
      state.busy = false
      render()
      const log2 = document.getElementById('chat-log')
      if (log2) log2.scrollTop = log2.scrollHeight
    }
  })

  document.getElementById('workout-dismiss-btn')?.addEventListener('click', () => {
    state.workoutProposal = null
    state.workoutRemoval = null
    state.replaceSessionIds = []
    state.workoutSync.pending = null
    state.workoutSync.message = 'Forslag avvist'
    state.workoutSync.error = ''
    render()
  })

  document.getElementById('athlete-type-dismiss-btn')?.addEventListener('click', () => {
    state.athleteTypeProposal = null
    render()
  })

  document.getElementById('agreements-dismiss-btn')?.addEventListener('click', () => {
    state.agreementsProposal = null
    render()
  })

  document.getElementById('week-check-dismiss-btn')?.addEventListener('click', () => {
    state.weekCheck = null
    render()
  })
  document.getElementById('ukesopp-dismiss-btn')?.addEventListener('click', () => {
    state.ukesopp = null
    state.ukesoppAnswerDrafts = {}
    state.ukesoppSaveMessage = ''
    state.ukesoppSaveError = ''
    render()
  })

  document.querySelectorAll('.ukesopp-answer').forEach((el) => {
    el.addEventListener('input', () => {
      const i = el.getAttribute('data-ukesopp-i')
      if (i == null) return
      state.ukesoppAnswerDrafts = {
        ...(state.ukesoppAnswerDrafts || {}),
        [i]: el.value,
      }
    })
  })

  document.getElementById('ukesopp-save-btn')?.addEventListener('click', async () => {
    const u = state.ukesopp
    if (!u?.week_start || !u?.week_end) return
    const answers = (u.questions || []).map((_, i) => {
      const el = document.querySelector(`.ukesopp-answer[data-ukesopp-i="${i}"]`)
      return (el?.value || state.ukesoppAnswerDrafts?.[i] || '').trim()
    })
    if (!answers.some(Boolean)) {
      state.ukesoppSaveError = 'Skriv minst ett svar før lagring'
      state.ukesoppSaveMessage = ''
      render()
      return
    }
    state.busy = true
    state.ukesoppSaveError = ''
    state.ukesoppSaveMessage = ''
    render()
    try {
      const data = await api('/v1/ukesopp/save', {
        method: 'POST',
        body: {
          week_start: u.week_start,
          week_end: u.week_end,
          answers,
        },
      })
      state.ukesoppSaveMessage =
        data.message_nb || 'Ukesopp lagret i appen (ikke Intervals).'
      state.ukesopp = null
      state.ukesoppAnswerDrafts = {}
      try {
        await refreshTicker()
      } catch {
        /* soft */
      }
    } catch (err) {
      state.ukesoppSaveError = err.message || 'Kunne ikke lagre ukesopp'
    } finally {
      state.busy = false
      render()
    }
  })

  document.getElementById('agreements-confirm-btn')?.addEventListener('click', async () => {
    const prop = state.agreementsProposal
    if (!prop) return
    state.busy = true
    state.workoutSync.error = ''
    render()
    try {
      const patch = {}
      for (const k of [
        'sessions_per_week',
        'goal_race_date',
        'goal_text',
        'allowed_disciplines',
        'agreements',
        'fitness_notes',
        'schedule_notes',
      ]) {
        if (prop[k] != null && prop[k] !== '') patch[k] = prop[k]
      }
      const data = await api('/v1/athlete/me', { method: 'PATCH', body: patch })
      state.athlete = data.athlete
      state.agreementsProposal = null
      state.workoutSync.message = 'Treningsavtaler oppdatert — bygger planforslag…'
      toast(state.workoutSync.message)
      // Agile path: agreements → plan preview (Utøver → AI → Forslag → Preview)
      const prev = await api('/v1/athlete/me/plan/adjust/preview', {
        method: 'POST',
        body: { enrich_with_llm: false },
      })
      state.planAdjust = prev
      state.workoutSync.message =
        prev.confirm_hint || 'Forhåndsvis ny plan — bekreft for å lagre.'
      toast(state.workoutSync.message)
    } catch (err) {
      state.workoutSync.error = err.message || 'Kunne ikke lagre avtaler / planforslag'
    } finally {
      state.busy = false
      render()
    }
  })

  document.getElementById('plan-adjust-dismiss-btn')?.addEventListener('click', () => {
    state.planAdjust = null
    state.workoutSync.error = ''
    render()
  })

  document.getElementById('plan-adjust-confirm-btn')?.addEventListener('click', async () => {
    const pa = state.planAdjust
    if (!pa) return
    const isWeek = pa.scope === 'week'
    const isRoll = pa.op === 'plan_roll' || pa.scope === 'detalj'
    if (!isWeek && !isRoll && !pa.plan_blocks?.length) return
    if ((isWeek || isRoll) && !pa.sessions?.length) return
    state.busy = true
    state.workoutSync.error = ''
    render()
    try {
      // Default: lagre kun i app. Opt-in checkbox for Intervals-forberedelse.
      const prepareSync = Boolean(
        document.getElementById('plan-prepare-icu-sync')?.checked,
      )
      let data
      if (isRoll) {
        data = await api('/v1/athlete/me/plan/roll/confirm', {
          method: 'POST',
          body: {
            detalj_start: pa.detalj_start,
            detalj_end: pa.detalj_end,
            sessions: pa.sessions,
            readiness: pa.readiness || {},
            prepare_intervals_sync: prepareSync,
          },
        })
      } else if (isWeek) {
        const ready = pa.readiness_hints || pa.readiness || {}
        const reason =
          pa.reason ||
          ready.summary_nb ||
          (pa.ease_load ? 'Lett uke bekreftet' : '')
        data = await api('/v1/athlete/me/plan/week-adjust/confirm', {
          method: 'POST',
          body: {
            week_start: pa.week_start,
            week_end: pa.week_end,
            sessions: pa.sessions,
            ease_load: Boolean(pa.ease_load),
            prepare_intervals_sync: prepareSync,
            reason,
            readiness: ready,
          },
        })
      } else {
        data = await api('/v1/athlete/me/plan/adjust/confirm', {
          method: 'POST',
          body: {
            plan_blocks: pa.plan_blocks,
            athlete_patch: pa.athlete_patch || {},
            prepare_intervals_sync: prepareSync,
          },
        })
      }
      if (data.athlete) state.athlete = data.athlete
      state.planAdjust = null
      state.workoutSync.message =
        data.message ||
        (isRoll ? 'Neste detalj lagret' : isWeek ? 'Uke oppdatert' : 'Plan oppdatert')
      toast(state.workoutSync.message)
      await refreshPlanBlocks()
      await refreshPlannedSessions()
      await refreshOverview()
      if (data.intervals_pending) {
        state.tab = 'plan'
        state.sync.pending = data.intervals_pending
        state.sync.message = data.intervals_pending.message || 'Bekreft Sync til Intervals'
      }
    } catch (err) {
      state.workoutSync.error = err.message || 'Kunne ikke bekrefte planjustering'
    } finally {
      state.busy = false
      render()
    }
  })

  document.getElementById('athlete-type-confirm-btn')?.addEventListener('click', async () => {
    const prop = state.athleteTypeProposal
    if (!prop?.to && !prop?.athlete_type) return
    state.busy = true
    state.workoutSync.error = ''
    render()
    try {
      const data = await api('/v1/athlete/me/athlete-type', {
        method: 'POST',
        body: {
          athlete_type: prop.to || prop.athlete_type,
          reason: prop.reason || '',
          rebuild_plan_preview: true,
        },
      })
      state.athlete = data.athlete
      state.athleteTypeProposal = null
      state.workoutSync.message = data.message || 'Hovedprofil oppdatert'
      toast(state.workoutSync.message)
      if (data.plan_preview?.plan_blocks?.length) {
        // Same confirm path as plan_update / Du adjust
        const prev = await api('/v1/athlete/me/plan/adjust/preview', {
          method: 'POST',
          body: { enrich_with_llm: false },
        })
        state.planAdjust = prev
      } else if (data.plan_preview?.plan_blocks) {
        state.planAdjust = {
          ...data.plan_preview,
          confirm_hint: data.plan_preview.confirm_hint,
        }
      }
    } catch (err) {
      state.workoutSync.error = err.message || 'Kunne ikke oppdatere type'
    } finally {
      state.busy = false
      render()
    }
  })

  document.getElementById('workout-remove-preview-btn')?.addEventListener('click', async () => {
    const removal = state.workoutRemoval
    if (!removal || state.workoutSync.busy) return
    if (!state.intervals.connected) {
      state.workoutSync.error = 'Koble Intervals under Du først'
      render()
      return
    }
    state.workoutSync.busy = true
    state.workoutSync.error = ''
    state.workoutSync.message = 'Lager slette-forhåndsvisning…'
    render()
    try {
      const data = await api('/v1/athlete/me/intervals/workouts/remove/preview', {
        method: 'POST',
        body: {
          external_ids: removal.external_ids || [],
          dates: removal.dates || [],
          names: removal.names || [],
        },
      })
      state.workoutSync.pending = data
      state.workoutSync.message = data.message || 'Bekreft sletting'
    } catch (err) {
      state.workoutSync.error = err.message || 'Forhåndsvisning feilet'
      state.workoutSync.message = ''
    } finally {
      state.workoutSync.busy = false
      render()
    }
  })

  document.querySelectorAll('.replace-session-cb').forEach((el) => {
    el.addEventListener('change', () => {
      state.replaceSessionIds = [...document.querySelectorAll('.replace-session-cb:checked')].map(
        (cb) => cb.value,
      )
      render()
    })
  })

  document.getElementById('workout-preview-btn')?.addEventListener('click', async () => {
    const workouts = state.workoutProposal?.workouts
    if (!workouts?.length || state.workoutSync.busy) return
    const replaceNeeded = Boolean(state.workoutProposal?.replace_required)
    const replaceIds = state.replaceSessionIds || state.workoutProposal?.replace_session_ids || []
    if (replaceNeeded && !replaceIds.length) {
      state.workoutSync.error = 'Velg minst én økt å erstatte'
      render()
      return
    }
    state.workoutSync.busy = true
    state.workoutSync.error = ''
    state.workoutSync.message = 'Lager forhåndsvisning…'
    render()
    try {
      const prepareSync = Boolean(
        document.getElementById('workout-prepare-icu-sync')?.checked,
      )
      const data = await api('/v1/athlete/me/intervals/workouts/preview', {
        method: 'POST',
        body: {
          workouts,
          prepare_intervals_sync: prepareSync,
          replace_session_ids: replaceIds,
        },
      })
      state.workoutSync.pending = data
      state.workoutSync.message = data.message || 'Bekreft lagring'
    } catch (err) {
      state.workoutSync.error = err.message || 'Forhåndsvisning feilet'
      state.workoutSync.message = ''
      // Cap-hit without replace may return structured detail — surface candidates
      const detail = err.detail || err.body || null
      if (detail?.replace_candidates?.length) {
        state.workoutProposal = {
          ...(state.workoutProposal || {}),
          workouts: state.workoutProposal?.workouts || workouts,
          replace_required: true,
          replace_candidates: detail.replace_candidates,
          replace_session_ids: detail.replace_candidates
            .filter((c) => c.same_date)
            .map((c) => c.id)
            .slice(0, workouts.length),
        }
        state.replaceSessionIds = [...(state.workoutProposal.replace_session_ids || [])]
      }
    } finally {
      state.workoutSync.busy = false
      render()
    }
  })

  document.getElementById('workout-confirm-push-btn')?.addEventListener('click', async () => {
    // One-shot: preview → confirm the *same* card workouts (CLI builder, not library stub).
    const workouts = state.workoutProposal?.workouts
    if (!workouts?.length || state.workoutSync.busy) return
    state.workoutSync.busy = true
    state.workoutSync.error = ''
    state.workoutSync.message = 'Lagrer og pusher…'
    render()
    try {
      const prev = await api('/v1/athlete/me/intervals/workouts/preview', {
        method: 'POST',
        body: {
          workouts,
          prepare_intervals_sync: true,
          replace_session_ids: state.replaceSessionIds || [],
        },
      })
      if (!prev?.pending_id) throw new Error('Mangler pending_id fra forhåndsvisning')
      const data = await api('/v1/athlete/me/intervals/calendar/confirm', {
        method: 'POST',
        body: { pending_id: prev.pending_id },
      })
      const n = data.pushed ?? 0
      const saved = data.planned_sessions_saved ?? workouts.length
      state.workoutSync.pending = null
      state.workoutProposal = null
      state.workoutSync.message = `${saved} økt(er) lagret i planen${n ? ` · ${n} på Intervals` : ''}`
      toast(state.workoutSync.message)
      state.messages = [
        ...state.messages,
        { role: 'assistant', content: `Bekreftet: ${state.workoutSync.message}.` },
      ]
      try {
        await refreshPlannedSessions()
        await refreshSessions()
        await refreshDashboard()
      } catch {
        /* soft */
      }
    } catch (err) {
      state.workoutSync.error = err.message || 'Bekreft og push feilet'
      state.workoutSync.message = ''
    } finally {
      state.workoutSync.busy = false
      render()
    }
  })

  document.getElementById('workout-confirm-no')?.addEventListener('click', () => {
    state.workoutSync.pending = null
    state.workoutSync.message = 'Avbrutt'
    state.workoutSync.error = ''
    render()
  })

  document.getElementById('workout-confirm-yes')?.addEventListener('click', async () => {
    const pending = state.workoutSync.pending
    if (!pending?.pending_id || state.workoutSync.busy) return
    state.workoutSync.busy = true
    state.workoutSync.error = ''
    state.workoutSync.message = 'Syncer…'
    render()
    try {
      const data = await api('/v1/athlete/me/intervals/calendar/confirm', {
        method: 'POST',
        body: { pending_id: pending.pending_id },
      })
      const n = data.pushed ?? data.deleted ?? pending.count ?? 0
      const saved = data.planned_sessions_saved
      state.workoutSync.pending = null
      state.workoutProposal = null
      state.workoutRemoval = null
      state.workoutSync.message =
        data.op === 'delete'
          ? `${n} coach-hendelse(r) slettet fra Intervals`
          : saved
            ? `${saved} økt(er) lagret i planen${n ? ` · ${n} på Intervals` : ''}`
            : `${n} økt(er) lagt på Intervals-kalenderen`
      toast(state.workoutSync.message)
      // Keep coach chat aligned with toast — never leave «har ikke oppdatert» after success.
      state.messages = [
        ...state.messages,
        {
          role: 'assistant',
          content:
            data.op === 'delete'
              ? state.workoutSync.message
              : `Bekreftet: ${state.workoutSync.message}.`,
        },
      ]
      try {
        await refreshPlannedSessions()
        await refreshSessions()
        await refreshDashboard()
        const sid = state.sessionDetail?.session?.id
        if (sid) {
          state.sessionDetail = await api(`/v1/sessions/${encodeURIComponent(sid)}`)
        }
      } catch {
        /* soft */
      }
    } catch (err) {
      state.workoutSync.error = err.message || 'Bekreftelse feilet'
      state.workoutSync.message = ''
    } finally {
      state.workoutSync.busy = false
      render()
    }
  })

  const findSession = (id) => {
    const sess = state.sessions || {}
    for (const bucket of ['today', 'upcoming', 'recent']) {
      for (const s of sess[bucket] || []) {
        if (s.id === id || s.external_id === id) return s
      }
    }
    for (const item of sess.library || []) {
      for (const o of item.occurrences || []) {
        if (o.id === id || o.external_id === id) return { ...item, ...o, name: item.name }
      }
    }
    return state.sessionDetail?.session?.id === id
      ? state.sessionDetail.session
      : null
  }

  const openSessionDetail = async (sessionId, { scrollLog = false } = {}) => {
    if (!sessionId) return
    try {
      const data = await api(`/v1/sessions/${encodeURIComponent(sessionId)}`)
      state.sessionDetail = data
      state.sessionEditOpen = Boolean(data.editable) || Boolean(data.session?.app_planned)
      let steps = (data.builder_steps || data.editable_fields?.builder_steps || []).map((s, i) => ({
        ...s,
        sort_order: i,
      }))
      // Seed a minimal Øktbygger so the panel is never empty for editable sessions
      if (
        (data.editable || data.session?.app_planned) &&
        (!steps || !steps.length)
      ) {
        steps = [
          { type: 'warmup', duration_minutes: 10, intensity: 'Z1–Z2', note: '', sort_order: 0 },
          { type: 'work', duration_minutes: 30, intensity: 'Z2', note: '', sort_order: 1 },
          { type: 'cooldown', duration_minutes: 5, intensity: 'lett', note: '', sort_order: 2 },
        ]
      }
      state.builderSteps = steps
      state.sessionChat = {
        messages: [],
        draft: '',
        busy: false,
        error: '',
      }
      state.planError = ''
      state.tab = 'okter'
      render()
      if (scrollLog) {
        document.getElementById('session-log-block')?.scrollIntoView({ behavior: 'smooth' })
      } else {
        document.getElementById('session-chat-block')?.scrollIntoView({ behavior: 'smooth', block: 'nearest' })
        document.getElementById('session-chat-input')?.focus({ preventScroll: true })
      }
    } catch (err) {
      state.planError = err.message || 'Kunne ikke åpne økt'
      toast(state.planError)
      render()
    }
  }

  document.querySelectorAll('[data-sessions-view]').forEach((btn) => {
    btn.addEventListener('click', () => {
      state.sessionsView = btn.getAttribute('data-sessions-view') || 'library'
      render()
    })
  })

  document.querySelectorAll('[data-open-detail]').forEach((el) => {
    const open = () => void openSessionDetail(el.getAttribute('data-open-detail'))
    el.addEventListener('click', (e) => {
      if (e.target.closest('[data-open-log]')) return
      open()
    })
    el.addEventListener('keydown', (e) => {
      if (e.key === 'Enter' || e.key === ' ') {
        e.preventDefault()
        open()
      }
    })
  })

  document.querySelectorAll('[data-open-log]').forEach((btn) => {
    btn.addEventListener('click', (e) => {
      e.stopPropagation()
      void openSessionDetail(btn.getAttribute('data-open-log'), { scrollLog: true })
    })
  })

  document.getElementById('close-session-detail')?.addEventListener('click', () => {
    state.sessionDetail = null
    state.sessionEditOpen = false
    state.sessionChat = { messages: [], draft: '', busy: false, error: '' }
    render()
  })

  document.getElementById('toggle-session-edit')?.addEventListener('click', () => {
    state.sessionEditOpen = !state.sessionEditOpen
    render()
  })

  function readBuilderStepsFromDom() {
    const rows = [...document.querySelectorAll('.builder-step')]
    return rows.map((row, i) => ({
      id: `s${i + 1}`,
      type: row.querySelector('[data-field="type"]')?.value || 'work',
      duration_minutes: (() => {
        const v = row.querySelector('[data-field="duration_minutes"]')?.value
        return v ? Number(v) : null
      })(),
      intensity: row.querySelector('[data-field="intensity"]')?.value || null,
      note: row.querySelector('[data-field="note"]')?.value || null,
      sort_order: i,
    }))
  }

  document.getElementById('builder-add-step')?.addEventListener('click', () => {
    state.builderSteps = [
      ...(state.builderSteps || []),
      {
        id: `s${Date.now()}`,
        type: 'work',
        duration_minutes: 10,
        intensity: '',
        note: '',
        sort_order: (state.builderSteps || []).length,
      },
    ]
    render()
  })
  document.querySelectorAll('[data-remove-step]').forEach((btn) => {
    btn.addEventListener('click', () => {
      const i = Number(btn.getAttribute('data-remove-step'))
      state.builderSteps = (state.builderSteps || []).filter((_, idx) => idx !== i)
      render()
    })
  })
  document.querySelectorAll('.builder-step [data-field]').forEach((el) => {
    el.addEventListener('change', () => {
      state.builderSteps = readBuilderStepsFromDom()
      render()
    })
  })
  document.getElementById('builder-save-plan')?.addEventListener('click', async () => {
    const detail = state.sessionDetail?.session
    if (!detail?.id || state.workoutSync.busy) return
    const form = document.getElementById('session-edit-form')
    if (!form) return
    const fd = new FormData(form)
    const steps = readBuilderStepsFromDom()
    if (!steps.length) {
      toast('Legg til minst ett steg før lagring')
      return
    }
    const durationRaw = String(fd.get('duration_minutes') || '').trim()
    const payload = {
      name: String(fd.get('name') || '').trim(),
      date: String(fd.get('date') || '').trim().slice(0, 10),
      sport: String(fd.get('sport') || 'other'),
      start_time: String(fd.get('start_time') || '07:00'),
      external_id: String(fd.get('external_id') || '') || null,
      steps,
      prepare_intervals_sync: false,
    }
    if (durationRaw) payload.duration_minutes = Number(durationRaw)
    state.workoutSync.busy = true
    state.workoutSync.error = ''
    render()
    try {
      const data = await api(`/v1/sessions/${encodeURIComponent(detail.id)}/builder/confirm`, {
        method: 'POST',
        body: payload,
      })
      toast(data.message || 'Lagret i planen')
      if (data.intervals_pending) {
        state.workoutSync.pending = data.intervals_pending
      }
      state.sessionDetail = await api(`/v1/sessions/${encodeURIComponent(detail.id)}`)
      state.builderSteps = data.builder_steps || state.builderSteps
    } catch (err) {
      state.workoutSync.error = err.message || 'Lagring feilet'
      toast(state.workoutSync.error)
    } finally {
      state.workoutSync.busy = false
      render()
    }
  })

  document.getElementById('session-edit-form')?.addEventListener('submit', async (e) => {
    e.preventDefault()
    const detail = state.sessionDetail?.session
    if (!detail?.id || state.workoutSync.busy) return
    const fd = new FormData(e.target)
    const durationRaw = String(fd.get('duration_minutes') || '').trim()
    const warmup = String(fd.get('warmup') || '').trim()
    const main = String(fd.get('main') || '').trim()
    const cooldown = String(fd.get('cooldown') || '').trim()
    const rawDesc = String(fd.get('description') || '').trim()
    const linesFrom = (block, label) => {
      const rows = block
        .split('\n')
        .map((l) => l.replace(/^[-*•]\s*/, '').trim())
        .filter(Boolean)
      if (!rows.length) return []
      return [`${label}:`, ...rows.map((r) => `- ${r}`), '']
    }
    let description = rawDesc
    if (warmup || main || cooldown) {
      description = [
        ...linesFrom(warmup, 'Oppvarming'),
        ...linesFrom(main, 'Hoveddel'),
        ...linesFrom(cooldown, 'Nedkjøling'),
      ]
        .join('\n')
        .trim()
      // Keep raw coach prose above intervals block if it looked like planned format
      if (rawDesc && rawDesc.includes('###')) {
        const head = rawDesc.split(/\n---\n/)[0].trim()
        description = `${head}\n\n---\n\n${description}`
      }
    }
    const steps = (typeof readBuilderStepsFromDom === 'function')
      ? readBuilderStepsFromDom()
      : (state.builderSteps || [])
    const payload = {
      name: String(fd.get('name') || '').trim(),
      date: String(fd.get('date') || '').trim().slice(0, 10),
      sport: String(fd.get('sport') || 'other'),
      description,
      start_time: String(fd.get('start_time') || '07:00'),
      external_id: String(fd.get('external_id') || '') || null,
      steps,
    }
    if (durationRaw) payload.duration_minutes = Number(durationRaw)
    state.workoutSync.busy = true
    state.workoutSync.error = ''
    render()
    try {
      const data = await api(
        `/v1/sessions/${encodeURIComponent(detail.id)}/edit/preview`,
        { method: 'POST', body: payload },
      )
      state.workoutSync.pending = data
      state.workoutProposal = null
      toast('Forhåndsvisning klar — bekreft for å skrive til Intervals')
    } catch (err) {
      state.workoutSync.error = err.message || 'Forhåndsvisning feilet'
    } finally {
      state.workoutSync.busy = false
      render()
    }
  })

  document.querySelectorAll('[data-session-chip]').forEach((btn) => {
    btn.addEventListener('click', () => {
      const msg = btn.getAttribute('data-session-chip') || ''
      state.sessionChat.draft = msg
      render()
      document.getElementById('session-chat-input')?.focus()
    })
  })

  document.getElementById('session-chat-input')?.addEventListener('input', (e) => {
    state.sessionChat.draft = e.target.value
  })

  document.getElementById('session-chat-form')?.addEventListener('submit', async (e) => {
    e.preventDefault()
    const detail = state.sessionDetail?.session
    const input = document.getElementById('session-chat-input')
    const text = (input?.value || state.sessionChat.draft || '').trim()
    if (!text || !detail?.id || state.sessionChat.busy) return
    state.sessionChat.messages = [
      ...state.sessionChat.messages,
      { role: 'user', content: text },
    ]
    state.sessionChat.draft = ''
    state.sessionChat.busy = true
    state.sessionChat.error = ''
    state.workoutProposal = null
    state.workoutRemoval = null
    state.workoutSync.pending = null
    state.workoutSync.error = ''
    render()
    try {
      // Same /v1/chat + build_system_prompt as Coach-fanen; session_id only focuses context
      const data = await sendCoachMessage(text, { sessionId: detail.id })
      state.sessionChat.messages = [
        ...state.sessionChat.messages,
        { role: 'assistant', content: data.reply || '…' },
      ]
      applyChatResponse(data, { mirrorToMain: true, userText: text })
      if (!data.proposal_hint && !data.removal_hint) toast('Svar fra coach')
    } catch (err) {
      state.sessionChat.error = err.message || 'Samtale feilet'
    } finally {
      state.sessionChat.busy = false
      render()
      const log = document.getElementById('session-chat-log')
      if (log) log.scrollTop = log.scrollHeight
    }
  })

  document.getElementById('completion-form')?.addEventListener('submit', async (e) => {
    e.preventDefault()
    const detail = state.sessionDetail?.session
    if (!detail?.id || state.busy) return
    const fd = new FormData(e.target)
    const payload = {
      status: String(fd.get('status') || ''),
      reason: String(fd.get('reason') || ''),
      note: String(fd.get('note') || ''),
      session_name: detail.name || '',
      session_date: detail.date || null,
      discipline: detail.discipline || '',
      append_profile_note: true,
    }
    state.busy = true
    state.planError = ''
    render()
    try {
      await api(`/v1/sessions/${encodeURIComponent(detail.id)}/completion`, {
        method: 'POST',
        body: payload,
      })
      toast('Øktlogg lagret (app — ikke Intervals)')
      await refreshSessions()
      try {
        state.sessionDetail = await api(
          `/v1/sessions/${encodeURIComponent(detail.id)}`,
        )
      } catch {
        /* keep prior detail */
      }
      const me = await api('/v1/athlete/me')
      if (me.athlete) state.athlete = me.athlete
    } catch (err) {
      state.planError = err.message || 'Lagring feilet'
    } finally {
      state.busy = false
      render()
    }
  })

  let pendingAccent = state.athlete?.accent_color
  document.querySelectorAll('#du-swatches .swatch').forEach((btn) => {
    btn.addEventListener('click', () => {
      pendingAccent = btn.dataset.color
      setAccent(pendingAccent)
      document.querySelectorAll('#du-swatches .swatch').forEach((b) => b.classList.toggle('selected', b === btn))
    })
  })

  const numOrNull = (v) => {
    const s = String(v ?? '').trim()
    if (!s) return null
    const n = Number(s)
    return Number.isFinite(n) ? n : null
  }

  const buildDuPayload = (form) => {
    const fd = new FormData(form)
    const agreementsRaw = String(fd.get('agreements') || '')
    return {
      display_name: String(fd.get('display_name') || '').trim(),
      coach_display_name: String(fd.get('coach_display_name') || '').trim(),
      coach_personality: String(fd.get('coach_personality') || 'direkte'),
      accent_color: pendingAccent || state.athlete.accent_color,
      goal_text: String(fd.get('goal_text') || ''),
      weekly_focus: String(fd.get('weekly_focus') || ''),
      injury_notes: String(fd.get('injury_notes') || ''),
      notes: String(fd.get('notes') || ''),
      fitness_notes: String(fd.get('fitness_notes') || ''),
      sessions_per_week: numOrNull(fd.get('sessions_per_week')),
      allowed_disciplines: String(fd.get('allowed_disciplines') || '')
        .split(/[,;/|]+/)
        .map((s) => s.trim().toLowerCase())
        .filter(Boolean),
      nutrition_ibs: String(fd.get('nutrition_ibs') || 'no'),
      nutrition_gluten: String(fd.get('nutrition_gluten') || 'none'),
      nutrition_lactose: fd.get('nutrition_lactose') === 'on',
      nutrition_other_restrictions: String(fd.get('nutrition_other_restrictions') || ''),
      nutrition_notes: String(fd.get('nutrition_notes') || ''),
      agreements: agreementsRaw
        .split('\n')
        .map((s) => s.trim())
        .filter(Boolean),
      ftp_tested: fd.get('ftp_tested') ? Number(fd.get('ftp_tested')) : null,
      ftp_tested_at: String(fd.get('ftp_tested_at') || '') || null,
      weight_kg: fd.get('weight_kg') ? Number(fd.get('weight_kg')) : null,
      age_years: fd.get('age_years') ? Number(fd.get('age_years')) : null,
      season_swim_hours_target: numOrNull(fd.get('season_swim_hours_target')),
      season_bike_hours_target: numOrNull(fd.get('season_bike_hours_target')),
      season_run_hours_target: numOrNull(fd.get('season_run_hours_target')),
      season_strength_hours_target: numOrNull(fd.get('season_strength_hours_target')),
      season_start_date: String(fd.get('season_start_date') || '') || null,
      goal_race_date: String(fd.get('goal_race_date') || '') || null,
      show_body_metrics: fd.get('show_body_metrics') === 'on',
      email: String(fd.get('email') || '').trim(),
      notify_email: fd.get('notify_email') === 'on',
    }
  }

  const duForm = document.getElementById('du-form')
  duForm?.addEventListener('submit', async (e) => {
    e.preventDefault()
    const payload = buildDuPayload(duForm)
    state.busy = true
    state.error = ''
    render()
    try {
      const data = await api('/v1/athlete/me', { method: 'PATCH', body: payload })
      state.athlete = data.athlete
      state.profileSavedForCoach = true
      setAccent(data.athlete.accent_color)
      toast('Profil oppdatert')
      await refreshOverview()
      await refreshDashboard()
    } catch (err) {
      state.error = err.message || 'Lagring feilet'
    } finally {
      state.busy = false
      render()
    }
  })

  document.getElementById('du-talk-coach-btn')?.addEventListener('click', async () => {
    state.busy = true
    state.error = ''
    state.workoutSync.error = ''
    render()
    try {
      // Always persist current Du form so sessions_per_week / goal date drive adjust
      if (duForm) {
        const payload = buildDuPayload(duForm)
        const saved = await api('/v1/athlete/me', { method: 'PATCH', body: payload })
        state.athlete = saved.athlete
        setAccent(saved.athlete.accent_color)
      }
      const data = await api('/v1/athlete/me/plan/adjust/preview', {
        method: 'POST',
        body: { enrich_with_llm: true, prepare_intervals_sync: false },
      })
      state.planAdjust = data
      state.profileSavedForCoach = false
      state.chatDraft = data.seed_chat_prompt || ''
      state.tab = 'coach'
      state.messages.push({
        role: 'assistant',
        content:
          data.coach_note ||
          'Jeg har laget en forhåndsvisning av justert grovplan ut fra profilen din under Du. Se kortet under — bekreft for å lagre lokalt (Intervals først etter Sync).',
      })
      toast('Planjustering klar til bekreftelse')
    } catch (err) {
      state.error = err.message || 'Kunne ikke foreslå planjustering'
      // Still open chat with a seed even if preview failed
      state.chatDraft =
        'Jeg har endret mål/avtaler under Du. Kan du foreslå justering av grovplan og kommende økter? Ikke sync Intervals før jeg bekrefter.'
      state.tab = 'coach'
    } finally {
      state.busy = false
      render()
    }
  })

  document.getElementById('add-plan-block')?.addEventListener('click', async () => {
    state.busy = true
    state.planError = ''
    render()
    try {
      const today = new Date()
      const start = today.toISOString().slice(0, 10)
      const endD = new Date(today)
      endD.setDate(endD.getDate() + 27)
      const end = endD.toISOString().slice(0, 10)
      await api('/v1/athlete/me/plan-blocks', {
        method: 'POST',
        body: {
          title: 'Ny blokk',
          theme: '',
          start_date: start,
          end_date: end,
          weekly_hours: 8,
          sort_order: state.planBlocks.length,
        },
      })
      await refreshPlanBlocks()
      await refreshOverview()
      toast('Blokk lagt til')
    } catch (err) {
      state.planError = err.message || 'Kunne ikke legge til blokk'
    } finally {
      state.busy = false
      render()
    }
  })

  document.querySelectorAll('[data-save-block]').forEach((btn) => {
    btn.addEventListener('click', async () => {
      const id = btn.getAttribute('data-save-block')
      const wrap = document.querySelector(`.block-edit[data-block-id="${id}"]`)
      if (!wrap) return
      const payload = {
        title: wrap.querySelector('[name="title"]')?.value || '',
        theme: wrap.querySelector('[name="theme"]')?.value || '',
        start_date: wrap.querySelector('[name="start_date"]')?.value || null,
        end_date: wrap.querySelector('[name="end_date"]')?.value || null,
        weekly_hours: numOrNull(wrap.querySelector('[name="weekly_hours"]')?.value),
        plan_b: wrap.querySelector('[name="plan_b"]')?.value || '',
        weekly_risk: wrap.querySelector('[name="weekly_risk"]')?.value || '',
      }
      state.busy = true
      state.planError = ''
      render()
      try {
        await api(`/v1/athlete/me/plan-blocks/${id}`, { method: 'PATCH', body: payload })
        await refreshPlanBlocks()
        await refreshOverview()
        toast('Blokk lagret')
      } catch (err) {
        state.planError = err.message || 'Kunne ikke lagre blokk'
      } finally {
        state.busy = false
        render()
      }
    })
  })

  document.querySelectorAll('[data-delete-block]').forEach((btn) => {
    btn.addEventListener('click', async () => {
      const id = btn.getAttribute('data-delete-block')
      state.busy = true
      state.planError = ''
      render()
      try {
        await api(`/v1/athlete/me/plan-blocks/${id}`, { method: 'DELETE' })
        await refreshPlanBlocks()
        await refreshOverview()
        toast('Blokk slettet')
      } catch (err) {
        state.planError = err.message || 'Kunne ikke slette'
      } finally {
        state.busy = false
        render()
      }
    })
  })

  const applyIntervalsPublic = (data) => {
    state.intervals.connected = !!data.connected
    state.intervals.intervals_athlete_id = data.intervals_athlete_id || ''
    state.intervals.api_key_hint = data.api_key_hint || null
    state.intervals.form_athlete_id = data.intervals_athlete_id || ''
    state.intervals.form_api_key = ''
  }

  const intervalsForm = document.getElementById('intervals-form')
  intervalsForm?.addEventListener('submit', async (e) => {
    e.preventDefault()
    if (state.intervalsBusy) return
    const fd = new FormData(intervalsForm)
    const payload = {
      intervals_athlete_id: String(fd.get('intervals_athlete_id') || '').trim(),
      intervals_api_key: String(fd.get('intervals_api_key') || '').trim(),
      verify: true,
    }
    if (!payload.intervals_athlete_id) {
      state.intervalsError = 'Athlete ID mangler'
      state.intervalsStatus = ''
      render()
      return
    }
    if (!payload.intervals_api_key && !state.intervals.connected) {
      state.intervalsError = 'API-nøkkel mangler'
      state.intervalsStatus = ''
      render()
      return
    }
    state.intervals.form_athlete_id = payload.intervals_athlete_id
    state.intervals.form_api_key = payload.intervals_api_key
    state.intervalsBusy = true
    state.intervalsError = ''
    state.intervalsStatus = 'Lagrer…'
    render()
    try {
      const data = await api('/v1/athlete/me/intervals', {
        method: 'PUT',
        body: payload,
        timeoutMs: INTERVALS_CLIENT_TIMEOUT_MS,
      })
      applyIntervalsPublic(data)
      if (data.verified === false && data.verify_error) {
        state.intervalsStatus = `Lagret, men tilkobling feilet: ${data.verify_error}`
        toast('Lagret — tilkobling feilet')
      } else if (data.verified) {
        state.intervalsStatus = 'Lagret og tilkobling OK'
        toast('Intervals lagret')
      } else {
        state.intervalsStatus = 'Lagret'
        toast('Intervals lagret')
      }
      try {
        await refreshOverview()
      } catch {
        /* overview is best-effort after save */
      }
    } catch (err) {
      state.intervalsError = err.message || 'Kunne ikke lagre Intervals'
      state.intervalsStatus = ''
    } finally {
      state.intervalsBusy = false
      render()
    }
  })

  document.getElementById('intervals-test')?.addEventListener('click', async () => {
    if (state.intervalsBusy || !state.intervals.connected) return
    state.intervalsBusy = true
    state.intervalsError = ''
    state.intervalsStatus = 'Tester tilkobling…'
    render()
    try {
      const data = await api('/v1/athlete/me/intervals/verify', {
        method: 'POST',
        timeoutMs: INTERVALS_CLIENT_TIMEOUT_MS,
      })
      applyIntervalsPublic(data)
      if (data.verified) {
        state.intervalsStatus = 'Tilkobling OK'
        toast('Tilkobling OK')
      } else {
        state.intervalsStatus = `Tilkobling feilet: ${data.verify_error || 'ukjent feil'}`
        toast('Tilkobling feilet')
      }
    } catch (err) {
      state.intervalsError = err.message || 'Test feilet'
      state.intervalsStatus = ''
    } finally {
      state.intervalsBusy = false
      render()
    }
  })

  const runSyncPreview = async (op, scope = null) => {
    if (state.sync.busy || !state.intervals.connected) return
    state.sync.busy = true
    state.sync.error = ''
    state.sync.message = ''
    state.sync.pending = null
    if (scope?.label) state.planCalendar.syncScopeLabel = scope.label
    render()
    try {
      const body = { op, include_notes: false }
      if (scope?.start && scope?.end) {
        body.start = scope.start
        body.end = scope.end
      }
      const data = await api('/v1/athlete/me/intervals/calendar/preview', {
        method: 'POST',
        body,
        timeoutMs: 20000,
      })
      state.sync.pending = data
      state.sync.message = data.message || 'Bekreft handling'
    } catch (err) {
      state.sync.error = err.message || 'Forhåndsvisning feilet'
    } finally {
      state.sync.busy = false
      render()
    }
  }

  const runTpSyncPreview = async (scope) => {
    if (state.tpSync.busy || !scope?.start || !scope?.end) return
    state.tpSync.busy = true
    state.tpSync.error = ''
    state.tpSync.pending = null
    if (scope.label) state.planCalendar.syncScopeLabel = scope.label
    render()
    try {
      const data = await api('/v1/athlete/me/trainingpeaks/beta/calendar/preview', {
        method: 'POST',
        body: { start: scope.start, end: scope.end, include_notes: false },
        timeoutMs: 25000,
      })
      state.tpSync.pending = data
      state.tpSync.message = data.message_nb || 'Bekreft TP'
    } catch (err) {
      state.tpSync.error = err.message || 'TP forhåndsvisning feilet'
    } finally {
      state.tpSync.busy = false
      render()
    }
  }

  document.getElementById('cal-prev-month')?.addEventListener('click', () => {
    state.planCalendar.month = addMonths(state.planCalendar.month, -1)
    render()
  })
  document.getElementById('cal-next-month')?.addEventListener('click', () => {
    state.planCalendar.month = addMonths(state.planCalendar.month, 1)
    render()
  })
  document.querySelectorAll('[data-cal-day]').forEach((btn) => {
    btn.addEventListener('click', () => {
      const iso = btn.getAttribute('data-cal-day')
      if (!iso) return
      state.planCalendar.selectedDate = iso
      render()
    })
  })
  document.querySelectorAll('[data-source-filter]').forEach((btn) => {
    btn.addEventListener('click', () => {
      const id = btn.getAttribute('data-source-filter')
      if (!id) return
      state.planCalendar.sourceFilter = id
      render()
    })
  })
  document.getElementById('cal-sync-week')?.addEventListener('click', () => {
    const d = state.planCalendar.selectedDate
    const range = weekRangeFromDate(d)
    if (!range) return
    runSyncPreview('push', {
      ...range,
      label: `Uke ${range.start} – ${range.end}`,
    })
  })
  document.getElementById('cal-sync-month')?.addEventListener('click', () => {
    const range = monthRange(state.planCalendar.month)
    if (!range) return
    runSyncPreview('push', {
      ...range,
      label: `Måned ${range.start} – ${range.end}`,
    })
  })
  document.getElementById('cal-sync-week-tp')?.addEventListener('click', () => {
    const d = state.planCalendar.selectedDate
    const range = weekRangeFromDate(d)
    if (!range) return
    runTpSyncPreview({
      ...range,
      label: `TP uke ${range.start} – ${range.end}`,
    })
  })
  document.getElementById('tp-sync-confirm-no')?.addEventListener('click', () => {
    state.tpSync.pending = null
    render()
  })
  document.getElementById('tp-sync-confirm-yes')?.addEventListener('click', async () => {
    const pending = state.tpSync.pending
    if (!pending?.pending_id || state.tpSync.busy) return
    state.tpSync.busy = true
    state.tpSync.error = ''
    render()
    try {
      const data = await api('/v1/athlete/me/trainingpeaks/beta/calendar/confirm', {
        method: 'POST',
        body: { pending_id: pending.pending_id },
        timeoutMs: 120000,
      })
      state.tpSync.pending = null
      state.tpSync.message = `TP: ${data.pushed}/${data.attempted} økter`
      toast(state.tpSync.message)
    } catch (err) {
      state.tpSync.error = err.message || 'TP sync feilet'
    } finally {
      state.tpSync.busy = false
      render()
    }
  })

  document.getElementById('sync-push')?.addEventListener('click', () => runSyncPreview('push'))
  document.getElementById('sync-delete')?.addEventListener('click', () => runSyncPreview('delete'))

  document.getElementById('sync-refresh')?.addEventListener('click', async () => {
    if (state.sync.busy || !state.intervals.connected) return
    state.sync.busy = true
    state.sync.statusError = ''
    state.sync.message = 'Henter status…'
    render()
    try {
      const data = await api('/v1/athlete/me/intervals/calendar/status', {
        timeoutMs: 20000,
      })
      state.sync.status = data
      state.sync.message = `${data.count} agent-noter på Intervals`
      toast('Status oppdatert')
    } catch (err) {
      state.sync.statusError = err.message || 'Status feilet'
      state.sync.message = ''
    } finally {
      state.sync.busy = false
      render()
    }
  })

  document.getElementById('sync-confirm-no')?.addEventListener('click', () => {
    state.sync.pending = null
    state.sync.message = 'Avbrutt'
    render()
  })

  document.getElementById('sync-confirm-yes')?.addEventListener('click', async () => {
    const pending = state.sync.pending
    if (!pending?.pending_id || state.sync.busy) return
    state.sync.busy = true
    state.sync.error = ''
    state.sync.message = 'Kjører…'
    render()
    try {
      const data = await api('/v1/athlete/me/intervals/calendar/confirm', {
        method: 'POST',
        body: { pending_id: pending.pending_id },
        timeoutMs: 120000,
      })
      state.sync.pending = null
      const n = data.pushed ?? data.deleted ?? pending.count
      state.sync.message =
        data.op === 'delete'
          ? `Fjernet ${n} hendelser fra Intervals`
          : `Synct ${n} hendelser til Intervals`
      toast(state.sync.message)
      try {
        state.sync.status = await api('/v1/athlete/me/intervals/calendar/status', {
          timeoutMs: 20000,
        })
      } catch {
        /* status best-effort */
      }
      try {
        await Promise.all([refreshSessions(), refreshDashboard(), refreshOverview()])
      } catch {
        /* soft — caches cleared server-side */
      }
    } catch (err) {
      state.sync.error = err.message || 'Bekreftelse feilet'
      state.sync.message = ''
    } finally {
      state.sync.busy = false
      render()
    }
  })

  document.getElementById('btn-logout')?.addEventListener('click', () => {
    logoutLocal()
  })
  document.getElementById('btn-restart-setup')?.addEventListener('click', () => {
    state.resetConfirm = 1
    state.resetDeleteIcu = false
    state.error = ''
    render()
  })
  document.getElementById('reset-cancel')?.addEventListener('click', () => {
    state.resetConfirm = 0
    state.resetDeleteIcu = false
    state.error = ''
    render()
  })
  document.getElementById('reset-delete-icu')?.addEventListener('change', (e) => {
    state.resetDeleteIcu = Boolean(e.target.checked)
  })
  document.getElementById('reset-confirm-1')?.addEventListener('click', () => {
    const box = document.getElementById('reset-delete-icu')
    if (box) state.resetDeleteIcu = Boolean(box.checked)
    state.resetConfirm = 2
    state.error = ''
    render()
  })
  document.getElementById('reset-confirm-2')?.addEventListener('click', () => {
    const phrase = (document.getElementById('reset-phrase')?.value || '').trim().toUpperCase()
    if (phrase !== 'SLETT') {
      state.error = 'Skriv SLETT (store bokstaver) for å bekrefte.'
      render()
      return
    }
    void runSetupReset()
  })
}

bootstrap().catch((err) => {
  app.innerHTML = `<div class="onboarding"><h1>Kunne ikke starte</h1><p class="error">${escapeHtml(err.message)}</p><p class="muted">Sjekk /health og DATABASE_URL (sslmode=require for Supabase). coach-api må svare på samme origin.</p></div>`
})
