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
import { ArrowDown, ArrowUp, ArrowUpDown, ChevronDown, ChevronRight, Inbox, KeyRound, MapPin, Plus } from 'lucide-react'
import { useMemo, useState } from 'react'
import { Link, useNavigate } from 'react-router'
import { EmptyState, PageHeader } from '@/components/EmptyState'
import { FitScore } from '@/components/FitScore'
import { StatusBadge } from '@/components/StatusBadge'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { useJobs, useRuns } from '@/lib/queries'
import { TRACK_LABEL } from '@/lib/status'
import type { Job } from '@/lib/types'
import { formatRelative, shortLocation } from '@/lib/format'
import { isAutoRejected, needsReview } from '@/lib/jobs'

const features = tableFeatures({
  rowSortingFeature,
  sortedRowModel: createSortedRowModel(),
  sortFns: { basic: sortFn_basic, alphanumeric: sortFn_alphanumeric },
})

const helper = createColumnHelper<typeof features, Job>()

const columns = helper.columns([
  helper.accessor((j) => j.fit_score ?? undefined, {
    id: 'fit_score',
    header: 'Fit',
    sortFn: 'basic',
    sortUndefined: 'last',
    cell: ({ row }) => <FitScore score={row.original.fit_score} />,
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
        <div className="text-sm text-muted-foreground">{row.original.company}</div>
      </div>
    ),
  }),
  helper.accessor((j) => j.location ?? '', {
    id: 'location',
    header: 'Location',
    sortFn: 'alphanumeric',
    cell: ({ row }) => (
      <span className="text-sm" title={row.original.location ?? undefined}>
        {shortLocation(row.original.location)}
        {row.original.remote_type && row.original.remote_type !== 'onsite' && (
          <span className="text-muted-foreground"> · {row.original.remote_type}</span>
        )}
      </span>
    ),
  }),
  helper.accessor((j) => (j.track ? TRACK_LABEL[j.track] : ''), {
    id: 'track',
    header: 'Track',
    sortFn: 'alphanumeric',
    cell: ({ getValue }) => <span className="text-sm">{getValue() || '—'}</span>,
  }),
  helper.accessor('first_seen_at', {
    header: 'Found',
    sortFn: 'basic',
    cell: ({ row }) => (
      <span className="font-mono text-sm tabular-nums text-muted-foreground">
        {formatRelative(row.original.first_seen_at)}
      </span>
    ),
  }),
  helper.accessor('status', {
    header: 'Status',
    enableSorting: false,
    cell: ({ row }) => <StatusBadge status={row.original.status} />,
  }),
])

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
    <div role="status" className="mb-6 flex items-start gap-3 rounded-xl border border-warning-text/40 bg-card px-4 py-3 text-sm">
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
  const rows = useMemo(() => (jobs ?? []).filter(needsReview), [jobs])
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
        title="Today"
        description="New matches, best fit first. The daily search adds jobs each morning and your Mac scores them."
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
      ) : rows.length === 0 ? (
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
          {/* Phones: cards instead of a wide table (no sideways scrolling). */}
          <ul className="flex flex-col gap-3 md:hidden">
            {table.getRowModel().rows.map(({ original: job }) => (
              <li key={job.id}>
                <Link
                  to={`/jobs/${job.id}`}
                  className="block rounded-xl border bg-card p-4 transition-colors duration-200 hover:bg-accent/50"
                >
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0">
                      <p className="font-medium">{job.title}</p>
                      <p className="text-sm text-muted-foreground">{job.company}</p>
                    </div>
                    <StatusBadge status={job.status} />
                  </div>
                  <div className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-1 text-sm">
                    <FitScore score={job.fit_score} />
                    {job.location && (
                      <span className="inline-flex items-center gap-1 text-muted-foreground">
                        <MapPin className="size-3.5" aria-hidden="true" />
                        {shortLocation(job.location)}
                      </span>
                    )}
                  </div>
                </Link>
              </li>
            ))}
          </ul>

          <div className="hidden overflow-x-auto rounded-xl border bg-card md:block">
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
                              <table.FlexRender header={header} />
                              <SortIcon dir={sorted} />
                            </button>
                          ) : (
                            <table.FlexRender header={header} />
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
                      <TableCell key={cell.id} className="py-3 whitespace-normal">
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
            <ul id="filtered-jobs" className="mt-2 flex flex-col divide-y rounded-xl border bg-card">
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
