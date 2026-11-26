import {
  Ban,
  CircleDashed,
  FileCheck2,
  MessagesSquare,
  PartyPopper,
  Send,
  ThumbsDown,
  Undo2,
  type LucideIcon,
} from 'lucide-react'
import type { ApplicationStatus, JobTrack } from './types'

export interface StatusMeta {
  label: string
  icon: LucideIcon
  /** Tailwind classes for text + background; always shown together with icon + label. */
  className: string
  description: string
}

export const STATUS_ORDER: ApplicationStatus[] = [
  'new',
  'docs_ready',
  'applied',
  'interviewing',
  'offer',
  'rejected',
  'withdrawn',
  'not_interested',
]

export const CLOSED_STATUSES: ApplicationStatus[] = ['rejected', 'withdrawn', 'not_interested']

export const STATUS: Record<ApplicationStatus, StatusMeta> = {
  new: {
    label: 'New',
    icon: CircleDashed,
    className: 'text-status-new bg-status-new-bg',
    description: 'Found, not yet reviewed',
  },
  docs_ready: {
    label: 'Docs ready',
    icon: FileCheck2,
    className: 'text-status-docs-ready bg-status-docs-ready-bg',
    description: 'Resume and cover letter are ready to send',
  },
  applied: {
    label: 'Applied',
    icon: Send,
    className: 'text-status-applied bg-status-applied-bg',
    description: 'Application submitted',
  },
  interviewing: {
    label: 'Interviewing',
    icon: MessagesSquare,
    className: 'text-status-interviewing bg-status-interviewing-bg',
    description: 'In conversation with the employer',
  },
  offer: {
    label: 'Offer',
    icon: PartyPopper,
    className: 'text-status-offer bg-status-offer-bg',
    description: 'Received an offer',
  },
  rejected: {
    label: 'Rejected',
    icon: ThumbsDown,
    className: 'text-status-rejected bg-status-rejected-bg',
    description: 'The employer said no',
  },
  withdrawn: {
    label: 'Withdrawn',
    icon: Undo2,
    className: 'text-status-closed bg-status-closed-bg',
    description: 'I withdrew my application',
  },
  not_interested: {
    label: 'Not interested',
    icon: Ban,
    className: 'text-status-closed bg-status-closed-bg',
    description: 'Skipped this one',
  },
}

export const TRACK_ORDER: JobTrack[] = ['software', 'program_admin', 'hybrid']

/** One color per track, everywhere (tags, cards, charts): the chart series colors, in fixed order. */
export const TRACK_SWATCH: Record<JobTrack, string> = {
  software: 'bg-chart-1',
  hybrid: 'bg-chart-2',
  program_admin: 'bg-chart-3',
}

export const TRACK_LABEL: Record<JobTrack, string> = {
  software: 'Software & ML',
  program_admin: 'Program admin',
  hybrid: 'University tech',
}

/** Fit score → word, so the score is never conveyed by color alone. */
export function fitLabel(score: number): string {
  if (score >= 85) return 'Strong'
  if (score >= 70) return 'Good'
  if (score >= 50) return 'Fair'
  return 'Weak'
}
