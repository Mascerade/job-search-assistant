import {
  Activity,
  ChartColumn,
  Ellipsis,
  Inbox,
  Plus,
  Settings,
  SquareKanban,
  UserRound,
  type LucideIcon,
} from 'lucide-react'
import { supabase } from './supabase'

export interface NavItem {
  to: string
  label: string
  icon: LucideIcon
  /** Shorter label for the phone bottom bar. */
  mobileLabel?: string
}

export const PRIMARY_NAV: NavItem[] = [
  { to: '/', label: 'Today', icon: Inbox },
  { to: '/board', label: 'Board', icon: SquareKanban },
  { to: '/insights', label: 'Insights', icon: ChartColumn },
  { to: '/add', label: 'Add job', icon: Plus, mobileLabel: 'Add' },
]

export const SECONDARY_NAV: NavItem[] = [
  { to: '/profile', label: 'Profile', icon: UserRound },
  { to: '/settings', label: 'Settings', icon: Settings },
  { to: '/runs', label: 'Runs & spend', icon: Activity },
]

// Phones: 5 items in the bottom bar (UI/UX Pro Max: bottom nav ≤ 5).
export const MOBILE_NAV: NavItem[] = [...PRIMARY_NAV, { to: '/more', label: 'More', icon: Ellipsis }]

export function signOut() {
  return supabase.auth.signOut()
}
