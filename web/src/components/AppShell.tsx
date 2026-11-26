import { BriefcaseBusiness, LogOut } from 'lucide-react'
import { NavLink, Outlet } from 'react-router'
import { ThemeToggle } from '@/components/ThemeToggle'
import { Button } from '@/components/ui/button'
import { MOBILE_NAV, PRIMARY_NAV, SECONDARY_NAV, signOut, type NavItem } from '@/lib/nav'
import { cn } from '@/lib/utils'

/** Notion-style sidebar row: 40px tall, a hover wash, and a darker wash + full-strength text when active. */
function SidebarLink({ item }: { item: NavItem }) {
  const Icon = item.icon
  return (
    <NavLink
      to={item.to}
      end={item.to === '/'}
      className={({ isActive }) =>
        cn(
          'flex h-10 items-center gap-2.5 rounded-md px-2.5 text-sm transition-colors duration-150',
          isActive
            ? 'bg-hover-strong font-medium text-foreground'
            : 'text-muted-foreground hover:bg-hover hover:text-foreground',
        )
      }
    >
      <Icon className="size-4 shrink-0" aria-hidden="true" />
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
      <aside className="sticky top-0 hidden h-dvh flex-col border-r bg-sidebar px-2 py-3 md:flex">
        <div className="mb-2 flex items-center gap-2.5 px-2.5 py-2">
          <span className="flex size-6 items-center justify-center rounded-sm bg-primary text-primary-foreground">
            <BriefcaseBusiness className="size-3.5" aria-hidden="true" />
          </span>
          <span className="text-sm font-medium">Job Search</span>
        </div>
        <nav aria-label="Main" className="flex flex-col gap-0.5">
          {PRIMARY_NAV.map((item) => (
            <SidebarLink key={item.to} item={item} />
          ))}
          <p className="mt-4 mb-1 px-2.5 text-xs font-medium text-muted-foreground">Account</p>
          {SECONDARY_NAV.map((item) => (
            <SidebarLink key={item.to} item={item} />
          ))}
        </nav>
        <div className="mt-auto flex flex-col gap-2 px-0.5">
          <ThemeToggle />
          <Button variant="ghost" className="h-10 justify-start gap-2.5 px-2.5 font-normal" onClick={signOut}>
            <LogOut data-icon="inline-start" />
            Sign out
          </Button>
        </div>
      </aside>

      {/* Page content. Bottom padding keeps content clear of the mobile bottom bar. */}
      <main id="main" className="mx-auto w-full max-w-6xl px-4 pt-6 pb-28 sm:px-6 md:pb-12 lg:px-16 lg:pt-12">
        <Outlet />
      </main>

      {/* Mobile bottom bar: 5 slots */}
      <nav
        aria-label="Main"
        className="fixed inset-x-0 bottom-0 z-40 border-t bg-background pb-[env(safe-area-inset-bottom)] md:hidden"
      >
        <ul className="grid grid-cols-5">
          {MOBILE_NAV.map((item) => {
            const Icon = item.icon
            return (
              <li key={item.to}>
                <NavLink
                  to={item.to}
                  end={item.to === '/'}
                  className={({ isActive }) =>
                    cn(
                      'flex min-h-14 flex-col items-center justify-center gap-1 text-xs transition-colors duration-150',
                      isActive ? 'font-medium text-primary' : 'text-muted-foreground',
                    )
                  }
                >
                  <Icon className="size-5" aria-hidden="true" />
                  {item.mobileLabel ?? item.label}
                </NavLink>
              </li>
            )
          })}
        </ul>
      </nav>
    </div>
  )
}
