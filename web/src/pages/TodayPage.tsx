import {
  createColumnHelper,
  createSortedRowModel,
  rowSortingFeature,
  sortFn_alphanumeric,
  sortFn_basic,
  tableFeatures,
  useTable,
  type SortingState,
} from '@tanstack/react-table'
import {
  ArrowDown,
  ArrowRight,
  ArrowUp,
  ArrowUpDown,
  Calendar,
  CalendarRange,
  CaseSensitive,
  ChevronDown,
  ChevronRight,
  CircleDot,
  Hash,
  Inbox,
  KeyRound,
  Layers,
  MapPin,
  Plus,
  type LucideIcon,
} from 'lucide-react'
import { useMemo, useState } from 'react'
import { Link, useNavigate } from 'react-router'
import { EmptyState, PageHeader } from '@/components/EmptyState'
import { ScoreNowBar } from '@/components/ScoreNowBar'
import { StartCell, StartTags } from '@/components/StartDate'
import { StatTile } from '@/components/StatTile'
import { StatusBadge } from '@/components/StatusBadge'
import { TrackTag } from '@/components/Tag'
import { Button } from '@/components/ui/button'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Skeleton } from '@/components/ui/skeleton'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { formatRelative, shortLocation } from '@/lib/format'
import { headline, inRange, pct } from '@/lib/insights'
import { isAutoRejected, needsReview } from '@/lib/jobs'
import { useJobs, useRuns } from '@/lib/queries'
import { fitLabel, TRACK_LABEL } from '@/lib/status'
import { startLine, startSortKey, useAvailableFrom } from '@/lib/timing'
import type { Job, JobTrack } from '@/lib/types'
import { cn } from '@/lib/utils'

const features = tableFeatures({
  rowSortingFeature,
  sortedRowModel: createSortedRowModel(),
  sortFns: { basic: sortFn_basic, alphanumeric: sortFn_alphanumeric },
})

const helper = createColumnHelper<typeof features, Job>()

const makeColumns = (availableFrom: string) => helper.columns([
  helper.accessor((j) => j.fit_score ?? undefined, {
    id: 'fit_score',
    header: 'Fit',
    sortFn: 'basic',
    sortUndefined: 'last',
    cell: ({ row }) => <FitCell score={row.original.fit_score} />,
  }),
  helper.accessor((j) => `${j.title} ${j.company}`, {
    id: 'role',
    header: 'Role',
    sortFn: 'alphanumeric',
    cell: ({ row }) => (
      <div className="min-w-48">
        <Link
          to={`/jobs/${row.original.id}`}
          className="font-medium text-foreground underline-offset-4 hover:underline"
        >
          {row.original.title}
        </Link>
        <div className="text-xs text-muted-foreground">{row.original.company}</div>
      </div>
    ),
  }),
  helper.accessor((j) => j.location ?? '', {
    id: 'location',
    header: 'Location',
    sortFn: 'alphanumeric',
    cell: ({ row }) => (
      <span className="text-sm text-muted-foreground" title={row.original.location ?? undefined}>
        {shortLocation(row.original.location)}
        {row.original.remote_type && row.original.remote_type !== 'onsite' && (
          <span> · {row.original.remote_type}</span>
        )}
      </span>
    ),
  }),
  helper.accessor((j) => (j.track ? TRACK_LABEL[j.track] : ''), {
    id: 'track',
    header: 'Role type',
    sortFn: 'alphanumeric',
    cell: ({ row }) =>
      row.original.track ? <TrackTag track={row.original.track} /> : <span className="text-muted-foreground">—</span>,
  }),
  // Sorts after-graduation starts first, then not stated, immediately, too early (lib/timing.ts);
  // best fit first within each group.
  helper.accessor((j) => `${startSortKey(j, availableFrom)}:${String(100 - (j.fit_score ?? 0)).padStart(3, '0')}`, {
    id: 'start',
    header: 'Start',
    sortFn: 'basic',
    cell: ({ row }) => <StartCell job={row.original} availableFrom={availableFrom} />,
  }),
  helper.accessor('first_seen_at', {
    header: 'Found',
    sortFn: 'basic',
    cell: ({ row }) => (
      <span className="text-sm whitespace-nowrap text-muted-foreground tabular-nums">
        {formatRelative(row.original.first_seen_at)}
      </span>
    ),
  }),
  helper.accessor('status', {
    header: 'Status',
    enableSorting: false,
    cell: ({ row }) => (
      <span className="flex flex-col items-start gap-1">
        <StatusBadge status={row.original.status} />
        {row.original.pipeline_state === 'needs_approval' && (
          <span className="text-xs font-medium whitespace-nowrap text-warning-text">Review suggestions</span>
        )}
      </span>
    ),
  }),
])

/** Database-style column icons (Notion shows the property type beside each header). */
const COLUMN_ICON: Record<string, LucideIcon> = {
  fit_score: Hash,
  role: CaseSensitive,
  location: MapPin,
  track: Layers,
  start: CalendarRange,
  first_seen_at: Calendar,
  status: CircleDot,
}

/** Fit as a number over its word ("82 / Good"), never color alone. */
function FitCell({ score }: { score: number | null }) {
  if (score === null) return <span className="text-sm text-muted-foreground">—</span>
  return (
    <span className="flex flex-col leading-tight" aria-label={`Fit score ${score} out of 100, ${fitLabel(score)}`}>
      <span className="text-sm font-medium tabular-nums">{score}</span>
      <span className="text-xs text-muted-foreground">{fitLabel(score)}</span>
    </span>
  )
}

/** Last-30-days headline numbers; the same definitions as the Insights page. */
function HeadlineRow({ jobs, rows }: { jobs: Job[]; rows: Job[] }) {
  const h = headline(inRange(jobs, '30'))
  const toReview = rows.filter((j) => j.pipeline_state === 'needs_approval').length
  const ready = jobs.filter((j) => j.pipeline_state === 'ready' && j.status === 'docs_ready' && !j.closed_at).length
  return (
    <section aria-labelledby="headline-title" className="mb-8">
      <div className="mb-3 flex items-center justify-between gap-3">
        <h2 id="headline-title" className="text-lg font-semibold tracking-tight">
          Last 30 days
        </h2>
        <Button asChild variant="ghost" size="sm">
          <Link to="/insights">
            See insights
            <ArrowRight data-icon="inline-end" />
          </Link>
        </Button>
      </div>
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4 lg:gap-4">
        <StatTile label="To review" value={toReview} note="Jobs with suggestions waiting" />
        <StatTile label="Ready to apply" value={ready} note="Resume + cover letter ready" />
        <StatTile label="Applied" value={h.applied} note={`${h.heardBack} heard back`} />
        <StatTile label="% applied" value={pct(h.pctApplied)} note={`${h.applied} of ${h.matches} matches`} />
      </div>
    </section>
  )
}

type View = 'all' | JobTrack
const VIEWS: { key: View; label: string }[] = [
  { key: 'all', label: 'All matches' },
  { key: 'software', label: TRACK_LABEL.software },
  { key: 'hybrid', label: TRACK_LABEL.hybrid },
  { key: 'program_admin', label: TRACK_LABEL.program_admin },
  { key: 'research', label: TRACK_LABEL.research },
]

/** Notion-style view tabs that filter the list by role type. */
function ViewTabs({ rows, view, onChange }: { rows: Job[]; view: View; onChange: (v: View) => void }) {
  return (
    <div role="group" aria-label="Show matches for" className="flex gap-5 overflow-x-auto border-b">
      {VIEWS.map(({ key, label }) => {
        const count = key === 'all' ? rows.length : rows.filter((j) => j.track === key).length
        const active = view === key
        return (
          <button
            key={key}
            type="button"
            aria-pressed={active}
            onClick={() => onChange(key)}
            className={cn(
              '-mb-px flex shrink-0 items-center gap-1.5 border-b-2 pt-1 pb-2.5 text-sm whitespace-nowrap transition-colors duration-150 pointer-coarse:min-h-11',
              active ? 'border-foreground font-medium text-foreground' : 'border-transparent text-muted-foreground hover:text-foreground',
            )}
          >
            {label}
            <span className="text-xs text-muted-foreground tabular-nums">{count}</span>
          </button>
        )
      })}
    </div>
  )
}

type PhoneSort = 'fit' | 'start' | 'newest'
const PHONE_SORTS: Record<PhoneSort, { label: string; sorting: SortingState }> = {
  fit: { label: 'Best fit', sorting: [{ id: 'fit_score', desc: true }] },
  start: { label: 'Start date', sorting: [{ id: 'start', desc: false }] },
  newest: { label: 'Newest', sorting: [{ id: 'first_seen_at', desc: true }] },
}

/** Phones have no column headers to click, so sorting is a menu. */
function PhoneSortMenu({ sorting, onChange }: { sorting: SortingState; onChange: (s: SortingState) => void }) {
  const id = sorting[0]?.id
  const value: PhoneSort = id === 'start' ? 'start' : id === 'first_seen_at' ? 'newest' : 'fit'
  return (
    <div className="flex items-center justify-end gap-2 pt-3 md:hidden">
      <label htmlFor="phone-sort" className="text-sm text-muted-foreground">
        Sort
      </label>
      <Select value={value} onValueChange={(v) => onChange(PHONE_SORTS[v as PhoneSort].sorting)}>
        <SelectTrigger id="phone-sort" size="sm" className="w-36 pointer-coarse:min-h-11">
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          {(Object.keys(PHONE_SORTS) as PhoneSort[]).map((k) => (
            <SelectItem key={k} value={k}>
              {PHONE_SORTS[k].label}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
    </div>
  )
}

function ColumnIcon({ id }: { id: string }) {
  const Icon = COLUMN_ICON[id]
  return Icon ? <Icon className="size-3.5" aria-hidden="true" /> : null
}

function SortIcon({ dir }: { dir: false | 'asc' | 'desc' }) {
  if (dir === 'asc') return <ArrowUp className="size-3.5" aria-hidden="true" />
  if (dir === 'desc') return <ArrowDown className="size-3.5" aria-hidden="true" />
  return <ArrowUpDown className="size-3.5 opacity-50" aria-hidden="true" />
}

/** Warns when the Mac's Claude Code sign-in is about to run out (the AI steps would pause). */
function SignInWarning() {
  const { data: runs } = useRuns()
  const latest = runs?.find((r) => r.kind === 'scoring' && r.status === 'succeeded')
  const days = (latest?.counts as Record<string, number> | null)?.signin_days_left
  if (days === undefined || days > 10) return null
  return (
    <div role="status" className="mb-6 flex items-start gap-3 rounded-lg border border-warning-text/40 bg-card px-4 py-3 text-sm">
      <KeyRound className="mt-0.5 size-4 shrink-0 text-warning-text" aria-hidden="true" />
      <p>
        <span className="font-medium">Claude Code sign-in ends in {days} {days === 1 ? 'day' : 'days'}.</span>{' '}
        After that, scoring pauses. On your Mac, run <code className="font-mono">claude</code> and type{' '}
        <code className="font-mono">/login</code>, or set up the one-year token from{' '}
        <code className="font-mono">claude setup-token</code>.
      </p>
    </div>
  )
}

export function TodayPage() {
  const { data: jobs, isLoading, error } = useJobs()
  const navigate = useNavigate()
  const [sorting, setSorting] = useState<SortingState>([{ id: 'fit_score', desc: true }])
  const availableFrom = useAvailableFrom()
  const columns = useMemo(() => makeColumns(availableFrom), [availableFrom])
  const all = useMemo(() => (jobs ?? []).filter(needsReview), [jobs])
  const [view, setView] = useState<View>('all')
  const rows = useMemo(() => (view === 'all' ? all : all.filter((j) => j.track === view)), [all, view])
  const filtered = useMemo(() => (jobs ?? []).filter((j) => isAutoRejected(j) && !j.closed_at), [jobs])
  const [showFiltered, setShowFiltered] = useState(false)

  const table = useTable({
    features,
    columns,
    data: rows,
    state: { sorting },
    onSortingChange: setSorting,
  })

  return (
    <>
      <PageHeader
        icon={Inbox}
        title="Today"
        description="New matches and documents waiting on you. The list updates every morning."
        actions={
          <Button asChild>
            <Link to="/add">
              <Plus data-icon="inline-start" />
              Add job
            </Link>
          </Button>
        }
      />

      <SignInWarning />
      <ScoreNowBar />

      {error && (
        <p role="alert" className="mb-4 text-sm text-destructive">
          Couldn't load jobs: {(error as Error).message}
        </p>
      )}

      {isLoading ? (
        <div className="flex flex-col gap-3" aria-busy="true" aria-label="Loading jobs">
          {Array.from({ length: 5 }, (_, i) => (
            <Skeleton key={i} className="h-16 w-full" />
          ))}
        </div>
      ) : all.length === 0 ? (
        <EmptyState
          icon={Inbox}
          title="Nothing to review"
          action={
            <Button asChild variant="outline">
              <Link to="/add">Add a job by hand</Link>
            </Button>
          }
        >
          New matches from the daily search will show up here. Until that's running, add jobs you find yourself.
        </EmptyState>
      ) : (
        <>
          <HeadlineRow jobs={jobs ?? []} rows={all} />
          <ViewTabs rows={all} view={view} onChange={setView} />
          <PhoneSortMenu sorting={sorting} onChange={setSorting} />

          {/* Phones: flat rows instead of a wide table (no sideways scrolling). */}
          <ul className="flex flex-col md:hidden">
            {table.getRowModel().rows.map(({ original: job }) => (
              <li key={job.id} className="border-b">
                <Link to={`/jobs/${job.id}`} className="flex flex-col gap-1.5 py-3 transition-colors duration-150 active:bg-hover">
                  <span className="flex items-start justify-between gap-3">
                    <span className="min-w-0 font-medium">{job.title}</span>
                    {job.fit_score !== null && (
                      <span className="shrink-0 font-medium tabular-nums" aria-label={`Fit ${job.fit_score}`}>
                        {job.fit_score}
                      </span>
                    )}
                  </span>
                  <span className="text-xs text-muted-foreground">
                    {job.company}
                    {job.location && ` · ${shortLocation(job.location)}`}
                  </span>
                  {startLine(job, availableFrom) && (
                    <span className="text-xs text-muted-foreground">{startLine(job, availableFrom)}</span>
                  )}
                  <span className="flex flex-wrap gap-1.5">
                    <StatusBadge status={job.status} />
                    {job.track && <TrackTag track={job.track} />}
                    <StartTags job={job} availableFrom={availableFrom} />
                    {job.pipeline_state === 'needs_approval' && (
                      <span className="text-xs font-medium text-warning-text">Review suggestions</span>
                    )}
                  </span>
                </Link>
              </li>
            ))}
          </ul>

          <div className="hidden md:block">
            <Table>
              <TableHeader>
                {table.getHeaderGroups().map((hg) => (
                  <TableRow key={hg.id}>
                    {hg.headers.map((header) => {
                      const sorted = header.column.getIsSorted()
                      return (
                        <TableHead
                          key={header.id}
                          aria-sort={sorted === 'asc' ? 'ascending' : sorted === 'desc' ? 'descending' : undefined}
                        >
                          {header.column.getCanSort() ? (
                            <button
                              type="button"
                              onClick={header.column.getToggleSortingHandler()}
                              className="inline-flex items-center gap-1 rounded-sm font-medium hover:text-foreground"
                            >
                              <ColumnIcon id={header.column.id} />
                              <table.FlexRender header={header} />
                              <SortIcon dir={sorted} />
                            </button>
                          ) : (
                            <span className="inline-flex items-center gap-1">
                              <ColumnIcon id={header.column.id} />
                              <table.FlexRender header={header} />
                            </span>
                          )}
                        </TableHead>
                      )
                    })}
                  </TableRow>
                ))}
              </TableHeader>
              <TableBody>
                {table.getRowModel().rows.map((row) => (
                  <TableRow
                    key={row.id}
                    className="cursor-pointer"
                    onClick={(e) => {
                      // Whole row is clickable; the title link stays the keyboard target.
                      if ((e.target as HTMLElement).closest('a,button')) return
                      navigate(`/jobs/${row.original.id}`)
                    }}
                  >
                    {row.getAllCells().map((cell) => (
                      <TableCell key={cell.id} className="whitespace-normal">
                        <table.FlexRender cell={cell} />
                      </TableCell>
                    ))}
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        </>
      )}

      {filtered.length > 0 && (
        <section className="mt-8">
          <Button
            variant="ghost"
            className="-ml-2 text-muted-foreground"
            aria-expanded={showFiltered}
            aria-controls="filtered-jobs"
            onClick={() => setShowFiltered((v) => !v)}
          >
            {showFiltered ? <ChevronDown data-icon="inline-start" /> : <ChevronRight data-icon="inline-start" />}
            {showFiltered ? 'Hide' : 'Show'} {filtered.length} filtered out or below your fit threshold
          </Button>
          {showFiltered && (
            <ul id="filtered-jobs" className="mt-2 flex flex-col divide-y rounded-lg border bg-card">
              {filtered.map((job) => (
                <li key={job.id} className="flex flex-col gap-0.5 px-4 py-3 sm:flex-row sm:items-center sm:gap-4">
                  <Link to={`/jobs/${job.id}`} className="min-w-0 flex-1 underline-offset-4 hover:underline">
                    <span className="font-medium">{job.title}</span>
                    <span className="text-muted-foreground"> · {job.company}</span>
                  </Link>
                  <span className="text-sm text-muted-foreground">
                    {job.pipeline_state === 'below_threshold' && job.fit_score !== null
                      ? `Fit ${job.fit_score}: ${job.fit_reason ?? 'below your threshold'}`
                      : (job.filter_reason ?? 'Filtered')}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </section>
      )}
    </>
  )
}
