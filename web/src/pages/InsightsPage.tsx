/**
 * Insights: what kinds of jobs the search finds, and how far each one gets.
 * Charts are plain HTML/CSS (no chart library) and follow the dataviz rules: bars <= 24px
 * with a 4px rounded data end and 2px gaps, text in text colors (never the series color),
 * a legend for 2+ series, hover/focus tooltips (value first), and a table view per chart.
 */
import { ChartColumn } from 'lucide-react'
import { useMemo, useState, type ReactNode } from 'react'
import { Link } from 'react-router'
import { EmptyState, PageHeader } from '@/components/EmptyState'
import { StatTile } from '@/components/StatTile'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import {
  agencyShare,
  bySource,
  byStart,
  byTrack,
  byWorkSetup,
  fitBins,
  funnel,
  headline,
  inRange,
  isMatch,
  matchesOverTime,
  pct,
  RANGES,
  topEmployers,
  TRACKS,
  useInsightJobs,
  type Part,
  type RangeKey,
  type StartBreakdown,
} from '@/lib/insights'
import { useSettings } from '@/lib/queries'
import { TRACK_LABEL, TRACK_SWATCH } from '@/lib/status'
import { formatDay, useAvailableFrom } from '@/lib/timing'
import type { JobTrack } from '@/lib/types'
import { cn } from '@/lib/utils'

// ---------- Shared chart pieces ----------

interface TableData {
  columns: string[]
  rows: (string | number)[][]
}

/** A chart in a flat card, with a "Show as table" toggle (the table view is the accessible fallback). */
function ChartCard({
  title,
  subtitle,
  table,
  className,
  children,
}: {
  title: string
  subtitle?: string
  table: TableData
  className?: string
  children: ReactNode
}) {
  const [asTable, setAsTable] = useState(false)
  return (
    <section className={cn('flex min-w-0 flex-col gap-4 rounded-lg border bg-card p-5', className)} aria-label={title}>
      <div className="flex items-start justify-between gap-3">
        <div>
          <h3 className="text-sm font-semibold">{title}</h3>
          {subtitle && <p className="text-xs text-muted-foreground">{subtitle}</p>}
        </div>
        <Button variant="ghost" size="sm" aria-pressed={asTable} onClick={() => setAsTable((v) => !v)}>
          {asTable ? 'Show chart' : 'Show as table'}
        </Button>
      </div>
      {asTable ? (
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b text-left text-xs text-muted-foreground">
              {table.columns.map((c, i) => (
                <th key={c} className={cn('py-1.5 font-medium', i > 0 && 'text-right')}>
                  {c}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {table.rows.map((r) => (
              <tr key={String(r[0])} className="border-b last:border-0">
                {r.map((v, i) => (
                  <td key={i} className={cn('py-1.5', i > 0 && 'text-right tabular-nums')}>
                    {v}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      ) : (
        children
      )}
    </section>
  )
}

/** Hover/focus readout: the value leads, the label follows. */
function Tip({ label, children, content }: { label: string; children: ReactNode; content: ReactNode }) {
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <button type="button" aria-label={label} className="block h-full w-full cursor-default rounded-sm">
          {children}
        </button>
      </TooltipTrigger>
      <TooltipContent side="top">{content}</TooltipContent>
    </Tooltip>
  )
}

/** Ranked horizontal bars: label, bar from a shared baseline, value at the tip. */
function RankedBars({
  parts,
  colorOf,
  labelWidth = 'w-32 sm:w-36',
  unit = ['match', 'matches'],
}: {
  parts: (Part & { note?: string })[]
  colorOf: (p: Part) => string
  labelWidth?: string
  /** Singular and plural, for the tooltip ("1 match", "3 matches"). */
  unit?: [string, string]
}) {
  const max = Math.max(1, ...parts.map((p) => p.count))
  if (!parts.length) return <p className="text-sm text-muted-foreground">No matches in this range yet.</p>
  return (
    <ul className="flex flex-col gap-2.5">
      {parts.map((p) => (
        <li key={p.key} className="flex items-center gap-3">
          <span className={cn('shrink-0 truncate text-sm', labelWidth)} title={p.label}>
            {p.label}
            {p.note && <span className="text-muted-foreground"> {p.note}</span>}
          </span>
          <span className="h-5 min-w-0 flex-1">
            <Tip label={`${p.label}: ${p.count} ${unit[p.count === 1 ? 0 : 1]}`} content={`${p.count} ${unit[p.count === 1 ? 0 : 1]} · ${p.label}`}>
              <span
                className={cn('block h-5 rounded-r-sm transition-opacity hover:opacity-85', colorOf(p))}
                style={{ width: `${Math.max((p.count / max) * 100, p.count ? 1.5 : 0)}%` }}
              />
            </Tip>
          </span>
          <span className="w-8 shrink-0 text-right text-sm font-medium tabular-nums">{p.count}</span>
        </li>
      ))}
    </ul>
  )
}

function Meter({ value, label }: { value: number; label: string }) {
  return (
    <div
      role="meter"
      aria-label={label}
      aria-valuemin={0}
      aria-valuemax={100}
      aria-valuenow={Math.round(value * 100)}
      className="h-2 w-full overflow-hidden rounded-full bg-chart-1/20"
    >
      <div className="h-full rounded-full bg-chart-1" style={{ width: `${Math.min(value, 1) * 100}%` }} />
    </div>
  )
}

/** Clean axis maximum (2, 4, 6, 10, 20, 50, …) and its three ticks. */
function niceTicks(max: number): number[] {
  const steps = [2, 4, 6, 8, 10, 20, 30, 40, 50, 100, 200, 500, 1000]
  const top = steps.find((s) => s >= max) ?? Math.ceil(max / 1000) * 1000
  return [0, top / 2, top]
}

// ---------- Charts ----------

/** Emphasis form: every step in the soft blue, "Applied" (the headline figure) in the strong blue. */
function Funnel({ stages }: { stages: ReturnType<typeof funnel> }) {
  const max = Math.max(1, stages[0]?.count ?? 1)
  return (
    <ul className="flex flex-col gap-2.5">
      {stages.map((s) => (
        <li key={s.label} className="grid grid-cols-[minmax(0,9rem)_1fr_auto] items-center gap-3 sm:grid-cols-[11rem_1fr_3rem_10rem]">
          <span className="truncate text-sm">{s.label}</span>
          <span className="h-5 min-w-0">
            <Tip
              label={`${s.label}: ${s.count}${s.share !== null ? `, ${pct(s.share)} of the step before` : ''}`}
              content={`${s.count} · ${s.label}`}
            >
              <span
                className={cn('block h-5 rounded-r-sm', s.label === 'Applied' ? 'bg-chart-1' : 'bg-chart-soft')}
                style={{ width: `${Math.max((s.count / max) * 100, s.count ? 1 : 0)}%` }}
              />
            </Tip>
          </span>
          <span className="text-right text-sm font-medium tabular-nums">{s.count}</span>
          <span className="col-span-3 -mt-1 text-xs text-muted-foreground sm:col-span-1 sm:mt-0">
            {s.share !== null ? `${pct(s.share)} of the step before` : ''}
          </span>
        </li>
      ))}
    </ul>
  )
}

function WorkSetup({ parts }: { parts: Part[] }) {
  const total = parts.reduce((a, p) => a + p.count, 0)
  const color: Record<string, string> = { onsite: 'bg-chart-1', hybrid: 'bg-chart-2', remote: 'bg-chart-3', unknown: 'bg-chart-muted' }
  if (!total) return <p className="text-sm text-muted-foreground">No matches in this range yet.</p>
  const shown = parts.filter((p) => p.count > 0)
  return (
    <div className="flex flex-col gap-3">
      <div className="flex h-7 gap-0.5" role="img" aria-label={shown.map((p) => `${p.label} ${p.count}`).join(', ')}>
        {shown.map((p) => {
          const share = p.count / total
          return (
            <div key={p.key} className="h-full" style={{ width: `${share * 100}%` }}>
              <Tip label={`${p.label}: ${p.count} (${pct(share)})`} content={`${pct(share)} · ${p.label} (${p.count})`}>
                <span className={cn('flex h-7 items-center rounded-sm px-2 text-xs font-medium', color[p.key], p.key === 'unknown' ? 'text-foreground' : 'text-white')}>
                  {share >= 0.12 ? pct(share) : ''}
                </span>
              </Tip>
            </div>
          )
        })}
      </div>
      <ul className="flex flex-wrap gap-x-4 gap-y-1.5">
        {parts.map((p) => (
          <li key={p.key} className="flex items-center gap-1.5 text-xs text-muted-foreground">
            <span aria-hidden="true" className={cn('size-2.5 rounded-[2px]', color[p.key])} />
            {p.label} {p.count}
          </li>
        ))}
      </ul>
    </div>
  )
}

/**
 * When matches start, in a fixed order (best timing first). Emphasis form, like the funnel:
 * "After graduation" (the jobs whose timing fits) in the strong blue, the rest in the soft blue.
 */
function StartChart({ data, availableFrom }: { data: StartBreakdown; availableFrom: string }) {
  if (!data.total) return <p className="text-sm text-muted-foreground">No matches in this range yet.</p>
  const after = data.parts.find((p) => p.key === 'after')?.count ?? 0
  const colorOf = (p: Part) => (p.key === 'after' ? 'bg-chart-1' : p.key === 'unknown' ? 'bg-chart-muted' : 'bg-chart-soft')
  return (
    <div className="flex flex-col gap-4 lg:grid lg:grid-cols-[15rem_minmax(0,1fr)] lg:gap-8">
      <div className="flex flex-col gap-1">
        <span className="text-lg font-semibold">
          {after} of {data.total}
        </span>
        <span className="text-xs text-muted-foreground">
          matches name a start on or after {formatDay(availableFrom)}, when you're available.
        </span>
        <span className="mt-2 text-xs text-muted-foreground">
          {data.terms
            ? `${data.terms} ${data.terms === 1 ? 'is a fixed-term job' : 'are fixed-term jobs'} with an end date; ${data.termsSoon} ${data.termsSoon === 1 ? 'ends' : 'end'} within 3 months of your start.`
            : 'No fixed-term jobs with an end date in this range.'}
        </span>
      </div>
      <RankedBars parts={data.parts} colorOf={colorOf} labelWidth="w-36 sm:w-40" />
    </div>
  )
}

function OverTime({ data }: { data: ReturnType<typeof matchesOverTime> }) {
  const { buckets, weekly } = data
  const ticks = niceTicks(Math.max(1, ...buckets.map((b) => b.total)))
  const top = ticks[2]
  const every = Math.max(1, Math.ceil(buckets.length / 5))
  const daysWithData = buckets.filter((b) => b.total > 0).length
  return (
    <div className="flex flex-col gap-3">
      <ul className="flex flex-wrap gap-x-4 gap-y-1.5" aria-label="Legend">
        {TRACKS.map((t) => (
          <li key={t} className="flex items-center gap-1.5 text-xs text-muted-foreground">
            <span aria-hidden="true" className={cn('size-2.5 rounded-[2px]', TRACK_SWATCH[t])} />
            {TRACK_LABEL[t]}
          </li>
        ))}
      </ul>
      <div className="mt-2 grid grid-cols-[1.75rem_1fr] gap-2">
        <div className="relative h-40" aria-hidden="true">
          {ticks.map((t) => (
            <span key={t} className="absolute right-0 -translate-y-1/2 text-xs text-muted-foreground tabular-nums" style={{ bottom: `${(t / top) * 100}%` }}>
              {t}
            </span>
          ))}
        </div>
        <div className="relative h-40">
          {ticks.map((t) => (
            <span
              key={t}
              aria-hidden="true"
              className={cn('absolute inset-x-0 h-px', t === 0 ? 'bg-chart-baseline' : 'bg-chart-grid')}
              style={{ bottom: `${(t / top) * 100}%` }}
            />
          ))}
          <div className="relative flex h-full items-end">
            {buckets.map((b) => {
              const parts = TRACKS.filter((t) => b.counts[t] > 0)
              const summary = TRACKS.map((t) => `${b.counts[t]} ${TRACK_LABEL[t]}`).join(', ')
              return (
                <div key={b.start.toISOString()} className="h-full min-w-0 flex-1 px-px">
                  <Tooltip>
                    <TooltipTrigger asChild>
                      <button
                        type="button"
                        aria-label={`${b.label}: ${b.total} ${b.total === 1 ? 'match' : 'matches'} (${summary})`}
                        className="flex h-full w-full cursor-default flex-col-reverse items-center gap-0.5 rounded-sm transition-colors hover:bg-hover"
                      >
                        {parts.map((t, i) => (
                          <span
                            key={t}
                            className={cn('w-full max-w-6', TRACK_SWATCH[t], i === parts.length - 1 && 'rounded-t-sm')}
                            style={{ height: `calc(${(b.counts[t] / top) * 100}% - 2px)` }}
                          />
                        ))}
                      </button>
                    </TooltipTrigger>
                    <TooltipContent side="top" className="flex-col items-start gap-1">
                      <span className="font-medium">
                        {b.total} {b.total === 1 ? 'match' : 'matches'} · {b.label}
                      </span>
                      {TRACKS.map((t: JobTrack) => (
                        <span key={t} className="flex items-center gap-2">
                          <span aria-hidden="true" className={cn('h-0.5 w-3', TRACK_SWATCH[t])} />
                          <span className="font-medium tabular-nums">{b.counts[t]}</span> {TRACK_LABEL[t]}
                        </span>
                      ))}
                    </TooltipContent>
                  </Tooltip>
                </div>
              )
            })}
          </div>
        </div>
        <span />
        <div className="relative h-4" aria-hidden="true">
          {buckets.map((b, i) =>
            i % every === 0 ? (
              <span
                key={b.label}
                className="absolute -translate-x-1/2 text-xs whitespace-nowrap text-muted-foreground"
                style={{ left: `${((i + 0.5) / buckets.length) * 100}%` }}
              >
                {weekly ? b.label.replace('Week of ', '') : b.label}
              </span>
            ) : null,
          )}
        </div>
      </div>
      {daysWithData < 5 && (
        <p className="text-xs text-muted-foreground">This fills in as the daily search runs each morning.</p>
      )}
    </div>
  )
}

function FitHistogram({ bins, threshold }: { bins: ReturnType<typeof fitBins>; threshold: number }) {
  const ticks = niceTicks(Math.max(1, ...bins.map((b) => b.count)))
  const top = ticks[2]
  return (
    <div className="grid grid-cols-[1.75rem_1fr] gap-2">
      <div className="relative h-36" aria-hidden="true">
        {ticks.map((t) => (
          <span key={t} className="absolute right-0 -translate-y-1/2 text-xs text-muted-foreground tabular-nums" style={{ bottom: `${(t / top) * 100}%` }}>
            {t}
          </span>
        ))}
      </div>
      <div className="relative h-36">
        {ticks.map((t) => (
          <span key={t} aria-hidden="true" className={cn('absolute inset-x-0 h-px', t === 0 ? 'bg-chart-baseline' : 'bg-chart-grid')} style={{ bottom: `${(t / top) * 100}%` }} />
        ))}
        <div className="relative flex h-full items-end">
          {bins.map((b) => (
            <div key={b.from} className="flex h-full min-w-0 flex-1 justify-center px-0.5">
              <Tip label={`Fit ${b.from}–${b.to}: ${b.count} jobs`} content={`${b.count} jobs · fit ${b.from}–${b.to}`}>
                <span className="flex h-full items-end justify-center">
                  <span
                    className={cn('w-full max-w-6 rounded-t-sm', b.from >= threshold ? 'bg-chart-1' : 'bg-chart-muted')}
                    style={{ height: `${(b.count / top) * 100}%` }}
                  />
                </span>
              </Tip>
            </div>
          ))}
        </div>
        <span aria-hidden="true" className="absolute -top-5 bottom-0 w-px bg-muted-foreground" style={{ left: `${threshold}%` }} />
        <span className="absolute -top-6 ml-1.5 text-xs font-medium whitespace-nowrap" style={{ left: `${threshold}%` }}>
          Your threshold: {threshold}
        </span>
      </div>
      <span />
      <div className="relative h-4 text-xs text-muted-foreground" aria-hidden="true">
        {[0, threshold, 100].map((x) => (
          <span key={x} className="absolute -translate-x-1/2 tabular-nums" style={{ left: `${x}%` }}>
            {x}
          </span>
        ))}
      </div>
    </div>
  )
}

// ---------- Page ----------

function RangePicker({ value, onChange }: { value: RangeKey; onChange: (r: RangeKey) => void }) {
  return (
    <div role="radiogroup" aria-label="Date range" className="mb-6 inline-flex w-full rounded-md border p-0.5 sm:w-auto">
      {RANGES.map((r) => {
        const active = r.key === value
        return (
          <button
            key={r.key}
            type="button"
            role="radio"
            aria-checked={active}
            onClick={() => onChange(r.key)}
            className={cn(
              'flex-1 rounded-sm px-3 py-1.5 text-sm whitespace-nowrap transition-colors duration-150 sm:flex-none pointer-coarse:min-h-11',
              active ? 'bg-hover-strong font-medium text-foreground' : 'text-muted-foreground hover:text-foreground',
            )}
          >
            <span className="sm:hidden">{r.short}</span>
            <span className="hidden sm:inline">{r.label}</span>
          </button>
        )
      })}
    </div>
  )
}

export function InsightsPage() {
  const { data: allJobs, isLoading, isFetching, error } = useInsightJobs()
  const { data: settings } = useSettings()
  const threshold = settings?.fit_threshold ?? 50
  const availableFrom = useAvailableFrom()
  const [range, setRange] = useState<RangeKey>('30')
  const rangeLabel = RANGES.find((r) => r.key === range)?.label.toLowerCase() ?? ''

  const view = useMemo(() => {
    const jobs = inRange(allJobs ?? [], range)
    const matches = jobs.filter(isMatch)
    return {
      jobs,
      matches,
      head: headline(jobs),
      stages: funnel(jobs, threshold),
      tracks: byTrack(matches),
      sources: bySource(matches),
      setup: byWorkSetup(matches),
      agency: agencyShare(matches),
      start: byStart(matches, availableFrom),
      time: matchesOverTime(matches, range),
      bins: fitBins(jobs),
      employers: topEmployers(matches),
    }
  }, [allJobs, range, threshold, availableFrom])

  const header = (
    <PageHeader
      icon={ChartColumn}
      title="Insights"
      description="How the search is going: what kinds of jobs it finds, and how far each one gets."
    />
  )

  if (isLoading) {
    return (
      <>
        {header}
        <div className="flex flex-col gap-6" aria-busy="true" aria-label="Loading insights">
          <Skeleton className="h-9 w-80" />
          <div className="grid gap-4 lg:grid-cols-4">
            {Array.from({ length: 4 }, (_, i) => (
              <Skeleton key={i} className="h-32" />
            ))}
          </div>
          <Skeleton className="h-72" />
        </div>
      </>
    )
  }
  if (error) {
    return (
      <>
        {header}
        <p role="alert" className="text-sm text-destructive">
          Couldn't load insights: {(error as Error).message}
        </p>
      </>
    )
  }
  if (!allJobs?.length) {
    return (
      <>
        {header}
        <EmptyState
          icon={ChartColumn}
          title="No data yet"
          action={
            <Button asChild variant="outline">
              <Link to="/add">Add a job</Link>
            </Button>
          }
        >
          Charts appear once the daily search has found some jobs.
        </EmptyState>
      </>
    )
  }

  const { head, stages, tracks, sources, setup, agency, start, time, bins, employers, jobs } = view
  const trackColor = (p: Part) => TRACK_SWATCH[p.key as JobTrack] ?? 'bg-chart-muted'

  return (
    <>
      {header}
      <RangePicker value={range} onChange={setRange} />

      <div className={cn('flex flex-col gap-8 transition-opacity duration-200', isFetching && 'opacity-60')}>
        {/* Headline numbers: % applied is the one hero figure. */}
        <section aria-label="Headline numbers" className="grid grid-cols-3 gap-3 lg:grid-cols-[minmax(0,1.35fr)_repeat(3,minmax(0,1fr))] lg:gap-4">
          <div className="col-span-3 flex flex-col gap-1.5 rounded-lg border bg-card p-4 lg:col-span-1">
            <span className="text-sm text-muted-foreground">% applied</span>
            <span className="text-5xl leading-[3.5rem] font-semibold tracking-tight">{pct(head.pctApplied)}</span>
            <Meter value={head.pctApplied ?? 0} label="Share of matches you've applied to" />
            <span className="text-xs text-muted-foreground">
              {head.applied} of {head.matches} matches in the {rangeLabel}
            </span>
          </div>
          <StatTile label="Matches" value={head.matches} note={`${head.passed} passed the filters`} />
          <StatTile label="Applied" value={head.applied} note={`${head.applied - head.heardBack} waiting on a reply`} />
          <StatTile label="Heard back" value={pct(head.pctHeardBack)} note={`${head.heardBack} of ${head.applied} applications`} />
        </section>

        <ChartCard
          title="From search to offer"
          subtitle={`Jobs found in the ${rangeLabel}, and the share that made it from the step before`}
          table={{ columns: ['Step', 'Jobs', 'Share of step before'], rows: stages.map((s) => [s.label, s.count, s.share === null ? '—' : pct(s.share)]) }}
        >
          <Funnel stages={stages} />
        </ChartCard>

        <section aria-labelledby="kinds-title" className="flex flex-col gap-4">
          <h2 id="kinds-title" className="text-lg font-semibold tracking-tight">
            What kinds of jobs
          </h2>
          <div className="grid gap-4 md:grid-cols-2">
            <ChartCard title="Role type" subtitle="Matches by track" table={{ columns: ['Role type', 'Matches'], rows: tracks.map((p) => [TRACK_LABEL[p.key as JobTrack] ?? p.key, p.count]) }}>
              <RankedBars parts={tracks.map((p) => ({ ...p, label: TRACK_LABEL[p.key as JobTrack] ?? p.key }))} colorOf={trackColor} />
            </ChartCard>
            <ChartCard title="Where they were found" subtitle="Matches by source" table={{ columns: ['Source', 'Matches'], rows: sources.map((p) => [p.label, p.count]) }}>
              <RankedBars parts={sources} colorOf={() => 'bg-chart-1'} />
            </ChartCard>
            <ChartCard title="Work setup" subtitle="On-site, hybrid, or remote" table={{ columns: ['Work setup', 'Matches'], rows: setup.map((p) => [p.label, p.count]) }}>
              <WorkSetup parts={setup} />
            </ChartCard>
            <ChartCard
              title="Staffing agencies"
              subtitle="Matches posted by an agency for another employer"
              table={{ columns: ['', 'Matches'], rows: [['From staffing agencies', agency.count], ['From employers directly', agency.total - agency.count]] }}
            >
              <div className="flex flex-col gap-2">
                <span className="text-lg font-semibold">{pct(agency.total ? agency.count / agency.total : null)}</span>
                <Meter value={agency.total ? agency.count / agency.total : 0} label="Share of matches from staffing agencies" />
                <span className="text-xs text-muted-foreground">
                  {agency.count} of {agency.total} matches. Their documents are written after direct employers’.
                </span>
              </div>
            </ChartCard>
            <ChartCard
              className="md:col-span-2"
              title="When they start"
              subtitle="Matches by the start date in the posting. Most don't say; those employers usually want someone within weeks."
              table={{
                columns: ['Start', 'Matches', 'Share'],
                rows: [
                  ...start.parts.map((p) => [p.label, p.count, pct(start.total ? p.count / start.total : null)]),
                  ['Fixed-term, with an end date', start.terms, pct(start.total ? start.terms / start.total : null)],
                  ['…ending within 3 months of your start', start.termsSoon, pct(start.total ? start.termsSoon / start.total : null)],
                ],
              }}
            >
              <StartChart data={start} availableFrom={availableFrom} />
            </ChartCard>
          </div>
        </section>

        <ChartCard
          title={time.weekly ? 'New matches per week' : 'New matches per day'}
          subtitle={`${RANGES.find((r) => r.key === range)?.label}, by role type`}
          table={{ columns: [time.weekly ? 'Week' : 'Day', ...TRACKS.map((t) => TRACK_LABEL[t]), 'Total'], rows: time.buckets.map((b) => [b.label, ...TRACKS.map((t) => b.counts[t]), b.total]) }}
        >
          <OverTime data={time} />
        </ChartCard>

        <div className="grid gap-4 md:grid-cols-2">
          <ChartCard
            title="Fit scores"
            subtitle={`Scored jobs found in the ${rangeLabel}`}
            table={{ columns: ['Fit', 'Jobs'], rows: bins.map((b) => [`${b.from}–${b.to}`, b.count]) }}
          >
            <div className="flex flex-col gap-3 pt-6">
              <FitHistogram bins={bins} threshold={threshold} />
              <p className="text-xs text-muted-foreground">
                {bins.filter((b) => b.from >= threshold).reduce((a, b) => a + b.count, 0)} of{' '}
                {jobs.filter((j) => j.fit_score !== null).length} scored jobs reached your threshold.
              </p>
            </div>
          </ChartCard>
          <ChartCard
            title="Top employers"
            subtitle={`Most matches, ${rangeLabel}`}
            table={{ columns: ['Employer', 'Matches'], rows: employers.map((e) => [e.agency ? `${e.label} (staffing agency)` : e.label, e.count]) }}
          >
            <RankedBars
              parts={employers.map((e) => ({ ...e, note: e.agency ? '(agency)' : undefined }))}
              colorOf={() => 'bg-chart-1'}
              labelWidth="w-40 sm:w-48"
            />
          </ChartCard>
        </div>
      </div>
    </>
  )
}
