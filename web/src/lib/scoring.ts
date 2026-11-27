/**
 * "Score now" on the Today page. The site leaves a score task; the Mac's listener scores
 * every job waiting to be scored (the same scoring as the 7:30 morning run) and writes its
 * progress into the task's `result` after each batch of ten.
 */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useEffect, useRef, useState } from 'react'
import type { Database } from './database.types'
import { keys } from './queries'
import { supabase } from './supabase'

type TaskRow = Database['public']['Tables']['tasks']['Row']

export interface ScoreProgress {
  total: number
  scored: number
  matches: number
  failed: number
}

export type ScoreState =
  | { kind: 'idle' }
  | { kind: 'queued' } // left for the Mac; it may be asleep
  | { kind: 'behind' } // another scoring run (the morning run) is going; this one is next
  | { kind: 'scoring'; progress: ScoreProgress }
  | { kind: 'paused'; progress: ScoreProgress } // no word from the Mac for a while
  | { kind: 'done'; id: string; progress: ScoreProgress }
  | { kind: 'error'; id: string; message: string }

/** A running task that hasn't reported for this long has probably stopped (the Mac slept). */
const QUIET_MS = 10 * 60 * 1000
/** How long the result stays on the page after scoring finishes. */
const SHOW_RESULT_MS = 30 * 60 * 1000

const scoreKeys = {
  task: ['score-task'] as const,
  waiting: ['jobs', 'waiting-to-score'] as const,
}

function progressOf(result: TaskRow['result']): ScoreProgress & { waiting: boolean } {
  const r = result && typeof result === 'object' && !Array.isArray(result) ? result : {}
  const num = (k: string) => (typeof r[k] === 'number' ? (r[k] as number) : 0)
  return { total: num('total'), scored: num('scored'), matches: num('matches'), failed: num('failed'), waiting: r.waiting === true }
}

export function scoreState(task: TaskRow | null | undefined, now: number): ScoreState {
  if (!task) return { kind: 'idle' }
  const age = now - new Date(task.updated_at).getTime()
  const p = progressOf(task.result)
  switch (task.step) {
    case 'queued':
      return { kind: 'queued' }
    case 'scoring':
      if (age > QUIET_MS) return { kind: 'paused', progress: p }
      return p.waiting ? { kind: 'behind' } : { kind: 'scoring', progress: p }
    case 'ready':
      return age < SHOW_RESULT_MS ? { kind: 'done', id: task.id, progress: p } : { kind: 'idle' }
    case 'error':
      return age < SHOW_RESULT_MS
        ? { kind: 'error', id: task.id, message: task.error ?? 'Something went wrong on the Mac.' }
        : { kind: 'idle' }
    default:
      return { kind: 'idle' }
  }
}

export function isRunning(state: ScoreState): boolean {
  return state.kind === 'queued' || state.kind === 'behind' || state.kind === 'scoring'
}

/** The newest score task, checked every few seconds while it runs. */
export function useScoreTask() {
  return useQuery({
    queryKey: scoreKeys.task,
    queryFn: async () => {
      const { data, error } = await supabase
        .from('tasks')
        .select('*')
        .eq('kind', 'score')
        .order('created_at', { ascending: false })
        .limit(1)
        .maybeSingle()
      if (error) throw new Error(error.message)
      return data
    },
    refetchInterval: (q) => (q.state.data && ['queued', 'scoring'].includes(q.state.data.step) ? 4000 : false),
  })
}

/** Jobs that passed the filters and haven't been scored yet (the pipeline's jobs_to_score). */
export function useWaitingToScore(running: boolean) {
  return useQuery({
    queryKey: scoreKeys.waiting,
    queryFn: async () => {
      const { count, error } = await supabase
        .from('jobs')
        .select('id', { count: 'exact', head: true })
        .eq('pipeline_state', 'new')
        .is('fit_score', null)
        .is('closed_at', null)
      if (error) throw new Error(error.message)
      return count ?? 0
    },
    refetchInterval: running ? 5000 : false,
  })
}

export function useStartScoring() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async () => {
      const { error } = await supabase.from('tasks').insert({ kind: 'score' })
      if (error) throw new Error(error.message)
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: scoreKeys.task }),
  })
}

/** Reload the job list as each batch of scores lands, and once more when scoring ends. */
export function useRefreshAsScoresArrive(task: TaskRow | null | undefined) {
  const qc = useQueryClient()
  const scored = progressOf(task?.result ?? null).scored
  const step = task?.step
  const last = useRef<{ scored: number; step: string | undefined } | null>(null)
  useEffect(() => {
    const before = last.current
    last.current = { scored, step }
    if (!before) return // first load: nothing has changed yet
    const finished = before.step === 'scoring' && step !== 'scoring'
    if (scored !== before.scored || finished) {
      qc.invalidateQueries({ queryKey: keys.jobs, exact: true })
      qc.invalidateQueries({ queryKey: scoreKeys.waiting })
    }
    if (finished) qc.invalidateQueries({ queryKey: keys.runs })
  }, [scored, step, qc])
}

/** The current time, refreshed every half minute (so "paused" and old results update on their own). */
export function useNow(everyMs = 30_000): number {
  const [now, setNow] = useState(() => Date.now())
  useEffect(() => {
    const timer = setInterval(() => setNow(Date.now()), everyMs)
    return () => clearInterval(timer)
  }, [everyMs])
  return now
}
