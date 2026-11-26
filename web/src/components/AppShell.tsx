import { BriefcaseBusiness, LogOut } from 'lucide-react'
import { NavLink, Outlet } from 'react-router'
import { ThemeToggle } from '@/components/ThemeToggle'
import { Button } from '@/components/ui/button'
import { MOBILE_NAV, PRIMARY_NAV, SECONDARY_NAV, signOut, type NavItem } from '@/lib/nav'
import { cn } from '@/lib/utils'

function SidebarLink({ item }: { item: NavItem }) {
  const Icon = item.icon
  return (
    <NavLink
      to={item.to}
      end={item.to === '/'}
      className={({ isActive }) =>
        cn(
          'flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition-colors duration-200',
          isActive ? 'bg-accent text-accent-foreground' : 'text-muted-foreground hover:bg-muted hover:text-foreground',
        )
      }
    >
      <Icon className="size-4" aria-hidden="true" />
      {item.label}
    </NavLink>
  )
}

export function AppShell() {
  return (
    <div className="min-h-dvh md:grid md:grid-cols-[15rem_1fr]">
      <a
        href="#main"
        className="sr-only focus:not-sr-only focus:fixed focus:top-2 focus:left-2 focus:z-50 focus:rounded-md focus:bg-card focus:px-3 focus:py-2"
      >
        Skip to content
      </a>

      {/* Desktop sidebar */}
      <aside className="sticky top-0 hidden h-dvh flex-col border-r bg-card px-3 py-5 md:flex">
        <div className="mb-6 flex items-center gap-2 px-3">
          <BriefcaseBusiness className="size-5 text-primary" aria-hidden="true" />
          <span className="font-semibold">Job Search</span>
        </div>
        <nav aria-label="Main" className="flex flex-col gap-1">
          {PRIMARY_NAV.map((item) => (
            <SidebarLink key={item.to} item={item} />
          ))}
          <div className="my-3 border-t" />
          {SECONDARY_NAV.map((item) => (
            <SidebarLink key={item.to} item={item} />
          ))}
        </nav>
        <div className="mt-auto flex flex-col gap-3">
          <ThemeToggle />
          <Button variant="ghost" className="justify-start text-muted-foreground" onClick={signOut}>
            <LogOut data-icon="inline-start" />
            Sign out
          </Button>
        </div>
      </aside>

      {/* Page content. Bottom padding keeps content clear of the mobile bottom bar. */}
      <main id="main" className="mx-auto w-full max-w-6xl px-4 pt-6 pb-28 sm:px-6 md:pb-10 lg:px-10">
        <Outlet />
      </main>

      {/* Mobile bottom bar */}
      <nav
        aria-label="Main"
        className="fixed inset-x-0 bottom-0 z-40 border-t bg-card pb-[env(safe-area-inset-bottom)] md:hidden"
      >
        <ul className="grid grid-cols-4">
          {MOBILE_NAV.map((item) => {
            const Icon = item.icon
            return (
              <li key={item.to}>
                <NavLink
                  to={item.to}
                  end={item.to === '/'}
                  className={({ isActive }) =>
                    cn(
                      'flex min-h-14 flex-col items-center justify-center gap-0.5 text-xs font-medium transition-colors duration-200',
                      isActive ? 'text-primary' : 'text-muted-foreground',
                    )
                  }
                >
                  <Icon className="size-5" aria-hidden="true" />
                  {item.label}
                </NavLink>
              </li>
            )
          })}
        </ul>
      </nav>
    </div>
  )
}

