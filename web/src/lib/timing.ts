/**
 * Start dates: when each employer wants someone to begin, read from the posting by the AI
 * (pipeline/src/jobsearch/timing.py). Compared with Settings → "Available from".
 *
 *   start_kind  'date'      the posting names a window (start_from..start_to, either end open)
 *               'asap'      it says immediately / as soon as possible
 *               'unstated'  it doesn't say (most postings: they want someone within weeks)
 *               null        not read yet
 *   term_end    last day of a fixed-term appointment, if the posting gives one
 *
 * Dates are plain YYYY-MM-DD strings, so they compare correctly as strings.
 */
import { useSettings } from './queries'
import type { Job } from './types'

/** Matches the pipeline's Settings.available_from default. */
export const DEFAULT_AVAILABLE_FROM = '2027-06-01'
/** A term that ends within this many days of your start leaves almost no time in the job. */
const TERM_WARNING_DAYS = 90

export type StartFields = Pick<Job, 'start_kind' | 'start_from' | 'start_to' | 'term_end' | 'start_note'>
export type StartFit = 'after' | 'before' | 'asap' | 'unstated' | 'unknown'

export function useAvailableFrom(): string {
  const { data } = useSettings()
  return data?.available_from || DEFAULT_AVAILABLE_FROM
}

const parse = (d: string) => {
  const [y, m, day] = d.split('-').map(Number)
  return new Date(y, m - 1, day)
}
const iso = (d: Date) =>
  `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
const addDays = (d: string, n: number) => {
  const x = parse(d)
  x.setDate(x.getDate() + n)
  return iso(x)
}

const monthYear = new Intl.DateTimeFormat('en-US', { month: 'short', year: 'numeric' })
const month = new Intl.DateTimeFormat('en-US', { month: 'short' })
const fullDate = new Intl.DateTimeFormat('en-US', { month: 'short', day: 'numeric', year: 'numeric' })

const isFirstOfMonth = (d: string) => d.endsWith('-01')
const isLastOfMonth = (d: string) => addDays(d, 1).endsWith('-01')

/** "Jun 30, 2027" */
export const formatDay = (d: string) => fullDate.format(parse(d))

/** One end of a window: "Jun 2027" when it's a whole-month boundary, else "Jun 15, 2027". */
const formatEnd = (d: string, monthBoundary: boolean) => (monthBoundary ? monthYear : fullDate).format(parse(d))

/** "Jun – Aug 2027", "Jun 2027", "Jun 15, 2027", "From Sep 2027", "By Mar 2027", "Immediately", "Not stated". */
export function startWindowLabel(j: StartFields): string {
  if (j.start_kind === 'asap') return 'Immediately'
  if (j.start_kind === 'unstated') return 'Not stated'
  if (j.start_kind !== 'date') return '—'
  const { start_from: from, start_to: to } = j
  if (from && to) {
    if (from === to) return formatDay(from)
    const whole = isFirstOfMonth(from) && isLastOfMonth(to)
    if (!whole) return `${formatDay(from)} – ${formatDay(to)}`
    const a = parse(from)
    const b = parse(to)
    if (a.getFullYear() === b.getFullYear() && a.getMonth() === b.getMonth()) return monthYear.format(a)
    if (a.getFullYear() === b.getFullYear()) return `${month.format(a)} – ${monthYear.format(b)}`
    return `${monthYear.format(a)} – ${monthYear.format(b)}`
  }
  if (from) return `From ${formatEnd(from, isFirstOfMonth(from))}`
  if (to) return `By ${formatEnd(to, isLastOfMonth(to))}`
  return 'Not stated'
}

/** Does the stated window reach the day you can start? */
export function startFit(j: StartFields, availableFrom: string): StartFit {
  switch (j.start_kind) {
    case 'date': {
      const end = j.start_to ?? j.start_from
      if (!end) return 'unstated'
      return end >= availableFrom ? 'after' : 'before'
    }
    case 'asap':
      return 'asap'
    case 'unstated':
      return 'unstated'
    default:
      return 'unknown'
  }
}

/** A fixed term that ends before, or within ~3 months of, the day you can start. */
export function termEndsSoon(j: StartFields, availableFrom: string): boolean {
  return j.term_end !== null && j.term_end < addDays(availableFrom, TERM_WARNING_DAYS)
}

const RANK: Record<StartFit, number> = { after: 0, unstated: 1, asap: 2, before: 3, unknown: 4 }

/**
 * Sort key, best timing first: after graduation (earliest start first), then not stated,
 * then immediately, then too early; a term that ends too soon sinks to the bottom of its group.
 */
export function startSortKey(j: StartFields, availableFrom: string): string {
  const rank = RANK[startFit(j, availableFrom)] * 2 + (termEndsSoon(j, availableFrom) ? 1 : 0)
  return `${rank}:${j.start_from ?? j.start_to ?? '9999-12-31'}`
}

/** Phone rows: one short line, only when the posting says something about timing. */
export function startLine(j: StartFields, availableFrom: string): string | null {
  if (j.start_kind === 'date') return `Starts ${startWindowLabel(j)}`
  if (j.start_kind === 'asap') return 'Starts immediately'
  if (j.term_end && !termEndsSoon(j, availableFrom)) return `Term ends ${formatDay(j.term_end)}`
  return null
}
