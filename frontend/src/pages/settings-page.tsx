import { useState } from 'react'
import { Link } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Settings, LogOut, LogIn, Shield, GitBranch, Users, UserPlus, Trash2, ChevronDown } from 'lucide-react'
import { motion, AnimatePresence } from 'framer-motion'
import { useAuth } from '@/lib/auth'
import { listUsers, createUser, deleteUser, apiErrorMessage } from '@/lib/api'
import { useHealthCheck } from '@/lib/use-health'
import type { User } from '@/lib/types'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Input } from '@/components/ui/input'
import { Skeleton } from '@/components/ui/skeleton'
import { Dialog, DialogContent, DialogTrigger } from '@/components/ui/dialog'
import { useToast } from '@/components/ui/toast'
import { PageHeader } from '@/components/shared/page-header'
import { ConfirmDialog } from '@/components/shared/confirm-dialog'
import { cn } from '@/lib/utils'

const PIPELINE_STEPS = [
  { step: 1, label: 'Batch Upload', desc: 'Zip extraction, raw scan indexing' },
  { step: 2, label: 'Auto-Crop', desc: 'Contour detection + perspective warp' },
  { step: 3, label: 'Rotation Review', desc: 'Manual orientation confirmation' },
  { step: 4, label: 'Duplicate Detection', desc: 'pHash + color signature matching' },
  { step: 5, label: 'Card Log', desc: 'Permanent processed card record' },
]

function AddReviewerDialog() {
  const [open, setOpen] = useState(false)
  const [name, setName] = useState('')
  const [password, setPassword] = useState('')
  const queryClient = useQueryClient()
  const { toast } = useToast()

  const mutation = useMutation({
    mutationFn: () => createUser({ name: name.trim(), password }),
    onSuccess: () => {
      toast({
        title: 'Reviewer account created',
        description: `${name.trim()} can now sign in with the password you set.`,
        variant: 'success',
      })
      queryClient.invalidateQueries({ queryKey: ['users'] })
      setOpen(false)
      setName('')
      setPassword('')
    },
    onError: (err) => {
      toast({ title: 'Could not create account', description: apiErrorMessage(err), variant: 'error' })
    },
  })

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button variant="secondary" size="sm" className="gap-2">
          <UserPlus className="h-3.5 w-3.5" />
          Add Reviewer
        </Button>
      </DialogTrigger>
      <DialogContent
        title="Add a Reviewer account"
        description="Reviewers can upload, process, and review batches, but can't manage accounts."
      >
        <div className="flex flex-col gap-4">
          <div className="space-y-1.5">
            <label className="text-caption font-medium text-muted-foreground" htmlFor="new-reviewer-name">
              Display name
            </label>
            <Input
              id="new-reviewer-name"
              autoFocus
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="e.g. Jamie"
              autoComplete="off"
            />
          </div>
          <div className="space-y-1.5">
            <label className="text-caption font-medium text-muted-foreground" htmlFor="new-reviewer-password">
              Password
            </label>
            <Input
              id="new-reviewer-password"
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="At least 8 characters"
              autoComplete="new-password"
            />
          </div>

          {mutation.isError && (
            <p className="rounded-xl bg-accent-rose px-3 py-2 text-caption text-accent-rose-foreground">
              {apiErrorMessage(mutation.error)}
            </p>
          )}

          <Button
            size="lg"
            disabled={!name.trim() || password.length < 8 || mutation.isPending}
            onClick={() => mutation.mutate()}
          >
            {mutation.isPending ? 'Creating…' : 'Create account'}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  )
}

function UserCollapsibleRow({
  account,
  onDelete,
  isPendingDelete,
}: {
  account: User
  onDelete: (user: User) => void
  isPendingDelete: boolean
}) {
  const [expanded, setExpanded] = useState(false)

  return (
    <div className="flex flex-col">
      <button
        type="button"
        onClick={() => setExpanded((prev) => !prev)}
        className="flex items-center justify-between gap-3 px-4 py-3 text-left transition-colors hover:bg-muted/40"
      >
        <div className="min-w-0">
          <p className="truncate text-body font-medium text-primary">{account.name}</p>
          <p className="text-caption text-muted-foreground">
            Added{' '}
            {new Date(account.created_at).toLocaleDateString('en-US', {
              month: 'short',
              day: 'numeric',
              year: 'numeric',
            })}
          </p>
        </div>
        <div className="flex shrink-0 items-center gap-2">
          <Badge variant={account.role === 'admin' ? 'lavender' : 'blue'} className="capitalize">
            {account.role}
          </Badge>
          <ChevronDown
            className={cn(
              'h-4 w-4 text-muted-foreground transition-transform duration-200',
              expanded && 'rotate-180'
            )}
          />
        </div>
      </button>

      <AnimatePresence initial={false}>
        {expanded && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: 'auto', opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.18, ease: 'easeInOut' }}
            className="overflow-hidden bg-muted/25 border-t border-border/60 px-4 py-3"
          >
            <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
              <div className="space-y-1 text-caption text-muted-foreground">
                <p>
                  <span className="font-semibold text-primary">Account ID:</span> #{account.id}
                </p>
                <p>
                  <span className="font-semibold text-primary">Role:</span>{' '}
                  {account.role === 'admin'
                    ? 'Administrator (Full system management & user admin access)'
                    : 'Reviewer (Upload, process, review & export batches)'}
                </p>
              </div>

              {account.role === 'reviewer' && (
                <Button
                  variant="secondary"
                  size="sm"
                  disabled={isPendingDelete}
                  onClick={() => onDelete(account)}
                  className="shrink-0 gap-2 border-accent-rose/60 text-accent-rose-foreground hover:bg-accent-rose hover:border-accent-rose"
                >
                  <Trash2 className="h-3.5 w-3.5" />
                  Delete account
                </Button>
              )}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}

function UserManagementCard() {
  const queryClient = useQueryClient()
  const { toast } = useToast()

  const { data: users, isLoading } = useQuery({ queryKey: ['users'], queryFn: listUsers })

  const [pendingDelete, setPendingDelete] = useState<User | null>(null)

  const deleteMutation = useMutation({
    mutationFn: (userId: number) => deleteUser(userId),
    onSuccess: () => {
      toast({ title: 'Account deleted', variant: 'success' })
      queryClient.invalidateQueries({ queryKey: ['users'] })
      setPendingDelete(null)
    },
    onError: (err) => {
      toast({ title: 'Could not delete account', description: apiErrorMessage(err), variant: 'error' })
    },
  })

  function closeDeleteDialog(open: boolean) {
    if (!open) {
      setPendingDelete(null)
      deleteMutation.reset()
    }
  }

  return (
    <Card>
      <CardContent className="p-0">
        <div className="flex items-center justify-between gap-2 border-b border-border px-4 py-3">
          <div className="flex items-center gap-2">
            <Users className="h-3.5 w-3.5 text-muted-foreground" />
            <p className="text-card-title text-primary">Team</p>
          </div>
          <AddReviewerDialog />
        </div>
        <div className="divide-y divide-border">
          {isLoading ? (
            <div className="space-y-2 px-4 py-4">
              <Skeleton className="h-5 w-full rounded-lg" />
              <Skeleton className="h-5 w-3/4 rounded-lg" />
            </div>
          ) : users?.length ? (
            users.map((account) => (
              <UserCollapsibleRow
                key={account.id}
                account={account}
                onDelete={setPendingDelete}
                isPendingDelete={deleteMutation.isPending}
              />
            ))
          ) : (
            <p className="px-4 py-4 text-caption text-muted-foreground">No accounts yet.</p>
          )}
        </div>
      </CardContent>

      <ConfirmDialog
        open={pendingDelete !== null}
        onOpenChange={closeDeleteDialog}
        title={`Remove ${pendingDelete?.name ?? ''}'s account?`}
        confirmLabel="Delete account"
        loadingLabel="Deleting…"
        destructive
        isLoading={deleteMutation.isPending}
        error={deleteMutation.isError ? apiErrorMessage(deleteMutation.error) : null}
        onConfirm={() => {
          if (pendingDelete) deleteMutation.mutate(pendingDelete.id)
        }}
      >
        <p className="text-caption text-muted-foreground">
          This is permanent and can&apos;t be undone. They&apos;ll be signed out immediately and
          won&apos;t be able to log back in.
        </p>
      </ConfirmDialog>
    </Card>
  )
}

export function SettingsPage() {
  const { user, isAdmin, logout } = useAuth()
  const { statusText, badgeVariant } = useHealthCheck()

  return (
    <div className="space-y-5">
      <PageHeader title="Settings" description="Account and system configuration." />

      <div className="grid grid-cols-1 gap-5 lg:grid-cols-12">
        {/* Left Column: Account & Team */}
        <div className="space-y-5 lg:col-span-6">
          {/* Account card */}
          <Card>
            <CardContent className="p-0">
              {user ? (
                <div className="flex items-center justify-between gap-4 px-4 py-4">
                  <div className="min-w-0">
                    <p className="truncate text-section text-primary">{user.name}</p>
                    <div className="mt-1 flex items-center gap-1.5">
                      <Shield className="h-3 w-3 shrink-0 text-muted-foreground" />
                      <p className="text-caption capitalize text-muted-foreground">{user.role}</p>
                    </div>
                  </div>
                  <Button
                    variant="secondary"
                    size="sm"
                    onClick={logout}
                    className="shrink-0 gap-2 border-accent-rose/60 text-accent-rose-foreground hover:bg-accent-rose hover:border-accent-rose"
                  >
                    <LogOut className="h-3.5 w-3.5" />
                    Sign out
                  </Button>
                </div>
              ) : (
                <div className="flex items-center justify-between gap-4 px-4 py-4">
                  <p className="text-body text-muted-foreground">
                    Sign in to upload, process, and review batches.
                  </p>
                  <Link to="/login" state={{ from: '/settings' }} className="shrink-0">
                    <Button size="sm" className="gap-2">
                      <LogIn className="h-3.5 w-3.5" />
                      Sign in
                    </Button>
                  </Link>
                </div>
              )}
            </CardContent>
          </Card>

          {/* User management (Admin only) */}
          {isAdmin && <UserManagementCard />}
        </div>

        {/* Right Column: System & Pipeline */}
        <div className="space-y-5 lg:col-span-6">
          {/* System info */}
          <Card>
            <CardContent className="p-0">
              <div className="flex items-center gap-2 border-b border-border px-4 py-3">
                <Settings className="h-3.5 w-3.5 text-muted-foreground" />
                <p className="text-card-title text-primary">System</p>
              </div>
              <div className="divide-y divide-border">
                {[
                  { label: 'Application', value: 'CardFlow' },
                  { label: 'Version', value: '1.0.0' },
                  { label: 'API Base', value: '/api' },
                  { label: 'Status', value: statusText, badge: badgeVariant },
                ].map(({ label, value, badge }) => (
                  <div key={label} className="flex items-center justify-between px-4 py-2.5">
                    <span className="text-caption text-muted-foreground">{label}</span>
                    {badge ? (
                      <Badge variant={badge}>{value}</Badge>
                    ) : (
                      <span className="text-body font-medium text-primary">{value}</span>
                    )}
                  </div>
                ))}
              </div>
            </CardContent>
          </Card>

          {/* Pipeline info */}
          <Card>
            <CardContent className="p-0">
              <div className="flex items-center gap-2 border-b border-border px-4 py-3">
                <GitBranch className="h-3.5 w-3.5 text-muted-foreground" />
                <p className="text-card-title text-primary">Processing Pipeline</p>
              </div>
              <div className="px-4 pb-4 pt-3">
                <p className="text-caption leading-relaxed text-muted-foreground">
                  CardFlow processes sports card scans through a 5-stage pipeline:
                  batch upload → auto-crop → rotation review → duplicate detection → card log.
                </p>
                <div className="mt-4 space-y-0">
                  {PIPELINE_STEPS.map(({ step, label, desc }, idx) => (
                    <div key={step} className="flex gap-3">
                      {/* Track column */}
                      <div className="flex flex-col items-center">
                        <div className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-accent-lavender text-caption font-semibold text-accent-lavender-foreground">
                          {step}
                        </div>
                        {idx < PIPELINE_STEPS.length - 1 && (
                          <div className="w-px flex-1 bg-border my-1" />
                        )}
                      </div>
                      {/* Content */}
                      <div className={idx < PIPELINE_STEPS.length - 1 ? 'pb-4' : 'pb-0'}>
                        <p className="text-caption font-semibold text-primary leading-6">{label}</p>
                        <p className="text-caption text-muted-foreground">{desc}</p>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  )
}
