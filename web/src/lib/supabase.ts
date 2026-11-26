import { createClient } from '@supabase/supabase-js'
import type { Database } from './database.types'

const url = import.meta.env.VITE_SUPABASE_URL as string | undefined
const key = import.meta.env.VITE_SUPABASE_PUBLISHABLE_KEY as string | undefined

if (!url || !key) {
  throw new Error(
    'Missing VITE_SUPABASE_URL or VITE_SUPABASE_PUBLISHABLE_KEY. Copy web/.env.example to web/.env.local and fill them in.',
  )
}

// The publishable key is safe in the browser: row-level security limits every
// table to the single owner account.
export const supabase = createClient<Database>(url, key)
