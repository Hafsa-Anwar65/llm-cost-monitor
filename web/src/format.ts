import type { Unit } from './types'

const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
const WEEKDAYS = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat']

export function money(n: number): string {
  if (n === 0) return '$0.00'
  if (Math.abs(n) >= 1) {
    return '$' + n.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
  }
  return '$' + n.toFixed(4)
}

export function moneyAxis(n: number): string {
  if (n === 0) return '$0'
  if (n >= 1000) return `$${+(n / 1000).toFixed(1)}k`
  return n >= 1 ? `$${+n.toFixed(2)}` : `$${+n.toFixed(4)}`
}

export function compact(n: number): string {
  const units: [string, number][] = [['B', 1e9], ['M', 1e6], ['K', 1e3]]
  for (const [suffix, size] of units) {
    if (Math.abs(n) >= size) return `${+(n / size).toFixed(1)}${suffix}`
  }
  return Math.round(n).toLocaleString('en-US')
}

export const int = (n: number): string => Math.round(n).toLocaleString('en-US')

export function duration(ms: number | null | undefined): string {
  if (ms === null || ms === undefined) return 'n/a'
  return ms >= 1000 ? `${(ms / 1000).toFixed(1)} s` : `${Math.round(ms)} ms`
}

export function durationAxis(ms: number): string {
  if (ms === 0) return '0'
  return ms >= 1000 ? `${+(ms / 1000).toFixed(1)}s` : `${Math.round(ms)}ms`
}

export const percent = (x: number, digits = 1): string => `${(x * 100).toFixed(digits)}%`

/** Bucket labels arrive as naive local time, e.g. "2026-10-07T14:00:00". */
function parts(t: string) {
  const [date, time = '00:00:00'] = t.split('T')
  const [y, m, d] = date.split('-').map(Number)
  const [hh, mm] = time.split(':').map(Number)
  return { y, m, d, hh, mm, weekday: new Date(y, m - 1, d).getDay() }
}

export function bucketTick(t: string, unit: Unit): string {
  const p = parts(t)
  if (unit === 'hour') {
    return p.hh === 0 ? `${MONTHS[p.m - 1]} ${p.d}` : `${String(p.hh).padStart(2, '0')}:00`
  }
  return `${MONTHS[p.m - 1]} ${p.d}`
}

export function bucketTitle(t: string, unit: Unit): string {
  const p = parts(t)
  const day = `${WEEKDAYS[p.weekday]}, ${MONTHS[p.m - 1]} ${p.d}`
  if (unit === 'hour') return `${day}, ${String(p.hh).padStart(2, '0')}:00`
  if (unit === 'week') return `Week of ${MONTHS[p.m - 1]} ${p.d}`
  return day
}

/** "2026-10-07 14:03:09" -> "Oct 7, 14:03" */
export function stamp(ts: string): string {
  const p = parts(ts.replace(' ', 'T'))
  return `${MONTHS[p.m - 1]} ${p.d}, ${String(p.hh).padStart(2, '0')}:${String(p.mm).padStart(2, '0')}`
}
