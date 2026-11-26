import { CircleCheck, CircleX, ClipboardPen, Copy, Download, Laptop, TriangleAlert, type LucideIcon } from 'lucide-react'
import { useState } from 'react'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from '@/components/ui/dialog'
import { applyCommand, applyReadiness, type ReadinessLevel } from '@/lib/apply'
import { downloadUrl, useDocuments } from '@/lib/documents'
import type { Profile } from '@/lib/profile'
import { useProfileVersions } from '@/lib/queries'
import type { Job } from '@/lib/types'
import { cn } from '@/lib/utils'

const LEVEL: Record<ReadinessLevel, { icon: LucideIcon; className: string; label: string }> = {
  ok: { icon: CircleCheck, className: 'text-success-text', label: 'Ready' },
  block: { icon: CircleX, className: 'text-destructive', label: 'Needs fixing first' },
  warn: { icon: TriangleAlert, className: 'text-warning-text', label: 'Heads up' },
  ask: { icon: TriangleAlert, className: 'text-warning-text', label: 'Claude will ask' },
}

/**
 * Apply assist entry point: readiness, the `/apply` command to type in Claude Code on the Mac,
 * and the documents to download for applying by hand. Claude fills the form in Chrome and
 * stops before Submit (see .claude/skills/apply/SKILL.md).
 */
export function HelpMeApplyDialog({ job, primary = true }: { job: Job; primary?: boolean }) {
  const [open, setOpen] = useState(false)
  const { data: docs } = useDocuments(job.id)
  const { data: versions } = useProfileVersions()
  const answers = (versions?.[0]?.data as Profile | undefined)?.application
  const items = applyReadiness(job, docs, answers)
  const command = applyCommand(job)
  const blocked = items.some((i) => i.level === 'block')

  async function copy() {
    try {
      await navigator.clipboard.writeText(command)
      toast.success('Copied. Paste it into Claude Code on your Mac.')
    } catch {
      toast.error("Couldn't copy; select the command and copy it yourself.")
    }
  }

  async function download(path: string | null | undefined) {
    if (!path) return
    try {
      window.location.assign(await downloadUrl(path))
    } catch (e) {
      toast.error(`Couldn't download: ${(e as Error).message}`)
    }
  }

  const finalDocs = docs?.resume?.state === 'final' && docs.cover?.state === 'final'

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button variant={primary ? 'default' : 'outline'}>
          <ClipboardPen data-icon="inline-start" />
          Help me apply
        </Button>
      </DialogTrigger>
      <DialogContent className="max-h-[90dvh] overflow-y-auto sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>Apply with Claude</DialogTitle>
          <DialogDescription>
            Claude fills this application in Chrome on your Mac and stops before Submit. You review everything and submit
            it yourself.
          </DialogDescription>
        </DialogHeader>

        {/* Apply assist runs on the Mac; on a phone, say so up front. */}
        <p className="flex items-start gap-2.5 rounded-md bg-muted p-3 text-sm md:hidden">
          <Laptop className="mt-0.5 size-4 shrink-0 text-muted-foreground" aria-hidden="true" />
          You're on your phone. Apply assist runs on your Mac: open this job there, or type the command below in Claude
          Code.
        </p>

        <section aria-labelledby="apply-ready" className="flex flex-col gap-2.5">
          <h3 id="apply-ready" className="text-sm font-medium">
            {blocked ? 'Before you can apply' : 'Ready to apply'}
          </h3>
          <ul className="flex flex-col gap-2">
            {items.map((item) => {
              const { icon: Icon, className, label } = LEVEL[item.level]
              return (
                <li key={item.text} className="flex items-start gap-2.5 text-sm">
                  <Icon className={cn('mt-0.5 size-4 shrink-0', className)} aria-hidden="true" />
                  <span>
                    <span className="sr-only">{label}: </span>
                    {item.text}
                  </span>
                </li>
              )
            })}
          </ul>
        </section>

        <section aria-labelledby="apply-command" className="flex flex-col gap-2">
          <h3 id="apply-command" className="text-sm font-medium">
            In Claude Code on your Mac, type:
          </h3>
          <div className="flex items-center gap-2 rounded-md bg-muted py-1.5 pr-1.5 pl-3">
            <code className="min-w-0 flex-1 truncate font-mono text-sm select-all">{command}</code>
            <Button variant="outline" size="sm" onClick={copy}>
              <Copy data-icon="inline-start" />
              Copy
            </Button>
          </div>
        </section>

        {finalDocs && (
          <section aria-labelledby="apply-docs" className="flex flex-col gap-1.5">
            <h3 id="apply-docs" className="text-sm font-medium">
              Or apply yourself with this job's documents:
            </h3>
            <div className="flex flex-wrap gap-x-4">
              <Button variant="link" className="h-auto px-0 pointer-coarse:min-h-11" onClick={() => download(docs?.resume?.pdf_path)}>
                <Download data-icon="inline-start" />
                Resume (PDF)
              </Button>
              <Button variant="link" className="h-auto px-0 pointer-coarse:min-h-11" onClick={() => download(docs?.cover?.pdf_path)}>
                <Download data-icon="inline-start" />
                Cover letter (PDF)
              </Button>
            </div>
          </section>
        )}

        <DialogFooter>
          <DialogClose asChild>
            <Button variant="ghost">Close</Button>
          </DialogClose>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
