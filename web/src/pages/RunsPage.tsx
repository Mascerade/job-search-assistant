import { Activity, CircleAlert, CircleCheck, LoaderCircle } from 'lucide-react'
import { useState } from 'react'
import { EmptyState, PageHeader } from '@/components/EmptyState'
import { Skeleton } from '@/components/ui/skeleton'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { formatDateTime, formatUsd } from '@/lib/format'
import { useRuns } from '@/lib/queries'
import type { Run } from '@/lib/types'

const RUN_STATUS: Record<Run['status'], { label: string; icon: typeof Activity; className: string }> = {
  running: { label: 'Running', icon: LoaderCircle, className: 'text-primary' },
  succeeded: { label: 'Succeeded', icon: CircleCheck, className: 'text-success-text' },
  failed: { label: 'Failed', icon: CircleAlert, className: 'text-destructive' },
}

const RUN_KIND: Record<string, string> = {
  daily: 'Daily feed (cloud)',
  local: 'Workday feed (Mac)',
  scoring: 'AI scoring (Mac)',
  on_demand: 'On demand',
}

export function RunsPage() {
  const { data: runs, isLoading } = useRuns()
  const [monthStart] = useState(() => {
    const now = new Date()
    return new Date(now.getFullYear(), now.getMonth(), 1).getTime()
  })
  const monthSpend = (runs ?? [])
    .filter((r) => new Date(r.started_at).getTime() >= monthStart)
    .reduce((sum, r) => sum + Number(r.cost_usd), 0)

  return (
    <>
      <PageHeader
        icon={Activity}
        title="Runs & spend"
        description={
          <>
            AI usage this month: <span className="font-medium tabular-nums text-foreground">{formatUsd(monthSpend)}</span>{' '}
            estimated API value. It's free on your Claude plan; the cap in Settings keeps usage modest.
          </>
        }
      />
      {isLoading ? (
        <Skeleton className="h-48 w-full" />
      ) : !runs?.length ? (
        <EmptyState icon={Activity} title="No runs yet">
          Each run of the daily search, scoring, and tailoring is logged here with what it did.
        </EmptyState>
      ) : (
        <div className="overflow-x-auto rounded-lg border bg-card">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Started</TableHead>
                <TableHead>Kind</TableHead>
                <TableHead>Status</TableHead>
                <TableHead>Counts</TableHead>
                <TableHead className="text-right">Est. AI value</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {runs.map((r) => {
                const s = RUN_STATUS[r.status]
                const Icon = s.icon
                return (
                  <TableRow key={r.id}>
                    <TableCell className="text-sm tabular-nums">{formatDateTime(r.started_at)}</TableCell>
                    <TableCell className="text-sm">{RUN_KIND[r.kind] ?? r.kind}</TableCell>
                    <TableCell>
                      <span className={`inline-flex items-center gap-1.5 text-sm ${s.className}`}>
                        <Icon className="size-4" aria-hidden="true" />
                        {s.label}
                      </span>
                      {r.error && <p className="max-w-xs truncate text-xs text-destructive" title={r.error}>{r.error}</p>}
                    </TableCell>
                    <TableCell className="text-sm text-muted-foreground">
                      {Object.entries(r.counts as Record<string, number>)
                        .map(([k, v]) => `${k.replaceAll('_', ' ')}: ${v}`)
                        .join(' · ') || '—'}
                    </TableCell>
                    <TableCell className="text-right text-sm tabular-nums">{formatUsd(Number(r.cost_usd))}</TableCell>
                  </TableRow>
                )
              })}
            </TableBody>
          </Table>
        </div>
      )}
    </>
  )
}
