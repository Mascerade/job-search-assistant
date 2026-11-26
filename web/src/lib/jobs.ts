import type { TagColor } from '@/components/Tag'
import type { Job } from './types'

/** Jobs the pipeline rejected stay out of Today and the Board unless you've acted on them. */
export function isAutoRejected(job: Job): boolean {
  if (job.source === 'manual') return false // jobs you add yourself always stay visible
  return job.status === 'new' && (job.pipeline_state === 'filtered_out' || job.pipeline_state === 'below_threshold')
}

/** Waiting for a decision: new or docs ready, not rejected by the pipeline, posting still open. */
export function needsReview(job: Job): boolean {
  return (job.status === 'new' || job.status === 'docs_ready') && !isAutoRejected(job) && !job.closed_at
}


/** Tag colors for job tags (always shown with their label). */
export const TAG_COLOR: Record<string, TagColor> = {
  'staffing-agency': 'orange',
  'short-description': 'yellow',
  'location-unclear': 'gray',
}

export const TAG_LABEL: Record<string, string> = {
  'location-unclear': 'Location unclear',
  // Adzuna only shares a snippet of the posting; the full text is behind the job link.
  'short-description': 'Short description',
  // Posted by a recruiting agency for another employer; tailored after direct-employer matches.
  'staffing-agency': 'Staffing agency',
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
