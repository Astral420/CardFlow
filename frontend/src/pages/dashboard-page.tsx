import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { RotateCw, Copy, Upload, ArrowRight, Layers, CheckCircle2, Clock } from 'lucide-react'
import { motion } from 'framer-motion'
import { listBatches, getRotationQueueCount, getDuplicateQueueCount } from '@/lib/api'
import { StatCard } from '@/components/shared/stat-card'
import { BatchStatusBadge } from '@/components/shared/status-badge'
import { UploadBatchDialog } from '@/components/shared/upload-batch-dialog'
import { PageHeader } from '@/components/shared/page-header'
import { SectionLabel } from '@/components/shared/section-label'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import { cn } from '@/lib/utils'
import type { Batch } from '@/lib/types'

const container = {
  hidden: {},
  show: { transition: { staggerChildren: 0.04 } },
}
const item = {
  hidden: { opacity: 0, y: 6 },
  show: { opacity: 1, y: 0, transition: { duration: 0.18 } },
}

function BatchRow({ batch }: { batch: Batch }) {
  return (
    <Link to={`/batches/${batch.id}`}>
      <motion.div
        variants={item}
        className="group flex items-center justify-between rounded-lg border border-border bg-surface px-3.5 py-2.5 transition-colors duration-150 hover:bg-muted/40"
      >
        <div className="flex items-center gap-3">
          <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-muted">
            <Layers className="h-3.5 w-3.5 text-muted-foreground" />
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
          <ArrowRight className="h-3.5 w-3.5 text-muted-foreground opacity-0 transition-opacity group-hover:opacity-100" />
        </div>
      </motion.div>
    </Link>
  )
}

export function DashboardPage() {
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
      className="space-y-6"
      variants={container}
      initial="hidden"
      animate="show"
    >
      <motion.div variants={item}>
        <PageHeader
          title="Dashboard"
          description="Operational overview of your card processing pipeline."
          actions={
            <UploadBatchDialog
              trigger={
                <Button size="md" className="gap-2">
                  <Upload className="h-4 w-4" />
                  Upload Batch
                </Button>
              }
            />
          }
        />
      </motion.div>

      {/* Top metrics */}
      <motion.div variants={item}>
        <SectionLabel className="mb-2.5">Top Metrics</SectionLabel>
        <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
          <StatCard
            label="Rotation Queue"
            value={rotQ}
            icon={<RotateCw className="h-4.5 w-4.5" />}
            accent="lavender"
            hint={rotQ > 0 ? 'Cards awaiting review' : 'All clear'}
          />
          <StatCard
            label="Duplicate Queue"
            value={dupQ}
            icon={<Copy className="h-4.5 w-4.5" />}
            accent="peach"
            hint={dupQ > 0 ? 'Pairs awaiting decision' : 'All clear'}
          />
          <StatCard
            label="Total Batches"
            value={batches?.length ?? '—'}
            icon={<Layers className="h-4.5 w-4.5" />}
            accent="blue"
            hint="Recent 5 shown"
          />
          <StatCard
            label="System"
            value="Operational"
            icon={<CheckCircle2 className="h-4.5 w-4.5" />}
            accent="mint"
          />
        </div>
      </motion.div>

      {/* Needs attention / quick actions */}
      <motion.div variants={item}>
        <SectionLabel className="mb-2.5">Needs Attention</SectionLabel>
        <div className="grid grid-cols-2 gap-3 lg:grid-cols-3">
          <Link to="/rotation-review">
            <Card className={cn(
              'group cursor-pointer p-4 transition-colors duration-150 hover:bg-muted/30',
              rotQ > 0 && 'ring-1 ring-accent-lavender-solid/40'
            )}>
              <div className="flex items-center gap-3">
                <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-accent-lavender text-accent-lavender-foreground">
                  <RotateCw className="h-4.5 w-4.5" />
                </div>
                <div className="min-w-0">
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
              'group cursor-pointer p-4 transition-colors duration-150 hover:bg-muted/30',
              dupQ > 0 && 'ring-1 ring-accent-peach-solid/40'
            )}>
              <div className="flex items-center gap-3">
                <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-accent-peach text-accent-peach-foreground">
                  <Copy className="h-4.5 w-4.5" />
                </div>
                <div className="min-w-0">
                  <p className="text-body font-semibold text-primary">Duplicate Review</p>
                  <p className="text-caption text-muted-foreground">
                    {dupQ > 0 ? `${dupQ} pair${dupQ === 1 ? '' : 's'} waiting` : 'Queue empty'}
                  </p>
                </div>
              </div>
            </Card>
          </Link>
          <Link to="/batches">
            <Card className="group cursor-pointer p-4 transition-colors duration-150 hover:bg-muted/30">
              <div className="flex items-center gap-3">
                <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-accent-blue text-accent-blue-foreground">
                  <Layers className="h-4.5 w-4.5" />
                </div>
                <div className="min-w-0">
                  <p className="text-body font-semibold text-primary">Manage Batches</p>
                  <p className="text-caption text-muted-foreground">Upload &amp; view batches</p>
                </div>
              </div>
            </Card>
          </Link>
        </div>
      </motion.div>

      {/* Recent batches */}
      <motion.div variants={item}>
        <SectionLabel
          className="mb-2.5"
          trailing={
            <Link to="/batches" className="text-caption font-medium text-muted-foreground transition-colors hover:text-primary">
              View all →
            </Link>
          }
        >
          Recent Batches
        </SectionLabel>

        {batchesLoading ? (
          <div className="space-y-2">
            {Array.from({ length: 3 }).map((_, i) => (
              <Skeleton key={i} className="h-14 w-full rounded-lg" />
            ))}
          </div>
        ) : !batches?.length ? (
          <Card className="flex flex-col items-center gap-3 p-10 text-center">
            <div className="flex h-11 w-11 items-center justify-center rounded-xl bg-muted">
              <Clock className="h-5 w-5 text-muted-foreground" />
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
