import { Settings as SettingsIcon } from 'lucide-react'
import { useState, type FormEvent } from 'react'
import { toast } from 'sonner'
import { PageHeader } from '@/components/EmptyState'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Skeleton } from '@/components/ui/skeleton'
import { Textarea } from '@/components/ui/textarea'
import { useSaveSettings, useSettings } from '@/lib/queries'
import { TRACK_LABEL, TRACK_ORDER } from '@/lib/status'
import { DEFAULT_AVAILABLE_FROM } from '@/lib/timing'
import type { AppSettings, JobTrack } from '@/lib/types'

// Matches the pipeline's Settings.focus_until default.
const DEFAULT_FOCUS_UNTIL = '2027-03-01'

const lines = (s: string) =>
  s
    .split('\n')
    .map((l) => l.trim())
    .filter(Boolean)

function Toggle({
  id,
  label,
  hint,
  checked,
  onChange,
}: {
  id: string
  label: string
  hint?: string
  checked: boolean
  onChange: (v: boolean) => void
}) {
  return (
    <div className="flex items-start gap-3">
      <input
        id={id}
        type="checkbox"
        checked={checked}
        onChange={(e) => onChange(e.target.checked)}
        className="mt-0.5 size-5 shrink-0 cursor-pointer accent-primary"
        aria-describedby={hint ? `${id}-hint` : undefined}
      />
      <div>
        <Label htmlFor={id} className="cursor-pointer">
          {label}
        </Label>
        {hint && (
          <p id={`${id}-hint`} className="text-xs text-muted-foreground">
            {hint}
          </p>
        )}
      </div>
    </div>
  )
}

interface FormState {
  fit_threshold: string
  monthly_spend_cap_usd: string
  experience_max_years: string
  full_time_only: boolean
  exclude_clearance: boolean
  include_remote_us: boolean
  include_hybrid: boolean
  towns: string
  focus_until: string
  available_from: string
  tracks: Record<JobTrack, { enabled: boolean; keywords: string }>
}

function toForm(s: AppSettings): FormState {
  return {
    fit_threshold: String(s.fit_threshold),
    monthly_spend_cap_usd: String(s.monthly_spend_cap_usd),
    experience_max_years: String(s.experience_max_years),
    full_time_only: s.full_time_only,
    exclude_clearance: s.exclude_clearance,
    include_remote_us: s.locations.include_remote_us,
    include_hybrid: s.locations.include_hybrid,
    towns: s.locations.towns.join('\n'),
    // Missing = the pipeline's default (March 1, 2027); null = turned off.
    focus_until: s.focus_until === undefined ? DEFAULT_FOCUS_UNTIL : (s.focus_until ?? ''),
    available_from: s.available_from || DEFAULT_AVAILABLE_FROM,
    tracks: Object.fromEntries(
      (Object.keys(s.tracks) as JobTrack[]).map((t) => [
        t,
        { enabled: s.tracks[t].enabled, keywords: s.tracks[t].keywords.join('\n') },
      ]),
    ) as FormState['tracks'],
  }
}

type Errors = Partial<
  Record<'fit_threshold' | 'monthly_spend_cap_usd' | 'experience_max_years' | 'available_from', string>
>

function validate(f: FormState): Errors {
  const e: Errors = {}
  const t = Number(f.fit_threshold)
  if (!Number.isInteger(t) || t < 0 || t > 100) e.fit_threshold = 'Use a whole number from 0 to 100.'
  const cap = Number(f.monthly_spend_cap_usd)
  if (!Number.isFinite(cap) || cap < 0) e.monthly_spend_cap_usd = 'Use a dollar amount of 0 or more.'
  const y = Number(f.experience_max_years)
  if (!Number.isInteger(y) || y < 0 || y > 10) e.experience_max_years = 'Use a whole number from 0 to 10.'
  if (!/^\d{4}-\d{2}-\d{2}$/.test(f.available_from)) e.available_from = 'Pick the first day you could start.'
  return e
}

export function SettingsPage() {
  const { data: settings, isLoading } = useSettings()
  if (isLoading || !settings) return <Skeleton className="h-96 w-full" />
  // Remount the form when saved settings change, so it always starts from the stored values.
  return <SettingsForm key={JSON.stringify(settings)} settings={settings} />
}

function SettingsForm({ settings }: { settings: AppSettings }) {
  const save = useSaveSettings()
  const [form, setForm] = useState<FormState>(() => toForm(settings))
  const [errors, setErrors] = useState<Errors>({})

  const patch = (p: Partial<FormState>) => setForm({ ...form, ...p })

  async function handleSubmit(e: FormEvent) {
    e.preventDefault()
    const errs = validate(form)
    setErrors(errs)
    const first = Object.keys(errs)[0]
    if (first) {
      document.getElementById(first)?.focus()
      return
    }
    const next: AppSettings = {
      ...settings,
      fit_threshold: Number(form.fit_threshold),
      monthly_spend_cap_usd: Number(form.monthly_spend_cap_usd),
      experience_max_years: Number(form.experience_max_years),
      full_time_only: form.full_time_only,
      exclude_clearance: form.exclude_clearance,
      focus_until: form.focus_until || null,
      available_from: form.available_from,
      locations: {
        include_remote_us: form.include_remote_us,
        include_hybrid: form.include_hybrid,
        towns: lines(form.towns),
      },
      tracks: Object.fromEntries(
        (Object.keys(form.tracks) as JobTrack[]).map((t) => [
          t,
          { enabled: form.tracks[t].enabled, keywords: lines(form.tracks[t].keywords) },
        ]),
      ) as AppSettings['tracks'],
    }
    try {
      await save.mutateAsync(next)
      toast.success('Settings saved')
    } catch (err) {
      toast.error(`Couldn't save settings: ${(err as Error).message}`)
    }
  }

  const numberField = (key: keyof Errors, label: string, hint: string, suffix?: string) => (
    <div className="flex flex-col gap-1.5">
      <Label htmlFor={key}>{label}</Label>
      <div className="flex items-center gap-2">
        <Input
          id={key}
          inputMode="decimal"
          className="w-28 tabular-nums"
          value={form[key]}
          onChange={(e) => patch({ [key]: e.target.value } as Partial<FormState>)}
          aria-invalid={!!errors[key]}
          aria-describedby={errors[key] ? `${key}-error` : `${key}-hint`}
        />
        {suffix && <span className="text-sm text-muted-foreground">{suffix}</span>}
      </div>
      {errors[key] ? (
        <p id={`${key}-error`} role="alert" className="text-xs font-medium text-destructive">
          {errors[key]}
        </p>
      ) : (
        <p id={`${key}-hint`} className="text-xs text-muted-foreground">
          {hint}
        </p>
      )}
    </div>
  )

  return (
    <>
      <PageHeader
        icon={SettingsIcon} title="Settings" description="What the daily search looks for. Changes apply from the next run." />
      <form onSubmit={handleSubmit} noValidate className="flex flex-col gap-6">
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Matching</CardTitle>
            <CardDescription>A job gets a resume and cover letter when its fit score reaches the threshold.</CardDescription>
          </CardHeader>
          <CardContent className="grid gap-6 sm:grid-cols-3">
            {numberField('fit_threshold', 'Fit score threshold', 'Lower it for more matches, raise it for fewer.', '/ 100')}
            {numberField('experience_max_years', 'Max years of experience asked', 'Postings asking for more are skipped.', 'years')}
            {numberField('monthly_spend_cap_usd', 'Monthly AI usage cap', "AI steps pause when this month's estimated API value reaches it (free on your Claude plan).", 'USD')}
          </CardContent>
          <CardContent className="flex flex-col gap-4 border-t pt-4">
            <Toggle id="full_time_only" label="Full-time only" hint="Skip contract, temporary, part-time, and internship roles." checked={form.full_time_only} onChange={(v) => patch({ full_time_only: v })} />
            <Toggle id="exclude_clearance" label="Skip roles that need a security clearance" checked={form.exclude_clearance} onChange={(v) => patch({ exclude_clearance: v })} />
          </CardContent>
          <CardContent className="flex flex-col gap-1.5 border-t pt-4">
            <Label htmlFor="available_from">Available from</Label>
            <Input
              id="available_from"
              type="date"
              required
              className="w-44 tabular-nums"
              value={form.available_from}
              onChange={(e) => patch({ available_from: e.target.value })}
              aria-invalid={errors.available_from ? true : undefined}
              aria-describedby={errors.available_from ? 'available_from-error available_from-hint' : 'available_from-hint'}
            />
            {errors.available_from && (
              <p id="available_from-error" className="text-xs text-destructive">
                {errors.available_from}
              </p>
            )}
            <p id="available_from-hint" className="max-w-prose text-xs text-muted-foreground">
              The first day you can start a job. Postings whose start date reaches it are marked “After graduation” on
              Today, and they get their resumes and cover letters first.
            </p>
          </CardContent>
          <CardContent className="flex flex-col gap-1.5 border-t pt-4">
            <Label htmlFor="focus_until">Software jobs first until</Label>
            <Input
              id="focus_until"
              type="date"
              className="w-44 tabular-nums"
              value={form.focus_until}
              onChange={(e) => patch({ focus_until: e.target.value })}
              aria-describedby="focus_until-hint"
            />
            <p id="focus_until-hint" className="max-w-prose text-xs text-muted-foreground">
              Until this date the daily resumes and cover letters go to software jobs first, then university tech
              and computational research, then program admin (admin roles usually hire a few weeks before the start
              date). Jobs that start after
              you're available and best fits still lead each group; staffing agencies always come last. Clear it to
              go by best fit only.
            </p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="text-base">Role tracks</CardTitle>
            <CardDescription>Job titles and phrases to search for, one per line.</CardDescription>
          </CardHeader>
          <CardContent className="grid gap-6 md:grid-cols-2">
            {TRACK_ORDER.filter((t) => t in form.tracks).map((t) => (
              <div key={t} className="flex flex-col gap-3">
                <Toggle
                  id={`track-${t}`}
                  label={TRACK_LABEL[t]}
                  checked={form.tracks[t].enabled}
                  onChange={(v) => patch({ tracks: { ...form.tracks, [t]: { ...form.tracks[t], enabled: v } } })}
                />
                <Label htmlFor={`kw-${t}`} className="sr-only">
                  {TRACK_LABEL[t]} keywords
                </Label>
                <Textarea
                  id={`kw-${t}`}
                  rows={8}
                  disabled={!form.tracks[t].enabled}
                  value={form.tracks[t].keywords}
                  onChange={(e) => patch({ tracks: { ...form.tracks, [t]: { ...form.tracks[t], keywords: e.target.value } } })}
                />
                {t === 'research' && (
                  <p className="text-xs text-muted-foreground">
                    Titles that don't say what kind of research, like "Research Assistant I", are kept only when the
                    description asks for programming.
                  </p>
                )}
              </div>
            ))}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="text-base">Locations</CardTitle>
            <CardDescription>On-site jobs must be in one of these towns.</CardDescription>
          </CardHeader>
          <CardContent className="grid gap-6 sm:grid-cols-2">
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="towns">Towns (one per line)</Label>
              <Textarea id="towns" rows={10} value={form.towns} onChange={(e) => patch({ towns: e.target.value })} />
            </div>
            <div className="flex flex-col gap-4">
              <Toggle id="include_remote_us" label="Include US-remote jobs" checked={form.include_remote_us} onChange={(v) => patch({ include_remote_us: v })} />
              <Toggle id="include_hybrid" label="Include hybrid jobs" checked={form.include_hybrid} onChange={(v) => patch({ include_hybrid: v })} />
            </div>
          </CardContent>
        </Card>

        <div className="flex justify-end">
          <Button type="submit" disabled={save.isPending}>
            {save.isPending ? 'Saving…' : 'Save settings'}
          </Button>
        </div>
      </form>
    </>
  )
}
