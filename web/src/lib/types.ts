import type { Database } from './database.types'

type Public = Database['public']

export type Job = Public['Tables']['jobs']['Row']
export type JobInsert = Public['Tables']['jobs']['Insert']
export type JobUpdate = Public['Tables']['jobs']['Update']
export type StatusHistory = Public['Tables']['status_history']['Row']
export type Run = Public['Tables']['runs']['Row']
export type ProfileVersion = Public['Tables']['profile_versions']['Row']

export type ApplicationStatus = Public['Enums']['application_status']
export type JobTrack = Public['Enums']['job_track']
export type RemoteType = 'onsite' | 'hybrid' | 'remote'

export interface Contact {
  name: string
  role?: string
  email?: string
  note?: string
}

/** Shape of settings.data (see the seed row in the initial migration). */
export interface AppSettings {
  fit_threshold: number
  monthly_spend_cap_usd: number
  experience_max_years: number
  full_time_only: boolean
  exclude_clearance: boolean
  tracks: Record<JobTrack, { enabled: boolean; keywords: string[] }>
  /** YYYY-MM-DD. Until then the daily documents go software → hybrid → admin; null = best fit. */
  focus_until?: string | null
  /** YYYY-MM-DD: the first day you can start a job. The Start column compares postings with it. */
  available_from?: string
  locations: { include_remote_us: boolean; include_hybrid: boolean; towns: string[] }
}
