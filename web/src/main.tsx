import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { FileQuestion } from 'lucide-react'
import { ThemeProvider } from 'next-themes'
import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { createBrowserRouter, Link, Navigate, Outlet, RouterProvider } from 'react-router'
import { AuthProvider, useAuth } from '@/auth/AuthProvider'
import { AppShell } from '@/components/AppShell'
import { EmptyState } from '@/components/EmptyState'
import { Button } from '@/components/ui/button'
import { Toaster } from '@/components/ui/sonner'
import { TooltipProvider } from '@/components/ui/tooltip'
import { LoginPage } from '@/pages/LoginPage'
import { TodayPage } from '@/pages/TodayPage'
import './index.css'

const queryClient = new QueryClient({
  defaultOptions: { queries: { staleTime: 30_000, refetchOnWindowFocus: true } },
})

function RequireAuth() {
  const { session, loading } = useAuth()
  if (loading) return null
  if (!session) return <Navigate to="/login" replace />
  return <Outlet />
}

function NotFound() {
  return (
    <EmptyState
      icon={FileQuestion}
      title="Page not found"
      action={
        <Button asChild variant="outline">
          <Link to="/">Go to Today</Link>
        </Button>
      }
    />
  )
}

const router = createBrowserRouter([
  { path: '/login', element: <LoginPage /> },
  {
    element: <RequireAuth />,
    children: [
      {
        element: <AppShell />,
        children: [
          { index: true, element: <TodayPage /> },
          // Other pages load on demand to keep the first download small.
          { path: 'board', lazy: () => import('@/pages/BoardPage').then((m) => ({ Component: m.BoardPage })) },
          { path: 'add', lazy: () => import('@/pages/AddJobPage').then((m) => ({ Component: m.AddJobPage })) },
          { path: 'jobs/:id', lazy: () => import('@/pages/JobDetailPage').then((m) => ({ Component: m.JobDetailPage })) },
          { path: 'profile', lazy: () => import('@/pages/ProfilePage').then((m) => ({ Component: m.ProfilePage })) },
          { path: 'settings', lazy: () => import('@/pages/SettingsPage').then((m) => ({ Component: m.SettingsPage })) },
          { path: 'runs', lazy: () => import('@/pages/RunsPage').then((m) => ({ Component: m.RunsPage })) },
          { path: 'more', lazy: () => import('@/pages/MorePage').then((m) => ({ Component: m.MorePage })) },
          { path: '*', element: <NotFound /> },
        ],
      },
    ],
  },
])

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <ThemeProvider attribute="class" defaultTheme="system" enableSystem disableTransitionOnChange>
      <QueryClientProvider client={queryClient}>
        <AuthProvider>
          <TooltipProvider>
            <RouterProvider router={router} />
            <Toaster position="top-center" />
          </TooltipProvider>
        </AuthProvider>
      </QueryClientProvider>
    </ThemeProvider>
  </StrictMode>,
)
