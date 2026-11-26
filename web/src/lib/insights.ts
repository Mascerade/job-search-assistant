/**
 * Numbers for the Insights page and Today's headline row. One set of definitions so the
 * two pages always agree:
 *   - match:      fit >= threshold (scored / needs_approval / tailoring / ready), a job you
 *                 added yourself, or any job whose status you've moved past New
 *   - applied:    applied_at is set (the database stamps it when the status becomes Applied)
 *   - heard back: applied, and now Interviewing, Offer, or Rejected
 * Date ranges are cohorts: jobs *found* in the range (first_seen_at), followed to today.
 */
import { keepPreviousData, useQuery } from '@tanstack/react-query'
import { keys } from './queries'
import { supabase } from './supabase'
import type { ApplicationStatus, Job, JobTrack } from './types'

export type InsightJob = Pick<
  Job,
  | 'id'
  | 'track'
  | 'source'
  | 'status'
  | 'pipeline_state'
  | 'fit_score'
  | 'first_seen_at'
  | 'applied_at'
  | 'remote_type'
  | 'company'
  | 'tags'
  | 'closed_at'
>

const COLUMNS =
  'id, track, source, status, pipeline_state, fit_score, first_seen_at, applied_at, remote_type, company, tags, closed_at'
const PAGE = 1000

/** Every job, light columns only (no descriptions), paged so it never stops at 1,000 rows. */
export function useInsightJobs() {
  return useQuery({
    queryKey: [...keys.jobs, 'insights'] as const,
    queryFn: async () => {
      const all: InsightJob[] = []
      for (let from = 0; ; from += PAGE) {
        const { data, error } = await supabase
          .from('jobs')
          .select(COLUMNS)
          .order('first_seen_at', { ascending: false })
          .range(from, from + PAGE - 1)
        if (error) throw new Error(error.message)
        all.push(...(data ?? []))
        if (!data || data.length < PAGE) break
      }
      return all
    },
    placeholderData: keepPreviousData, // a refetch keeps the old charts on screen
  })
}

// ---------- Definitions ----------

const MATCH_STATES = new Set(['scored', 'needs_approval', 'tailoring', 'ready'])
const ACTED_ON = new Set<ApplicationStatus>(['docs_ready', 'applied', 'interviewing', 'offer', 'rejected', 'withdrawn'])
const HEARD_BACK = new Set<ApplicationStatus>(['interviewing', 'offer', 'rejected'])
const AGGREGATOR_NAMES: Partial<Record<Job['source'], string>> = {
  adzuna: 'Adzuna',
  jsearch: 'JSearch',
  higheredjobs: 'HigherEdJobs',
}
export const STAFFING_TAG = 'staffing-agency'

type J = Pick<InsightJob, 'source' | 'status' | 'pipeline_state' | 'applied_at'>
export const isMatch = (j: J) => j.source === 'manual' || MATCH_STATES.has(j.pipeline_state) || ACTED_ON.has(j.status)
export const isApplied = (j: J) => j.applied_at !== null
export const heardBack = (j: J) => isApplied(j) && HEARD_BACK.has(j.status)

export function sourceGroup(source: Job['source']): string {
  if (source === 'manual') return 'Added by you'
  return AGGREGATOR_NAMES[source] ?? 'Employer sites'
}

// ---------- Ranges ----------

export type RangeKey = '7' | '30' | '90' | 'all'
export const RANGES: { key: RangeKey; label: string; short: string }[] = [
  { key: '7', label: 'Last 7 days', short: '7 days' },
  { key: '30', label: 'Last 30 days', short: '30 days' },
  { key: '90', label: 'Last 90 days', short: '90 days' },
  { key: 'all', label: 'All time', short: 'All' },
]
const DAY = 86_400_000

export function inRange<T extends Pick<InsightJob, 'first_seen_at'>>(jobs: T[], range: RangeKey, now = Date.now()): T[] {
  if (range === 'all') return jobs
  const since = now - Number(range) * DAY
  return jobs.filter((j) => new Date(j.first_seen_at).getTime() >= since)
}

// ---------- Aggregates ----------

export interface Headline {
  matches: number
  passed: number
  docsReady: number
  applied: number
  heardBack: number
  pctApplied: number | null
  pctHeardBack: number | null
}

export function headline(jobs: InsightJob[]): Headline {
  const matches = jobs.filter(isMatch)
  const applied = jobs.filter(isApplied)
  const heard = applied.filter(heardBack)
  return {
    matches: matches.length,
    passed: jobs.filter((j) => j.pipeline_state !== 'filtered_out').length,
    docsReady: jobs.filter((j) => j.pipeline_state === 'ready').length,
    applied: applied.length,
    heardBack: heard.length,
    pctApplied: matches.length ? applied.length / matches.length : null,
    pctHeardBack: applied.length ? heard.length / applied.length : null,
  }
}

export interface Stage {
  label: string
  count: number
  /** Share of the stage before (null for the first stage, or when the one before is 0). */
  share: number | null
}

export function funnel(jobs: InsightJob[], threshold: number): Stage[] {
  const counts: [string, number][] = [
    ['Saved by the search', jobs.length],
    ['Passed the filters', jobs.filter((j) => j.pipeline_state !== 'filtered_out').length],
    [`Matched (fit ≥ ${threshold})`, jobs.filter(isMatch).length],
    ['Documents ready', jobs.filter((j) => j.pipeline_state === 'ready').length],
    ['Applied', jobs.filter(isApplied).length],
    ['Heard back', jobs.filter(heardBack).length],
    ['Offer', jobs.filter((j) => j.status === 'offer').length],
  ]
  return counts.map(([label, count], i) => {
    const prev = i ? counts[i - 1][1] : 0
    return { label, count, share: i && prev ? count / prev : null }
  })
}

export interface Part {
  key: string
  label: string
  count: number
}

const byCount = (a: Part, b: Part) => b.count - a.count

function countBy<T>(items: T[], keyOf: (t: T) => string, labelOf: (k: string) => string = (k) => k): Part[] {
  const m = new Map<string, number>()
  for (const t of items) m.set(keyOf(t), (m.get(keyOf(t)) ?? 0) + 1)
  return [...m.entries()].map(([key, count]) => ({ key, label: labelOf(key), count }))
}

export const TRACKS: JobTrack[] = ['software', 'hybrid', 'program_admin']

export function byTrack(matches: InsightJob[]): Part[] {
  return countBy(matches.filter((j) => j.track), (j) => j.track as string).sort(byCount)
}

export function bySource(matches: InsightJob[]): Part[] {
  return countBy(matches, (j) => sourceGroup(j.source)).sort(byCount)
}

/** On-site / hybrid / remote / unknown, in that fixed order (a part-to-whole bar). */
export function byWorkSetup(matches: InsightJob[]): Part[] {
  const order: [string, string][] = [
    ['onsite', 'On-site'],
    ['hybrid', 'Hybrid'],
    ['remote', 'Remote'],
    ['unknown', 'Unknown'],
  ]
  const counts = countBy(matches, (j) => j.remote_type ?? 'unknown')
  return order.map(([key, label]) => ({ key, label, count: counts.find((c) => c.key === key)?.count ?? 0 }))
}

export function agencyShare(matches: InsightJob[]): { count: number; total: number } {
  return { count: matches.filter((j) => j.tags.includes(STAFFING_TAG)).length, total: matches.length }
}

export interface Employer extends Part {
  agency: boolean
}

export function topEmployers(matches: InsightJob[], n = 8): Employer[] {
  return countBy(matches, (j) => j.company)
    .sort((a, b) => byCount(a, b) || a.label.localeCompare(b.label))
    .slice(0, n)
    .map((p) => ({
      ...p,
      agency: matches.some((j) => j.company === p.key && j.tags.includes(STAFFING_TAG)),
    }))
}

export interface Bin {
  from: number
  to: number
  count: number
}

/** Fit scores in 10-point bins (90–100 includes 100). */
export function fitBins(jobs: InsightJob[]): Bin[] {
  const bins: Bin[] = Array.from({ length: 10 }, (_, i) => ({ from: i * 10, to: i * 10 + 10, count: 0 }))
  for (const j of jobs) if (j.fit_score !== null) bins[Math.min(9, Math.floor(j.fit_score / 10))].count += 1
  return bins
}

export interface Bucket {
  /** Start of the day or week, local time. */
  start: Date
  label: string
  counts: Record<JobTrack, number>
  total: number
}

const startOfDay = (d: Date) => new Date(d.getFullYear(), d.getMonth(), d.getDate())
const dayLabel = new Intl.DateTimeFormat('en-US', { month: 'short', day: 'numeric' })

/** New matches per day (or per week when the range is longer than 45 days), stacked by track. */
export function matchesOverTime(matches: InsightJob[], range: RangeKey, now = new Date()): { weekly: boolean; buckets: Bucket[] } {
  const today = startOfDay(now)
  const earliest = matches.reduce((min, j) => Math.min(min, new Date(j.first_seen_at).getTime()), today.getTime())
  const days = range === 'all' ? Math.max(1, Math.ceil((today.getTime() - startOfDay(new Date(earliest)).getTime()) / DAY) + 1) : Number(range)
  const weekly = days > 45
  const size = weekly ? 7 : 1
  const n = Math.ceil(days / size)
  const first = new Date(today.getTime() - (n * size - 1) * DAY)
  const buckets: Bucket[] = Array.from({ length: n }, (_, i) => {
    const start = new Date(first.getTime() + i * size * DAY)
    return {
      start,
      label: weekly ? `Week of ${dayLabel.format(start)}` : dayLabel.format(start),
      counts: { software: 0, hybrid: 0, program_admin: 0 },
      total: 0,
    }
  })
  for (const j of matches) {
    if (!j.track) continue
    const i = Math.floor((startOfDay(new Date(j.first_seen_at)).getTime() - first.getTime()) / (size * DAY))
    if (i < 0 || i >= n) continue
    buckets[i].counts[j.track] += 1
    buckets[i].total += 1
  }
  return { weekly, buckets }
}

export const pct = (x: number | null) => (x === null ? '—' : `${Math.round(x * 100)}%`)
