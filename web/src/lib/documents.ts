/**
 * Tailored documents (milestone 4): types for the preview the pipeline stores in
 * documents.content.preview, plus data hooks. Decisions on suggestions are the only
 * thing the website writes; the Mac renders PDFs when nothing is pending.
 */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useEffect, useRef } from 'react'
import { supabase } from './supabase'
import type { Database } from './database.types'

type Public = Database['public']
export type DocumentRow = Public['Tables']['documents']['Row']
export type SuggestionRow = Public['Tables']['suggestions']['Row']
export type TaskRow = Public['Tables']['tasks']['Row']
export type TaskKind = 'tailor' | 'regenerate' | 'render'

export interface PreviewLine {
  path: string
  text: string
  suggestion: boolean
}

export interface ResumePreview {
  headline: string | null
  summary: PreviewLine | null
  sections: { heading: string; items: { title: string; subtitle: string; lines: PreviewLine[] }[] }[]
  skills: string[]
  suggested_skills: PreviewLine[]
}

export interface CoverPreview {
  greeting: string
  paragraphs: PreviewLine[]
  closing: string
}

export interface JobDocuments {
  resume: DocumentRow | null
  cover: DocumentRow | null
  suggestions: SuggestionRow[]
}

const docKeys = {
  docs: (jobId: string) => ['jobs', jobId, 'documents'] as const,
  task: (jobId: string) => ['jobs', jobId, 'task'] as const,
}

export function preview<T>(doc: DocumentRow | null): T | null {
  const content = doc?.content as { preview?: T } | null
  return content?.preview ?? null
}

export function useDocuments(jobId: string) {
  return useQuery({
    queryKey: docKeys.docs(jobId),
    queryFn: async (): Promise<JobDocuments> => {
      const { data: docs, error } = await supabase
        .from('documents')
        .select('*')
        .eq('job_id', jobId)
        .order('version', { ascending: false })
      if (error) throw new Error(error.message)
      const resume = docs.find((d) => d.kind === 'resume') ?? null
      const cover = docs.find((d) => d.kind === 'cover_letter') ?? null
      const ids = [resume?.id, cover?.id].filter((x): x is string => !!x)
      if (!ids.length) return { resume, cover, suggestions: [] }
      const { data: suggestions, error: sErr } = await supabase
        .from('suggestions')
        .select('*')
        .in('document_id', ids)
        .order('path')
      if (sErr) throw new Error(sErr.message)
      return { resume, cover, suggestions }
    },
  })
}

const ACTIVE_STEPS = new Set(['queued', 'writing', 'rendering'])

/** The most recent button press for this job; polls while the Mac is working on it. */
export function useLatestTask(jobId: string) {
  return useQuery({
    queryKey: docKeys.task(jobId),
    queryFn: async () => {
      const { data, error } = await supabase
        .from('tasks')
        .select('*')
        .eq('job_id', jobId)
        .order('created_at', { ascending: false })
        .limit(1)
        .maybeSingle()
      if (error) throw new Error(error.message)
      return data
    },
    refetchInterval: (q) => (q.state.data && ACTIVE_STEPS.has(q.state.data.step) ? 5000 : false),
  })
}

export function isActive(task: TaskRow | null | undefined): boolean {
  return !!task && ACTIVE_STEPS.has(task.step)
}

/** When a task finishes, refresh the documents and the job (not the task query itself). */
export function useRefreshWhenTaskFinishes(jobId: string, task: TaskRow | null | undefined) {
  const qc = useQueryClient()
  const step = task?.step
  const wasActive = useRef(false)
  useEffect(() => {
    const active = !!step && ACTIVE_STEPS.has(step)
    if (wasActive.current && !active) {
      qc.invalidateQueries({ queryKey: docKeys.docs(jobId) })
      qc.invalidateQueries({ queryKey: ['jobs', jobId], exact: true })
      qc.invalidateQueries({ queryKey: ['jobs'], exact: true })
    }
    wasActive.current = active
  }, [step, jobId, qc])
}

export function useCreateTask(jobId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (kind: TaskKind) => {
      const { error } = await supabase.from('tasks').insert({ job_id: jobId, kind })
      if (error) throw new Error(error.message)
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: docKeys.task(jobId) }),
  })
}

export function useDecideSuggestion(jobId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (args: { id: string; decision: 'approved' | 'rejected' | 'pending'; finalText?: string | null }) => {
      const { error } = await supabase
        .from('suggestions')
        .update({
          decision: args.decision,
          decided_at: args.decision === 'pending' ? null : new Date().toISOString(),
          ...(args.finalText !== undefined ? { final_text: args.finalText } : {}),
        })
        .eq('id', args.id)
      if (error) throw new Error(error.message)
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: docKeys.docs(jobId) }),
  })
}

/** A short-lived download link for a private file. */
export async function downloadUrl(path: string): Promise<string> {
  const { data, error } = await supabase.storage.from('documents').createSignedUrl(path, 60, { download: true })
  if (error) throw new Error(error.message)
  return data.signedUrl
}
