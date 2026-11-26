import type { JobInsert, JobTrack, RemoteType } from './types'

export interface JobFormValues {
  url: string
  company: string
  title: string
  location: string
  remote_type: RemoteType | ''
  track: JobTrack | ''
  salary_min: string
  salary_max: string
  description: string
}

export const EMPTY_JOB_FORM: JobFormValues = {
  url: '',
  company: '',
  title: '',
  location: '',
  remote_type: '',
  track: '',
  salary_min: '',
  salary_max: '',
  description: '',
}

export type JobFormErrors = Partial<Record<keyof JobFormValues, string>>

export function validateJobForm(v: JobFormValues): JobFormErrors {
  const errors: JobFormErrors = {}
  if (!v.company.trim()) errors.company = 'Enter the company or organization.'
  if (!v.title.trim()) errors.title = 'Enter the job title.'
  if (v.url.trim()) {
    try {
      const u = new URL(v.url.trim())
      if (!['http:', 'https:'].includes(u.protocol)) throw new Error()
    } catch {
      errors.url = 'Enter a full link starting with https://'
    }
  }
  const min = v.salary_min.trim() ? Number(v.salary_min) : null
  const max = v.salary_max.trim() ? Number(v.salary_max) : null
  if (min !== null && (!Number.isInteger(min) || min < 0)) errors.salary_min = 'Use a whole number, like 65000.'
  if (max !== null && (!Number.isInteger(max) || max < 0)) errors.salary_max = 'Use a whole number, like 80000.'
  if (min !== null && max !== null && !errors.salary_min && !errors.salary_max && min > max)
    errors.salary_max = 'The maximum should be at least the minimum.'
  return errors
}

export function toJobInsert(v: JobFormValues): JobInsert {
  const orNull = (s: string) => (s.trim() ? s.trim() : null)
  return {
    url: orNull(v.url),
    company: v.company.trim(),
    title: v.title.trim(),
    location: orNull(v.location),
    remote_type: v.remote_type || null,
    track: v.track || null,
    salary_min: v.salary_min.trim() ? Number(v.salary_min) : null,
    salary_max: v.salary_max.trim() ? Number(v.salary_max) : null,
    description: orNull(v.description),
  }
}

