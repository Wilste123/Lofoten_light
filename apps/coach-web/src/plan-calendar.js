/** Month grid helpers for Plan tab (Monday-first weeks). */

export function pad2(n) {
  return String(n).padStart(2, '0')
}

export function toIsoDate(d) {
  return `${d.getFullYear()}-${pad2(d.getMonth() + 1)}-${pad2(d.getDate())}`
}

export function parseIsoDate(s) {
  if (!s || s.length < 10) return null
  const d = new Date(`${s.slice(0, 10)}T12:00:00`)
  return Number.isNaN(d.getTime()) ? null : d
}

export function monthKeyFromDate(d = new Date()) {
  return `${d.getFullYear()}-${pad2(d.getMonth() + 1)}-01`
}

export function addMonths(monthKey, delta) {
  const d = parseIsoDate(monthKey) || new Date()
  d.setDate(1)
  d.setMonth(d.getMonth() + delta)
  return monthKeyFromDate(d)
}

export function monthLabelNb(monthKey) {
  const d = parseIsoDate(monthKey)
  if (!d) return monthKey
  return d.toLocaleDateString('nb-NO', { month: 'long', year: 'numeric' })
}

export function sessionIsoDate(s) {
  const raw = s?.session_date ?? s?.date ?? ''
  if (raw && typeof raw === 'object' && raw.toISOString) {
    return raw.toISOString().slice(0, 10)
  }
  return String(raw || '').slice(0, 10)
}

/** First month (YYYY-MM-01) with a session on/after ``fromIso``, else first session month. */
export function defaultMonthKeyForSessions(sessions, fromIso = toIsoDate(new Date())) {
  const rows = (sessions || [])
    .map((s) => sessionIsoDate(s))
    .filter(Boolean)
    .sort()
  if (!rows.length) return null
  const pick = rows.find((d) => d >= fromIso) || rows[0]
  return `${pick.slice(0, 7)}-01`
}

export function sessionsByDate(sessions) {
  const map = new Map()
  for (const s of sessions || []) {
    const day = sessionIsoDate(s)
    if (!day) continue
    if (!map.has(day)) map.set(day, [])
    map.get(day).push(s)
  }
  return map
}

export function mondayOfWeek(isoDate) {
  const d = parseIsoDate(isoDate)
  if (!d) return null
  const copy = new Date(d)
  const dow = (copy.getDay() + 6) % 7
  copy.setDate(copy.getDate() - dow)
  return toIsoDate(copy)
}

export function weekRangeFromDate(isoDate) {
  const start = mondayOfWeek(isoDate)
  if (!start) return null
  const d = parseIsoDate(start)
  const end = new Date(d)
  end.setDate(end.getDate() + 6)
  return { start, end: toIsoDate(end) }
}

export function monthRange(monthKey) {
  const d = parseIsoDate(monthKey)
  if (!d) return null
  const start = toIsoDate(d)
  const end = new Date(d.getFullYear(), d.getMonth() + 1, 0)
  return { start, end: toIsoDate(end) }
}

/**
 * 6 rows × 7 cols — cells may be outside current month (muted).
 */
export function buildMonthGrid(monthKey, byDate) {
  const first = parseIsoDate(monthKey)
  if (!first) return []
  const year = first.getFullYear()
  const month = first.getMonth()
  const startPad = (first.getDay() + 6) % 7
  const daysInMonth = new Date(year, month + 1, 0).getDate()
  const cells = []
  const gridStart = new Date(year, month, 1 - startPad)
  for (let i = 0; i < 42; i++) {
    const cur = new Date(gridStart)
    cur.setDate(gridStart.getDate() + i)
    const iso = toIsoDate(cur)
    const inMonth = cur.getMonth() === month
    const sessions = byDate.get(iso) || []
    cells.push({ iso, inMonth, day: cur.getDate(), sessions })
  }
  return cells
}
