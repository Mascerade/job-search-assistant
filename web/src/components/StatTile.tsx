import type { ReactNode } from 'react'
import { cn } from '@/lib/utils'

/** A headline number: label, value, and a short note. Flat, hairline border. */
export function StatTile({
  label,
  value,
  note,
  className,
}: {
  label: string
  value: ReactNode
  note?: ReactNode
  className?: string
}) {
  return (
    <div className={cn('flex min-w-0 flex-col gap-1 rounded-lg border bg-card p-4', className)}>
      <span className="text-sm text-muted-foreground">{label}</span>
      <span className="text-[1.75rem] leading-9 font-semibold tracking-tight">{value}</span>
      {note && <span className="text-xs text-muted-foreground">{note}</span>}
    </div>
  )
}
