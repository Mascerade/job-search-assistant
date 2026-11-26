import { Pencil, UserRound } from 'lucide-react'
import { useMemo, useState } from 'react'
import { toast } from 'sonner'
import { parse, stringify } from 'yaml'
import { ApplicationAnswersCard } from '@/components/ApplicationAnswersCard'
import { EmptyState, PageHeader } from '@/components/EmptyState'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Skeleton } from '@/components/ui/skeleton'
import { Textarea } from '@/components/ui/textarea'
import { formatDateTime } from '@/lib/format'
import { canonicalProfile, countFacts, validateProfile, type Profile } from '@/lib/profile'
import { useProfileVersions, useSaveProfile } from '@/lib/queries'

function ProfileSummary({ profile }: { profile: Profile }) {
  return (
    <div className="flex flex-col gap-6">
      <div>
        <p className="text-lg font-semibold">{profile.contact.name}</p>
        <p className="text-sm text-muted-foreground">
          {[profile.contact.email, profile.contact.phone, profile.contact.location].filter(Boolean).join(' · ')}
        </p>
      </div>
      <dl className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        {[
          ['Education', profile.education.length],
          ['Experience', profile.experience.length],
          ['Projects', profile.projects.length],
          ['Facts', countFacts(profile)],
        ].map(([label, n]) => (
          <div key={label} className="rounded-lg border bg-card p-3">
            <dt className="text-xs text-muted-foreground">{label}</dt>
            <dd className="text-xl font-medium tabular-nums">{n}</dd>
          </div>
        ))}
      </dl>
      {[...profile.experience, ...profile.projects].map((e) => (
        <section key={e.id}>
          <h3 className="font-medium">
            {e.title ?? e.name}
            {e.org && <span className="text-muted-foreground"> · {e.org}</span>}
          </h3>
          <ul className="mt-1 flex flex-col gap-1">
            {e.facts.map((f) => (
              <li key={f.id} className="flex gap-2 text-sm">
                <code className="shrink-0 pt-0.5 font-mono text-xs text-muted-foreground">{f.id}</code>
                <span>{f.text}</span>
              </li>
            ))}
          </ul>
        </section>
      ))}
    </div>
  )
}

export function ProfilePage() {
  const { data: versions, isLoading } = useProfileVersions()
  const save = useSaveProfile()
  const current = versions?.[0]
  const [editing, setEditing] = useState(false)
  const [text, setText] = useState('')
  const [note, setNote] = useState('')
  const [errors, setErrors] = useState<string[]>([])
  const [baseVersion, setBaseVersion] = useState<number | undefined>(undefined)

  const profile = useMemo(() => (current ? (current.data as unknown as Profile) : null), [current])

  function startEditing() {
    setText(profile ? stringify(canonicalProfile(profile), { lineWidth: 0 }) : '')
    setNote('')
    setErrors([])
    setBaseVersion(current?.version)
    setEditing(true)
  }

  async function handleSave() {
    let parsed: unknown
    try {
      parsed = parse(text)
    } catch (e) {
      setErrors([`YAML error: ${(e as Error).message}`])
      return
    }
    const problems = validateProfile(parsed)
    setErrors(problems)
    if (problems.length) return
    try {
      await save.mutateAsync({ data: parsed as Record<string, unknown>, note: note.trim(), baseVersion })
      toast.success('Profile saved as a new version')
      setEditing(false)
    } catch (e) {
      setErrors([`Couldn't save: ${(e as Error).message}`])
    }
  }

  return (
    <>
      <PageHeader
        icon={UserRound}
        title="Master profile"
        description="Every fact the AI may use in your resumes and cover letters. Anything not here can only appear as a suggestion you approve."
        actions={
          !editing && (
            <Button onClick={startEditing}>
              <Pencil data-icon="inline-start" />
              {profile ? 'Edit' : 'Create'}
            </Button>
          )
        }
      />

      {isLoading ? (
        <Skeleton className="h-64 w-full" />
      ) : editing ? (
        <Card>
          <CardContent className="flex flex-col gap-4">
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="profile-yaml">Profile (YAML)</Label>
              <Textarea
                id="profile-yaml"
                rows={28}
                spellCheck={false}
                className="font-mono text-xs leading-relaxed"
                value={text}
                onChange={(e) => setText(e.target.value)}
                aria-invalid={errors.length > 0}
                aria-describedby={errors.length ? 'profile-errors' : 'profile-hint'}
              />
              <p id="profile-hint" className="text-xs text-muted-foreground">
                Each fact needs a unique id. Leave numbers out until you know them; [placeholders] aren't allowed.
              </p>
            </div>
            {errors.length > 0 && (
              <ul id="profile-errors" role="alert" className="flex flex-col gap-1 rounded-lg border border-destructive/40 bg-destructive/10 p-3 text-sm text-destructive">
                {errors.map((e) => (
                  <li key={e}>{e}</li>
                ))}
              </ul>
            )}
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="profile-note">What changed? (optional)</Label>
              <Input id="profile-note" value={note} onChange={(e) => setNote(e.target.value)} placeholder="Added SPM F1 score" />
            </div>
            <div className="flex flex-col-reverse gap-2 sm:flex-row sm:justify-end">
              <Button variant="outline" onClick={() => setEditing(false)}>
                Cancel
              </Button>
              <Button onClick={handleSave} disabled={save.isPending}>
                {save.isPending ? 'Saving…' : 'Save new version'}
              </Button>
            </div>
          </CardContent>
        </Card>
      ) : !profile ? (
        <EmptyState icon={UserRound} title="No profile yet">
          Upload the draft profile from your terminal with <code className="font-mono">jobsearch profile push</code>, or
          create one here.
        </EmptyState>
      ) : (
        <div className="flex flex-col gap-6">
        {/* Remounts after each save, so it always starts from the newest version. */}
        <ApplicationAnswersCard key={current!.version} profile={profile} version={current!.version} />
        <div className="grid gap-6 lg:grid-cols-[1fr_16rem]">
          <Card>
            <CardContent>
              <ProfileSummary profile={profile} />
            </CardContent>
          </Card>
          <Card className="h-fit">
            <CardHeader>
              <CardTitle className="text-base">Versions</CardTitle>
            </CardHeader>
            <CardContent>
              <ol className="flex flex-col gap-3">
                {versions!.slice(0, 10).map((v) => (
                  <li key={v.version} className="text-sm">
                    <span className="tabular-nums">v{v.version}</span>
                    <span className="text-muted-foreground"> · {formatDateTime(v.created_at)}</span>
                    {v.note && <p className="text-xs text-muted-foreground">{v.note}</p>}
                  </li>
                ))}
              </ol>
            </CardContent>
          </Card>
        </div>
        </div>
      )}
    </>
  )
}
