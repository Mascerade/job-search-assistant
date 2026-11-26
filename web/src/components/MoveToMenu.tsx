import { ArrowRightLeft, Check, Ellipsis } from 'lucide-react'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { useSetStatus } from '@/lib/queries'
import { STATUS, STATUS_ORDER } from '@/lib/status'
import type { ApplicationStatus, Job } from '@/lib/types'

/**
 * "Move to…" menu: the click/keyboard alternative to dragging a card on the board
 * (WCAG 2.2 "dragging movements"). Also used on the job detail page.
 */
export function MoveToMenu({
  job,
  variant = 'icon',
}: {
  job: Pick<Job, 'id' | 'status' | 'title'>
  variant?: 'icon' | 'full'
}) {
  const { setStatus } = useSetStatus()

  async function move(status: ApplicationStatus) {
    if (status === job.status) return
    try {
      await setStatus(job.id, status)
      toast.success(`Moved to ${STATUS[status].label}`)
    } catch (e) {
      toast.error(`Couldn't update status: ${(e as Error).message}`)
    }
  }

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        {variant === 'icon' ? (
          <Button variant="ghost" size="icon-sm" aria-label={`Move "${job.title}" to another status`}>
            <Ellipsis />
          </Button>
        ) : (
          <Button variant="outline">
            <ArrowRightLeft data-icon="inline-start" />
            Move to…
          </Button>
        )}
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-52">
        <DropdownMenuLabel>Move to</DropdownMenuLabel>
        <DropdownMenuSeparator />
        {STATUS_ORDER.map((s) => {
          const Icon = STATUS[s].icon
          const current = s === job.status
          return (
            <DropdownMenuItem key={s} disabled={current} onSelect={() => move(s)}>
              <Icon aria-hidden="true" />
              {STATUS[s].label}
              {current && <Check className="ml-auto" aria-label="current status" />}
            </DropdownMenuItem>
          )
        })}
      </DropdownMenuContent>
    </DropdownMenu>
  )
}
