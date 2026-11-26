import { BriefcaseBusiness, MailCheck } from 'lucide-react'
import { useState, type FormEvent } from 'react'
import { Navigate } from 'react-router'
import { useAuth } from '@/auth/AuthProvider'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { supabase } from '@/lib/supabase'

/** Passwordless sign-in: an emailed magic link (accessible authentication). */
export function LoginPage() {
  const { session } = useAuth()
  const [email, setEmail] = useState('')
  const [state, setState] = useState<'idle' | 'sending' | 'sent'>('idle')
  const [error, setError] = useState<string | null>(null)

  if (session) return <Navigate to="/" replace />

  async function handleSubmit(e: FormEvent) {
    e.preventDefault()
    setError(null)
    if (!/^\S+@\S+\.\S+$/.test(email.trim())) {
      setError('Enter a valid email address.')
      return
    }
    setState('sending')
    const { error } = await supabase.auth.signInWithOtp({
      email: email.trim(),
      // Sign-ups are disabled: only the owner account can get a link.
      options: { shouldCreateUser: false, emailRedirectTo: window.location.origin },
    })
    if (error) {
      setState('idle')
      setError(
        /signups? not allowed|not found/i.test(error.message)
          ? "That email isn't registered for this site."
          : `Couldn't send the link: ${error.message}`,
      )
      return
    }
    setState('sent')
  }

  return (
    <main className="flex min-h-dvh items-center justify-center px-4">
      <Card className="w-full max-w-sm">
        <CardHeader>
          <div className="mb-2 flex items-center gap-2 text-primary">
            <BriefcaseBusiness className="size-5" aria-hidden="true" />
            <span className="font-semibold">Job Search</span>
          </div>
          <CardTitle className="text-xl">Sign in</CardTitle>
          <CardDescription>We'll email you a one-time sign-in link. No password needed.</CardDescription>
        </CardHeader>
        <CardContent>
          {state === 'sent' ? (
            <div role="status" className="flex flex-col items-center gap-2 py-4 text-center">
              <MailCheck className="size-8 text-success-text" aria-hidden="true" />
              <p className="font-medium">Check your email</p>
              <p className="text-sm text-muted-foreground">
                We sent a sign-in link to <span className="font-medium text-foreground">{email}</span>.
              </p>
              <Button variant="link" onClick={() => setState('idle')}>
                Use a different email
              </Button>
            </div>
          ) : (
            <form onSubmit={handleSubmit} noValidate className="flex flex-col gap-4">
              <div className="flex flex-col gap-1.5">
                <Label htmlFor="email">Email</Label>
                <Input
                  id="email"
                  type="email"
                  autoComplete="email"
                  inputMode="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  aria-invalid={!!error}
                  aria-describedby={error ? 'email-error' : undefined}
                />
                {error && (
                  <p id="email-error" role="alert" className="text-xs font-medium text-destructive">
                    {error}
                  </p>
                )}
              </div>
              <Button type="submit" disabled={state === 'sending'}>
                {state === 'sending' ? 'Sending link…' : 'Email me a sign-in link'}
              </Button>
            </form>
          )}
        </CardContent>
      </Card>
    </main>
  )
}
