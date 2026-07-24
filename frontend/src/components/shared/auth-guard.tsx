import { useAuth } from '@/lib/auth'

export function AuthGuard({ children }: { children: React.ReactNode }) {
  const { isLoading } = useAuth()

  if (isLoading) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-background">
        <div className="h-8 w-8 animate-spin rounded-full border-2 border-border border-t-primary" />
      </div>
    )
  }

  // Guests (unauthenticated) can view the dashboard read-only -- individual
  // pages/components gate mutating controls on useAuth().canEdit instead of
  // this component blocking navigation outright.
  return <>{children}</>
}
