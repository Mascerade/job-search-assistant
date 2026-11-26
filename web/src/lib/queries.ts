/**
 * Data hooks. The website talks to Supabase directly; row-level security makes
 * sure only the owner account can read or write anything.
 */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import type { Json } from './database.types'
import { supabase } from './supabase'
import type { AppSettings, ApplicationStatus, Job, JobInsert, JobUpdate } from './types'

export const keys = {
  jobs: ['jobs'] as const,
  job: (id: string) => ['jobs', id] as const,
  history: (id: string) => ['jobs', id, 'history'] as const,
  score: (id: string) => ['jobs', id, 'score'] as const,
  settings: ['settings'] as const,
  profile: ['profile'] as const,
  profileVersions: ['profile', 'versions'] as const,
  runs: ['runs'] as const,
}

type JsonObject = { [key: string]: Json | undefined }

/** Throw on a Supabase error; otherwise return the (non-null) data. */
function unwrap<D>(result: { data: D; error: { message: string } | null }): NonNullable<D> {
  if (result.error) throw new Error(result.error.message)
  if (result.data === null || result.data === undefined) throw new Error('No data returned')
  return result.data as NonNullable<D>
}

/** Like unwrap, but a missing row is fine (returns null). */
function unwrapMaybe<D>(result: { data: D; error: { message: string } | null }): D {
  if (result.error) throw new Error(result.error.message)
  return result.data
}

// ---------- Jobs ----------

export function useJobs() {
  return useQuery({
    queryKey: keys.jobs,
    queryFn: async () =>
      unwrap(
        await supabase
          .from('jobs')
          .select('*')
          .order('first_seen_at', { ascending: false })
          .limit(1000),
      ),
  })
}

export function useJob(id: string) {
  return useQuery({
    queryKey: keys.job(id),
    queryFn: async () => unwrapMaybe(await supabase.from('jobs').select('*').eq('id', id).maybeSingle()),
  })
}

export function useStatusHistory(jobId: string) {
  return useQuery({
    queryKey: keys.history(jobId),
    queryFn: async () =>
      unwrap(
        await supabase
          .from('status_history')
          .select('*')
          .eq('job_id', jobId)
          .order('changed_at', { ascending: false }),
      ),
  })
}

export function useCreateJob() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (job: JobInsert) =>
      unwrap(await supabase.from('jobs').insert(job).select('*').single()),
    onSuccess: () => qc.invalidateQueries({ queryKey: keys.jobs }),
  })
}

export function useUpdateJob() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async ({ id, patch }: { id: string; patch: JobUpdate }) =>
      unwrap(await supabase.from('jobs').update(patch).eq('id', id).select('*').single()),
    // Optimistic update so status changes feel instant on the board.
    onMutate: async ({ id, patch }) => {
      await qc.cancelQueries({ queryKey: keys.jobs })
      const previous = qc.getQueryData<Job[]>(keys.jobs)
      qc.setQueryData<Job[]>(keys.jobs, (jobs) =>
        jobs?.map((j) => (j.id === id ? ({ ...j, ...patch } as Job) : j)),
      )
      qc.setQueryData<Job | null>(keys.job(id), (job) => (job ? ({ ...job, ...patch } as Job) : job))
      return { previous }
    },
    onError: (_err, _vars, ctx) => {
      if (ctx?.previous) qc.setQueryData(keys.jobs, ctx.previous)
    },
    onSettled: (_data, _err, { id }) => {
      qc.invalidateQueries({ queryKey: keys.jobs })
      qc.invalidateQueries({ queryKey: keys.history(id) })
    },
  })
}

export function useSetStatus() {
  const update = useUpdateJob()
  return {
    ...update,
    setStatus: (id: string, status: ApplicationStatus) => update.mutateAsync({ id, patch: { status } }),
  }
}

export function useDeleteJob() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (id: string) => {
      const { error } = await supabase.from('jobs').delete().eq('id', id)
      if (error) throw new Error(error.message)
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: keys.jobs }),
  })
}

export interface ScoreDetails {
  years_required?: number | null
  immediate_start?: boolean
  concerns?: string[]
}

/** The most recent AI score for a job (reason + structured details), if any. */
export function useLatestScore(jobId: string) {
  return useQuery({
    queryKey: keys.score(jobId),
    queryFn: async () => {
      const row = unwrapMaybe(
        await supabase
          .from('scores')
          .select('score, reason, model, details, created_at')
          .eq('job_id', jobId)
          .order('created_at', { ascending: false })
          .limit(1)
          .maybeSingle(),
      )
      return row ? { ...row, details: (row.details ?? {}) as ScoreDetails } : null
    },
  })
}

// ---------- Settings ----------

export function useSettings() {
  return useQuery({
    queryKey: keys.settings,
    queryFn: async () => {
      const row = unwrapMaybe(await supabase.from('settings').select('*').eq('id', 1).maybeSingle())
      return (row?.data ?? null) as AppSettings | null
    },
  })
}

export function useSaveSettings() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (data: AppSettings) =>
      unwrap(
        await supabase
          .from('settings')
          .update({ data: data as unknown as JsonObject })
          .eq('id', 1)
          .select('*')
          .single(),
      ),
    onSuccess: () => qc.invalidateQueries({ queryKey: keys.settings }),
  })
}

// ---------- Profile ----------

export function useProfileVersions() {
  return useQuery({
    queryKey: keys.profileVersions,
    queryFn: async () =>
      unwrap(
        await supabase
          .from('profile_versions')
          .select('*')
          .order('version', { ascending: false })
          .limit(50),
      ),
  })
}

/** The newest saved profile, read fresh (not from the cache) right before a save. */
export async function fetchLatestProfile(): Promise<{ version: number; data: Record<string, unknown> } | null> {
  const row = unwrapMaybe(
    await supabase.from('profile_versions').select('version, data').order('version', { ascending: false }).limit(1).maybeSingle(),
  )
  return row ? { version: row.version, data: row.data as Record<string, unknown> } : null
}

/**
 * Saves a new profile version. `baseVersion` is the version the edit started from: if a newer
 * one was saved meanwhile (the daily run learns skills, apply assist saves answers), refuse
 * instead of silently overwriting it.
 */
export function useSaveProfile() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async ({ data, note, baseVersion }: { data: Record<string, unknown>; note: string; baseVersion?: number }) => {
      if (baseVersion !== undefined) {
        const latest = unwrapMaybe(
          await supabase.from('profile_versions').select('version').order('version', { ascending: false }).limit(1).maybeSingle(),
        )
        if (latest && latest.version !== baseVersion) {
          throw new Error(
            `your profile changed since you opened it (now version ${latest.version}). Copy your edits, reload, and try again.`,
          )
        }
      }
      return unwrap(
        await supabase
          .from('profile_versions')
          .insert({ data: data as JsonObject, note })
          .select('*')
          .single(),
      )
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: keys.profile }),
  })
}

// ---------- Runs ----------

export function useRuns() {
  return useQuery({
    queryKey: keys.runs,
    queryFn: async () =>
      unwrap(await supabase.from('runs').select('*').order('started_at', { ascending: false }).limit(60)),
  })
}
