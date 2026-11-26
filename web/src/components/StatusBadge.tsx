import { STATUS } from '@/lib/status'
import type { ApplicationStatus } from '@/lib/types'
import { cn } from '@/lib/utils'

/** Status = color + icon + text label (never color alone). */
export function StatusBadge({ status, className }: { status: ApplicationStatus; className?: string }) {
  const meta = STATUS[status]
  const Icon = meta.icon
  return (
    <span
      className={cn(
        'inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs font-medium whitespace-nowrap',
        meta.className,
        className,
      )}
    >
      <Icon className="size-3.5" aria-hidden="true" />
      {meta.label}
    </span>
  )
}
