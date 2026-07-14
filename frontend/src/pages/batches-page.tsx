import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { Upload, Search, Layers, ArrowRight } from 'lucide-react'
import { motion } from 'framer-motion'
import { listBatches } from '@/lib/api'
import { BatchStatusBadge } from '@/components/shared/status-badge'
import { UploadBatchDialog } from '@/components/shared/upload-batch-dialog'
import { EmptyState } from '@/components/shared/empty-state'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import { ProgressBar } from '@/components/ui/progress-bar'
import { cn } from '@/lib/utils'
import type { Batch, BatchStatus } from '@/lib/types'

const STATUS_FILTERS: { label: string; value: BatchStatus | 'all' }[] = [
  { label: 'All', value: 'all' },
  { label: 'Extracting', value: 'extracting' },
  { label: 'Cropping', value: 'cropping' },
  { label: 'Rotation Review', value: 'rotation_review' },
  { label: 'Duplicate Review', value: 'duplicate_review' },
  { label: 'Complete', value: 'complete' },
]

function BatchCard({ batch }: { batch: Batch }) {
  const date = new Date(batch.created_at).toLocaleDateString('en-US', {
    month: 'short', day: 'numeric', year: 'numeric',
  })

  const progressValue =
    batch.status === 'complete' ? 100 :
    batch.status === 'duplicate_review' ? 80 :
    batch.status === 'rotation_review' ? 60 :
    batch.status === 'cropping' ? 40 :
    batch.status === 'extracting' ? 20 : 0

  return (
    <Link to={`/batches/${batch.id}`}>
      <Card className="group cursor-pointer transition-all duration-200 hover:shadow-float hover:-translate-y-0.5">
        <CardContent className="space-y-4 p-5">
          <div className="flex items-start justify-between gap-2">
            <div className="min-w-0">
              <p className="truncate text-card-title text-primary">
                {batch.source_label ?? `Batch #${batch.id}`}
              </p>
              <p className="mt-0.5 text-caption text-muted-foreground">{date}</p>
            </div>
            <div className="flex items-center gap-2 shrink-0">
              <BatchStatusBadge status={batch.status} />
              <ArrowRight className="h-4 w-4 text-muted-foreground opacity-0 transition-opacity group-hover:opacity-100" />
            </div>
          </div>
          <div>
            <div className="mb-1.5 flex justify-between">
              <span className="text-caption text-muted-foreground">Pipeline progress</span>
              <span className="text-caption font-medium text-primary">{progressValue}%</span>
            </div>
            <ProgressBar value={progressValue} />
          </div>
          <div className="flex items-center gap-1 text-caption text-muted-foreground">
            <span>ID: {batch.id}</span>
          </div>
        </CardContent>
      </Card>
    </Link>
  )
}

export function BatchesPage() {
  const [search, setSearch] = useState('')
  const [statusFilter, setStatusFilter] = useState<BatchStatus | 'all'>('all')

  const { data: batches, isLoading } = useQuery({
    queryKey: ['batches'],
    queryFn: () => listBatches(100),
  })

  const filtered = (batches ?? []).filter((b) => {
    const matchesSearch =
      !search ||
      b.source_label?.toLowerCase().includes(search.toLowerCase()) ||
      String(b.id).includes(search)
    const matchesStatus = statusFilter === 'all' || b.status === statusFilter
    return matchesSearch && matchesStatus
  })

  return (
    <div className="space-y-6 py-2">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-page-title text-primary">Batches</h1>
          <p className="mt-1 text-body text-muted-foreground">
            Manage your card scan batches and track pipeline progress.
          </p>
        </div>
        <UploadBatchDialog
          trigger={
            <Button size="md">
              <Upload className="h-4 w-4" />
              Upload Batch
            </Button>
          }
        />
      </div>

      {/* Toolbar */}
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
        <div className="relative flex-1 max-w-sm">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
          <input
            type="text"
            placeholder="Search batches…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="w-full rounded-xl border border-border bg-surface py-2.5 pl-9 pr-4 text-body text-primary placeholder:text-muted-foreground outline-none transition-all focus:border-primary focus:ring-2 focus:ring-primary/10"
          />
        </div>
        <div className="flex items-center gap-1 flex-wrap">
          {STATUS_FILTERS.map((f) => (
            <button
              key={f.value}
              onClick={() => setStatusFilter(f.value)}
              className={cn(
                'rounded-full px-3 py-1.5 text-caption font-medium transition-all duration-150',
                statusFilter === f.value
                  ? 'bg-primary text-primary-foreground'
                  : 'text-muted-foreground hover:bg-muted hover:text-primary'
              )}
            >
              {f.label}
            </button>
          ))}
        </div>
      </div>

      {/* Grid */}
      {isLoading ? (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {Array.from({ length: 6 }).map((_, i) => (
            <Skeleton key={i} className="h-44 w-full rounded-2xl" />
          ))}
        </div>
      ) : !filtered.length ? (
        <EmptyState
          icon={<Layers className="h-6 w-6" />}
          title={search || statusFilter !== 'all' ? 'No matching batches' : 'No batches yet'}
          description={
            search || statusFilter !== 'all'
              ? 'Try adjusting your search or filter.'
              : 'Upload your first batch to start processing.'
          }
          action={
            !search && statusFilter === 'all' ? (
              <UploadBatchDialog
                trigger={<Button variant="secondary" size="sm">Upload batch</Button>}
              />
            ) : undefined
          }
        />
      ) : (
        <motion.div
          className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3"
          initial="hidden"
          animate="show"
          variants={{ hidden: {}, show: { transition: { staggerChildren: 0.04 } } }}
        >
          {filtered.map((b) => (
            <motion.div
              key={b.id}
              variants={{ hidden: { opacity: 0, y: 6 }, show: { opacity: 1, y: 0, transition: { duration: 0.2 } } }}
            >
              <BatchCard batch={b} />
            </motion.div>
          ))}
        </motion.div>
      )}
    </div>
  )
}
