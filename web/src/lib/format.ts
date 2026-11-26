const rtf = new Intl.RelativeTimeFormat('en', { numeric: 'auto' })
const dateFmt = new Intl.DateTimeFormat('en-US', { month: 'short', day: 'numeric', year: 'numeric' })
const dateTimeFmt = new Intl.DateTimeFormat('en-US', {
  month: 'short',
  day: 'numeric',
  hour: 'numeric',
  minute: '2-digit',
})
const money = new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 0 })
const cents = new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', minimumFractionDigits: 2 })

export function formatRelative(iso: string, now = Date.now()): string {
  const diffSec = Math.round((new Date(iso).getTime() - now) / 1000)
  const abs = Math.abs(diffSec)
  if (abs < 60) return 'just now'
  if (abs < 3600) return rtf.format(Math.round(diffSec / 60), 'minute')
  if (abs < 86400) return rtf.format(Math.round(diffSec / 3600), 'hour')
  if (abs < 86400 * 14) return rtf.format(Math.round(diffSec / 86400), 'day')
  return dateFmt.format(new Date(iso))
}

export const formatDate = (iso: string) => dateFmt.format(new Date(iso))
export const formatDateTime = (iso: string) => dateTimeFmt.format(new Date(iso))
export const formatUsd = (n: number) => cents.format(n)

export function formatSalary(min: number | null, max: number | null): string | null {
  if (min === null && max === null) return null
  if (min !== null && max !== null) return `${money.format(min)}–${money.format(max)}`
  return min !== null ? `from ${money.format(min)}` : `up to ${money.format(max as number)}`
}

const STATES: Record<string, string> = { massachusetts: 'MA', 'new york': 'NY', 'new hampshire': 'NH', 'rhode island': 'RI' }

/**
 * Compact location for lists: "25 Buick St, Administrative Offices, Boston, Massachusetts, United States"
 * → "Boston, MA"; several locations → "Boston, MA +1". The job page shows the full text.
 */
export function shortLocation(location: string | null): string {
  if (!location) return '—'
  const all = location.split(';').map((l) => l.trim()).filter(Boolean)
  const first = (all[0] ?? '').replace(/\s*Job Posting Location$/i, '')
  const parts = first.split(',').map((p) => p.trim()).filter((p) => p && !/^(united states|usa|us)$/i.test(p))
  const stateIdx = parts.findIndex((p) => /^[A-Z]{2}$/.test(p) || p.toLowerCase() in STATES)
  let short = first
  if (stateIdx > 0) {
    const state = parts[stateIdx]
    short = `${parts[stateIdx - 1]}, ${STATES[state.toLowerCase()] ?? state}`
  } else if (parts.length > 2) {
    short = parts.slice(-2).join(', ')
  }
  return all.length > 1 ? `${short} +${all.length - 1}` : short
}
