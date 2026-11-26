import { fitLabel } from '@/lib/status'
import { cn } from '@/lib/utils'

/**
 * Fit score as "85 · Strong": a number plus a word (never color alone), with an
 * optional small meter as decoration. `compact` drops the meter for narrow cards.
 */
export function FitScore({
  score,
  compact = false,
  className,
}: {
  score: number | null
  compact?: boolean
  className?: string
}) {
  if (score === null) {
    return <span className={cn('text-sm whitespace-nowrap text-muted-foreground', className)}>Not scored</span>
  }
  const label = fitLabel(score)
  return (
    <span
      className={cn('inline-flex items-center gap-2 whitespace-nowrap', className)}
      aria-label={`Fit score ${score} out of 100, ${label}`}
    >
      <span className="font-mono text-sm font-medium tabular-nums">{score}</span>
      <span className="text-sm text-muted-foreground">· {label}</span>
      {!compact && (
        <span aria-hidden="true" className="hidden h-1.5 w-12 overflow-hidden rounded-full bg-muted sm:inline-block">
          <span className="block h-full rounded-full bg-primary" style={{ width: `${score}%` }} />
        </span>
      )}
    </span>
  )
}
