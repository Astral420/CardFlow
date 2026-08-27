/**
 * DeleteBatchDialog
 *
 * Two-step irreversible-action dialog for hard-deleting a batch:
 *
 *   Step 1 — Warning review
 *     Shows exactly what will be permanently destroyed (R2 objects, DB rows).
 *     "I understand, continue" advances to step 2.
 *
 *   Step 2 — Type-to-confirm
 *     User must type the batch name (source_label or "Batch #<id>") before the
 *     destructive confirm button activates. This pattern is standard for
 *     unrecoverable destructive actions (GitHub, Vercel, AWS) and ensures
 *     color alone is not the only safeguard (ui-ux-pro-max checklist).
 *
 * Optimistic UX Flow:
 *   On confirm: dialog closes instantly, optimistic deletion removes batch
 *   from cache, user is navigated to /batches, and a persistent loading toast
 *   tracks background Celery progress. On failure, cache is rolled back and
 *   toast transitions to error.
 */

import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { AlertTriangle, Trash2, ShieldAlert } from 'lucide-react'
import { AnimatePresence, motion } from 'framer-motion'
import { Dialog, DialogContent, DialogTrigger } from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { deleteBatch, apiErrorMessage } from '@/lib/api'
import { useToast } from '@/components/ui/toast'
import type { Batch, BatchDetail } from '@/lib/types'

interface DeleteBatchDialogProps {
  batch: BatchDetail | Batch
  trigger: React.ReactNode
}

type Step = 'warning' | 'confirm'

export function DeleteBatchDialog({ batch, trigger }: DeleteBatchDialogProps) {
  const [open, setOpen] = useState(false)
  const [step, setStep] = useState<Step>('warning')
  const [typed, setTyped] = useState('')
  const [error, setError] = useState<string | null>(null)

  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const { toast, update: updateToast } = useToast()

  const batchLabel = batch.source_label ?? `Batch #${batch.id}`
  const confirmMatch = typed.trim() === batchLabel.trim()
  const toastId = `delete-batch-${batch.id}`

  const mutation = useMutation({
    mutationFn: () => deleteBatch(batch.id),

    onMutate: async () => {
      // 1. Cancel in-flight list and detail queries
      await queryClient.cancelQueries({ queryKey: ['batches'] })
      await queryClient.cancelQueries({ queryKey: ['batch', batch.id] })

      // 2. Snapshot previous list state for rollback
      const previousBatches = queryClient.getQueryData<Batch[]>(['batches'])

      // 3. Optimistic removal from batch list cache
      queryClient.setQueryData<Batch[]>(['batches'], (old) =>
        old ? old.filter((b) => b.id !== batch.id) : []
      )

      // 4. Mark single batch detail as deleting in cache
      queryClient.setQueryData<BatchDetail>(['batch', batch.id], (old) =>
        old ? { ...old, status: 'deleting' } : undefined
      )

      // 5. Fire persistent loading toast
      toast({
        id: toastId,
        variant: 'loading',
        title: `Deleting ${batchLabel}…`,
        description: 'Removing images and records in background.',
        persistent: true,
      })

      // 6. Instantly close modal and unblock user navigation
      setOpen(false)
      navigate('/batches')

      return { previousBatches }
    },

    onSuccess: () => {
      updateToast(toastId, {
        variant: 'success',
        title: `${batchLabel} deleted`,
        description: undefined,
        persistent: false,
      })
      queryClient.invalidateQueries({ queryKey: ['batches'] })
      queryClient.removeQueries({ queryKey: ['batch', batch.id] })
      queryClient.removeQueries({ queryKey: ['batch-scans', batch.id] })
      queryClient.removeQueries({ queryKey: ['batch-duplicates', batch.id] })
    },

    onError: (err, _vars, context) => {
      if (context?.previousBatches) {
        queryClient.setQueryData(['batches'], context.previousBatches)
      }
      queryClient.invalidateQueries({ queryKey: ['batch', batch.id] })

      updateToast(toastId, {
        variant: 'error',
        title: `Failed to delete ${batchLabel}`,
        description: apiErrorMessage(err),
        persistent: false,
      })
    },
  })

  function handleOpenChange(next: boolean) {
    if (mutation.isPending) return
    if (!next) {
      // Reset to initial state when dialog closes.
      setStep('warning')
      setTyped('')
      setError(null)
      mutation.reset()
    }
    setOpen(next)
  }

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogTrigger asChild>{trigger}</DialogTrigger>
      <DialogContent
        title="Delete batch"
        description={
          step === 'warning'
            ? 'Review what will be permanently removed.'
            : 'Type the batch name to confirm.'
        }
        className="max-w-md"
      >
        <AnimatePresence mode="wait" initial={false}>
          {/* ── Step 1: Warning ── */}
          {step === 'warning' && (
            <motion.div
              key="warning"
              initial={{ opacity: 0, x: -12 }}
              animate={{ opacity: 1, x: 0 }}
              exit={{ opacity: 0, x: 12 }}
              transition={{ duration: 0.18 }}
              className="flex flex-col gap-4"
            >
              {/* Destructive warning banner */}
              <div className="flex gap-3 rounded-xl border border-accent-rose-solid/30 bg-accent-rose/20 p-4">
                <ShieldAlert className="mt-0.5 h-5 w-5 shrink-0 text-accent-rose-foreground" />
                <div className="space-y-1">
                  <p className="text-body font-semibold text-accent-rose-foreground">
                    This action is permanent and cannot be undone.
                  </p>
                  <p className="text-caption text-accent-rose-foreground/80">
                    Deleting this batch will immediately and irreversibly remove:
                  </p>
                </div>
              </div>

              {/* Destruction checklist */}
              <ul className="divide-y divide-border rounded-xl border border-border bg-muted/40 overflow-hidden">
                {[
                  { label: 'All raw scan images', sub: 'R2 cloud storage — permanent' },
                  { label: 'All cropped card images', sub: 'R2 cloud storage — permanent' },
                  { label: 'Original upload ZIP', sub: 'R2 cloud storage — permanent' },
                  { label: 'All database records', sub: 'Scans, crops, duplicate data' },
                ].map(({ label, sub }) => (
                  <li key={label} className="flex items-center gap-3 px-4 py-2.5">
                    <AlertTriangle className="h-3.5 w-3.5 shrink-0 text-accent-rose-foreground" />
                    <div className="min-w-0">
                      <p className="text-body font-medium text-primary">{label}</p>
                      <p className="text-caption text-muted-foreground">{sub}</p>
                    </div>
                  </li>
                ))}
              </ul>

              {/* Batch being deleted */}
              <div className="rounded-xl border border-border bg-surface px-4 py-3">
                <p className="text-caption font-semibold uppercase tracking-wider text-muted-foreground">
                  Batch to delete
                </p>
                <p className="mt-1 truncate text-body font-medium text-primary">{batchLabel}</p>
                {'counts' in batch && batch.counts && (
                  <p className="mt-0.5 text-caption text-muted-foreground">
                    {batch.counts.scans} scan{batch.counts.scans !== 1 ? 's' : ''} ·{' '}
                    {batch.counts.cropped + batch.counts.skipped} cropped
                  </p>
                )}
              </div>

              <div className="flex justify-end gap-2">
                <Button
                  variant="secondary"
                  size="md"
                  onClick={() => handleOpenChange(false)}
                >
                  Cancel
                </Button>
                <Button
                  variant="destructive"
                  size="md"
                  onClick={() => setStep('confirm')}
                  aria-label="Continue to confirmation step"
                >
                  I understand, continue
                </Button>
              </div>
            </motion.div>
          )}

          {/* ── Step 2: Type-to-confirm ── */}
          {step === 'confirm' && (
            <motion.div
              key="confirm"
              initial={{ opacity: 0, x: 12 }}
              animate={{ opacity: 1, x: 0 }}
              exit={{ opacity: 0, x: -12 }}
              transition={{ duration: 0.18 }}
              className="flex flex-col gap-4"
            >
              <div className="space-y-1.5">
                <label
                  htmlFor="delete-confirm-input"
                  className="text-body text-primary"
                >
                  Type{' '}
                  <span className="rounded bg-muted px-1.5 py-0.5 font-mono text-caption font-semibold text-primary">
                    {batchLabel}
                  </span>{' '}
                  to confirm deletion.
                </label>
                <Input
                  id="delete-confirm-input"
                  autoFocus
                  placeholder={batchLabel}
                  value={typed}
                  onChange={(e) => {
                    setTyped(e.target.value)
                    setError(null)
                  }}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter' && confirmMatch && !mutation.isPending) {
                      mutation.mutate()
                    }
                  }}
                  aria-describedby={error ? 'delete-error' : undefined}
                  className={confirmMatch ? 'border-accent-mint-solid/60' : ''}
                  disabled={mutation.isPending}
                />
              </div>

              {error && (
                <p
                  id="delete-error"
                  role="alert"
                  className="rounded-xl bg-accent-rose px-3 py-2 text-caption text-accent-rose-foreground"
                >
                  {error}
                </p>
              )}

              <div className="flex justify-end gap-2">
                <Button
                  variant="secondary"
                  size="md"
                  disabled={mutation.isPending}
                  onClick={() => {
                    setStep('warning')
                    setTyped('')
                    setError(null)
                  }}
                >
                  Back
                </Button>
                <Button
                  variant="destructive"
                  size="md"
                  disabled={!confirmMatch || mutation.isPending}
                  onClick={() => mutation.mutate()}
                  aria-label="Confirm permanent batch deletion"
                  className="gap-2"
                >
                  <Trash2 className="h-3.5 w-3.5" />
                  Delete batch permanently
                </Button>
              </div>
            </motion.div>
          )}
        </AnimatePresence>
      </DialogContent>
    </Dialog>
  )
}

