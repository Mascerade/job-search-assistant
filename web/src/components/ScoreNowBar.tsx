import { CircleAlert, CircleCheck, Gauge, LoaderCircle, X, type LucideIcon } from 'lucide-react'
import { useState, type ReactNode } from 'react'
import { Button } from '@/components/ui/button'
import {
  isRunning,
  scoreState,
  useRefreshAsScoresArrive,
  useScoreTask,
  useNow,
  useStartScoring,
  useWaitingToScore,
  type ScoreProgress,
  type ScoreState,
} from '@/lib/scoring'
import { cn } from '@/lib/utils'

function plural(n: number, one: string, many: string): string {
  return `${n} ${n === 1 ? one : many}`
}

interface View {
  icon: LucideIcon
  tone?: string
  spin?: boolean
  message: ReactNode
  progress?: ScoreProgress
  action?: ReactNode
}

function view(state: ScoreState, waiting: number, startButton: (label: string) => ReactNode): View {
  const again = (label: string) => (waiting > 0 ? startButton(label) : null)
  switch (state.kind) {
    case 'queued':
      return {
        icon: LoaderCircle,
        spin: true,
        message: (
          <>
            <span className="font-medium">Waiting for your Mac…</span> Scoring starts as soon as it's awake and online.
          </>
        ),
      }
    case 'behind':
      return {
        icon: LoaderCircle,
        spin: true,
        message: (
          <>
            <span className="font-medium">Your Mac is already scoring.</span> This starts as soon as that run
            finishes.
          </>
        ),
      }
    case 'scoring': {
      const { scored, total, matches } = state.progress
      return {
        icon: LoaderCircle,
        spin: true,
        progress: state.progress,
        message:
          total === 0 ? (
            <span className="font-medium">Starting…</span>
          ) : (
            <>
              <span className="font-medium">
                Scoring {scored} of {total}…
              </span>{' '}
              {plural(matches, 'match', 'matches')} so far. They appear below as they're scored.
            </>
          ),
      }
    }
    case 'paused':
      return {
        icon: CircleAlert,
        tone: 'text-warning-text',
        progress: state.progress,
        message: (
          <>
            <span className="font-medium">Scoring paused.</span> Your Mac may be asleep. It picks up again when the
            Mac wakes; if it doesn't, start it again.
          </>
        ),
        action: again('Start again'),
      }
    case 'done': {
      const { scored, matches, failed } = state.progress
      return {
        icon: CircleCheck,
        tone: 'text-success-text',
        message:
          scored === 0 && failed === 0 ? (
            <span className="font-medium">Nothing was waiting to be scored.</span>
          ) : (
            <>
              <span className="font-medium">
                Scored {plural(scored, 'job', 'jobs')}: {plural(matches, 'match', 'matches')}.
              </span>
              {failed > 0 && ` ${plural(failed, "job couldn't", "jobs couldn't")} be scored; the morning run tries again.`}
            </>
          ),
        action: again('Score now'),
      }
    }
    case 'error':
      return {
        icon: CircleAlert,
        tone: 'text-destructive',
        message: (
          <>
            <span className="font-medium">Scoring didn't finish.</span> {state.message}
          </>
        ),
        action: again('Try again'),
      }
    case 'idle':
      return {
        icon: Gauge,
        message: (
          <>
            <span className="font-medium">{plural(waiting, 'new job', 'new jobs')} waiting to be scored.</span> Your
            Mac scores them every morning at 7:30, or now if you'd rather not wait.
          </>
        ),
        action: startButton('Score now'),
      }
  }
}

/**
 * Today page: jobs waiting to be scored, with a "Score now" button so they don't have to
 * wait for the 7:30 morning run. Shows the Mac's progress while it scores, then the result.
 * Hidden when nothing is waiting and nothing has happened recently.
 */
export function ScoreNowBar() {
  const { data: task } = useScoreTask()
  const [dismissed, setDismissed] = useState<string | null>(null)
  const now = useNow()
  const latest = scoreState(task, now)
  const finished = latest.kind === 'done' || latest.kind === 'error'
  const state: ScoreState = finished && latest.id === dismissed ? { kind: 'idle' } : latest
  const { data: waiting = 0 } = useWaitingToScore(isRunning(state))
  const start = useStartScoring()
  useRefreshAsScoresArrive(task)

  if (state.kind === 'idle' && waiting === 0) return null

  const startButton = (label: string) => (
    <Button variant="outline" onClick={() => start.mutate()} disabled={start.isPending}>
      {start.isPending && <LoaderCircle className="motion-safe:animate-spin" data-icon="inline-start" aria-hidden="true" />}
      {label}
    </Button>
  )
  const dismissButton =
    state.kind === 'done' || state.kind === 'error' ? (
      <Button variant="ghost" size="icon-sm" aria-label="Dismiss" onClick={() => setDismissed(state.id)}>
        <X />
      </Button>
    ) : null

  const v = view(state, waiting, startButton)
  const { icon: Icon, tone = 'text-muted-foreground', spin = false, progress, action } = v
  const pct = progress && progress.total > 0 ? Math.min(progress.scored / progress.total, 1) : 0
  return (
    <section
      aria-label="Scoring"
      className="mb-6 flex flex-col gap-3 rounded-lg border bg-card px-4 py-3 text-sm sm:flex-row sm:items-center"
    >
      <div className="flex min-w-0 flex-1 items-start gap-3">
        <Icon className={cn('mt-0.5 size-4 shrink-0', tone, spin && 'motion-safe:animate-spin')} aria-hidden="true" />
        <div className="min-w-0 flex-1">
          <p aria-live="polite">{v.message}</p>
          {progress && progress.total > 0 && (
            <div
              role="progressbar"
              aria-label="Jobs scored"
              aria-valuemin={0}
              aria-valuemax={progress.total}
              aria-valuenow={progress.scored}
              className="mt-2 h-1.5 w-full max-w-sm overflow-hidden rounded-full bg-muted"
            >
              <div
                className="h-full origin-left rounded-full bg-primary motion-safe:transition-transform motion-safe:duration-500"
                style={{ transform: `scaleX(${pct})` }}
              />
            </div>
          )}
          {start.error && (
            <p role="alert" className="mt-1 text-destructive">
              Couldn't ask the Mac to score: {start.error.message}
            </p>
          )}
        </div>
      </div>
      {(action || dismissButton) && (
        <div className="flex shrink-0 items-center gap-2 pl-7 sm:pl-0">
          {action}
          {dismissButton}
        </div>
      )}
    </section>
  )
}
