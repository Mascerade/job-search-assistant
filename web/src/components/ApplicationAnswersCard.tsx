import { Plus, X } from 'lucide-react'
import { useState, type ReactNode } from 'react'
import { Link } from 'react-router'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Textarea } from '@/components/ui/textarea'
import { validateProfile, type ApplicationAnswers, type Profile } from '@/lib/profile'
import { fetchLatestProfile, useSaveProfile } from '@/lib/queries'
import { formatDay, useAvailableFrom } from '@/lib/timing'

/**
 * Standard answers for application forms (apply assist, milestone 6). Saved into the profile's
 * `application` section as a new profile version; never sent to the AI that scores or writes.
 */

type YesNo = 'unset' | 'yes' | 'no'
const BOOL_FIELDS = ['work_authorized_us', 'sponsorship_now', 'sponsorship_future', 'over_18', 'willing_to_relocate'] as const
const TEXT_FIELDS = ['preferred_name', 'pronouns', 'address', 'gpa', 'salary_expectation', 'how_heard'] as const
const LINK_FIELDS = ['linkedin', 'github', 'website', 'portfolio'] as const
const DEMOGRAPHIC_FIELDS = ['gender', 'hispanic_latino', 'race_ethnicity', 'veteran', 'disability'] as const
type BoolField = (typeof BOOL_FIELDS)[number]
type TextField = (typeof TEXT_FIELDS)[number]
type LinkField = (typeof LINK_FIELDS)[number]
type DemographicField = (typeof DEMOGRAPHIC_FIELDS)[number]

const DECLINE = 'Decline to self-identify'
/** The usual US self-identification choices; Claude picks the form's closest option. */
const DEMOGRAPHIC_OPTIONS: Record<DemographicField, { label: string; options: string[] }> = {
  gender: { label: 'Gender', options: ['Male', 'Female', 'Non-binary', DECLINE] },
  hispanic_latino: { label: 'Hispanic or Latino?', options: ['Yes', 'No', DECLINE] },
  race_ethnicity: {
    label: 'Race / ethnicity',
    options: [
      'American Indian or Alaska Native',
      'Asian',
      'Black or African American',
      'Native Hawaiian or Other Pacific Islander',
      'White',
      'Two or more races',
      DECLINE,
    ],
  },
  veteran: {
    label: 'Veteran status',
    options: ['I am not a protected veteran', 'I identify as one or more of the classifications of protected veteran', DECLINE],
  },
  disability: {
    label: 'Disability status',
    options: ['Yes, I have a disability (or previously had one)', "No, I don't have a disability", DECLINE],
  },
}

interface FormState {
  bools: Record<BoolField, YesNo>
  text: Record<TextField, string>
  links: Record<LinkField, string>
  demographics: Record<DemographicField, string>
  custom: { question: string; answer: string }[]
}

/** LinkedIn / GitHub / website from the profile's contact links, by domain (mirrors apply.links_for). */
function contactLinks(links: string[] = []): Partial<Record<LinkField, string>> {
  const out: Partial<Record<LinkField, string>> = {}
  for (const raw of links) {
    const host = raw.trim().toLowerCase().replace(/^https?:\/\//, '').replace(/^www\./, '')
    const key: LinkField = host.startsWith('linkedin.com') ? 'linkedin' : host.startsWith('github.com') ? 'github' : 'website'
    out[key] ??= raw.trim()
  }
  return out
}

function toForm(profile: Profile): FormState {
  const a: ApplicationAnswers = profile.application ?? {}
  const defaults = contactLinks(profile.contact.links)
  const yn = (v: boolean | null | undefined): YesNo => (v === true ? 'yes' : v === false ? 'no' : 'unset')
  return {
    bools: Object.fromEntries(BOOL_FIELDS.map((k) => [k, yn(a[k])])) as FormState['bools'],
    text: Object.fromEntries(TEXT_FIELDS.map((k) => [k, a[k] == null ? '' : String(a[k])])) as FormState['text'],
    links: Object.fromEntries(LINK_FIELDS.map((k) => [k, a.links?.[k] ?? defaults[k] ?? ''])) as FormState['links'],
    demographics: Object.fromEntries(DEMOGRAPHIC_FIELDS.map((k) => [k, a.demographics?.[k] ?? 'unset'])) as FormState['demographics'],
    custom: (a.custom ?? []).map((qa) => ({ ...qa })),
  }
}

/** Only what's set, so the profile YAML stays short. Links equal to the contact links aren't stored. */
function fromForm(form: FormState, profile: Profile): ApplicationAnswers | null {
  const out: ApplicationAnswers = {}
  for (const k of BOOL_FIELDS) if (form.bools[k] !== 'unset') out[k] = form.bools[k] === 'yes'
  for (const k of TEXT_FIELDS) if (form.text[k].trim()) out[k] = form.text[k].trim()
  const defaults = contactLinks(profile.contact.links)
  const links = Object.fromEntries(
    LINK_FIELDS.filter((k) => form.links[k].trim() && form.links[k].trim() !== defaults[k]).map((k) => [k, form.links[k].trim()]),
  )
  if (Object.keys(links).length) out.links = links
  const demo = Object.fromEntries(DEMOGRAPHIC_FIELDS.filter((k) => form.demographics[k] !== 'unset').map((k) => [k, form.demographics[k]]))
  if (Object.keys(demo).length) out.demographics = demo
  const custom = form.custom
    .map((qa) => ({ question: qa.question.trim(), answer: qa.answer.trim() }))
    .filter((qa) => qa.question || qa.answer)
  if (custom.length) out.custom = custom
  return Object.keys(out).length ? out : null
}

function Group({ title, note, children }: { title: string; note?: string; children: ReactNode }) {
  return (
    <fieldset className="flex flex-col gap-4 border-t pt-6 first:border-t-0 first:pt-0">
      <legend className="sr-only">{title}</legend>
      <div aria-hidden="true">
        <p className="text-sm font-semibold">{title}</p>
        {note && <p className="text-xs text-muted-foreground">{note}</p>}
      </div>
      {children}
    </fieldset>
  )
}

function Field({ id, label, hint, children }: { id: string; label: string; hint?: ReactNode; children: ReactNode }) {
  return (
    <div className="flex min-w-0 flex-col gap-1.5">
      <Label htmlFor={id}>{label}</Label>
      {children}
      {hint && (
        <p id={`${id}-hint`} className="text-xs text-muted-foreground">
          {hint}
        </p>
      )}
    </div>
  )
}

export function ApplicationAnswersCard({ profile, version }: { profile: Profile; version: number }) {
  const save = useSaveProfile()
  const availableFrom = useAvailableFrom()
  const [form, setForm] = useState<FormState>(() => toForm(profile))
  const [errors, setErrors] = useState<string[]>([])

  const setBool = (k: BoolField, v: YesNo) => setForm((f) => ({ ...f, bools: { ...f.bools, [k]: v } }))
  const setText = (k: TextField, v: string) => setForm((f) => ({ ...f, text: { ...f.text, [k]: v } }))
  const setLink = (k: LinkField, v: string) => setForm((f) => ({ ...f, links: { ...f.links, [k]: v } }))
  const setDemo = (k: DemographicField, v: string) => setForm((f) => ({ ...f, demographics: { ...f.demographics, [k]: v } }))
  const setQA = (i: number, patch: Partial<{ question: string; answer: string }>) =>
    setForm((f) => ({ ...f, custom: f.custom.map((qa, j) => (j === i ? { ...qa, ...patch } : qa)) }))

  async function handleSave() {
    const incomplete = form.custom.findIndex((qa) => !qa.question.trim() !== !qa.answer.trim())
    if (incomplete >= 0) {
      setErrors([`Common question ${incomplete + 1} needs both a question and an answer (or remove it).`])
      return
    }
    const application = fromForm(form, profile)
    try {
      // This form only changes `application`, so a newer version saved meanwhile (the daily run
      // learning a skill, a YAML edit) is fine: put the answers onto it. Refuse only if the newer
      // version changed the answers themselves (e.g. one saved while applying).
      const latest = await fetchLatestProfile()
      const base = latest ?? { version, data: profile as unknown as Record<string, unknown> }
      if (base.version !== version && JSON.stringify(base.data.application ?? null) !== JSON.stringify(profile.application ?? null)) {
        setErrors([`Your saved answers changed since you opened this page (now version ${base.version}). Reload to see them, then edit again.`])
        return
      }
      const next: Record<string, unknown> = { ...base.data }
      if (application) next.application = application
      else delete next.application
      const problems = validateProfile(next)
      setErrors(problems)
      if (problems.length) return
      await save.mutateAsync({ data: next, note: 'Application answers', baseVersion: base.version })
      toast.success('Answers saved as a new profile version')
    } catch (e) {
      setErrors([`Couldn't save: ${(e as Error).message}`])
    }
  }

  const yesNo = (k: BoolField, label: string) => (
    <Field id={`ans-${k}`} label={label}>
      <Select value={form.bools[k]} onValueChange={(v) => setBool(k, v as YesNo)}>
        <SelectTrigger id={`ans-${k}`} className="w-full">
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value="unset">Not set</SelectItem>
          <SelectItem value="yes">Yes</SelectItem>
          <SelectItem value="no">No</SelectItem>
        </SelectContent>
      </Select>
    </Field>
  )
  const text = (k: TextField, label: string, opts: { placeholder?: string; hint?: string } = {}) => (
    <Field id={`ans-${k}`} label={label} hint={opts.hint}>
      <Input
        id={`ans-${k}`}
        value={form.text[k]}
        placeholder={opts.placeholder ?? 'Not set'}
        onChange={(e) => setText(k, e.target.value)}
        aria-describedby={opts.hint ? `ans-${k}-hint` : undefined}
      />
    </Field>
  )

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-lg">Application answers</CardTitle>
        <CardDescription>
          Claude uses these to fill job applications. Leave anything blank to be asked each time. Saving creates a new
          profile version.
        </CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-6">
        <Group title="Work eligibility">
          <div className="grid gap-4 sm:grid-cols-2">
            {yesNo('work_authorized_us', 'Authorized to work in the US?')}
            {yesNo('sponsorship_now', 'Need visa sponsorship now?')}
            {yesNo('sponsorship_future', 'Need sponsorship in the future?')}
            {yesNo('over_18', '18 or older?')}
          </div>
        </Group>

        <Group title="About you">
          <div className="grid gap-4 sm:grid-cols-2">
            {text('preferred_name', 'Preferred name')}
            {text('pronouns', 'Pronouns')}
            {text('address', 'Mailing address', { hint: 'Workday forms always ask for this.' })}
            {text('gpa', 'GPA')}
          </div>
        </Group>

        <Group title="Preferences">
          <div className="grid gap-4 sm:grid-cols-2">
            {text('salary_expectation', 'Salary expectation', {
              placeholder: 'Ask me each time',
              hint: 'Blank means Claude asks you on each form.',
            })}
            {yesNo('willing_to_relocate', 'Willing to relocate?')}
            {text('how_heard', 'How did you hear about us?', { placeholder: 'Company careers site' })}
            <Field
              id="ans-earliest-start"
              label="Earliest start date"
              hint={
                <>
                  From{' '}
                  <Link to="/settings" className="text-primary underline-offset-4 hover:underline">
                    Settings → Available from
                  </Link>
                  .
                </>
              }
            >
              <Input id="ans-earliest-start" value={formatDay(availableFrom)} readOnly className="bg-muted" />
            </Field>
          </div>
        </Group>

        <Group title="Links" note="Filled in from your profile's contact links; change them here if a form needs something different.">
          <div className="grid gap-4 sm:grid-cols-2">
            {LINK_FIELDS.map((k) => (
              <Field key={k} id={`ans-link-${k}`} label={{ linkedin: 'LinkedIn', github: 'GitHub', website: 'Website', portfolio: 'Portfolio' }[k]}>
                <Input id={`ans-link-${k}`} value={form.links[k]} placeholder="Not set" onChange={(e) => setLink(k, e.target.value)} />
              </Field>
            ))}
          </div>
        </Group>

        <Group title="Common questions" note="Answers you've approved for questions that come up again. Claude offers to save new ones as you apply.">
          {form.custom.map((qa, i) => (
            <div key={i} className="flex flex-col gap-3 rounded-md border p-3">
              <div className="flex items-end gap-2">
                <div className="min-w-0 flex-1">
                  <Field id={`ans-q-${i}`} label="Question">
                    <Input id={`ans-q-${i}`} value={qa.question} onChange={(e) => setQA(i, { question: e.target.value })} />
                  </Field>
                </div>
                <Button
                  variant="ghost"
                  size="icon"
                  aria-label={`Remove question ${i + 1}`}
                  onClick={() => setForm((f) => ({ ...f, custom: f.custom.filter((_, j) => j !== i) }))}
                >
                  <X />
                </Button>
              </div>
              <Field id={`ans-a-${i}`} label="Answer">
                <Textarea id={`ans-a-${i}`} rows={2} value={qa.answer} onChange={(e) => setQA(i, { answer: e.target.value })} />
              </Field>
            </div>
          ))}
          <div>
            <Button variant="ghost" onClick={() => setForm((f) => ({ ...f, custom: [...f.custom, { question: '', answer: '' }] }))}>
              <Plus data-icon="inline-start" />
              Add question
            </Button>
          </div>
        </Group>

        <Group
          title="Voluntary self-identification"
          note="Optional. Used only for the demographic questions some forms ask. Stored privately with your profile; older profile versions keep earlier answers."
        >
          <div className="grid gap-4 sm:grid-cols-2">
            {DEMOGRAPHIC_FIELDS.map((k) => (
              <Field key={k} id={`ans-demo-${k}`} label={DEMOGRAPHIC_OPTIONS[k].label}>
                <Select value={form.demographics[k]} onValueChange={(v) => setDemo(k, v)}>
                  <SelectTrigger id={`ans-demo-${k}`} className="w-full">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="unset">Not set</SelectItem>
                    {[
                      ...DEMOGRAPHIC_OPTIONS[k].options,
                      // keep a value typed in the YAML editor that isn't one of the usual choices
                      ...(form.demographics[k] !== 'unset' && !DEMOGRAPHIC_OPTIONS[k].options.includes(form.demographics[k])
                        ? [form.demographics[k]]
                        : []),
                    ].map((o) => (
                      <SelectItem key={o} value={o}>
                        {o}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </Field>
            ))}
          </div>
        </Group>

        {errors.length > 0 && (
          <ul role="alert" className="flex flex-col gap-1 rounded-lg border border-destructive/40 bg-destructive/10 p-3 text-sm text-destructive">
            {errors.map((e) => (
              <li key={e}>{e}</li>
            ))}
          </ul>
        )}
        <div className="flex flex-wrap items-center gap-3 border-t pt-6">
          <Button onClick={handleSave} disabled={save.isPending}>
            {save.isPending ? 'Saving…' : 'Save answers'}
          </Button>
          <span className="text-xs text-muted-foreground">Saves profile version {version + 1}</span>
        </div>
      </CardContent>
    </Card>
  )
}
