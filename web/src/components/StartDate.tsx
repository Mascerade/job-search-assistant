import { Tag } from '@/components/Tag'
import { formatDay, startFit, startWindowLabel, termEndsSoon, type StartFields } from '@/lib/timing'
import { cn } from '@/lib/utils'

/**
 * The tags that make timing stand out (always a text label, never color alone):
 * green "After graduation", gray "Before graduation", red "Ends <date>" for a term that ends
 * within ~3 months of the day you can start.
 */
export function StartTags({ job, availableFrom }: { job: StartFields; availableFrom: string }) {
  const fit = startFit(job, availableFrom)
  return (
    <>
      {fit === 'after' && <Tag color="green">After graduation</Tag>}
      {fit === 'before' && <Tag color="gray">Before graduation</Tag>}
      {job.term_end && termEndsSoon(job, availableFrom) && <Tag color="red">Ends {formatDay(job.term_end)}</Tag>}
    </>
  )
}

/** Today's Start column: the window on top, then its tag or the term's end date. */
export function StartCell({ job, availableFrom }: { job: StartFields; availableFrom: string }) {
  const label = startWindowLabel(job)
  const quiet = job.start_kind !== 'date' && job.start_kind !== 'asap'
  const termNote = job.term_end && !termEndsSoon(job, availableFrom) ? job.term_end : null
  return (
    <span className="flex flex-col items-start gap-1" title={job.start_note ?? undefined}>
      <span className={cn('text-sm whitespace-nowrap', quiet && 'text-muted-foreground')}>{label}</span>
      <StartTags job={job} availableFrom={availableFrom} />
      {termNote && (
        <span className="text-xs whitespace-nowrap text-muted-foreground">Term ends {formatDay(termNote)}</span>
      )}
    </span>
  )
}
