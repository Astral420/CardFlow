import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { RotateCw, Copy, Upload, ArrowRight, Layers, CheckCircle2, Clock, ChevronRight, AlertCircle } from 'lucide-react'
import { motion } from 'framer-motion'
import { listBatches, getRotationQueueCount, getDuplicateQueueCount } from '@/lib/api'
import { useHealthCheck } from '@/lib/use-health'
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
    <Link
      to={`/batches/${batch.id}`}
      className="group flex items-center gap-4 px-4 py-3 transition-colors duration-150 hover:bg-muted/40"
    >
      <p className="min-w-0 flex-1 truncate text-body font-medium text-primary">
        {batch.source_label ?? `Batch #${batch.id}`}
      </p>
      <p className="shrink-0 text-caption text-muted-foreground tabular-nums">
        {new Date(batch.created_at).toLocaleDateString('en-US', {
          month: 'short', day: 'numeric', year: 'numeric',
        })}
      </p>
      <div className="flex shrink-0 items-center gap-2">
        <BatchStatusBadge status={batch.status} />
        <ArrowRight className="h-3.5 w-3.5 text-muted-foreground opacity-0 transition-opacity group-hover:opacity-100" />
      </div>
    </Link>
  )
}

export function DashboardPage() {
  const { data: batches, isLoading: batchesLoading } = useQuery({
    queryKey: ['batches'],
    queryFn: () => listBatches(5),
    refetchInterval: (query) => {
      const list = query.state.data ?? []
      const hasActive = list.some((b) => b.status !== 'complete')
      return hasActive ? 3000 : 15_000
    },
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

  const { statusText, isOperational, accent, isLoading } = useHealthCheck()

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
            icon={<RotateCw className="h-4 w-4" />}
            accent="lavender"
            hint={rotQ > 0 ? 'Cards awaiting review' : 'All clear'}
          />
          <StatCard
            label="Duplicate Queue"
            value={dupQ}
            icon={<Copy className="h-4 w-4" />}
            accent="peach"
            hint={dupQ > 0 ? 'Pairs awaiting decision' : 'All clear'}
          />
          <StatCard
            label="Total Batches"
            value={batches?.length ?? '—'}
            icon={<Layers className="h-4 w-4" />}
            accent="blue"
            hint="Recent 5 shown"
          />
          <StatCard
            label="System"
            value={statusText}
            icon={
              isLoading ? (
                <Clock className="h-4 w-4" />
              ) : isOperational ? (
                <CheckCircle2 className="h-4 w-4" />
              ) : (
                <AlertCircle className="h-4 w-4 text-accent-rose-foreground" />
              )
            }
            accent={accent}
          />
        </div>
      </motion.div>

      {/* Needs attention / quick actions */}
      <motion.div variants={item}>
        <SectionLabel className="mb-2.5">Needs Attention</SectionLabel>
        <div className="grid grid-cols-2 gap-3 lg:grid-cols-3">
          <Link to="/rotation-review">
            <Card className={cn(
              'group cursor-pointer p-4 transition-all duration-150 hover:border-border/80 hover:shadow-float',
              rotQ > 0 && 'ring-1 ring-accent-lavender-solid/40'
            )}>
              <div className="flex items-center gap-2">
                <RotateCw className="h-4 w-4 shrink-0 text-muted-foreground" />
                <p className="flex-1 text-body font-semibold text-primary">Rotation Review</p>
                <ChevronRight className="h-4 w-4 shrink-0 text-muted-foreground opacity-40 transition-opacity group-hover:opacity-100" />
              </div>
              <p className="mt-1.5 text-caption text-muted-foreground">
                {rotQ > 0 ? `${rotQ} card${rotQ === 1 ? '' : 's'} waiting` : 'Queue empty'}
              </p>
            </Card>
          </Link>
          <Link to="/duplicate-review">
            <Card className={cn(
              'group cursor-pointer p-4 transition-all duration-150 hover:border-border/80 hover:shadow-float',
              dupQ > 0 && 'ring-1 ring-accent-peach-solid/40'
            )}>
              <div className="flex items-center gap-2">
                <Copy className="h-4 w-4 shrink-0 text-muted-foreground" />
                <p className="flex-1 text-body font-semibold text-primary">Duplicate Review</p>
                <ChevronRight className="h-4 w-4 shrink-0 text-muted-foreground opacity-40 transition-opacity group-hover:opacity-100" />
              </div>
              <p className="mt-1.5 text-caption text-muted-foreground">
                {dupQ > 0 ? `${dupQ} pair${dupQ === 1 ? '' : 's'} waiting` : 'Queue empty'}
              </p>
            </Card>
          </Link>
          <Link to="/batches">
            <Card className="group cursor-pointer p-4 transition-all duration-150 hover:border-border/80 hover:shadow-float">
              <div className="flex items-center gap-2">
                <Layers className="h-4 w-4 shrink-0 text-muted-foreground" />
                <p className="flex-1 text-body font-semibold text-primary">Manage Batches</p>
                <ChevronRight className="h-4 w-4 shrink-0 text-muted-foreground opacity-40 transition-opacity group-hover:opacity-100" />
              </div>
              <p className="mt-1.5 text-caption text-muted-foreground">Upload &amp; view batches</p>
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
          <Card className="overflow-hidden">
            <motion.div className="divide-y divide-border" variants={container} initial="hidden" animate="show">
              {batches.map((b) => <BatchRow key={b.id} batch={b} />)}
            </motion.div>
          </Card>
        )}
      </motion.div>
    </motion.div>
  )
}
