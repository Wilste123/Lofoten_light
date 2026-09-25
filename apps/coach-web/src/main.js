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
  await refreshOverview()
  render()
}

async function refreshOverview() {
  try {
    state.overview = await api('/v1/overview')
  } catch {
    state.overview = null
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
        <button class="btn" type="submit" ${state.busy ? 'disabled' : ''}>Start med treneren</button>
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
      <button class="btn" type="submit" ${state.busy ? 'disabled' : ''}>Send</button>
    </form>
    ${state.error && state.tab === 'coach' ? `<p class="error">${escapeHtml(state.error)}</p>` : ''}
  `
}

function renderOverview() {
  const o = state.overview || {}
  const ftpEst =
    o.ftp_estimated != null
      ? `${o.ftp_estimated} W${o.estimate_confidence ? ` (${o.estimate_confidence})` : ''}`
      : o.estimate_disclaimer || 'Estimat etter 5 sykkeløkter med watt'
  return `
    <div class="card-block">
      <h2>Kjapt overblikk</h2>
      <p class="muted">${escapeHtml(o.uplift_line || '')}</p>
    </div>
    <div class="card-block">
      <h2>Form</h2>
      <div class="stat-row"><span>Testet FTP</span><span>${o.ftp_tested != null ? `${o.ftp_tested} W` : '—'}</span></div>
      <div class="stat-row"><span>Estimert FTP</span><span>${escapeHtml(String(ftpEst))}</span></div>
      <div class="stat-row"><span>VO₂</span><span>${o.vo2_estimate != null ? o.vo2_estimate : '—'}</span></div>
    </div>
    <div class="card-block">
      <h2>Kontekst</h2>
      <div class="stat-row"><span>Mål</span><span>${escapeHtml(o.goal_text || '—')}</span></div>
      <div class="stat-row"><span>Ukens fokus</span><span>${escapeHtml(o.weekly_focus || '—')}</span></div>
      <div class="stat-row"><span>Skade</span><span>${escapeHtml(o.injury_notes || '—')}</span></div>
    </div>
    <div class="card-block">
      <h2>Intervals</h2>
      <p class="muted">${escapeHtml(o.intervals_hint || 'Ikke koblet ennå.')}</p>
      <p class="muted" style="margin-top:0.5rem">Detaljer og kalender lever i Intervals — appen eier mål og avtaler.</p>
    </div>
  `
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
      <div class="card-block">
        <h2>Profil</h2>
        <div class="field"><label>Navn</label><input name="display_name" value="${escapeHtml(a.display_name || '')}" /></div>
        <div class="grid-2">
          <div class="field"><label>Trener</label><input name="coach_display_name" value="${escapeHtml(a.coach_display_name || '')}" /></div>
          <div class="field"><label>Personlighet</label><select name="coach_personality">${pers}</select></div>
        </div>
        <div class="field"><label>Aksentfarge</label><div class="swatches" id="du-swatches">${swatches}</div></div>
      </div>
      <div class="card-block">
        <h2>Mål & avtaler</h2>
        <div class="field"><label>Mål</label><textarea name="goal_text" rows="2">${escapeHtml(a.goal_text || '')}</textarea></div>
        <div class="field"><label>Ukens fokus</label><input name="weekly_focus" value="${escapeHtml(a.weekly_focus || '')}" /></div>
        <div class="field"><label>Skade / begrensninger</label><textarea name="injury_notes" rows="2">${escapeHtml(a.injury_notes || '')}</textarea></div>
        <div class="field"><label>Avtaler (én per linje)</label><textarea name="agreements" rows="3" placeholder="f.eks. Ingen langløp denne uka">${escapeHtml(agreements)}</textarea></div>
        <div class="field"><label>Notater</label><textarea name="notes" rows="2">${escapeHtml(a.notes || '')}</textarea></div>
      </div>
      <div class="card-block">
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
      <div class="card-block">
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
      <button class="btn" type="submit" ${state.busy ? 'disabled' : ''}>Lagre profil</button>
    </form>
  `
}

function bindApp() {
  document.querySelectorAll('.tabs button').forEach((btn) => {
    btn.addEventListener('click', async () => {
      state.tab = btn.dataset.tab
      state.error = ''
      if (state.tab === 'overblikk') await refreshOverview()
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
}

bootstrap().catch((err) => {
  app.innerHTML = `<div class="onboarding"><h1>Kunne ikke starte</h1><p class="error">${escapeHtml(err.message)}</p><p class="muted">Sjekk at coach-api kjører på port 8000.</p></div>`
})
