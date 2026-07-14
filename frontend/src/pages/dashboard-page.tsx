import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { RotateCw, Copy, Upload, ArrowRight, Layers, CheckCircle2, Clock } from 'lucide-react'
import { motion } from 'framer-motion'
import { useAuth } from '@/lib/auth'
import { listBatches, getRotationQueueCount, getDuplicateQueueCount } from '@/lib/api'
import { StatCard } from '@/components/shared/stat-card'
import { BatchStatusBadge } from '@/components/shared/status-badge'
import { UploadBatchDialog } from '@/components/shared/upload-batch-dialog'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import { cn } from '@/lib/utils'
import type { Batch } from '@/lib/types'

const container = {
  hidden: {},
  show: { transition: { staggerChildren: 0.05 } },
}
const item = {
  hidden: { opacity: 0, y: 6 },
  show: { opacity: 1, y: 0, transition: { duration: 0.2 } },
}

function BatchRow({ batch }: { batch: Batch }) {
  return (
    <Link to={`/batches/${batch.id}`}>
      <motion.div
        variants={item}
        className="group flex items-center justify-between rounded-xl border border-border bg-surface px-4 py-3 shadow-soft transition-all duration-200 hover:shadow-float hover:-translate-y-px"
      >
        <div className="flex items-center gap-3">
          <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-muted">
            <Layers className="h-4 w-4 text-muted-foreground" />
          </div>
          <div>
            <p className="text-body font-medium text-primary">
              {batch.source_label ?? `Batch #${batch.id}`}
            </p>
            <p className="text-caption text-muted-foreground">
              {new Date(batch.created_at).toLocaleDateString('en-US', {
                month: 'short', day: 'numeric', year: 'numeric',
              })}
            </p>
          </div>
        </div>
        <div className="flex items-center gap-3">
          <BatchStatusBadge status={batch.status} />
          <ArrowRight className="h-4 w-4 text-muted-foreground opacity-0 transition-opacity group-hover:opacity-100" />
        </div>
      </motion.div>
    </Link>
  )
}

export function DashboardPage() {
  const { user } = useAuth()

  const { data: batches, isLoading: batchesLoading } = useQuery({
    queryKey: ['batches'],
    queryFn: () => listBatches(5),
  })

  const { data: rotationCount } = useQuery({
    queryKey: ['queue-count', 'rotation'],
    queryFn: getRotationQueueCount,
    refetchInterval: 15_000,
  })

  const { data: duplicateCount } = useQuery({
    queryKey: ['queue-count', 'duplicate'],
    queryFn: getDuplicateQueueCount,
    refetchInterval: 15_000,
  })

  const rotQ = rotationCount?.count ?? 0
  const dupQ = duplicateCount?.count ?? 0

  return (
    <motion.div
      className="space-y-8 py-2"
      variants={container}
      initial="hidden"
      animate="show"
    >
      {/* Welcome */}
      <motion.div variants={item} className="flex items-start justify-between">
        <div>
          <h1 className="text-page-title text-primary">
            Good{' '}
            {new Date().getHours() < 12 ? 'morning' : new Date().getHours() < 18 ? 'afternoon' : 'evening'},{' '}
            {user?.name ?? 'there'} 👋
          </h1>
          <p className="mt-1 text-body text-muted-foreground">
            Here's what needs your attention today.
          </p>
        </div>
        <UploadBatchDialog
          trigger={
            <Button size="md" className="gap-2">
              <Upload className="h-4 w-4" />
              Upload Batch
            </Button>
          }
        />
      </motion.div>

      {/* Pipeline Status */}
      <motion.div variants={item}>
        <p className="mb-3 text-caption font-semibold uppercase tracking-wider text-muted-foreground">
          Pipeline Status
        </p>
        <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
          <StatCard
            label="Rotation Queue"
            value={rotQ}
            icon={<RotateCw className="h-5 w-5" />}
            accent="lavender"
            hint={rotQ > 0 ? 'Cards awaiting review' : 'All clear'}
          />
          <StatCard
            label="Duplicate Queue"
            value={dupQ}
            icon={<Copy className="h-5 w-5" />}
            accent="peach"
            hint={dupQ > 0 ? 'Pairs awaiting decision' : 'All clear'}
          />
          <StatCard
            label="Total Batches"
            value={batches?.length ?? '—'}
            icon={<Layers className="h-5 w-5" />}
            accent="blue"
            hint="Recent 5 shown"
          />
          <StatCard
            label="System"
            value="Operational"
            icon={<CheckCircle2 className="h-5 w-5" />}
            accent="mint"
          />
        </div>
      </motion.div>

      {/* Quick Actions */}
      <motion.div variants={item}>
        <p className="mb-3 text-caption font-semibold uppercase tracking-wider text-muted-foreground">
          Quick Actions
        </p>
        <div className="grid grid-cols-2 gap-3 lg:grid-cols-3">
          <Link to="/rotation-review">
            <Card className={cn(
              'group cursor-pointer p-5 transition-all duration-200 hover:shadow-float hover:-translate-y-px',
              rotQ > 0 && 'ring-2 ring-accent-lavender-solid/40'
            )}>
              <div className="flex items-center gap-3">
                <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-accent-lavender text-accent-lavender-foreground">
                  <RotateCw className="h-5 w-5" />
                </div>
                <div>
                  <p className="text-body font-semibold text-primary">Rotation Review</p>
                  <p className="text-caption text-muted-foreground">
                    {rotQ > 0 ? `${rotQ} card${rotQ === 1 ? '' : 's'} waiting` : 'Queue empty'}
                  </p>
                </div>
              </div>
            </Card>
          </Link>
          <Link to="/duplicate-review">
            <Card className={cn(
              'group cursor-pointer p-5 transition-all duration-200 hover:shadow-float hover:-translate-y-px',
              dupQ > 0 && 'ring-2 ring-accent-peach-solid/40'
            )}>
              <div className="flex items-center gap-3">
                <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-accent-peach text-accent-peach-foreground">
                  <Copy className="h-5 w-5" />
                </div>
                <div>
                  <p className="text-body font-semibold text-primary">Duplicate Review</p>
                  <p className="text-caption text-muted-foreground">
                    {dupQ > 0 ? `${dupQ} pair${dupQ === 1 ? '' : 's'} waiting` : 'Queue empty'}
                  </p>
                </div>
              </div>
            </Card>
          </Link>
          <Link to="/batches">
            <Card className="group cursor-pointer p-5 transition-all duration-200 hover:shadow-float hover:-translate-y-px">
              <div className="flex items-center gap-3">
                <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-accent-blue text-accent-blue-foreground">
                  <Layers className="h-5 w-5" />
                </div>
                <div>
                  <p className="text-body font-semibold text-primary">Manage Batches</p>
                  <p className="text-caption text-muted-foreground">Upload & view batches</p>
                </div>
              </div>
            </Card>
          </Link>
        </div>
      </motion.div>

      {/* Recent Batches */}
      <motion.div variants={item}>
        <div className="mb-3 flex items-center justify-between">
          <p className="text-caption font-semibold uppercase tracking-wider text-muted-foreground">
            Recent Batches
          </p>
          <Link to="/batches" className="text-caption font-medium text-muted-foreground hover:text-primary transition-colors">
            View all →
          </Link>
        </div>

        {batchesLoading ? (
          <div className="space-y-2">
            {Array.from({ length: 3 }).map((_, i) => (
              <Skeleton key={i} className="h-16 w-full rounded-xl" />
            ))}
          </div>
        ) : !batches?.length ? (
          <Card className="flex flex-col items-center gap-3 p-10 text-center">
            <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-muted">
              <Clock className="h-6 w-6 text-muted-foreground" />
            </div>
            <div>
              <p className="text-body font-medium text-primary">No batches yet</p>
              <p className="mt-1 text-caption text-muted-foreground">Upload your first batch to get started.</p>
            </div>
            <UploadBatchDialog
              trigger={<Button variant="secondary" size="sm">Upload batch</Button>}
            />
          </Card>
        ) : (
          <motion.div className="space-y-2" variants={container} initial="hidden" animate="show">
            {batches.map((b) => <BatchRow key={b.id} batch={b} />)}
          </motion.div>
        )}
      </motion.div>
    </motion.div>
  )
}
