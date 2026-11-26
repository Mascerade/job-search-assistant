/**
 * Apply assist (milestone 6): is a job ready for `/apply`? Mirrors `readiness()` in
 * pipeline/src/jobsearch/apply.py (the pipeline re-checks when `/apply` runs), plus the
 * "all good" lines the Help me apply dialog shows as a checklist.
 */
import type { JobDocuments } from './documents'
import type { ApplicationAnswers } from './profile'
import type { Job } from './types'

export type ReadinessLevel = 'ok' | 'block' | 'warn' | 'ask'
export interface ReadinessItem {
  level: ReadinessLevel
  text: string
}

const HOSTS: [string, string][] = [
  ['greenhouse.io', 'greenhouse'],
  ['lever.co', 'lever'],
  ['ashbyhq.com', 'ashby'],
  ['myworkdayjobs.com', 'workday'],
  ['smartrecruiters.com', 'smartrecruiters'],
]
const KNOWN_ATS = new Set(HOSTS.map(([, ats]) => ats))
const PAST_APPLYING = new Set(['applied', 'interviewing', 'offer', 'rejected', 'withdrawn'])

/** Which application system the job uses ("other" = an unfamiliar employer site). */
export function atsOf(job: Pick<Job, 'source' | 'url'>): string {
  if (KNOWN_ATS.has(job.source)) return job.source
  const url = (job.url ?? '').toLowerCase()
  return HOSTS.find(([host]) => url.includes(host))?.[1] ?? 'other'
}

/** The command to type in Claude Code: the same 8-character id the pipeline accepts. */
export const applyCommand = (job: Pick<Job, 'id'>) => `/apply ${job.id.slice(0, 8)}`

/** Show the button only while applying is still ahead (not after Applied and later). */
export const canApply = (job: Pick<Job, 'status'>) => !PAST_APPLYING.has(job.status)

export function applyReadiness(
  job: Pick<Job, 'status' | 'closed_at' | 'source' | 'url' | 'company'>,
  docs: JobDocuments | undefined,
  answers: ApplicationAnswers | null | undefined,
): ReadinessItem[] {
  const items: ReadinessItem[] = []
  const { resume, cover, suggestions } = docs ?? { resume: null, cover: null, suggestions: [] }
  const pending = suggestions.some((s) => s.decision === 'pending')
  if (!resume || !cover) {
    items.push({ level: 'block', text: 'No tailored resume and cover letter yet. Use Tailor now on the Documents tab.' })
  } else if (pending || resume.state === 'needs_approval' || cover.state === 'needs_approval') {
    items.push({ level: 'block', text: 'Suggestions are waiting for your approval on the Documents tab' })
  } else if (resume.state !== 'final' || cover.state !== 'final') {
    items.push({ level: 'block', text: 'The documents are still being built' })
  } else {
    items.push({ level: 'ok', text: `Resume v${resume.version} and cover letter v${cover.version} are final` })
    items.push({ level: 'ok', text: 'No suggestions waiting for you' })
  }

  if (job.closed_at) items.push({ level: 'block', text: 'The employer closed this posting' })
  else items.push({ level: 'ok', text: 'Posting is still open' })
  if (PAST_APPLYING.has(job.status)) items.push({ level: 'block', text: `This job is already marked ${job.status}` })

  const ats = atsOf(job)
  if (ats === 'workday') {
    items.push({ level: 'warn', text: `Workday: sign in to ${job.company}'s careers site first. Claude never types passwords.` })
  } else if (job.source === 'adzuna' && ats === 'other') {
    items.push({ level: 'warn', text: "Adzuna link: Claude will find the form on the employer's page" })
  } else if (ats === 'other') {
    items.push({ level: 'warn', text: 'Unfamiliar application site: Claude will go slower and check more with you' })
  }

  if (!answers) {
    items.push({ level: 'ask', text: 'No application answers saved yet, so Claude will ask for each one (Profile page)' })
  } else {
    if (answers.work_authorized_us == null || answers.sponsorship_now == null)
      items.push({ level: 'ask', text: "Work authorization and sponsorship aren't set, so Claude will ask" })
    if (!answers.salary_expectation)
      items.push({ level: 'ask', text: "Salary expectation isn't set, so Claude will ask you on the form" })
  }
  return items
}
