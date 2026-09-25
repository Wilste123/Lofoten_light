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
  tab: 'coach',
  messages: [],
  overview: null,
  planBlocks: [],
  intervals: {
    connected: false,
    intervals_athlete_id: '',
    api_key_hint: null,
    form_athlete_id: '',
    form_api_key: '',
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

async function api(path, { method = 'GET', body, athleteId } = {}) {
  const headers = { 'Content-Type': 'application/json' }
  const id = athleteId ?? getAthleteId()
  if (id) headers['X-Athlete-Id'] = id
  const res = await fetch(`${API}${path}`, {
    method,
    headers,
    body: body ? JSON.stringify(body) : undefined,
  })
  const data = await res.json().catch(() => ({}))
  if (!res.ok) throw new Error(data.detail || data.message || `Feil ${res.status}`)
  return data
}

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

async function bootstrap() {
  const id = getAthleteId()
  const data = await api('/v1/session/bootstrap', {
    method: 'POST',
    body: { athlete_id: id },
    athleteId: null,
  })
  if (data.needs_onboarding || !data.athlete) {
    state.athlete = null
    render()
    return
  }
  state.athlete = data.athlete
  setAccent(data.athlete.accent_color)
  setAthleteId(data.athlete.id)
  await Promise.all([refreshOverview(), refreshIntervals(), refreshPlanBlocks()])
  render()
}

async function refreshOverview() {
  try {
    state.overview = await api('/v1/overview')
  } catch {
    state.overview = null
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
    app.innerHTML = renderOnboarding()
    bindOnboarding()
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
      <section class="panel ${state.tab === 'overblikk' ? 'active' : ''}" data-panel="overblikk">
        ${renderOverview()}
      </section>
      <section class="panel ${state.tab === 'du' ? 'active' : ''}" data-panel="du">
        ${renderDu()}
      </section>
    </main>
    <nav class="tabs" aria-label="Hovedfaner">
      <button type="button" data-tab="coach" class="${state.tab === 'coach' ? 'active' : ''}">Coach</button>
      <button type="button" data-tab="overblikk" class="${state.tab === 'overblikk' ? 'active' : ''}">Overblikk</button>
      <button type="button" data-tab="du" class="${state.tab === 'du' ? 'active' : ''}">Du</button>
    </nav>
  `
  bindApp()
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
    </div>
  `
}

function bindOnboarding() {
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
      state.athlete = data.athlete
      setAthleteId(data.athlete.id)
      setAccent(data.athlete.accent_color)
      state.messages = [
        {
          role: 'assistant',
          content: `Hei ${data.athlete.display_name}. Jeg er ${data.athlete.coach_display_name}. Si ifra hva du vil prioritere — mål, skade, eller ukens fokus.`,
        },
      ]
      await refreshOverview()
      await refreshIntervals()
      await refreshPlanBlocks()
      toast('Profil lagret')
    } catch (err) {
      state.error = err.message || 'Kunne ikke lagre'
    } finally {
      state.busy = false
      render()
    }
  })
}

function renderChat() {
  const bubbles = state.messages
    .map((m) => `<div class="bubble ${m.role}">${escapeHtml(m.content)}</div>`)
    .join('')
  return `
    <div class="chat-log" id="chat-log">${bubbles || `<p class="muted">Skriv til ${escapeHtml(state.athlete.coach_display_name)}.</p>`}</div>
    <form class="chat-form" id="chat-form">
      <input id="chat-input" autocomplete="off" placeholder="Spør treneren…" ${state.busy ? 'disabled' : ''} />
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

function renderProgressSection(o) {
  const progress = o.progress || {}
  const rows = progress.disciplines || []
  const source = progress.source || 'demo'
  const badge =
    source === 'demo'
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
      const target =
        d.target_hours != null ? `${formatHours(d.completed_hours)} / ${formatHours(d.target_hours)} t` : `${formatHours(d.completed_hours)} t · sett mål i Du`
      const compliance =
        d.compliance_pct != null ? `${d.compliance_pct} %` : '—'
      return `
        <div class="progress-row">
          <div class="progress-meta">
            <span class="progress-label">${escapeHtml(d.label)}</span>
            <span class="progress-nums">${escapeHtml(target)}</span>
            <span class="progress-pct">${escapeHtml(compliance)}</span>
          </div>
          <div class="progress-track" role="progressbar" aria-valuenow="${pct}" aria-valuemin="0" aria-valuemax="100" aria-label="${escapeHtml(d.label)}">
            <div class="progress-fill" style="width:${Math.min(100, Math.max(0, pct))}%"></div>
          </div>
        </div>`
    })
    .join('')
  return `
    <section class="section-block">
      <div class="section-head">
        <h2>Fremskritt</h2>
        ${badge}
      </div>
      <p class="muted tight">${source === 'demo' ? 'Illustrasjonstall — koble Intervals for ekte volum.' : 'Sesongvolum vs mål.'}${windowLabel ? ` <span class="dim">(${escapeHtml(windowLabel)})</span>` : ''}</p>
      <div class="progress-list">${bars || `<p class="muted">Ingen disipliner.</p>`}</div>
    </section>`
}

function renderPlanStrip(o) {
  const p = o.periodization || {}
  const cur = p.current_block
  const next = p.next_block
  const days = p.days_to_goal
  const daysLabel =
    days == null
      ? 'Sett racedato i Du'
      : days < 0
        ? `${Math.abs(days)} dager siden mål`
        : `${days} dager til mål`
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
        <p class="muted tight">fra ${escapeHtml(next.start_date || '?')}</p>
      </div>`
    : `<div class="plan-next">
        <p class="plan-kicker">Neste</p>
        <p class="muted tight">Ingen neste blokk</p>
      </div>`
  return `
    <section class="section-block plan-strip">
      <div class="section-head">
        <h2>Periodisering</h2>
        <span class="days-pill">${escapeHtml(daysLabel)}</span>
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
  const ftpEst =
    o.ftp_estimated != null
      ? `${o.ftp_estimated} W${o.estimate_confidence ? ` (${o.estimate_confidence})` : ''}`
      : o.estimate_disclaimer || 'Estimat etter 5 sykkeløkter med watt'
  return `
    <div class="overview-hero">
      <p class="brand-mark">Lofoten Coach</p>
      <h2>Kjapt overblikk</h2>
      <p class="muted">${escapeHtml(o.uplift_line || '')}</p>
    </div>
    ${renderPlanStrip(o)}
    ${renderProgressSection(o)}
    <section class="section-block">
      <h2>Form</h2>
      <div class="stat-row"><span>Testet FTP</span><span>${o.ftp_tested != null ? `${o.ftp_tested} W` : '—'}</span></div>
      <div class="stat-row"><span>Estimert FTP</span><span>${escapeHtml(String(ftpEst))}</span></div>
      <div class="stat-row"><span>VO₂</span><span>${o.vo2_estimate != null ? o.vo2_estimate : '—'}</span></div>
    </section>
    <section class="section-block">
      <h2>Kontekst</h2>
      <div class="stat-row"><span>Mål</span><span>${escapeHtml(o.goal_text || '—')}</span></div>
      <div class="stat-row"><span>Ukens fokus</span><span>${escapeHtml(o.weekly_focus || '—')}</span></div>
      <div class="stat-row"><span>Skade</span><span>${escapeHtml(o.injury_notes || '—')}</span></div>
    </section>
    <section class="section-block">
      <h2>Intervals</h2>
      <div class="stat-row">
        <span>Status</span>
        <span>${o.intervals_linked ? 'Koblet' : 'Ikke koblet'}</span>
      </div>
      <p class="muted">${escapeHtml(o.intervals_hint || 'Ikke koblet ennå.')}</p>
      ${
        o.intervals_linked
          ? ''
          : `<p class="muted tight">Gå til <strong>Du</strong> og lim inn athlete ID + API-nøkkel.</p>`
      }
    </section>
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
        <p class="muted tight">Volummål for fremskritt / compliance på Overblikk.</p>
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
    ${renderPlanBlocksEditor()}
    <form id="intervals-form" class="section-block" style="margin-top:1rem">
      <h2>Intervals</h2>
      <p class="muted">
        ${
          state.intervals.connected
            ? `Koblet${state.intervals.api_key_hint ? ` · nøkkel ${escapeHtml(state.intervals.api_key_hint)}` : ''}.`
            : 'Ikke koblet. Hent nøkkel under Intervals → Settings → Developer.'
        }
      </p>
      <div class="field">
        <label for="intervals_athlete_id">Intervals athlete ID</label>
        <input id="intervals_athlete_id" name="intervals_athlete_id" autocomplete="off"
          value="${escapeHtml(state.intervals.form_athlete_id || '')}"
          placeholder="f.eks. i123456" required />
      </div>
      <div class="field">
        <label for="intervals_api_key">API-nøkkel</label>
        <input id="intervals_api_key" name="intervals_api_key" type="password" autocomplete="off"
          value="${escapeHtml(state.intervals.form_api_key || '')}"
          placeholder="${state.intervals.api_key_hint ? 'Ny nøkkel for å bytte' : 'Lim inn API-nøkkel'}" required />
      </div>
      ${state.intervalsError ? `<p class="error">${escapeHtml(state.intervalsError)}</p>` : ''}
      <button class="btn btn-primary" type="submit" ${state.busy ? 'disabled' : ''}>Lagre Intervals</button>
    </form>
  `
}

function bindApp() {
  document.querySelectorAll('.tabs button').forEach((btn) => {
    btn.addEventListener('click', async () => {
      state.tab = btn.dataset.tab
      state.error = ''
      state.intervalsError = ''
      state.planError = ''
      if (state.tab === 'overblikk') await refreshOverview()
      if (state.tab === 'du') {
        await refreshIntervals()
        await refreshPlanBlocks()
      }
      render()
    })
  })

  const chatForm = document.getElementById('chat-form')
  chatForm?.addEventListener('submit', async (e) => {
    e.preventDefault()
    const input = document.getElementById('chat-input')
    const message = (input?.value || '').trim()
    if (!message || state.busy) return
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

  const intervalsForm = document.getElementById('intervals-form')
  intervalsForm?.addEventListener('submit', async (e) => {
    e.preventDefault()
    const fd = new FormData(intervalsForm)
    const payload = {
      intervals_athlete_id: String(fd.get('intervals_athlete_id') || '').trim(),
      intervals_api_key: String(fd.get('intervals_api_key') || '').trim(),
      verify: true,
    }
    state.intervals.form_athlete_id = payload.intervals_athlete_id
    state.intervals.form_api_key = payload.intervals_api_key
    state.busy = true
    state.intervalsError = ''
    render()
    try {
      const data = await api('/v1/athlete/me/intervals', { method: 'PUT', body: payload })
      state.intervals.connected = !!data.connected
      state.intervals.intervals_athlete_id = data.intervals_athlete_id || ''
      state.intervals.api_key_hint = data.api_key_hint || null
      state.intervals.form_athlete_id = data.intervals_athlete_id || ''
      state.intervals.form_api_key = ''
      if (data.verified === false && data.verify_error) {
        toast(`Lagret — Intervals-sjekk feilet: ${data.verify_error}`)
      } else if (data.verified) {
        toast('Intervals lagret og verifisert')
      } else {
        toast('Intervals lagret')
      }
      await refreshOverview()
    } catch (err) {
      state.intervalsError = err.message || 'Kunne ikke lagre Intervals'
    } finally {
      state.busy = false
      render()
    }
  })
}

bootstrap().catch((err) => {
  app.innerHTML = `<div class="onboarding"><h1>Kunne ikke starte</h1><p class="error">${escapeHtml(err.message)}</p><p class="muted">Sjekk at coach-api kjører på port 8000.</p></div>`
})
