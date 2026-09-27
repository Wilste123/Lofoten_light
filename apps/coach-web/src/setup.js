/** Adaptive AI landing setup — conversation-first, knowledge-grounded. */

export const SETUP_STEPS = ['account', 'chat', 'intervals', 'preview']

export const SETUP_STEP_LABELS = {
  account: 'Profil',
  chat: 'Samtale',
  intervals: 'Intervals',
  preview: 'Forhåndsvis',
}

export function emptySetupDraft(seed = {}) {
  return {
    display_name: seed.display_name || '',
    username: seed.username || '',
    username_touched: Boolean(seed.username),
    coach_display_name: seed.coach_display_name || 'Rocky',
    coach_personality: seed.coach_personality || 'direkte',
    coach_style_note: seed.coach_style_note || '',
    accent_color: seed.accent_color || '#1a6b4a',
    goal_text: seed.goal_text || '',
    season_start_date: seed.season_start_date || '',
    goal_race_date: seed.goal_race_date || '',
    weekly_hours_target: seed.weekly_hours_target ?? '',
    schedule_notes: seed.schedule_notes || '',
    background_notes: seed.background_notes || '',
    injury_notes: seed.injury_notes || '',
    coach_respect_notes: seed.coach_respect_notes || '',
    notes: seed.notes || '',
    ftp_tested: seed.ftp_tested ?? '',
    ftp_tested_at: seed.ftp_tested_at || '',
    weight_kg: seed.weight_kg ?? '',
    age_years: seed.age_years ?? '',
    nutrition_ibs: seed.nutrition_ibs || 'no',
    nutrition_gluten: seed.nutrition_gluten || 'none',
    nutrition_lactose: Boolean(seed.nutrition_lactose),
    nutrition_other_restrictions: seed.nutrition_other_restrictions || '',
    nutrition_notes: seed.nutrition_notes || '',
    intervals_athlete_id: '',
    intervals_api_key: '',
    skip_intervals: false,
  }
}

export function draftPayload(draft) {
  const num = (v) => (v === '' || v == null ? null : Number(v))
  return {
    display_name: String(draft.display_name || '').trim(),
    username: String(draft.username || '').trim().toLowerCase(),
    coach_display_name: String(draft.coach_display_name || 'Rocky').trim(),
    coach_personality: draft.coach_personality || 'direkte',
    coach_style_note: String(draft.coach_style_note || ''),
    accent_color: draft.accent_color,
    goal_text: String(draft.goal_text || ''),
    injury_notes: String(draft.injury_notes || ''),
    schedule_notes: String(draft.schedule_notes || ''),
    background_notes: String(draft.background_notes || ''),
    coach_respect_notes: String(draft.coach_respect_notes || ''),
    notes: String(draft.notes || ''),
    weekly_hours_target: num(draft.weekly_hours_target),
    season_start_date: draft.season_start_date || null,
    goal_race_date: draft.goal_race_date || null,
    ftp_tested: num(draft.ftp_tested),
    ftp_tested_at: draft.ftp_tested_at || null,
    weight_kg: num(draft.weight_kg),
    age_years: num(draft.age_years),
    nutrition_ibs: draft.nutrition_ibs || 'no',
    nutrition_gluten: draft.nutrition_gluten || 'none',
    nutrition_lactose: Boolean(draft.nutrition_lactose),
    nutrition_other_restrictions: String(draft.nutrition_other_restrictions || ''),
    nutrition_notes: String(draft.nutrition_notes || ''),
    intervals_athlete_id: draft.skip_intervals
      ? ''
      : String(draft.intervals_athlete_id || '').trim(),
    intervals_api_key: draft.skip_intervals
      ? ''
      : String(draft.intervals_api_key || '').trim(),
    enrich_with_llm: true,
  }
}

function stepIndicator(step) {
  const idx = SETUP_STEPS.indexOf(step)
  const parts = SETUP_STEPS.map((id, i) => {
    const cls = i < idx ? 'done' : i === idx ? 'current' : ''
    return `<span class="setup-step-dot ${cls}" title="${SETUP_STEP_LABELS[id]}">${i + 1}</span>`
  }).join('<span class="setup-step-line"></span>')
  return `<div class="setup-steps" aria-label="Steg">${parts}</div>
    <p class="muted tight setup-step-label">${SETUP_STEP_LABELS[step] || ''}</p>`
}

function draftChips(draft) {
  const chips = []
  if (draft.goal_text) chips.push(['Mål', draft.goal_text])
  if (draft.background_notes) chips.push(['Bakgrunn', draft.background_notes])
  if (draft.injury_notes) chips.push(['Helse', draft.injury_notes])
  if (draft.schedule_notes) chips.push(['Tid', draft.schedule_notes])
  if (draft.weekly_hours_target) chips.push(['t/uke', String(draft.weekly_hours_target)])
  if (draft.coach_respect_notes) chips.push(['Respektér', draft.coach_respect_notes])
  if (!chips.length) return ''
  return `<div class="setup-chips">${chips
    .map(
      ([k, v]) =>
        `<span class="setup-chip"><strong>${k}:</strong> ${String(v).slice(0, 60)}${
          String(v).length > 60 ? '…' : ''
        }</span>`,
    )
    .join('')}</div>`
}

export function renderSetupWizard({ state, accents, personalities, escapeHtml: esc }) {
  const o = state.setup.draft
  const step = state.setup.step
  const mode = state.setup.mode
  const title =
    mode === 'restart' ? 'Sett opp planen på nytt' : 'Sett opp med treneren'
  const swatches = accents
    .map(
      (c) =>
        `<button type="button" class="swatch ${o.accent_color === c ? 'selected' : ''}" data-color="${c}" style="background:${c}" aria-label="Farge ${c}"></button>`,
    )
    .join('')
  const pers = personalities
    .map(
      (p) =>
        `<option value="${p.id}" ${o.coach_personality === p.id ? 'selected' : ''}>${p.label}</option>`,
    )
    .join('')

  let body = ''
  if (step === 'account') {
    body = `
      <div class="setup-coach-bubble" role="status">
        <strong>${esc(o.coach_display_name || 'Rocky')}</strong> her. Kort om deg først —
        deretter snakker vi fritt om mål, erfaring og helse. Planen tilpasses deg
        (nybegynner, comeback, skade, tidsklemma …), ikke én mal for alle.
      </div>
      <form id="setup-form">
        <div class="field">
          <label for="display_name">Ditt navn</label>
          <input id="display_name" name="display_name" required value="${esc(o.display_name)}" placeholder="f.eks. William" ${mode === 'restart' ? 'readonly' : ''} />
        </div>
        <div class="field">
          <label for="username">Brukernavn</label>
          <input id="username" name="username" required autocomplete="username"
            value="${esc(o.username)}"
            placeholder="f.eks. william"
            pattern="[a-z0-9]([a-z0-9-]{0,30}[a-z0-9])?"
            ${mode === 'restart' ? 'readonly' : ''} />
          <p class="muted tight">Brukes for innlogging — ingen passord.</p>
        </div>
        <div class="grid-2">
          <div class="field">
            <label for="coach_display_name">Trenerens navn</label>
            <input id="coach_display_name" name="coach_display_name" value="${esc(o.coach_display_name)}" />
          </div>
          <div class="field">
            <label for="coach_personality">Personlighet</label>
            <select id="coach_personality" name="coach_personality">${pers}</select>
          </div>
        </div>
        <div class="field">
          <label>Aksentfarge</label>
          <div class="swatches" id="setup-swatches">${swatches}</div>
        </div>
        ${state.error ? `<p class="error">${esc(state.error)}</p>` : ''}
        <div class="setup-nav">
          <button type="button" class="btn secondary" id="setup-back" ${state.busy ? 'disabled' : ''}>Avbryt</button>
          <button type="submit" class="btn btn-primary" ${state.busy ? 'disabled' : ''}>Start samtale</button>
        </div>
      </form>`
  } else if (step === 'chat') {
    const msgs = (state.setup.messages || [])
      .map((m) => `<div class="bubble ${m.role}">${esc(m.content)}</div>`)
      .join('')
    body = `
      <div class="setup-coach-bubble muted tight">
        Fortell fritt — f.eks. «helt ny på trening», «comeback etter pause», «isjas + 6 t/uke», «mot Lofoten».
        Treneren bruker knowledge-basen. Når nok er på plass kan du gå videre til Intervals / plan.
      </div>
      ${draftChips(o)}
      <div class="chat-log setup-chat-log" id="setup-chat-log">${
        msgs ||
        `<p class="muted">Si hei — hva er målet ditt, og hvordan er erfaringen din?</p>`
      }</div>
      <form class="chat-form" id="setup-chat-form">
        <input id="setup-chat-input" autocomplete="off" placeholder="Skriv til treneren…"
          value="${esc(state.setup.chatDraft || '')}" ${state.busy ? 'disabled' : ''} />
        <button class="btn btn-primary" type="submit" ${state.busy ? 'disabled' : ''}>Send</button>
      </form>
      ${state.error ? `<p class="error">${esc(state.error)}</p>` : ''}
      <div class="setup-nav">
        <button type="button" class="btn secondary" id="setup-back" ${state.busy ? 'disabled' : ''}>Tilbake</button>
        <button type="button" class="btn btn-primary" id="setup-to-intervals" ${state.busy ? 'disabled' : ''}>
          ${state.setup.readyForPlan ? 'Videre til Intervals / plan' : 'Videre (Intervals)'}
        </button>
      </div>`
  } else if (step === 'intervals') {
    body = `
      <div class="setup-coach-bubble">
        Koble Intervals.icu valgfritt — da kan jeg lese økter og (etter bekreftelse) speile grovplan-noter.
      </div>
      <details class="howto-card" open>
        <summary>Slik henter du API-nøkkel fra Intervals</summary>
        <ol class="howto-list">
          <li>Logg inn på <strong>intervals.icu</strong>.</li>
          <li>Gå til <strong>Settings</strong> → <strong>Developer Settings</strong>.</li>
          <li>Under API key: <strong>Get API Key</strong> / vis nøkkel, kopier den.</li>
          <li><strong>Athlete ID</strong> står i Settings (f.eks. <code>i123456</code>).</li>
          <li>Lim inn under. Nøkkel lagres kun på server. Vi skriver aldri stille til Intervals.</li>
        </ol>
      </details>
      <form id="setup-form">
        <div class="field">
          <label><input type="checkbox" name="skip_intervals" ${o.skip_intervals ? 'checked' : ''} /> Hopp over — koble senere under Du</label>
        </div>
        <div class="field">
          <label for="intervals_athlete_id">Intervals athlete ID</label>
          <input id="intervals_athlete_id" name="intervals_athlete_id" autocomplete="off"
            value="${esc(o.intervals_athlete_id)}" placeholder="f.eks. i123456"
            ${o.skip_intervals ? 'disabled' : ''} />
        </div>
        <div class="field">
          <label for="intervals_api_key">API-nøkkel</label>
          <input id="intervals_api_key" name="intervals_api_key" type="password" autocomplete="off"
            value="${esc(o.intervals_api_key)}" placeholder="Lim inn API-nøkkel"
            ${o.skip_intervals ? 'disabled' : ''} />
        </div>
        ${state.error ? `<p class="error">${esc(state.error)}</p>` : ''}
        <div class="setup-nav">
          <button type="button" class="btn secondary" id="setup-back" ${state.busy ? 'disabled' : ''}>Tilbake</button>
          <button type="submit" class="btn btn-primary" ${state.busy ? 'disabled' : ''}>Lag forhåndsvisning</button>
        </div>
      </form>`
  } else if (step === 'preview') {
    const p = state.setup.preview
    if (!p) {
      body = `
        <p class="muted">Genererer periodisering fra knowledge + samtalen…</p>
        ${state.error ? `<p class="error">${esc(state.error)}</p>` : ''}
        <div class="setup-nav">
          <button type="button" class="btn secondary" id="setup-back" ${state.busy ? 'disabled' : ''}>Tilbake</button>
          <button type="button" class="btn btn-primary" id="setup-gen-preview" ${state.busy ? 'disabled' : ''}>
            ${state.busy ? 'Genererer…' : 'Generer forhåndsvisning'}
          </button>
        </div>`
    } else {
      const rows = (p.plan_blocks || [])
        .map(
          (b) =>
            `<tr>
              <td><strong>${esc(b.title)}</strong></td>
              <td class="dim">${esc(b.start_date)}–${esc(b.end_date)}</td>
              <td>${esc(b.weekly_hours)} t</td>
              <td>${esc(b.theme)}</td>
            </tr>`,
        )
        .join('')
      const evCount = p.intervals_sync?.events_count ?? 0
      const sample = (p.intervals_sync?.events_preview || [])
        .slice(0, 6)
        .map(
          (e) =>
            `<li><code>${esc(e.day || e.start_date_local || '')}</code> · ${esc(e.name || '')}</li>`,
        )
        .join('')
      const paths = (p.knowledge?.paths || []).slice(0, 8).join(', ')
      body = `
        <div class="setup-coach-bubble">
          ${
            p.coach_note
              ? esc(p.coach_note)
              : 'Her er grovplanen. Bekreft for å lagre lokalt. Intervals synces kun med egen bekreftelse.'
          }
        </div>
        <p class="muted tight">
          Kilde: ${esc(p.plan_source || '—')}
          ${p.athlete_archetype ? ` · ${esc(p.athlete_archetype)}` : ''}
          ${paths ? ` · knowledge: ${esc(paths)}` : ''}
        </p>
        <div class="setup-preview-card">
          <h3>Periodisering</h3>
          <pre class="setup-overview">${esc(p.overview_md || '')}</pre>
          <div class="table-wrap">
            <table class="setup-blocks-table">
              <thead><tr><th>Blokk</th><th>Periode</th><th>Uke</th><th>Tema</th></tr></thead>
              <tbody>${rows}</tbody>
            </table>
          </div>
          <h3>Hva lagres vs Intervals</h3>
          <ul class="setup-persist-list">
            <li><strong>I appen:</strong> profil (SQLite + profile.md), sesongmål, plan_blocks.</li>
            <li><strong>Intervals (valgfritt):</strong> grovplan-ukenoter (NOTE, <code>ll-coach-…</code>) — ${evCount} i forhåndsvisning. Ikke ZWO.</li>
            <li><strong>Aldri stille:</strong> sync krever egen bekreftelse etter lagring.</li>
          </ul>
          ${
            sample
              ? `<p class="muted tight">Eksempel Intervals-noter:</p><ul class="sync-sample">${sample}</ul>`
              : ''
          }
          <div class="field">
            <label><input type="checkbox" id="prepare_intervals_sync"
              ${state.setup.prepareIntervals ? 'checked' : ''}
              ${
                !(o.intervals_athlete_id && o.intervals_api_key) && !state.intervals?.connected
                  ? 'disabled'
                  : ''
              } />
              Etter lagring: forbered Sync av grovplan-noter til Intervals
            </label>
          </div>
        </div>
        ${state.error ? `<p class="error">${esc(state.error)}</p>` : ''}
        <div class="setup-nav">
          <button type="button" class="btn secondary" id="setup-back" ${state.busy ? 'disabled' : ''}>Tilbake</button>
          <button type="button" class="btn btn-primary" id="setup-confirm-plan" ${state.busy ? 'disabled' : ''}>
            ${state.busy ? 'Lagrer…' : 'Bekreft og lagre plan'}
          </button>
        </div>`
    }
  }

  return `
    <div class="onboarding setup-flow">
      <p class="brand-mark">Lofoten coach</p>
      <h1>${esc(title)}</h1>
      ${stepIndicator(step)}
      ${body}
      ${
        mode === 'restart'
          ? ''
          : `<p class="muted" style="margin-top:1.25rem">
        <button type="button" class="linkish" id="setup-to-login">Jeg har allerede profil</button>
      </p>`
      }
    </div>`
}

export function readSetupForm(form, draft) {
  const fd = new FormData(form)
  const next = { ...draft }
  for (const key of [
    'display_name',
    'username',
    'coach_display_name',
    'coach_personality',
    'coach_style_note',
    'intervals_athlete_id',
    'intervals_api_key',
  ]) {
    if (fd.has(key)) next[key] = String(fd.get(key) || '')
  }
  if (form.querySelector('[name=skip_intervals]')) {
    next.skip_intervals = fd.get('skip_intervals') === 'on'
  }
  if (next.username) next.username = next.username.trim().toLowerCase()
  return next
}

export function applyExtractedToDraft(draft, extracted) {
  if (!extracted || typeof extracted !== 'object') return draft
  const next = { ...draft }
  for (const [k, v] of Object.entries(extracted)) {
    if (k === 'ready_for_plan' || v == null || v === '') continue
    next[k] = v
  }
  return next
}
