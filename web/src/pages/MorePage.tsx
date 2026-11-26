import { ChevronRight, Ellipsis, LogOut } from 'lucide-react'
import { Link } from 'react-router'
import { PageHeader } from '@/components/EmptyState'
import { ThemeToggle } from '@/components/ThemeToggle'
import { Button } from '@/components/ui/button'
import { SECONDARY_NAV, signOut } from '@/lib/nav'

/** Phone-only page holding the navigation that doesn't fit in the bottom bar. */
export function MorePage() {
  return (
    <>
      <PageHeader
        icon={Ellipsis} title="More" />
      <nav aria-label="More pages">
        <ul className="flex flex-col divide-y rounded-lg border bg-card">
          {SECONDARY_NAV.map(({ to, label, icon: Icon }) => (
            <li key={to}>
              <Link to={to} className="flex min-h-14 items-center gap-3 px-4 text-sm font-medium">
                <Icon className="size-5 text-muted-foreground" aria-hidden="true" />
                {label}
                <ChevronRight className="ml-auto size-4 text-muted-foreground" aria-hidden="true" />
              </Link>
            </li>
          ))}
        </ul>
      </nav>
      <h2 className="mt-8 mb-2 text-sm font-medium text-muted-foreground">Appearance</h2>
      <ThemeToggle />
      <Button variant="outline" className="mt-8 w-full" onClick={signOut}>
        <LogOut data-icon="inline-start" />
        Sign out
      </Button>
    </>
  )
}
