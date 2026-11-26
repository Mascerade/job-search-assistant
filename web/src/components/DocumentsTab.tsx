import {
  Check,
  CircleAlert,
  CircleCheck,
  FileDown,
  FileText,
  Info,
  LoaderCircle,
  Pencil,
  RefreshCw,
  Sparkles,
  Undo2,
  X,
} from 'lucide-react'
import { useState } from 'react'
import { toast } from 'sonner'
import { EmptyState } from '@/components/EmptyState'
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
import { Label } from '@/components/ui/label'
import { Skeleton } from '@/components/ui/skeleton'
import { Textarea } from '@/components/ui/textarea'
import {
  downloadUrl,
  isActive,
  preview,
  useCreateTask,
  useDecideSuggestion,
  useDocuments,
  useLatestTask,
  useRefreshWhenTaskFinishes,
  type CoverPreview,
  type DocumentRow,
  type PreviewLine,
  type ResumePreview,
  type SuggestionRow,
  type TaskRow,
} from '@/lib/documents'
import type { Job } from '@/lib/types'
import { cn } from '@/lib/utils'

// ---------------------------------------------------------------------------
// Progress of the latest button press (the Mac picks tasks up every 10 minutes)
// ---------------------------------------------------------------------------

const STEP_LABEL: Record<string, string> = {
  queued: 'Queued',
  writing: 'Writing',
  rendering: 'Building PDFs',
  ready: 'Ready',
  error: 'Error',
}

function TaskProgress({ task }: { task: TaskRow | null | undefined }) {
  if (!task || task.step === 'ready') return null
  const steps = task.kind === 'render' ? ['queued', 'rendering', 'ready'] : ['queued', 'writing', 'rendering', 'ready']
  const current = steps.indexOf(task.step)
  if (task.step === 'error') {
    return (
      <p role="alert" className="mb-4 flex items-start gap-2 rounded-lg border border-destructive/40 bg-destructive/10 px-4 py-3 text-sm">
        <CircleAlert className="mt-0.5 size-4 shrink-0 text-destructive" aria-hidden="true" />
        <span>
          <span className="font-medium">That didn't work:</span> {task.error ?? 'unknown error'}. Try again, or check{' '}
          <code className="font-mono">jobsearch schedule status</code> on your Mac.
        </span>
      </p>
    )
  }
  return (
    <div role="status" aria-live="polite" className="mb-4 rounded-lg border bg-card px-4 py-3">
      <ol className="flex flex-wrap items-center gap-x-2 gap-y-1 text-sm">
        {steps.map((s, i) => (
          <li key={s} className="flex items-center gap-2">
            {i > 0 && <span aria-hidden="true" className="text-muted-foreground">→</span>}
            <span
              className={cn(
                'inline-flex items-center gap-1.5',
                i < current && 'text-muted-foreground',
                i === current && 'font-medium text-primary',
                i > current && 'text-muted-foreground/70',
              )}
            >
              {i === current && <LoaderCircle className="size-3.5 animate-spin" aria-hidden="true" />}
              {i < current && <Check className="size-3.5" aria-hidden="true" />}
              {STEP_LABEL[s]}
              {i === current && <span className="sr-only">(in progress)</span>}
            </span>
          </li>
        ))}
      </ol>
      {task.step === 'queued' && (
        <p className="mt-1 text-xs text-muted-foreground">
          Your Mac picks this up within 10 minutes (it needs to be awake). Writing takes about a minute.
        </p>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// A line that may be a suggestion
// ---------------------------------------------------------------------------

function SuggestedLine({
  line,
  row,
  jobId,
  onDecided,
  as = 'li',
}: {
  line: PreviewLine
  row: SuggestionRow | undefined
  jobId: string
  onDecided: () => void
  as?: 'li' | 'p'
}) {
  const decide = useDecideSuggestion(jobId)
  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState(row?.final_text ?? line.text)
  const Tag = as
  if (!line.suggestion || !row) {
    return <Tag className={cn(as === 'li' && 'ml-4 list-disc')}>{line.text}</Tag>
  }
  const shown = row.final_text ?? line.text

  async function set(decision: 'approved' | 'rejected' | 'pending', finalText?: string | null) {
    try {
      await decide.mutateAsync({ id: row!.id, decision, finalText })
      setEditing(false)
      onDecided()
    } catch (e) {
      toast.error(`Couldn't save: ${(e as Error).message}`)
    }
  }

  return (
    <Tag className="my-2 list-none rounded-lg border border-warning-text/40 bg-status-interviewing-bg/40 p-3">
      <span className="mb-1 flex items-center gap-1.5 text-xs font-medium text-warning-text">
        <Sparkles className="size-3.5" aria-hidden="true" />
        Suggestion
        {row.decision !== 'pending' && (
          <span className={cn('ml-1', row.decision === 'approved' ? 'text-success-text' : 'text-muted-foreground')}>
            · {row.decision === 'approved' ? (row.final_text ? 'Approved with your edit' : 'Approved') : 'Rejected'}
          </span>
        )}
      </span>
      {editing ? (
        <div className="flex flex-col gap-2">
          <Label htmlFor={`edit-${row.id}`} className="sr-only">
            Edit suggestion
          </Label>
          <Textarea id={`edit-${row.id}`} rows={3} value={draft} onChange={(e) => setDraft(e.target.value)} />
          <div className="flex flex-wrap gap-2">
            <Button size="sm" disabled={!draft.trim() || decide.isPending} onClick={() => set('approved', draft.trim())}>
              <Check data-icon="inline-start" />
              Save and approve
            </Button>
            <Button size="sm" variant="ghost" onClick={() => setEditing(false)}>
              Cancel
            </Button>
          </div>
        </div>
      ) : (
        <span className={cn('block', row.decision === 'rejected' && 'text-muted-foreground line-through')}>{shown}</span>
      )}
      <span className="mt-1.5 flex items-start gap-1.5 text-xs text-muted-foreground">
        <Info className="mt-0.5 size-3.5 shrink-0" aria-hidden="true" />
        {row.rationale}
      </span>
      {!editing && (
        <span className="mt-2 flex flex-wrap gap-2">
          {row.decision === 'pending' ? (
            <>
              <Button size="sm" variant="outline" disabled={decide.isPending} onClick={() => set('approved')}>
                <Check data-icon="inline-start" />
                Approve
              </Button>
              <Button size="sm" variant="outline" disabled={decide.isPending} onClick={() => setEditing(true)}>
                <Pencil data-icon="inline-start" />
                Edit
              </Button>
              <Button size="sm" variant="outline" disabled={decide.isPending} onClick={() => set('rejected')}>
                <X data-icon="inline-start" />
                Reject
              </Button>
            </>
          ) : (
            <Button size="sm" variant="ghost" disabled={decide.isPending} onClick={() => set('pending', null)}>
              <Undo2 data-icon="inline-start" />
              Undo
            </Button>
          )}
        </span>
      )}
    </Tag>
  )
}

// ---------------------------------------------------------------------------
// Document cards
// ---------------------------------------------------------------------------

const DOC_STATE: Record<string, { label: string; className: string; icon: typeof Check }> = {
  needs_approval: { label: 'Waiting for your review', className: 'text-warning-text', icon: Sparkles },
  pending_render: { label: 'Building PDF', className: 'text-primary', icon: LoaderCircle },
  final: { label: 'Ready', className: 'text-success-text', icon: CircleCheck },
  error: { label: 'Error', className: 'text-destructive', icon: CircleAlert },
}

function DocCard({ title, doc, children }: { title: string; doc: DocumentRow; children: React.ReactNode }) {
  const state = DOC_STATE[doc.state] ?? DOC_STATE.error
  const Icon = state.icon

  async function download(path: string | null) {
    if (!path) return
    try {
      window.location.assign(await downloadUrl(path))
    } catch (e) {
      toast.error(`Couldn't download: ${(e as Error).message}`)
    }
  }

  return (
    <Card>
      <CardHeader className="flex flex-row flex-wrap items-center justify-between gap-2">
        <div>
          <CardTitle className="text-base">
            {title} <span className="font-mono text-xs font-normal text-muted-foreground">v{doc.version}</span>
          </CardTitle>
          <p className={cn('mt-0.5 inline-flex items-center gap-1.5 text-xs font-medium', state.className)}>
            <Icon className="size-3.5" aria-hidden="true" />
            {state.label}
          </p>
        </div>
        {doc.state === 'final' && (
          <div className="flex gap-2">
            <Button size="sm" onClick={() => download(doc.pdf_path)}>
              <FileDown data-icon="inline-start" />
              PDF
            </Button>
            <Button size="sm" variant="outline" onClick={() => download(doc.docx_path)}>
              <FileText data-icon="inline-start" />
              Word
            </Button>
          </div>
        )}
      </CardHeader>
      <CardContent className="text-sm leading-relaxed">{children}</CardContent>
    </Card>
  )
}

// ---------------------------------------------------------------------------
// The tab
// ---------------------------------------------------------------------------

export function DocumentsTab({ job }: { job: Job }) {
  const { data, isLoading, refetch } = useDocuments(job.id)
  const { data: task } = useLatestTask(job.id)
  useRefreshWhenTaskFinishes(job.id, task)
  const createTask = useCreateTask(job.id)
  const [confirmRegen, setConfirmRegen] = useState(false)
  const busy = isActive(task)

  async function request(kind: 'tailor' | 'regenerate' | 'render', message: string) {
    try {
      await createTask.mutateAsync(kind)
      toast.success(message)
    } catch (e) {
      toast.error(`Couldn't send the request: ${(e as Error).message}`)
    }
  }

  // When the last suggestion is decided, ask the Mac to build the PDFs.
  async function afterDecision() {
    const fresh = (await refetch()).data
    const pending = fresh?.suggestions.filter((s) => s.decision === 'pending').length ?? 1
    if (pending === 0 && !busy) {
      await request('render', 'All reviewed. Building your PDFs.')
    }
  }

  if (isLoading) return <Skeleton className="h-64 w-full" />

  const resume = data?.resume ?? null
  const cover = data?.cover ?? null
  const byPath = new Map((data?.suggestions ?? []).map((s) => [`${s.document_id}:${s.path}`, s]))
  const pending = (data?.suggestions ?? []).filter((s) => s.decision === 'pending').length

  if (!resume || !cover) {
    return (
      <>
        <TaskProgress task={task} />
        <EmptyState
          icon={FileText}
          title="No documents yet"
          action={
            <Button disabled={busy || createTask.isPending} onClick={() => request('tailor', 'Requested. Your Mac will write them shortly.')}>
              <Sparkles data-icon="inline-start" />
              Tailor now
            </Button>
          }
        >
          Matches get a tailored resume and cover letter automatically each morning, best fit first. Use Tailor now to
          get this one sooner.
        </EmptyState>
      </>
    )
  }

  const rp = preview<ResumePreview>(resume)
  const cp = preview<CoverPreview>(cover)
  const line = (doc: DocumentRow, l: PreviewLine, as: 'li' | 'p' = 'li') => (
    <SuggestedLine key={l.path} line={l} row={byPath.get(`${doc.id}:${l.path}`)} jobId={job.id} onDecided={afterDecision} as={as} />
  )

  return (
    <div className="flex flex-col gap-6">
      <TaskProgress task={task} />
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="text-sm text-muted-foreground" role="status">
          {pending > 0
            ? `${pending} ${pending === 1 ? 'suggestion needs' : 'suggestions need'} your review before the PDFs are built.`
            : 'Every line comes from your master profile.'}
        </p>
        <Button variant="outline" disabled={busy} onClick={() => setConfirmRegen(true)}>
          <RefreshCw data-icon="inline-start" />
          Regenerate
        </Button>
      </div>

      <DocCard title="Resume" doc={resume}>
        {rp && (
          <div className="flex flex-col gap-4">
            {rp.headline && <p className="text-center text-muted-foreground">{rp.headline}</p>}
            {rp.summary && <div>{line(resume, rp.summary, 'p')}</div>}
            {rp.sections.map((s) => (
              <section key={s.heading}>
                <h3 className="mb-2 text-xs font-semibold tracking-wide text-muted-foreground uppercase">{s.heading}</h3>
                <div className="flex flex-col gap-3">
                  {s.items.map((item) => (
                    <div key={item.title + item.subtitle}>
                      <p className="font-medium">
                        {item.title} <span className="font-normal text-muted-foreground">· {item.subtitle}</span>
                      </p>
                      <ul className="mt-1 flex flex-col gap-1">{item.lines.map((l) => line(resume, l))}</ul>
                    </div>
                  ))}
                </div>
              </section>
            ))}
            {(rp.skills.length > 0 || rp.suggested_skills.length > 0) && (
              <section>
                <h3 className="mb-2 text-xs font-semibold tracking-wide text-muted-foreground uppercase">Skills</h3>
                <ul className="flex flex-col gap-1">
                  {rp.skills.map((s) => (
                    <li key={s}>{s}</li>
                  ))}
                  {rp.suggested_skills.map((l) => line(resume, l))}
                </ul>
              </section>
            )}
          </div>
        )}
      </DocCard>

      <DocCard title="Cover letter" doc={cover}>
        {cp && (
          <div className="flex max-w-prose flex-col gap-3">
            <p>{cp.greeting}</p>
            {cp.paragraphs.map((p) => line(cover, p, 'p'))}
            <p>{cp.closing}</p>
          </div>
        )}
      </DocCard>

      <Dialog open={confirmRegen} onOpenChange={setConfirmRegen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Write a new version?</DialogTitle>
            <DialogDescription>
              Your Mac writes a fresh resume and cover letter for this job (version {resume.version + 1}). The current
              version stays in history.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setConfirmRegen(false)}>
              Cancel
            </Button>
            <Button
              onClick={async () => {
                setConfirmRegen(false)
                await request('regenerate', 'Requested. Your Mac will write a new version shortly.')
              }}
            >
              Regenerate
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}
