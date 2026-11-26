import {
  ArrowLeft,
  CalendarClock,
  CircleOff,
  ExternalLink,
  FileText,
  History,
  MapPin,
  Pencil,
  Sparkles,
  Trash2,
  TriangleAlert,
  UserPlus,
  Wallet,
  X,
} from 'lucide-react'
import { useId, useState, type FormEvent } from 'react'
import { Link, useNavigate, useParams } from 'react-router'
import { toast } from 'sonner'
import { EmptyState } from '@/components/EmptyState'
import { FitScore } from '@/components/FitScore'
import { JobForm } from '@/components/JobForm'
import { EMPTY_JOB_FORM, toJobInsert, type JobFormValues } from '@/lib/jobForm'
import { MoveToMenu } from '@/components/MoveToMenu'
import { StatusBadge } from '@/components/StatusBadge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Skeleton } from '@/components/ui/skeleton'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { Textarea } from '@/components/ui/textarea'
import { formatDateTime, formatRelative, formatSalary } from '@/lib/format'
import { useDeleteJob, useJob, useLatestScore, useStatusHistory, useUpdateJob } from '@/lib/queries'
import { sourceLabel, TAG_LABEL } from '@/lib/jobs'
import { STATUS, TRACK_LABEL } from '@/lib/status'
import type { Contact, Job } from '@/lib/types'

function toFormValues(job: Job): JobFormValues {
  return {
    ...EMPTY_JOB_FORM,
    url: job.url ?? '',
    company: job.company,
    title: job.title,
    location: job.location ?? '',
    remote_type: (job.remote_type as JobFormValues['remote_type']) ?? '',
    track: job.track ?? '',
    salary_min: job.salary_min?.toString() ?? '',
    salary_max: job.salary_max?.toString() ?? '',
    description: job.description ?? '',
  }
}

function FitCard({ job }: { job: Job }) {
  const { data: score } = useLatestScore(job.id)
  const concerns = score?.details.concerns ?? []
  const years = score?.details.years_required
  return (
    <Card className="mb-6">
      <CardContent className="flex flex-col gap-3">
        <div className="flex flex-col gap-1 sm:flex-row sm:items-center sm:gap-4">
          <div className="flex items-center gap-2">
            <Sparkles className="size-4 text-primary" aria-hidden="true" />
            <span className="text-sm font-medium">Fit</span>
            <FitScore score={job.fit_score} />
          </div>
          <p className="text-sm text-muted-foreground">
            {job.fit_reason ?? 'Not scored yet. Your Mac scores new jobs each morning.'}
          </p>
        </div>
        {(concerns.length > 0 || (years !== undefined && years !== null)) && (
          <div className="border-t pt-3">
            <h2 className="mb-1.5 text-xs font-medium tracking-wide text-muted-foreground uppercase">Watch out for</h2>
            <ul className="flex flex-col gap-1 text-sm">
              {years !== undefined && years !== null && (
                <li className="flex items-start gap-2">
                  <CalendarClock className="mt-0.5 size-4 shrink-0 text-muted-foreground" aria-hidden="true" />
                  Asks for {years === 0 ? 'no prior' : `${years}+ years of`} experience
                </li>
              )}
              {concerns.map((c) => (
                <li key={c} className="flex items-start gap-2">
                  <TriangleAlert className="mt-0.5 size-4 shrink-0 text-warning-text" aria-hidden="true" />
                  {c}
                </li>
              ))}
            </ul>
          </div>
        )}
      </CardContent>
    </Card>
  )
}

function NotesCard({ job }: { job: Job }) {
  const update = useUpdateJob()
  const [notes, setNotes] = useState(job.notes)
  const dirty = notes !== job.notes

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">Notes</CardTitle>
      </CardHeader>
      <CardContent className="flex flex-col gap-3">
        <Label htmlFor="job-notes" className="sr-only">
          Notes
        </Label>
        <Textarea
          id="job-notes"
          rows={6}
          value={notes}
          onChange={(e) => setNotes(e.target.value)}
          placeholder="Interview dates, who referred you, questions to ask…"
        />
        <div className="flex items-center justify-end gap-3">
          <span role="status" className="text-xs text-muted-foreground">
            {update.isPending ? 'Saving…' : dirty ? 'Unsaved changes' : ''}
          </span>
          <Button
            disabled={!dirty || update.isPending}
            onClick={async () => {
              try {
                await update.mutateAsync({ id: job.id, patch: { notes } })
                toast.success('Notes saved')
              } catch (e) {
                toast.error(`Couldn't save notes: ${(e as Error).message}`)
              }
            }}
          >
            Save notes
          </Button>
        </div>
      </CardContent>
    </Card>
  )
}

function ContactsCard({ job }: { job: Job }) {
  const update = useUpdateJob()
  const contacts = (job.contacts as unknown as Contact[]) ?? []
  const uid = useId()
  const [draft, setDraft] = useState<Contact>({ name: '', role: '', email: '' })
  const [error, setError] = useState<string | null>(null)

  async function save(next: Contact[], message: string) {
    try {
      await update.mutateAsync({ id: job.id, patch: { contacts: next as unknown as Job['contacts'] } })
      toast.success(message)
    } catch (e) {
      toast.error(`Couldn't save contacts: ${(e as Error).message}`)
    }
  }

  async function add(e: FormEvent) {
    e.preventDefault()
    if (!draft.name.trim()) {
      setError('Enter a name.')
      return
    }
    setError(null)
    const clean: Contact = {
      name: draft.name.trim(),
      ...(draft.role?.trim() ? { role: draft.role.trim() } : {}),
      ...(draft.email?.trim() ? { email: draft.email.trim() } : {}),
    }
    await save([...contacts, clean], `Added ${clean.name}`)
    setDraft({ name: '', role: '', email: '' })
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">Contacts</CardTitle>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        {contacts.length > 0 && (
          <ul className="flex flex-col divide-y rounded-lg border">
            {contacts.map((c, i) => (
              <li key={`${c.name}-${i}`} className="flex items-center gap-3 px-3 py-2">
                <div className="min-w-0 flex-1">
                  <p className="text-sm font-medium">{c.name}</p>
                  <p className="truncate text-xs text-muted-foreground">
                    {[c.role, c.email].filter(Boolean).join(' · ') || '—'}
                  </p>
                </div>
                <Button
                  variant="ghost"
                  size="icon-sm"
                  aria-label={`Remove ${c.name}`}
                  onClick={() => save(contacts.filter((_, j) => j !== i), `Removed ${c.name}`)}
                >
                  <X />
                </Button>
              </li>
            ))}
          </ul>
        )}
        <form onSubmit={add} noValidate className="grid gap-3 sm:grid-cols-[1fr_1fr_1fr_auto] sm:items-end">
          <div className="flex flex-col gap-1.5">
            <Label htmlFor={`${uid}-name`}>Name</Label>
            <Input
              id={`${uid}-name`}
              value={draft.name}
              onChange={(e) => setDraft({ ...draft, name: e.target.value })}
              aria-invalid={!!error}
              aria-describedby={error ? `${uid}-name-error` : undefined}
            />
            {error && (
              <p id={`${uid}-name-error`} role="alert" className="text-xs font-medium text-destructive">
                {error}
              </p>
            )}
          </div>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor={`${uid}-role`}>Role</Label>
            <Input
              id={`${uid}-role`}
              placeholder="Recruiter"
              value={draft.role}
              onChange={(e) => setDraft({ ...draft, role: e.target.value })}
            />
          </div>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor={`${uid}-email`}>Email</Label>
            <Input
              id={`${uid}-email`}
              type="email"
              value={draft.email}
              onChange={(e) => setDraft({ ...draft, email: e.target.value })}
            />
          </div>
          <Button type="submit" variant="outline" disabled={update.isPending}>
            <UserPlus data-icon="inline-start" />
            Add
          </Button>
        </form>
      </CardContent>
    </Card>
  )
}

function HistoryList({ jobId }: { jobId: string }) {
  const { data, isLoading } = useStatusHistory(jobId)
  if (isLoading) return <Skeleton className="h-24 w-full" />
  if (!data?.length) return <p className="text-sm text-muted-foreground">No history yet.</p>
  return (
    <ol className="relative flex flex-col gap-4 border-l pl-5">
      {data.map((h) => (
        <li key={h.id} className="relative">
          <span className="absolute top-1.5 -left-[25px] size-2.5 rounded-full border-2 border-card bg-primary" aria-hidden="true" />
          <div className="flex flex-wrap items-center gap-2 text-sm">
            {h.from_status ? (
              <>
                <StatusBadge status={h.from_status} />
                <span className="text-muted-foreground">to</span>
                <StatusBadge status={h.to_status} />
              </>
            ) : (
              <>
                <span className="text-muted-foreground">Added as</span>
                <StatusBadge status={h.to_status} />
              </>
            )}
          </div>
          <p className="mt-1 font-mono text-xs tabular-nums text-muted-foreground">{formatDateTime(h.changed_at)}</p>
        </li>
      ))}
    </ol>
  )
}

export function JobDetailPage() {
  const { id = '' } = useParams()
  const navigate = useNavigate()
  const { data: job, isLoading, error } = useJob(id)
  const update = useUpdateJob()
  const remove = useDeleteJob()
  const [editing, setEditing] = useState(false)
  const [confirmDelete, setConfirmDelete] = useState(false)

  if (isLoading) {
    return (
      <div className="flex flex-col gap-4" aria-busy="true" aria-label="Loading job">
        <Skeleton className="h-8 w-2/3" />
        <Skeleton className="h-5 w-1/3" />
        <Skeleton className="h-64 w-full" />
      </div>
    )
  }
  if (error || !job) {
    return (
      <EmptyState
        icon={FileText}
        title="Job not found"
        action={
          <Button asChild variant="outline">
            <Link to="/">Back to Today</Link>
          </Button>
        }
      >
        {error ? (error as Error).message : 'It may have been deleted.'}
      </EmptyState>
    )
  }

  const salary = formatSalary(job.salary_min, job.salary_max)

  return (
    <>
      <Button
        variant="ghost"
        className="mb-4 -ml-2 text-muted-foreground"
        onClick={() => (window.history.length > 1 ? navigate(-1) : navigate('/'))}
      >
        <ArrowLeft data-icon="inline-start" />
        Back
      </Button>

      <header className="mb-6 flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
        <div className="min-w-0">
          <div className="mb-2 flex flex-wrap items-center gap-2">
            <StatusBadge status={job.status} />
            {job.track && <span className="text-xs text-muted-foreground">{TRACK_LABEL[job.track]}</span>}
            {job.closed_at && (
              <span className="inline-flex items-center gap-1 rounded-full bg-status-closed-bg px-2.5 py-0.5 text-xs font-medium text-status-closed">
                <CircleOff className="size-3.5" aria-hidden="true" />
                Posting closed
              </span>
            )}
            {job.tags.map((t) => (
              <span key={t} className="rounded-full border px-2 py-0.5 text-xs">
                {TAG_LABEL[t] ?? t}
              </span>
            ))}
          </div>
          <h1 className="text-2xl font-semibold tracking-tight">{job.title}</h1>
          <p className="text-lg text-muted-foreground">{job.company}</p>
          <dl className="mt-3 flex flex-wrap gap-x-5 gap-y-1 text-sm text-muted-foreground">
            {(job.location || job.remote_type) && (
              <div className="inline-flex items-center gap-1.5">
                <MapPin className="size-4" aria-hidden="true" />
                <dt className="sr-only">Location</dt>
                <dd>{[job.location, job.remote_type].filter(Boolean).join(' · ')}</dd>
              </div>
            )}
            {salary && (
              <div className="inline-flex items-center gap-1.5">
                <Wallet className="size-4" aria-hidden="true" />
                <dt className="sr-only">Salary</dt>
                <dd className="font-mono tabular-nums">{salary}</dd>
              </div>
            )}
            <div className="inline-flex items-center gap-1.5">
              <CalendarClock className="size-4" aria-hidden="true" />
              <dt className="sr-only">Found</dt>
              <dd>
                Found {formatRelative(job.first_seen_at)}
                {sourceLabel(job) && ` on ${sourceLabel(job)}`}
              </dd>
            </div>
          </dl>
        </div>
        <div className="flex flex-wrap gap-2">
          {job.url && (
            <Button asChild>
              <a href={job.url} target="_blank" rel="noopener noreferrer">
                <ExternalLink data-icon="inline-start" />
                Open posting
                <span className="sr-only">(opens in a new tab)</span>
              </a>
            </Button>
          )}
          <MoveToMenu job={job} variant="full" />
          <Button variant="outline" onClick={() => setEditing(true)}>
            <Pencil data-icon="inline-start" />
            Edit
          </Button>
          <Button variant="destructive" onClick={() => setConfirmDelete(true)}>
            <Trash2 data-icon="inline-start" />
            Delete
          </Button>
        </div>
      </header>

      {job.pipeline_state === 'filtered_out' && (
        <p role="note" className="mb-4 rounded-lg border border-dashed px-4 py-3 text-sm text-muted-foreground">
          The daily search filtered this job out: <span className="font-medium text-foreground">{job.filter_reason}</span>.
          It stays off Today and the Board unless you move it yourself.
        </p>
      )}

      <FitCard job={job} />

      <Tabs defaultValue="posting">
        <TabsList className="mb-4 grid w-full grid-cols-4 sm:w-fit">
          <TabsTrigger value="posting">Posting</TabsTrigger>
          <TabsTrigger value="documents">Documents</TabsTrigger>
          <TabsTrigger value="notes">Notes</TabsTrigger>
          <TabsTrigger value="history">History</TabsTrigger>
        </TabsList>

        <TabsContent value="posting">
          <Card>
            <CardContent>
              {job.description ? (
                <div className="max-w-prose text-sm leading-relaxed whitespace-pre-wrap">{job.description}</div>
              ) : (
                <p className="text-sm text-muted-foreground">
                  No posting text saved. Use Edit to paste it in; the tailoring step needs it.
                </p>
              )}
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="documents">
          <EmptyState icon={FileText} title="No documents yet">
            Tailored resumes and cover letters will appear here, with any AI suggestions waiting for your approval.
            This arrives in milestone 4.
          </EmptyState>
        </TabsContent>

        <TabsContent value="notes" className="flex flex-col gap-6">
          <NotesCard key={job.notes} job={job} />
          <ContactsCard job={job} />
        </TabsContent>

        <TabsContent value="history">
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2 text-base">
                <History className="size-4" aria-hidden="true" />
                Status history
              </CardTitle>
            </CardHeader>
            <CardContent>
              <HistoryList jobId={job.id} />
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>

      <Dialog open={editing} onOpenChange={setEditing}>
        <DialogContent className="max-h-[90dvh] overflow-y-auto sm:max-w-2xl">
          <DialogHeader>
            <DialogTitle>Edit job details</DialogTitle>
            <DialogDescription>Fix anything the posting got wrong or add the full description.</DialogDescription>
          </DialogHeader>
          <JobForm
            initial={toFormValues(job)}
            submitLabel="Save changes"
            pending={update.isPending}
            onCancel={() => setEditing(false)}
            onSubmit={async (values) => {
              try {
                await update.mutateAsync({ id: job.id, patch: toJobInsert(values) })
                toast.success('Job updated')
                setEditing(false)
              } catch (e) {
                toast.error(`Couldn't save: ${(e as Error).message}`)
              }
            }}
          />
        </DialogContent>
      </Dialog>

      <Dialog open={confirmDelete} onOpenChange={setConfirmDelete}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Delete this job?</DialogTitle>
            <DialogDescription>
              This permanently removes "{job.title}" at {job.company}, with its notes, contacts, and history. To keep a
              record instead, move it to {STATUS.not_interested.label}.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setConfirmDelete(false)}>
              Cancel
            </Button>
            <Button
              variant="destructive"
              disabled={remove.isPending}
              onClick={async () => {
                try {
                  await remove.mutateAsync(job.id)
                  toast.success('Job deleted')
                  navigate('/board', { replace: true })
                } catch (e) {
                  toast.error(`Couldn't delete: ${(e as Error).message}`)
                }
              }}
            >
              Delete job
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  )
}
