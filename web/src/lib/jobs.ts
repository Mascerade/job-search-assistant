import type { Job } from './types'

/** Jobs the pipeline rejected stay out of Today and the Board unless you've acted on them. */
export function isAutoRejected(job: Job): boolean {
  return job.status === 'new' && (job.pipeline_state === 'filtered_out' || job.pipeline_state === 'below_threshold')
}

/** Waiting for a decision: new or docs ready, not rejected by the pipeline, posting still open. */
export function needsReview(job: Job): boolean {
  return (job.status === 'new' || job.status === 'docs_ready') && !isAutoRejected(job) && !job.closed_at
}

export const TAG_LABEL: Record<string, string> = {
  'location-unclear': 'Location unclear',
  'immediate-start': 'Wants someone soon',
}

const AGGREGATORS: Partial<Record<Job['source'], string>> = {
  adzuna: 'Adzuna',
  jsearch: 'JSearch',
  higheredjobs: 'HigherEdJobs',
}

/** Where a job was found, in plain words: "Harvard University's careers site", "Adzuna", or null if you added it. */
export function sourceLabel(job: Pick<Job, 'source' | 'company'>): string | null {
  if (job.source === 'manual') return null
  return AGGREGATORS[job.source] ?? `${job.company}'s careers site`
}
