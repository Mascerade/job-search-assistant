import { useId, useState, type FormEvent } from 'react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Textarea } from '@/components/ui/textarea'
import { TRACK_LABEL, TRACK_ORDER } from '@/lib/status'
import { EMPTY_JOB_FORM, validateJobForm, type JobFormErrors, type JobFormValues } from '@/lib/jobForm'
import type { JobTrack, RemoteType } from '@/lib/types'

function Field({
  id,
  label,
  hint,
  error,
  required,
  children,
}: {
  id: string
  label: string
  hint?: string
  error?: string
  required?: boolean
  children: React.ReactNode
}) {
  return (
    <div className="flex flex-col gap-1.5">
      <Label htmlFor={id}>
        {label}
        {required && <span className="text-muted-foreground"> (required)</span>}
      </Label>
      {children}
      {hint && !error && (
        <p id={`${id}-hint`} className="text-xs text-muted-foreground">
          {hint}
        </p>
      )}
      {error && (
        <p id={`${id}-error`} role="alert" className="text-xs font-medium text-destructive">
          {error}
        </p>
      )}
    </div>
  )
}

export function JobForm({
  initial = EMPTY_JOB_FORM,
  submitLabel,
  pending,
  onSubmit,
  onCancel,
}: {
  initial?: JobFormValues
  submitLabel: string
  pending?: boolean
  onSubmit: (values: JobFormValues) => void
  onCancel?: () => void
}) {
  const uid = useId()
  const id = (name: string) => `${uid}-${name}`
  const [values, setValues] = useState(initial)
  const [errors, setErrors] = useState<JobFormErrors>({})
  const [submitted, setSubmitted] = useState(false)

  function set<K extends keyof JobFormValues>(key: K, value: JobFormValues[K]) {
    const next = { ...values, [key]: value }
    setValues(next)
    // After the first submit attempt, re-validate as the user fixes things.
    if (submitted) setErrors(validateJobForm(next))
  }

  function handleSubmit(e: FormEvent) {
    e.preventDefault()
    setSubmitted(true)
    const errs = validateJobForm(values)
    setErrors(errs)
    const first = Object.keys(errs)[0]
    if (first) {
      document.getElementById(id(first))?.focus()
      return
    }
    onSubmit(values)
  }

  const describedBy = (name: keyof JobFormValues, hasHint = false) =>
    errors[name] ? `${id(name)}-error` : hasHint ? `${id(name)}-hint` : undefined

  return (
    <form onSubmit={handleSubmit} noValidate className="flex flex-col gap-5">
      <Field id={id('url')} label="Link to the posting" hint="Paste the URL from the employer's site, Handshake, LinkedIn, etc." error={errors.url}>
        <Input
          id={id('url')}
          type="url"
          inputMode="url"
          autoComplete="url"
          placeholder="https://"
          value={values.url}
          onChange={(e) => set('url', e.target.value)}
          aria-invalid={!!errors.url}
          aria-describedby={describedBy('url', true)}
        />
      </Field>

      <div className="grid gap-5 sm:grid-cols-2">
        <Field id={id('company')} label="Company or organization" required error={errors.company}>
          <Input
            id={id('company')}
            value={values.company}
            onChange={(e) => set('company', e.target.value)}
            aria-invalid={!!errors.company}
            aria-describedby={describedBy('company')}
            required
          />
        </Field>
        <Field id={id('title')} label="Job title" required error={errors.title}>
          <Input
            id={id('title')}
            value={values.title}
            onChange={(e) => set('title', e.target.value)}
            aria-invalid={!!errors.title}
            aria-describedby={describedBy('title')}
            required
          />
        </Field>
      </div>

      <div className="grid gap-5 sm:grid-cols-3">
        <Field id={id('location')} label="Location">
          <Input
            id={id('location')}
            placeholder="Cambridge, MA"
            value={values.location}
            onChange={(e) => set('location', e.target.value)}
          />
        </Field>
        <Field id={id('remote_type')} label="Work arrangement">
          <Select value={values.remote_type} onValueChange={(v) => set('remote_type', v as RemoteType)}>
            <SelectTrigger id={id('remote_type')} className="w-full">
              <SelectValue placeholder="Choose…" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="onsite">On-site</SelectItem>
              <SelectItem value="hybrid">Hybrid</SelectItem>
              <SelectItem value="remote">Remote</SelectItem>
            </SelectContent>
          </Select>
        </Field>
        <Field id={id('track')} label="Track">
          <Select value={values.track} onValueChange={(v) => set('track', v as JobTrack)}>
            <SelectTrigger id={id('track')} className="w-full">
              <SelectValue placeholder="Choose…" />
            </SelectTrigger>
            <SelectContent>
              {TRACK_ORDER.map((t) => (
                <SelectItem key={t} value={t}>
                  {TRACK_LABEL[t]}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </Field>
      </div>

      <div className="grid gap-5 sm:grid-cols-2">
        <Field id={id('salary_min')} label="Salary minimum (USD/year)" error={errors.salary_min}>
          <Input
            id={id('salary_min')}
            inputMode="numeric"
            placeholder="65000"
            value={values.salary_min}
            onChange={(e) => set('salary_min', e.target.value)}
            aria-invalid={!!errors.salary_min}
            aria-describedby={describedBy('salary_min')}
          />
        </Field>
        <Field id={id('salary_max')} label="Salary maximum (USD/year)" error={errors.salary_max}>
          <Input
            id={id('salary_max')}
            inputMode="numeric"
            placeholder="80000"
            value={values.salary_max}
            onChange={(e) => set('salary_max', e.target.value)}
            aria-invalid={!!errors.salary_max}
            aria-describedby={describedBy('salary_max')}
          />
        </Field>
      </div>

      <Field
        id={id('description')}
        label="Posting text"
        hint="Paste the full job description. The tailoring step uses it, so more detail means better documents."
      >
        <Textarea
          id={id('description')}
          rows={10}
          value={values.description}
          onChange={(e) => set('description', e.target.value)}
          aria-describedby={describedBy('description', true)}
        />
      </Field>

      <div className="flex flex-col-reverse gap-2 sm:flex-row sm:justify-end">
        {onCancel && (
          <Button type="button" variant="outline" onClick={onCancel}>
            Cancel
          </Button>
        )}
        <Button type="submit" disabled={pending}>
          {pending ? 'Saving…' : submitLabel}
        </Button>
      </div>
    </form>
  )
}
