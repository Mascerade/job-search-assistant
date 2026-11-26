import type { LucideIcon } from 'lucide-react'
import type { ReactNode } from 'react'
import { TRACK_LABEL, TRACK_SWATCH } from '@/lib/status'
import type { JobTrack } from '@/lib/types'
import { cn } from '@/lib/utils'

export type TagColor = 'gray' | 'brown' | 'orange' | 'yellow' | 'green' | 'blue' | 'purple' | 'pink' | 'red'

const COLOR: Record<TagColor, string> = {
  gray: 'bg-tag-gray-bg text-tag-gray-fg',
  brown: 'bg-tag-brown-bg text-tag-brown-fg',
  orange: 'bg-tag-orange-bg text-tag-orange-fg',
  yellow: 'bg-tag-yellow-bg text-tag-yellow-fg',
  green: 'bg-tag-green-bg text-tag-green-fg',
  blue: 'bg-tag-blue-bg text-tag-blue-fg',
  purple: 'bg-tag-purple-bg text-tag-purple-fg',
  pink: 'bg-tag-pink-bg text-tag-pink-fg',
  red: 'bg-tag-red-bg text-tag-red-fg',
}

/** Notion-style select tag: a pastel fill with readable text (every pair >= 6:1). */
export function Tag({
  color = 'gray',
  icon: Icon,
  className,
  children,
}: {
  color?: TagColor
  icon?: LucideIcon
  className?: string
  children: ReactNode
}) {
  return (
    <span
      className={cn(
        'inline-flex items-center gap-1 rounded-sm px-1.5 py-0.5 text-xs leading-4 font-medium whitespace-nowrap',
        COLOR[color],
        className,
      )}
    >
      {Icon && <Icon className="size-3.5" aria-hidden="true" />}
      {children}
    </span>
  )
}

/** Role type: a gray tag with a dot in the track's chart color (the label carries the meaning). */
export function TrackTag({ track, className }: { track: JobTrack; className?: string }) {
  return (
    <Tag className={cn('gap-1.5', className)}>
      <span aria-hidden="true" className={cn('size-2 rounded-full', TRACK_SWATCH[track])} />
      {TRACK_LABEL[track]}
    </Tag>
  )
}
