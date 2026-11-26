import {
  DndContext,
  DragOverlay,
  KeyboardSensor,
  PointerSensor,
  useDraggable,
  useDroppable,
  useSensor,
  useSensors,
  type DragEndEvent,
  type DragStartEvent,
} from '@dnd-kit/core'
import { GripVertical, SquareKanban } from 'lucide-react'
import { useMemo, useState } from 'react'
import { Link } from 'react-router'
import { toast } from 'sonner'
import { EmptyState, PageHeader } from '@/components/EmptyState'
import { FitScore } from '@/components/FitScore'
import { MoveToMenu } from '@/components/MoveToMenu'
import { StatusBadge } from '@/components/StatusBadge'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Label } from '@/components/ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Skeleton } from '@/components/ui/skeleton'
import { isAutoRejected } from '@/lib/jobs'
import { useJobs, useSetStatus } from '@/lib/queries'
import { CLOSED_STATUSES, STATUS } from '@/lib/status'
import type { ApplicationStatus, Job } from '@/lib/types'
import { cn } from '@/lib/utils'

type OpenColumn = 'new' | 'docs_ready' | 'applied' | 'interviewing' | 'offer'
type ColumnId = OpenColumn | 'closed'

const OPEN_COLUMNS: OpenColumn[] = ['new', 'docs_ready', 'applied', 'interviewing', 'offer']
const ALL_COLUMNS: { id: ColumnId; label: string }[] = [
  ...OPEN_COLUMNS.map((id) => ({ id, label: STATUS[id].label })),
  { id: 'closed', label: 'Closed' },
]

function columnOf(status: ApplicationStatus): ColumnId {
  return CLOSED_STATUSES.includes(status) ? 'closed' : (status as OpenColumn)
}

/** Card contents shared by the desktop board and the phone list. */
function JobCardBody({ job, showStatus }: { job: Job; showStatus?: boolean }) {
  return (
    <>
      <Link to={`/jobs/${job.id}`} className="block font-medium leading-snug underline-offset-4 hover:underline">
        {job.title}
      </Link>
      <p className="text-sm text-muted-foreground">{job.company}</p>
      {showStatus && <StatusBadge status={job.status} className="mt-2" />}
      {job.closed_at && <p className="mt-1 text-xs font-medium text-warning-text">Posting closed</p>}
    </>
  )
}

function DraggableCard({ job, showStatus }: { job: Job; showStatus?: boolean }) {
  const { attributes, listeners, setNodeRef, isDragging } = useDraggable({ id: job.id, data: { job } })
  return (
    <li
      ref={setNodeRef}
      className={cn('rounded-lg border bg-card p-3 shadow-xs transition-opacity duration-200', isDragging && 'opacity-40')}
    >
      <div className="flex gap-1">
        <button
          type="button"
          className="-ml-1 flex w-5 shrink-0 cursor-grab touch-none items-start justify-center rounded-sm pt-0.5 text-muted-foreground hover:text-foreground active:cursor-grabbing"
          aria-label={`Drag "${job.title}" to another column`}
          {...listeners}
          {...attributes}
        >
          <GripVertical className="size-4" aria-hidden="true" />
        </button>
        <div className="min-w-0 flex-1">
          <JobCardBody job={job} showStatus={showStatus} />
        </div>
      </div>
      <div className="mt-2 flex items-center justify-between gap-2 pl-4">
        <FitScore score={job.fit_score} compact />
        <MoveToMenu job={job} />
      </div>
    </li>
  )
}

function ColumnHeading({ id, label, count }: { id: ColumnId; label: string; count: number }) {
  const meta = STATUS[id === 'closed' ? 'not_interested' : id]
  const Icon = meta.icon
  return (
    <h2 id={`col-${id}`} className="flex items-center gap-2 px-2 py-1.5 text-sm font-semibold">
      <span className={cn('inline-flex size-6 items-center justify-center rounded-full', meta.className)}>
        <Icon className="size-3.5" aria-hidden="true" />
      </span>
      {label}
      <span className="ml-auto font-mono text-xs tabular-nums text-muted-foreground">{count}</span>
    </h2>
  )
}

function Column({ id, jobs }: { id: OpenColumn; jobs: Job[] }) {
  const { setNodeRef, isOver } = useDroppable({ id })
  return (
    <section
      ref={setNodeRef}
      aria-labelledby={`col-${id}`}
      className={cn(
        'flex min-h-48 min-w-0 flex-col rounded-xl border bg-muted/50 p-2 transition-colors duration-200',
        isOver && 'border-primary bg-accent',
      )}
    >
      <ColumnHeading id={id} label={STATUS[id].label} count={jobs.length} />
      <ul className="flex flex-col gap-2">
        {jobs.map((job) => (
          <DraggableCard key={job.id} job={job} />
        ))}
      </ul>
    </section>
  )
}

/** Closed applications sit in a strip under the board; dropping here asks which kind of closed. */
function ClosedZone({ jobs, dragging }: { jobs: Job[]; dragging: boolean }) {
  const { setNodeRef, isOver } = useDroppable({ id: 'closed' })
  return (
    <section
      ref={setNodeRef}
      aria-labelledby="col-closed"
      className={cn(
        'mt-3 rounded-xl border border-dashed bg-muted/30 p-2 transition-colors duration-200',
        dragging && 'border-primary/60',
        isOver && 'border-primary bg-accent',
      )}
    >
      <ColumnHeading id="closed" label="Closed" count={jobs.length} />
      {jobs.length === 0 ? (
        <p className="px-2 pb-2 text-sm text-muted-foreground">
          {dragging ? 'Drop here to close an application.' : 'Rejected, withdrawn, and skipped jobs collect here.'}
        </p>
      ) : (
        <ul className="grid grid-cols-3 gap-2 2xl:grid-cols-4">
          {jobs.map((job) => (
            <DraggableCard key={job.id} job={job} showStatus />
          ))}
        </ul>
      )}
    </section>
  )
}

/** Dropping on "Closed" is ambiguous, so ask which closed status it should be. */
function CloseDialog({
  job,
  onChoose,
  onCancel,
}: {
  job: Job | null
  onChoose: (s: ApplicationStatus) => void
  onCancel: () => void
}) {
  return (
    <Dialog open={!!job} onOpenChange={(open) => !open && onCancel()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Close this application?</DialogTitle>
          <DialogDescription>{job ? `Why is "${job.title}" at ${job.company} closed?` : ''}</DialogDescription>
        </DialogHeader>
        <div className="flex flex-col gap-2">
          {CLOSED_STATUSES.map((s) => {
            const Icon = STATUS[s].icon
            return (
              <Button key={s} variant="outline" className="h-auto justify-start py-2.5" onClick={() => onChoose(s)}>
                <Icon data-icon="inline-start" />
                <span className="flex flex-col items-start">
                  <span>{STATUS[s].label}</span>
                  <span className="text-xs font-normal text-muted-foreground">{STATUS[s].description}</span>
                </span>
              </Button>
            )
          })}
        </div>
        <DialogFooter>
          <Button variant="ghost" onClick={onCancel}>
            Cancel
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

export function BoardPage() {
  const { data: jobs, isLoading } = useJobs()
  const { setStatus } = useSetStatus()
  const [active, setActive] = useState<Job | null>(null)
  const [closing, setClosing] = useState<Job | null>(null)
  const [mobileColumn, setMobileColumn] = useState<ColumnId>('new')

  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 6 } }),
    useSensor(KeyboardSensor),
  )

  const byColumn = useMemo(() => {
    const map = Object.fromEntries(ALL_COLUMNS.map((c) => [c.id, [] as Job[]])) as Record<ColumnId, Job[]>
    for (const job of jobs ?? []) if (!isAutoRejected(job)) map[columnOf(job.status)].push(job)
    for (const list of Object.values(map)) list.sort((a, b) => (b.fit_score ?? -1) - (a.fit_score ?? -1))
    return map
  }, [jobs])

  async function move(job: Job, status: ApplicationStatus) {
    try {
      await setStatus(job.id, status)
      toast.success(`Moved "${job.title}" to ${STATUS[status].label}`)
    } catch (e) {
      toast.error(`Couldn't update status: ${(e as Error).message}`)
    }
  }

  function handleDragStart(e: DragStartEvent) {
    setActive((e.active.data.current as { job: Job }).job)
  }

  function handleDragEnd(e: DragEndEvent) {
    setActive(null)
    const job = (e.active.data.current as { job: Job }).job
    const target = e.over?.id as ColumnId | undefined
    if (!target || target === columnOf(job.status)) return
    if (target === 'closed') setClosing(job)
    else move(job, target)
  }

  return (
    <>
      <PageHeader
        title="Board"
        description="Drag a card by its handle, or use the arrows button on any card to move it without dragging."
      />

      {isLoading ? (
        <div className="flex gap-3" aria-busy="true" aria-label="Loading board">
          {Array.from({ length: 4 }, (_, i) => (
            <Skeleton key={i} className="h-64 flex-1" />
          ))}
        </div>
      ) : (jobs ?? []).length === 0 ? (
        <EmptyState
          icon={SquareKanban}
          title="No jobs yet"
          action={
            <Button asChild>
              <Link to="/add">Add a job</Link>
            </Button>
          }
        >
          Every job you track appears here, grouped by where your application stands.
        </EmptyState>
      ) : (
        <>
          {/* Phones, tablets, small laptops: one column at a time, picked from a list. */}
          <div className="xl:hidden">
            <div className="mb-4 flex flex-col gap-1.5">
              <Label htmlFor="board-column">Showing</Label>
              <Select value={mobileColumn} onValueChange={(v) => setMobileColumn(v as ColumnId)}>
                <SelectTrigger id="board-column" className="w-full sm:w-72">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {ALL_COLUMNS.map((c) => (
                    <SelectItem key={c.id} value={c.id}>
                      {c.label} ({byColumn[c.id].length})
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            {byColumn[mobileColumn].length === 0 ? (
              <p className="rounded-lg border border-dashed p-6 text-center text-sm text-muted-foreground">
                No jobs in this column.
              </p>
            ) : (
              <ul className="grid gap-3 md:grid-cols-2">
                {byColumn[mobileColumn].map((job) => (
                  <li key={job.id} className="rounded-lg border bg-card p-4">
                    <JobCardBody job={job} showStatus={mobileColumn === 'closed'} />
                    <div className="mt-3 flex flex-wrap items-center justify-between gap-2">
                      <FitScore score={job.fit_score} />
                      <MoveToMenu job={job} variant="full" />
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </div>

          {/* Wide screens: five open columns, with closed jobs in a strip below. */}
          <DndContext
            sensors={sensors}
            onDragStart={handleDragStart}
            onDragEnd={handleDragEnd}
            onDragCancel={() => setActive(null)}
          >
            <div className="hidden xl:block">
              <div className="grid grid-cols-5 gap-3">
                {OPEN_COLUMNS.map((id) => (
                  <Column key={id} id={id} jobs={byColumn[id]} />
                ))}
              </div>
              <ClosedZone jobs={byColumn.closed} dragging={!!active} />
            </div>
            <DragOverlay>
              {active ? (
                <div className="w-56 rounded-lg border bg-card p-3 shadow-lg">
                  <p className="font-medium">{active.title}</p>
                  <p className="text-sm text-muted-foreground">{active.company}</p>
                </div>
              ) : null}
            </DragOverlay>
          </DndContext>
        </>
      )}

      <CloseDialog
        job={closing}
        onCancel={() => setClosing(null)}
        onChoose={(s) => {
          if (closing) move(closing, s)
          setClosing(null)
        }}
      />
    </>
  )
}
