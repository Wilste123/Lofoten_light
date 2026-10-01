/** Lightweight SVG charts for Dashboard (no chart lib). Norwegian labels in callers. */

const DISC_COLORS = {
  swim: 'var(--chart-swim, #3d8fd1)',
  bike: 'var(--chart-bike, #1a6b4a)',
  run: 'var(--chart-run, #c45c4a)',
  strength: 'var(--chart-strength, #b08d3a)',
}

function esc(s) {
  return String(s ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
}

const VOLUME_BUCKET_NB = {
  day: 'dag',
  week: 'uke',
  month: 'måned',
  year: 'år',
}

/** Norwegian title for volume chart grain. */
export function volumeBucketTitle(bucket) {
  const b = VOLUME_BUCKET_NB[bucket] || VOLUME_BUCKET_NB.day
  return `Volum per ${b}`
}

/**
 * Vertical bar chart for period volume (day / week / month / year bars).
 * @param {{ bars: Array<{label:string,hours:number}>, bucket?: string, series_kind?: string, label_nb?: string }} volume
 */
export function renderVolumeBars(volume) {
  const bars = volume?.bars || []
  const grain = VOLUME_BUCKET_NB[volume?.bucket] || 'dag'
  const kind = volume?.series_kind || 'executed'
  const kindClass = kind === 'planned' ? 'is-planned' : 'is-executed'
  const kindNote =
    kind === 'planned'
      ? '<p class="muted tight chart-kind">Planlagt (planned_sessions) — ikke gjennomført.</p>'
      : '<p class="muted tight chart-kind">Gjennomført (ICU-aktiviteter).</p>'
  if (!bars.length) {
    return `${kindNote}<p class="muted tight chart-empty">Ingen volumdata for perioden.</p>`
  }
  const max = Math.max(...bars.map((b) => Number(b.hours) || 0), 0.01)
  const n = bars.length
  const showEvery = n > 14 ? Math.ceil(n / 8) : n > 7 ? 2 : 1
  const cols = bars
    .map((b, i) => {
      const h = Number(b.hours) || 0
      const pct = Math.max(0, Math.min(100, (h / max) * 100))
      const showLabel = i % showEvery === 0 || i === n - 1
      const title = `${b.label}: ${h.toFixed(1)} t`
      return `
        <div class="chart-bar-col" title="${esc(title)}">
          <div class="chart-bar-track">
            <div class="chart-bar ${kindClass}" style="height:${pct.toFixed(1)}%"></div>
          </div>
          <span class="chart-bar-label ${showLabel ? '' : 'is-hidden'}">${esc(b.label)}</span>
        </div>`
    })
    .join('')
  return `
    ${kindNote}
    <div class="chart chart-volume ${kindClass}" role="img" aria-label="Volum per ${grain} (${kind === 'planned' ? 'planlagt' : 'gjennomført'})">
      <div class="chart-bars">${cols}</div>
    </div>`
}

/**
 * Horizontal bars by discipline.
 * @param {Array<{id:string,label:string,hours:number}>} rows
 */
export function renderDisciplineBars(rows) {
  const list = rows || []
  if (!list.length) {
    return `<p class="muted tight chart-empty">Ingen disiplin-data.</p>`
  }
  const max = Math.max(...list.map((r) => Number(r.hours) || 0), 0.01)
  const items = list
    .map((r) => {
      const h = Number(r.hours) || 0
      const pct = Math.max(0, Math.min(100, (h / max) * 100))
      const color = DISC_COLORS[r.id] || 'var(--accent)'
      return `
        <div class="chart-h-row">
          <span class="chart-h-label">${esc(r.label)}</span>
          <div class="chart-h-track">
            <div class="chart-h-fill" style="width:${pct.toFixed(1)}%;background:${color}"></div>
          </div>
          <span class="chart-h-val">${h.toFixed(1)} t</span>
        </div>`
    })
    .join('')
  return `<div class="chart chart-discipline" role="img" aria-label="Timer per disiplin">${items}</div>`
}

/**
 * CTL/ATL line chart from wellness series points.
 * @param {{ available?: boolean, points?: Array<{date:string,label?:string,ctl?:number|null,atl?:number|null}> }} series
 */
export function renderLoadLines(series) {
  const points = series?.points || []
  if (!series?.available || points.length < 2) {
    if (series?.available && points.length === 1) {
      const p = points[0]
      return `<p class="muted tight chart-empty">Kun ett punkt (CTL ${p.ctl ?? '—'} / ATL ${p.atl ?? '—'}).</p>`
    }
    return `<p class="muted tight chart-empty">${esc(series?.note || 'Ingen CTL/ATL for perioden.')}</p>`
  }

  const w = 320
  const h = 120
  const padL = 28
  const padR = 8
  const padT = 10
  const padB = 22
  const innerW = w - padL - padR
  const innerH = h - padT - padB

  const vals = []
  for (const p of points) {
    if (p.ctl != null) vals.push(Number(p.ctl))
    if (p.atl != null) vals.push(Number(p.atl))
  }
  let minV = Math.min(...vals)
  let maxV = Math.max(...vals)
  if (minV === maxV) {
    minV -= 5
    maxV += 5
  }
  const span = maxV - minV || 1

  const xAt = (i) => padL + (points.length === 1 ? innerW / 2 : (i / (points.length - 1)) * innerW)
  const yAt = (v) => padT + innerH - ((v - minV) / span) * innerH

  const pathFor = (key) => {
    const parts = []
    points.forEach((p, i) => {
      const v = p[key]
      if (v == null) return
      const cmd = parts.length ? 'L' : 'M'
      parts.push(`${cmd}${xAt(i).toFixed(1)},${yAt(Number(v)).toFixed(1)}`)
    })
    return parts.join(' ')
  }

  const ctlPath = pathFor('ctl')
  const atlPath = pathFor('atl')
  const yMax = maxV.toFixed(0)
  const yMin = minV.toFixed(0)
  const labelEvery = points.length > 10 ? Math.ceil(points.length / 5) : Math.max(1, Math.ceil(points.length / 4))
  const xLabels = points
    .map((p, i) => {
      if (i % labelEvery !== 0 && i !== points.length - 1) return ''
      const lab = p.label || (p.date ? `${p.date.slice(8, 10)}.${p.date.slice(5, 7)}` : '')
      return `<text class="chart-svg-label" x="${xAt(i).toFixed(1)}" y="${h - 4}" text-anchor="middle">${esc(lab)}</text>`
    })
    .join('')

  return `
    <div class="chart chart-load" role="img" aria-label="CTL og ATL over perioden">
      <svg viewBox="0 0 ${w} ${h}" class="chart-svg" preserveAspectRatio="xMidYMid meet">
        <line class="chart-grid" x1="${padL}" y1="${padT}" x2="${padL}" y2="${padT + innerH}" />
        <line class="chart-grid" x1="${padL}" y1="${padT + innerH}" x2="${w - padR}" y2="${padT + innerH}" />
        <text class="chart-svg-label" x="${padL - 4}" y="${padT + 4}" text-anchor="end">${yMax}</text>
        <text class="chart-svg-label" x="${padL - 4}" y="${padT + innerH}" text-anchor="end">${yMin}</text>
        ${ctlPath ? `<path class="chart-line chart-line-ctl" d="${ctlPath}" fill="none" />` : ''}
        ${atlPath ? `<path class="chart-line chart-line-atl" d="${atlPath}" fill="none" />` : ''}
        ${xLabels}
      </svg>
      <div class="chart-legend">
        <span class="chart-legend-item"><i class="swatch ctl"></i>CTL</span>
        <span class="chart-legend-item"><i class="swatch atl"></i>ATL</span>
      </div>
    </div>`
}

/**
 * Beta: CTL/ATL/TSB with past (solid) + planlagt future (dashed).
 * @param {{ past?: Array, future?: Array, available?: boolean, note_nb?: string, label_past_nb?: string, label_future_nb?: string }} chart
 */
export function renderBetaLoadTrajectory(chart) {
  const past = chart?.past || []
  const future = chart?.future || []
  const points = [...past, ...future.filter((f) => !past.some((p) => p.date === f.date))]
  if (!chart?.available || points.length < 2) {
    return `<p class="muted tight chart-empty">${esc(chart?.note_nb || 'Ingen CTL/ATL/TSB ennå — koble Intervals / ha planlagte økter.')}</p>`
  }

  const w = 340
  const h = 140
  const padL = 30
  const padR = 8
  const padT = 12
  const padB = 24
  const innerW = w - padL - padR
  const innerH = h - padT - padB

  const vals = []
  for (const p of points) {
    ;['ctl', 'atl', 'tsb'].forEach((k) => {
      if (p[k] != null) vals.push(Number(p[k]))
    })
  }
  let minV = Math.min(...vals)
  let maxV = Math.max(...vals)
  if (minV === maxV) {
    minV -= 8
    maxV += 8
  }
  // include 0 for TSB reference
  minV = Math.min(minV, 0)
  maxV = Math.max(maxV, 0)
  const span = maxV - minV || 1
  const xAt = (i) => padL + (points.length === 1 ? innerW / 2 : (i / (points.length - 1)) * innerW)
  const yAt = (v) => padT + innerH - ((v - minV) / span) * innerH

  const splitIdx = past.length > 0 ? past.length - 1 : 0

  const pathFor = (key, fromIdx, toIdx, dashed) => {
    const parts = []
    for (let i = fromIdx; i <= toIdx; i++) {
      const v = points[i]?.[key]
      if (v == null) continue
      const cmd = parts.length ? 'L' : 'M'
      parts.push(`${cmd}${xAt(i).toFixed(1)},${yAt(Number(v)).toFixed(1)}`)
    }
    if (!parts.length) return ''
    const dash = dashed ? ' stroke-dasharray="4 3"' : ''
    return `<path class="chart-line chart-line-${key}${dashed ? ' is-planned' : ''}" d="${parts.join(' ')}" fill="none"${dash} />`
  }

  const pastEnd = Math.max(0, splitIdx)
  const futStart = Math.min(splitIdx, points.length - 1)
  const ctlPast = pathFor('ctl', 0, pastEnd, false)
  const atlPast = pathFor('atl', 0, pastEnd, false)
  const tsbPast = pathFor('tsb', 0, pastEnd, false)
  const ctlFut = future.length ? pathFor('ctl', futStart, points.length - 1, true) : ''
  const atlFut = future.length ? pathFor('atl', futStart, points.length - 1, true) : ''
  const tsbFut = future.length ? pathFor('tsb', futStart, points.length - 1, true) : ''

  const zeroY = yAt(0)
  const labelEvery = points.length > 12 ? Math.ceil(points.length / 5) : Math.max(1, Math.ceil(points.length / 4))
  const xLabels = points
    .map((p, i) => {
      if (i % labelEvery !== 0 && i !== points.length - 1) return ''
      const lab = p.label || (p.date ? `${p.date.slice(8, 10)}.${p.date.slice(5, 7)}` : '')
      return `<text class="chart-svg-label" x="${xAt(i).toFixed(1)}" y="${h - 4}" text-anchor="middle">${esc(lab)}</text>`
    })
    .join('')

  const kindNote = `
    <p class="muted tight chart-kind">
      <span class="chart-kind-past">${esc(chart.label_past_nb || 'Gjennomført (ICU)')}</span>
      ·
      <span class="chart-kind-planned">${esc(chart.label_future_nb || 'Planlagt')}</span>
    </p>`

  return `
    ${kindNote}
    <div class="chart chart-load chart-beta-load" role="img" aria-label="CTL ATL TSB fortid og planlagt">
      <svg viewBox="0 0 ${w} ${h}" class="chart-svg" preserveAspectRatio="xMidYMid meet">
        <line class="chart-grid" x1="${padL}" y1="${padT}" x2="${padL}" y2="${padT + innerH}" />
        <line class="chart-grid" x1="${padL}" y1="${padT + innerH}" x2="${w - padR}" y2="${padT + innerH}" />
        <line class="chart-grid chart-zero" x1="${padL}" y1="${zeroY.toFixed(1)}" x2="${w - padR}" y2="${zeroY.toFixed(1)}" stroke-dasharray="2 2" />
        <text class="chart-svg-label" x="${padL - 4}" y="${padT + 4}" text-anchor="end">${maxV.toFixed(0)}</text>
        <text class="chart-svg-label" x="${padL - 4}" y="${padT + innerH}" text-anchor="end">${minV.toFixed(0)}</text>
        ${ctlPast}${atlPast}${tsbPast}${ctlFut}${atlFut}${tsbFut}
        ${xLabels}
      </svg>
      <div class="chart-legend">
        <span class="chart-legend-item"><i class="swatch ctl"></i>CTL</span>
        <span class="chart-legend-item"><i class="swatch atl"></i>ATL</span>
        <span class="chart-legend-item"><i class="swatch tsb"></i>TSB</span>
        <span class="chart-legend-item"><i class="swatch planned"></i>planlagt</span>
      </div>
    </div>`
}

/**
 * Horizontal ACWR risk bar with soft/hard bands.
 * @param {{ soft?: number, hard?: number, current?: { acwr?: number|null, band?: string, label_nb?: string, note_nb?: string } }} bands
 */
export function renderAcwrRiskBar(bands) {
  const soft = Number(bands?.soft ?? 1.3)
  const hard = Number(bands?.hard ?? 1.5)
  const cur = bands?.current || {}
  const acwr = cur.acwr
  const maxScale = Math.max(2.0, hard + 0.3, acwr != null ? Number(acwr) + 0.2 : 0)
  const pct = (v) => Math.max(0, Math.min(100, (Number(v) / maxScale) * 100))
  const marker =
    acwr == null
      ? ''
      : `<div class="acwr-marker" style="left:${pct(acwr).toFixed(1)}%" title="ATL:CTL ${Number(acwr).toFixed(2)}"></div>`
  return `
    <div class="acwr-block" role="img" aria-label="Akutt til kronisk belastning">
      <div class="acwr-track">
        <div class="acwr-zone ok" style="width:${pct(soft).toFixed(1)}%"></div>
        <div class="acwr-zone elevated" style="width:${(pct(hard) - pct(soft)).toFixed(1)}%"></div>
        <div class="acwr-zone high" style="width:${(100 - pct(hard)).toFixed(1)}%"></div>
        ${marker}
      </div>
      <div class="acwr-labels">
        <span>&lt;${soft}</span>
        <span>${soft}–${hard}</span>
        <span>&gt;${hard}</span>
      </div>
      <p class="stat-row"><span>${esc(cur.label_nb || 'ACWR')}</span><span>${acwr != null ? Number(acwr).toFixed(2) : '—'}</span></p>
      <p class="muted tight">${esc(cur.note_nb || '')}</p>
    </div>`
}

