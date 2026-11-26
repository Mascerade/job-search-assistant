import { Activity, Ellipsis, Inbox, Plus, Settings, SquareKanban, UserRound, type LucideIcon } from 'lucide-react'
import { supabase } from './supabase'

export interface NavItem {
  to: string
  label: string
  icon: LucideIcon
}

export const PRIMARY_NAV: NavItem[] = [
  { to: '/', label: 'Today', icon: Inbox },
  { to: '/board', label: 'Board', icon: SquareKanban },
  { to: '/add', label: 'Add job', icon: Plus },
]

export const SECONDARY_NAV: NavItem[] = [
  { to: '/profile', label: 'Profile', icon: UserRound },
  { to: '/settings', label: 'Settings', icon: Settings },
  { to: '/runs', label: 'Runs & spend', icon: Activity },
]

// Phones: 4 items max in the bottom bar (UI/UX Pro Max: bottom nav ≤ 5).
export const MOBILE_NAV: NavItem[] = [...PRIMARY_NAV, { to: '/more', label: 'More', icon: Ellipsis }]

export function signOut() {
  return supabase.auth.signOut()
}
