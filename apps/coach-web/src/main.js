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
    athlete_id: '',
    invite_token: '',
  },
  tab: 'coach',
  messages: [],
  overview: null,
  dashboard: null,
  sessions: null,
  sessionDetail: null,
  chatDraft: '',
  planBlocks: [],
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
  onboarding: {
    display_name: '',
    coach_display_name: 'Rocky',
    coach_personality: 'direkte',
    coach_style_note: '',
    accent_color: ACCENTS[0],
    goal_text: '',
    injury_notes: '',
    schedule_notes: '',
    ftp_tested: '',
    ftp_tested_at: '',
    weight_kg: '',
    age_years: '',
    nutrition_ibs: 'no',
    nutrition_gluten: 'none',
    nutrition_lactose: false,
    nutrition_other_restrictions: '',
    nutrition_notes: '',
  },
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

async function api(path, { method = 'GET', body, athleteId, timeoutMs } = {}) {
  const headers = { 'Content-Type': 'application/json' }
  const id = athleteId ?? getAthleteId()
  if (id) headers['X-Athlete-Id'] = id
  const ctrl = typeof timeoutMs === 'number' ? new AbortController() : null
  const timer =
    ctrl && timeoutMs > 0
      ? setTimeout(() => ctrl.abort(), timeoutMs)
      : null
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
      throw new Error('Tidsavbrudd — prøv igjen')
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
          : data.message || `Feil ${res.status}`
    throw new Error(msg)
  }
  return data
}

/** Client wall budget for Intervals save/verify — must exceed server soft-verify (~5s). */
const INTERVALS_CLIENT_TIMEOUT_MS = 10000

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
  state.athlete = athlete
  state.gate = null
  state.error = ''
  state.busy = false
  setAccent(athlete.accent_color)
  setAthleteId(athlete.id)
  if (welcome) {
    state.messages = [{ role: 'assistant', content: welcome }]
  }
  await Promise.all([
    refreshOverview(),
    refreshIntervals(),
    refreshPlanBlocks(),
    refreshDashboard(),
    refreshSessions(),
  ])
  render()
}

/**
 * Reconnect to existing athlete via POST /v1/session/login.
 * Does not create profiles.
 */
async function loginWithId(athleteId, inviteToken) {
  const id = String(athleteId || '').trim()
  if (!id) {
    throw new Error('Skriv inn profil-ID')
  }
  const body = { athlete_id: id }
  const token = String(inviteToken || '').trim()
  if (token) body.invite_token = token
  const data = await api('/v1/session/login', {
    method: 'POST',
    body,
    athleteId: null,
  })
  if (!data.athlete) {
    throw new Error('Ukjent profil-ID. Sjekk at ID er riktig, eller opprett ny bruker.')
  }
  return data.athlete
}

async function bootstrap() {
  const params = new URLSearchParams(location.search)
  const fromQuery = params.get('athlete')
  if (fromQuery) {
    state.busy = true
    state.error = ''
    try {
      const athlete = await loginWithId(fromQuery)
      await enterApp(athlete, {
        welcome: `Hei ${athlete.display_name}. Jeg er ${athlete.coach_display_name}. Velkommen tilbake.`,
      })
      // Drop ?athlete= so refresh uses localStorage
      if (location.search) {
        history.replaceState({}, '', location.pathname)
      }
    } catch (err) {
      clearAthleteId()
      state.athlete = null
      state.gate = 'login'
      state.login.athlete_id = fromQuery
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

  try {
    const athlete = await loginWithId(id)
    await enterApp(athlete)
  } catch (err) {
    clearAthleteId()
    state.athlete = null
    state.gate = 'login'
    state.login.athlete_id = id
    state.error = err.message || 'Ukjent profil-ID'
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
    state.dashboard = await api('/v1/dashboard')
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

async function refreshPlanBlocks() {
  try {
    const data = await api('/v1/athlete/me/plan-blocks')
    state.planBlocks = data.blocks || []
  } catch {
    state.planBlocks = []
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
      <section class="panel ${state.tab === 'du' ? 'active' : ''}" data-panel="du">
        ${renderDu()}
      </section>
    </main>
    <nav class="tabs tabs-five" aria-label="Hovedfaner">
      <button type="button" data-tab="coach" class="${state.tab === 'coach' ? 'active' : ''}">Coach</button>
      <button type="button" data-tab="dashboard" class="${state.tab === 'dashboard' ? 'active' : ''}">Dashboard</button>
      <button type="button" data-tab="plan" class="${state.tab === 'plan' ? 'active' : ''}">Plan</button>
      <button type="button" data-tab="okter" class="${state.tab === 'okter' ? 'active' : ''}">Økter</button>
      <button type="button" data-tab="du" class="${state.tab === 'du' ? 'active' : ''}">Du</button>
    </nav>
  `
  bindApp()
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
    state.gate = 'onboarding'
    state.error = ''
    render()
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
  return `
    <div class="onboarding">
      <p class="brand-mark">Lofoten coach</p>
      <h1>Logg inn</h1>
      <p class="lead">Lim inn profil-ID (fra Du-fanen, eller f.eks. <code>william-lofoten</code>). Ingen passord.</p>
      <form id="login-form">
        <div class="field">
          <label for="login_athlete_id">Profil-ID</label>
          <input id="login_athlete_id" name="athlete_id" required autocomplete="username"
            value="${escapeHtml(L.athlete_id)}"
            placeholder="william-lofoten eller UUID" ${state.busy ? 'disabled' : ''} />
        </div>
        <div class="field">
          <label for="login_invite_token">Invite-token (valgfritt)</label>
          <input id="login_invite_token" name="invite_token" autocomplete="off"
            value="${escapeHtml(L.invite_token)}"
            placeholder="Kun hvis du har fått token" ${state.busy ? 'disabled' : ''} />
        </div>
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
    state.gate = 'onboarding'
    state.error = ''
    render()
  })
  document.getElementById('use-seed-william')?.addEventListener('click', () => {
    void runSeedWilliamLogin()
  })
  document.getElementById('login-form')?.addEventListener('submit', async (e) => {
    e.preventDefault()
    const fd = new FormData(e.target)
    const athleteId = String(fd.get('athlete_id') || '').trim()
    const inviteToken = String(fd.get('invite_token') || '').trim()
    state.login.athlete_id = athleteId
    state.login.invite_token = inviteToken
    state.busy = true
    state.error = ''
    render()
    try {
      const athlete = await loginWithId(athleteId, inviteToken)
      await enterApp(athlete, {
        welcome: `Hei ${athlete.display_name}. Jeg er ${athlete.coach_display_name}. Velkommen tilbake — spør om mål, skade eller ukens fokus.`,
      })
      toast('Innlogget')
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
    const athlete = await loginWithId('william-lofoten')
    await enterApp(athlete, {
      welcome: `Hei ${athlete.display_name}. Jeg er ${athlete.coach_display_name}. Profilen er seedet fra repo — spør om avtaler, rygg eller ukens fokus.`,
    })
    toast('Seedet William lastet')
  } catch (err) {
    state.error =
      err.message ||
      'Fant ikke william-lofoten. Kjør seed / fly deploy med SEED_ON_BOOT=1.'
    state.busy = false
    if (!state.gate) state.gate = 'login'
    render()
  }
}

function renderOnboarding() {
  const o = state.onboarding
  const swatches = ACCENTS.map(
    (c) =>
      `<button type="button" class="swatch ${o.accent_color === c ? 'selected' : ''}" data-color="${c}" style="background:${c}" aria-label="Farge ${c}"></button>`
  ).join('')
  const pers = PERSONALITIES.map(
    (p) => `<option value="${p.id}" ${o.coach_personality === p.id ? 'selected' : ''}>${p.label}</option>`
  ).join('')
  return `
    <div class="onboarding">
      <h1>Din trener</h1>
      <p class="lead">Sett opp profilen — vi skriver <code>profile.md</code> treneren bruker (også for andre enn William), inkl. ernæring/GI så råd blir tryggere.</p>
      <form id="onboard-form">
        <div class="field">
          <label for="display_name">Ditt navn</label>
          <input id="display_name" name="display_name" required value="${escapeHtml(o.display_name)}" placeholder="f.eks. William" />
        </div>
        <div class="grid-2">
          <div class="field">
            <label for="coach_display_name">Trenerens navn</label>
            <input id="coach_display_name" name="coach_display_name" value="${escapeHtml(o.coach_display_name)}" />
          </div>
          <div class="field">
            <label for="coach_personality">Personlighet</label>
            <select id="coach_personality" name="coach_personality">${pers}</select>
          </div>
        </div>
        <div class="field">
          <label for="coach_style_note">Stil (valgfritt, én setning)</label>
          <input id="coach_style_note" name="coach_style_note" value="${escapeHtml(o.coach_style_note)}" placeholder="Kort og konkret" />
        </div>
        <div class="field">
          <label>Aksentfarge</label>
          <div class="swatches">${swatches}</div>
        </div>
        <div class="field">
          <label for="goal_text">Mål</label>
          <textarea id="goal_text" name="goal_text" rows="2" placeholder="f.eks. Half Extreme Lofoten 2027">${escapeHtml(o.goal_text)}</textarea>
        </div>
        <div class="field">
          <label for="schedule_notes">Tilgjengelighet / timeplan</label>
          <textarea id="schedule_notes" name="schedule_notes" rows="2" placeholder="f.eks. basseng tir/tor kveld">${escapeHtml(o.schedule_notes)}</textarea>
        </div>
        <div class="field">
          <label for="injury_notes">Skade / begrensninger</label>
          <textarea id="injury_notes" name="injury_notes" rows="2" placeholder="f.eks. isjas, skuldre">${escapeHtml(o.injury_notes)}</textarea>
        </div>
        <div class="grid-2">
          <div class="field">
            <label for="ftp_tested">Testet FTP (valgfritt)</label>
            <input id="ftp_tested" name="ftp_tested" type="number" inputmode="decimal" value="${escapeHtml(o.ftp_tested)}" placeholder="W" />
          </div>
          <div class="field">
            <label for="ftp_tested_at">FTP-dato</label>
            <input id="ftp_tested_at" name="ftp_tested_at" type="date" value="${escapeHtml(o.ftp_tested_at)}" />
          </div>
        </div>
        <div class="grid-2">
          <div class="field">
            <label for="weight_kg">Vekt kg (valgfritt)</label>
            <input id="weight_kg" name="weight_kg" type="number" inputmode="decimal" value="${escapeHtml(o.weight_kg)}" />
          </div>
          <div class="field">
            <label for="age_years">Alder (valgfritt)</label>
            <input id="age_years" name="age_years" type="number" inputmode="numeric" value="${escapeHtml(o.age_years)}" />
          </div>
        </div>
        <div class="field">
          <label for="nutrition_ibs">IBS</label>
          <select id="nutrition_ibs" name="nutrition_ibs">
            <option value="no" ${o.nutrition_ibs === 'no' ? 'selected' : ''}>Nei</option>
            <option value="yes" ${o.nutrition_ibs === 'yes' ? 'selected' : ''}>Ja</option>
            <option value="unsure" ${o.nutrition_ibs === 'unsure' ? 'selected' : ''}>Usikker</option>
          </select>
        </div>
        <div class="field">
          <label for="nutrition_gluten">Gluten</label>
          <select id="nutrition_gluten" name="nutrition_gluten">
            <option value="none" ${o.nutrition_gluten === 'none' ? 'selected' : ''}>Ingen restriksjon</option>
            <option value="sensitive" ${o.nutrition_gluten === 'sensitive' ? 'selected' : ''}>Sensitivitet</option>
            <option value="celiac" ${o.nutrition_gluten === 'celiac' ? 'selected' : ''}>Cøliaki</option>
          </select>
        </div>
        <div class="field">
          <label><input type="checkbox" name="nutrition_lactose" ${o.nutrition_lactose ? 'checked' : ''} /> Laktoseproblemer</label>
        </div>
        <div class="field">
          <label for="nutrition_other_restrictions">Andre matrestriksjoner</label>
          <textarea id="nutrition_other_restrictions" name="nutrition_other_restrictions" rows="2">${escapeHtml(o.nutrition_other_restrictions)}</textarea>
        </div>
        <div class="field">
          <label for="nutrition_notes">Ernæringsnotater</label>
          <textarea id="nutrition_notes" name="nutrition_notes" rows="2" placeholder="Treneren tilpasser — diagnostiserer ikke">${escapeHtml(o.nutrition_notes)}</textarea>
        </div>
        ${state.error ? `<p class="error">${escapeHtml(state.error)}</p>` : ''}
        <button class="btn btn-primary" type="submit" ${state.busy ? 'disabled' : ''}>Start med treneren</button>
      </form>
      <p class="muted" style="margin-top:1.25rem">
        <button type="button" class="linkish" id="onboard-back">Tilbake</button>
        ·
        <button type="button" class="linkish" id="onboard-to-login">Jeg har allerede profil</button>
      </p>
    </div>
  `
}

function bindOnboarding() {
  document.getElementById('onboard-back')?.addEventListener('click', () => {
    state.gate = 'entry'
    state.error = ''
    render()
  })
  document.getElementById('onboard-to-login')?.addEventListener('click', () => {
    state.gate = 'login'
    state.error = ''
    render()
  })
  document.querySelectorAll('.swatch').forEach((btn) => {
    btn.addEventListener('click', () => {
      const form = document.getElementById('onboard-form')
      if (form) {
        const fd = new FormData(form)
        for (const key of [
          'display_name',
          'coach_display_name',
          'coach_personality',
          'coach_style_note',
          'goal_text',
          'schedule_notes',
          'injury_notes',
          'ftp_tested',
          'ftp_tested_at',
          'weight_kg',
          'age_years',
          'nutrition_ibs',
          'nutrition_gluten',
          'nutrition_other_restrictions',
          'nutrition_notes',
        ]) {
          if (fd.has(key)) state.onboarding[key] = String(fd.get(key) || '')
        }
        state.onboarding.nutrition_lactose = fd.get('nutrition_lactose') === 'on'
      }
      state.onboarding.accent_color = btn.dataset.color
      setAccent(btn.dataset.color)
      render()
    })
  })
  const form = document.getElementById('onboard-form')
  form?.addEventListener('submit', async (e) => {
    e.preventDefault()
    const fd = new FormData(form)
    const payload = {
      display_name: String(fd.get('display_name') || '').trim(),
      coach_display_name: String(fd.get('coach_display_name') || 'Rocky').trim(),
      coach_personality: String(fd.get('coach_personality') || 'direkte'),
      coach_style_note: String(fd.get('coach_style_note') || ''),
      accent_color: state.onboarding.accent_color,
      goal_text: String(fd.get('goal_text') || ''),
      schedule_notes: String(fd.get('schedule_notes') || ''),
      injury_notes: String(fd.get('injury_notes') || ''),
      ftp_tested: fd.get('ftp_tested') ? Number(fd.get('ftp_tested')) : null,
      ftp_tested_at: String(fd.get('ftp_tested_at') || '') || null,
      weight_kg: fd.get('weight_kg') ? Number(fd.get('weight_kg')) : null,
      age_years: fd.get('age_years') ? Number(fd.get('age_years')) : null,
      nutrition_ibs: String(fd.get('nutrition_ibs') || 'no'),
      nutrition_gluten: String(fd.get('nutrition_gluten') || 'none'),
      nutrition_lactose: fd.get('nutrition_lactose') === 'on',
      nutrition_other_restrictions: String(fd.get('nutrition_other_restrictions') || ''),
      nutrition_notes: String(fd.get('nutrition_notes') || ''),
    }
    state.busy = true
    state.error = ''
    render()
    try {
      const data = await api('/v1/onboarding', { method: 'POST', body: payload, athleteId: null })
      await enterApp(data.athlete, {
        welcome: `Hei ${data.athlete.display_name}. Jeg er ${data.athlete.coach_display_name}. Si ifra hva du vil prioritere — mål, skade, eller ukens fokus.`,
      })
      toast('Profil lagret')
    } catch (err) {
      state.error = err.message || 'Kunne ikke lagre'
      state.busy = false
      render()
    }
  })
}

function renderChat() {
  const draft = state.chatDraft || ''
  const bubbles = state.messages
    .map((m) => `<div class="bubble ${m.role}">${escapeHtml(m.content)}</div>`)
    .join('')
  return `
    <div class="chat-log" id="chat-log">${bubbles || `<p class="muted">Skriv til ${escapeHtml(state.athlete.coach_display_name)} — eller åpne en økt under Økter.</p>`}</div>
    <form class="chat-form" id="chat-form">
      <input id="chat-input" autocomplete="off" placeholder="Spør treneren…" value="${escapeHtml(draft)}" ${state.busy ? 'disabled' : ''} />
      <button class="btn btn-primary" type="submit" ${state.busy ? 'disabled' : ''}>Send</button>
    </form>
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
      <p class="muted tight plan-footnote">Detaljer i Intervals — her bare grovplan / bulk.</p>
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

function renderSleepCard(sleep, fetchError, detail) {
  if (!sleep) {
    return `<section class="section-block"><h2>Søvn</h2><p class="muted">Ingen data.</p></section>`
  }
  const badge = fetchError
    ? `<span class="badge badge-demo">Henting feilet</span>`
    : sleep.available
      ? `<span class="badge badge-live">Intervals</span>`
      : `<span class="badge badge-off">Mangler</span>`
  return `
    <section class="section-block">
      <div class="section-head"><h2>Søvn</h2>${badge}</div>
      ${fetchError && detail ? `<p class="error tight">${escapeHtml(detail)}</p>` : ''}
      <div class="stat-row"><span>Snitt (14 d)</span><span>${sleep.avg_hours != null ? `${sleep.avg_hours} t` : '—'}</span></div>
      <div class="stat-row"><span>Søvnscore</span><span>${sleep.avg_score != null ? sleep.avg_score : '—'}</span></div>
      <div class="stat-row"><span>Korte netter (&lt;6,5 t)</span><span>${sleep.short_nights ?? '—'}</span></div>
      <p class="muted tight">${escapeHtml(sleep.note || '')}</p>
    </section>`
}

function renderBodyCard(body, hidden) {
  if (hidden) {
    return `
      <section class="section-block body-metrics-hidden">
        <div class="section-head"><h2>Kropp</h2><span class="badge badge-off">Skjult</span></div>
        <p class="muted tight">Vekt og fett% er slått av under <strong>Du → Personvern</strong>.</p>
      </section>`
  }
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

function renderLoadCard(dash) {
  const load = dash.load || {}
  const wl = load.from_wellness || {}
  const hours = dash.hours || {}
  const badge =
    hours.source === 'intervals'
      ? `<span class="badge badge-live">Intervals</span>`
      : hours.fetch_error
        ? `<span class="badge badge-demo">Henting feilet</span>`
        : `<span class="badge badge-demo">Demo</span>`
  const discs = (hours.disciplines || [])
    .map(
      (d) =>
        `<div class="stat-row"><span>${escapeHtml(d.label)}</span><span>${formatHours(d.completed_hours)}${d.target_hours != null ? ` / ${formatHours(d.target_hours)} t` : ' t'}</span></div>`
    )
    .join('')
  return `
    <section class="section-block">
      <div class="section-head"><h2>Timer &amp; belastning</h2>${badge}</div>
      <div class="stat-row"><span>CTL</span><span>${wl.ctl != null ? wl.ctl : '—'}</span></div>
      <div class="stat-row"><span>ATL</span><span>${wl.atl != null ? wl.atl : '—'}</span></div>
      <div class="stat-row"><span>Readiness</span><span>${wl.readiness != null ? wl.readiness : '—'}</span></div>
      <div class="hours-mini">${discs || `<p class="muted">Ingen timedata.</p>`}</div>
      <p class="muted tight">${escapeHtml(load.note || '')}</p>
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
  return `
    <div class="tab-hero">
      <p class="brand-mark">Dashboard</p>
      <h2>Treningsstatus</h2>
      <p class="muted">${escapeHtml(dash.uplift_line || 'Timer, søvn, compliance — app-beregnet.')}</p>
    </div>
    <p class="compliance-banner" role="note">
      <strong>Compliance</strong> beregnes i appen (aktiviteter vs sesongmål) og
      <em>skrives ikke</em> til Intervals.
    </p>
    ${renderLoadCard(dash)}
    ${renderSleepCard(dash.sleep, dash.wellness_fetch_error, dash.wellness_fetch_error_detail)}
    ${renderBodyCard(dash.body, dash.body_hidden || !dash.show_body_metrics)}
    ${renderProgressSection(progressForSection)}
    ${renderFormCard({ ...(dash.form || {}), ...o })}
    ${renderPlanStrip(o)}
  `
}

function statusLabel(status) {
  const map = {
    completed: 'Fullført',
    skipped: 'Hoppet over',
    injured: 'Skade',
    tired: 'For sliten',
    sick: 'Syk',
    other: 'Annet',
  }
  return map[status] || status || ''
}

function renderSessionRow(s) {
  const comp = s.completion
  const statusBit = comp
    ? `<span class="badge badge-live">${escapeHtml(statusLabel(comp.status))}</span>`
    : `<span class="badge badge-off">Ulågget</span>`
  const dur =
    s.duration_hours != null ? ` · ${formatHours(s.duration_hours)} t` : ''
  return `
    <article class="session-row" data-session-id="${escapeHtml(s.id)}">
      <div class="session-main">
        <p class="session-date">${escapeHtml(s.date || '—')} · ${escapeHtml(s.discipline_label || s.type || '')}${escapeHtml(dur)}</p>
        <h3>${escapeHtml(s.name || 'Økt')}</h3>
        ${statusBit}
      </div>
      <div class="session-actions">
        <button type="button" class="btn btn-sm" data-ask-coach="${escapeHtml(s.id)}">Spør coach</button>
        <button type="button" class="btn btn-sm secondary" data-open-session="${escapeHtml(s.id)}">Logg</button>
      </div>
    </article>`
}

function renderSessionDetail() {
  const d = state.sessionDetail
  if (!d) return ''
  const s = d.session || {}
  const statuses = [
    ['completed', 'Fullført'],
    ['skipped', 'Hoppet over'],
    ['injured', 'Skade'],
    ['tired', 'For sliten'],
    ['sick', 'Syk'],
    ['other', 'Annet'],
  ]
  const opts = statuses
    .map(
      ([v, lab]) =>
        `<option value="${v}" ${s.completion?.status === v ? 'selected' : ''}>${lab}</option>`
    )
    .join('')
  return `
    <div class="session-detail section-block" id="session-detail">
      <div class="section-head">
        <h2>${escapeHtml(s.name || 'Økt')}</h2>
        <button type="button" class="btn btn-sm secondary" id="close-session-detail">Lukk</button>
      </div>
      <p class="muted tight">${escapeHtml(s.date || '')} · ${escapeHtml(s.discipline_label || '')}</p>
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
          <button type="button" class="btn secondary" data-ask-coach="${escapeHtml(s.id)}">Spør coach om denne</button>
        </div>
      </form>
      ${state.planError ? `<p class="error">${escapeHtml(state.planError)}</p>` : ''}
    </div>`
}

function renderOkterTab() {
  const sess = state.sessions
  const linked = state.intervals.connected
  let body = ''
  if (!sess) {
    body = `<p class="muted">Laster økter…</p>`
  } else if (sess.source === 'none') {
    body = `<p class="muted">Koble Intervals under Du for å se kommende og siste økter.</p>`
  } else if (sess.fetch_error) {
    body = `<p class="error">Kunne ikke hente økter: ${escapeHtml(sess.fetch_error_detail || '')}</p>`
  } else {
    const today = (sess.today || []).map(renderSessionRow).join('')
    const upcoming = (sess.upcoming || []).map(renderSessionRow).join('')
    const recent = (sess.recent || []).map(renderSessionRow).join('')
    body = `
      ${today ? `<section class="section-block"><h2>I dag</h2><div class="session-list">${today}</div></section>` : ''}
      <section class="section-block">
        <h2>Kommende</h2>
        <div class="session-list">${upcoming || `<p class="muted">Ingen planlagte økter i vinduet.</p>`}</div>
      </section>
      <section class="section-block">
        <h2>Siste</h2>
        <div class="session-list">${recent || `<p class="muted">Ingen aktiviteter i vinduet.</p>`}</div>
      </section>`
  }
  return `
    <div class="tab-hero">
      <p class="brand-mark">Økter</p>
      <h2>Kalender &amp; logg</h2>
      <p class="muted">Fra Intervals — spør coach eller logg fullført / hoppet over her (app-lagring).</p>
    </div>
    <p class="compliance-banner muted tight">${escapeHtml(sess?.compliance_note || 'Compliance beregnes i appen, ikke i Intervals.')}</p>
    <p class="muted tight">${linked ? 'Intervals koblet.' : 'Ikke koblet ennå.'}</p>
    ${renderSessionDetail()}
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
      .slice(0, 5)
      .map(
        (e) =>
          `<li><code>${escapeHtml(e.external_id || e.name || '')}</code> ${escapeHtml(e.name || e.day || '')}</li>`
      )
      .join('')
    confirmHtml = `
      <div class="confirm-card" role="dialog" aria-label="Bekreft Intervals-sync">
        <p><strong>${escapeHtml(pending.message || 'Bekreft handling')}</strong></p>
        <p class="muted tight">${escapeHtml(pending.op)} · ${pending.count} hendelser</p>
        <ul class="sync-sample">${sample}</ul>
        ${pending.events_truncated ? `<p class="muted tight">+${pending.events_truncated} til</p>` : ''}
        <div class="row-actions">
          <button type="button" class="btn btn-primary" id="sync-confirm-yes" ${state.sync.busy ? 'disabled' : ''}>Ja, kjør</button>
          <button type="button" class="btn secondary" id="sync-confirm-no" ${state.sync.busy ? 'disabled' : ''}>Avbryt</button>
        </div>
      </div>`
  }
  const statusList = (status?.events || [])
    .slice(0, 8)
    .map(
      (e) =>
        `<li>${escapeHtml(e.name || 'Note')} · <span class="dim">${escapeHtml((e.start_date_local || '').slice(0, 10))}</span></li>`
    )
    .join('')
  return `
    <section class="section-block sync-panel">
      <div class="section-head">
        <h2>Sync til Intervals</h2>
        <span class="badge ${linked ? 'badge-live' : 'badge-off'}">${linked ? 'Koblet' : 'Ikke koblet'}</span>
      </div>
      <p class="muted tight">Pusher ukenoter for grovplan-blokker (<code>ll-coach-…</code>). Aldri stille auto-push — forhåndsvis, så Ja/Avbryt.</p>
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
              ? `<p class="muted tight">${status.count} agent-noter (${escapeHtml(status.window?.start || '')} – ${escapeHtml(status.window?.end || '')})</p>
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
      <p class="muted">Makro/meso her — dagsøkter under Økter / Intervals.</p>
    </div>
    ${renderPlanStrip(o)}
    ${renderPlanBlocksEditor()}
    ${renderSyncPanel()}
  `
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
          <label for="profile_id_display">Din profil-ID</label>
          <div class="profile-id-row">
            <input id="profile_id_display" type="text" readonly value="${escapeHtml(a.id || '')}" />
            <button type="button" class="btn secondary" id="copy-profile-id">Kopier</button>
          </div>
          <p class="muted tight">Lagre denne — trengs for «Jeg har allerede profil» på ny enhet.</p>
        </div>
        <div class="field"><label>Navn</label><input name="display_name" value="${escapeHtml(a.display_name || '')}" /></div>
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
            <input type="checkbox" name="show_body_metrics" ${a.show_body_metrics !== false ? 'checked' : ''} />
            Vis vekt og fett% på Dashboard
          </label>
          <p class="muted tight">Slå av for å skjule kroppsmål fra wellness/BIA. Standard: på.</p>
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
      <button class="btn btn-primary" type="submit" ${state.busy ? 'disabled' : ''}>Lagre profil</button>
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
      }
      if (state.tab === 'plan') {
        await refreshOverview()
        await refreshPlanBlocks()
        await refreshIntervals()
      }
      if (state.tab === 'okter') {
        await refreshIntervals()
        await refreshSessions()
      }
      if (state.tab === 'du') {
        await refreshIntervals()
      }
      render()
    })
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
    state.messages.push({ role: 'user', content: message })
    state.busy = true
    state.error = ''
    render()
    const log = document.getElementById('chat-log')
    if (log) log.scrollTop = log.scrollHeight
    try {
      const data = await api('/v1/chat', { method: 'POST', body: { message } })
      state.messages.push({ role: 'assistant', content: data.reply })
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

  const findSession = (id) => {
    const sess = state.sessions || {}
    for (const bucket of ['today', 'upcoming', 'recent']) {
      for (const s of sess[bucket] || []) {
        if (s.id === id || s.external_id === id) return s
      }
    }
    return state.sessionDetail?.session?.id === id
      ? state.sessionDetail.session
      : null
  }

  const askCoachAbout = async (sessionId) => {
    try {
      const data = await api(`/v1/sessions/${encodeURIComponent(sessionId)}`)
      state.sessionDetail = data
      state.chatDraft = data.seed_prompt || ''
      state.tab = 'coach'
      toast('Spørsmål klart i Coach')
      render()
      document.getElementById('chat-input')?.focus()
    } catch (err) {
      state.error = err.message || 'Kunne ikke åpne økt'
      toast(state.error)
    }
  }

  document.querySelectorAll('[data-ask-coach]').forEach((btn) => {
    btn.addEventListener('click', () => {
      void askCoachAbout(btn.getAttribute('data-ask-coach'))
    })
  })

  document.querySelectorAll('[data-open-session]').forEach((btn) => {
    btn.addEventListener('click', async () => {
      const id = btn.getAttribute('data-open-session')
      try {
        state.sessionDetail = await api(`/v1/sessions/${encodeURIComponent(id)}`)
        state.planError = ''
        render()
        document.getElementById('session-detail')?.scrollIntoView({ behavior: 'smooth' })
      } catch (err) {
        state.planError = err.message || 'Kunne ikke åpne'
        render()
      }
    })
  })

  document.getElementById('close-session-detail')?.addEventListener('click', () => {
    state.sessionDetail = null
    render()
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
      const updated = findSession(detail.id)
      if (updated) {
        state.sessionDetail = {
          session: updated,
          seed_prompt: state.sessionDetail?.seed_prompt,
        }
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

  const duForm = document.getElementById('du-form')
  duForm?.addEventListener('submit', async (e) => {
    e.preventDefault()
    const fd = new FormData(duForm)
    const agreementsRaw = String(fd.get('agreements') || '')
    const payload = {
      display_name: String(fd.get('display_name') || '').trim(),
      coach_display_name: String(fd.get('coach_display_name') || '').trim(),
      coach_personality: String(fd.get('coach_personality') || 'direkte'),
      accent_color: pendingAccent || state.athlete.accent_color,
      goal_text: String(fd.get('goal_text') || ''),
      weekly_focus: String(fd.get('weekly_focus') || ''),
      injury_notes: String(fd.get('injury_notes') || ''),
      notes: String(fd.get('notes') || ''),
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
    }
    state.busy = true
    state.error = ''
    render()
    try {
      const data = await api('/v1/athlete/me', { method: 'PATCH', body: payload })
      state.athlete = data.athlete
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

  const runSyncPreview = async (op) => {
    if (state.sync.busy || !state.intervals.connected) return
    state.sync.busy = true
    state.sync.error = ''
    state.sync.message = ''
    state.sync.pending = null
    render()
    try {
      const data = await api('/v1/athlete/me/intervals/calendar/preview', {
        method: 'POST',
        body: { op },
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
    } catch (err) {
      state.sync.error = err.message || 'Bekreftelse feilet'
      state.sync.message = ''
    } finally {
      state.sync.busy = false
      render()
    }
  })
}

bootstrap().catch((err) => {
  app.innerHTML = `<div class="onboarding"><h1>Kunne ikke starte</h1><p class="error">${escapeHtml(err.message)}</p><p class="muted">Sjekk at coach-api kjører på port 8000.</p></div>`
})
