import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { Upload, Layers, ArrowRight, LayoutGrid, Columns } from 'lucide-react'
import { motion } from 'framer-motion'
import { listBatches } from '@/lib/api'
import { BatchStatusBadge, BATCH_STATUS_META } from '@/components/shared/status-badge'
import { UploadBatchDialog } from '@/components/shared/upload-batch-dialog'
import { EmptyState } from '@/components/shared/empty-state'
import { PageHeader } from '@/components/shared/page-header'
import { Toolbar, ToolbarSpacer } from '@/components/shared/toolbar'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { IconButton } from '@/components/ui/icon-button'
import { SearchBar } from '@/components/ui/search-bar'
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

// Pipeline order for the kanban board — left to right, matches the
// 5-stage pipeline described on the Settings page.
const PIPELINE_COLUMNS: BatchStatus[] = [
  'extracting',
  'cropping',
  'rotation_review',
  'duplicate_review',
  'complete',
]

// Solid dot color per status, reusing the exact same variant mapping
// BatchStatusBadge uses so a column and its cards' badges always agree.
const STATUS_DOT_CLASS: Record<BatchStatus, string> = {
  extracting: 'bg-accent-peach-solid',
  cropping: 'bg-accent-blue-solid',
  rotation_review: 'bg-accent-lavender-solid',
  duplicate_review: 'bg-accent-lavender-solid',
  complete: 'bg-accent-mint-solid',
}

function progressForStatus(status: BatchStatus) {
  return status === 'complete' ? 100 :
    status === 'duplicate_review' ? 80 :
    status === 'rotation_review' ? 60 :
    status === 'cropping' ? 40 :
    status === 'extracting' ? 20 : 0
}

function BatchCard({ batch }: { batch: Batch }) {
  const date = new Date(batch.created_at).toLocaleDateString('en-US', {
    month: 'short', day: 'numeric', year: 'numeric',
  })
  const progressValue = progressForStatus(batch.status)

  return (
    <Link to={`/batches/${batch.id}`}>
      <Card className="group cursor-pointer transition-all duration-150 hover:-translate-y-px hover:border-primary/15 hover:shadow-soft">
        <CardContent className="space-y-3.5 p-4">
          <div className="flex items-start justify-between gap-2">
            <div className="min-w-0">
              <p className="truncate text-card-title text-primary">
                {batch.source_label ?? `Batch #${batch.id}`}
              </p>
              <p className="mt-0.5 text-caption text-muted-foreground">{date}</p>
            </div>
            <div className="flex items-center gap-2 shrink-0">
              <BatchStatusBadge status={batch.status} />
              <ArrowRight className="h-3.5 w-3.5 text-muted-foreground opacity-0 transition-opacity group-hover:opacity-100" />
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

function KanbanCard({ batch }: { batch: Batch }) {
  const date = new Date(batch.created_at).toLocaleDateString('en-US', {
    month: 'short', day: 'numeric',
  })

  return (
    <Link to={`/batches/${batch.id}`}>
      <motion.div
        layout
        initial={{ opacity: 0, y: 4 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.15 }}
        className="group cursor-pointer rounded-lg border border-border bg-surface p-3.5 shadow-soft transition-all duration-150 hover:-translate-y-0.5 hover:border-primary/20 hover:shadow-float"
      >
        {/* Title row */}
        <div className="flex items-start justify-between gap-2">
          <p className="truncate text-body font-semibold text-primary">
            {batch.source_label ?? `Batch #${batch.id}`}
          </p>
          <ArrowRight className="h-3.5 w-3.5 shrink-0 text-muted-foreground opacity-0 transition-opacity group-hover:opacity-100" />
        </div>

        {/* Divider */}
        <div className="my-2.5 border-t border-border" />

        {/* Metadata row */}
        <div className="flex items-center justify-between text-caption text-muted-foreground">
          <span className="font-medium">ID: {batch.id}</span>
          <span>{date}</span>
        </div>
      </motion.div>
    </Link>
  )
}

function KanbanColumn({ status, batches }: { status: BatchStatus; batches: Batch[] }) {
  const meta = BATCH_STATUS_META[status]

  return (
    <div className="flex w-[288px] shrink-0 flex-col rounded-xl border border-border bg-background">
      {/* Column header */}
      <div className="flex items-center justify-between gap-2 border-b border-border px-4 py-3">
        <div className="flex items-center gap-2 min-w-0">
          <span className={cn('h-2 w-2 shrink-0 rounded-full', STATUS_DOT_CLASS[status])} />
          <p className="truncate text-card-title font-semibold text-primary">{meta.label}</p>
        </div>
        <span className="shrink-0 rounded-full bg-muted px-2 py-0.5 text-caption font-semibold text-muted-foreground">
          {batches.length}
        </span>
      </div>

      {/* Card list */}
      <div className="max-h-[calc(100vh-260px)] flex-1 overflow-y-auto p-3">
        {batches.length === 0 ? (
          <p className="px-2 py-6 text-center text-caption text-muted-foreground/60">No batches</p>
        ) : (
          <div className="flex flex-col gap-2.5">
            {batches.map((b) => <KanbanCard key={b.id} batch={b} />)}
          </div>
        )}
      </div>
    </div>
  )
}

function BatchKanbanBoard({ batches }: { batches: Batch[] }) {
  return (
    <div className="flex gap-4 overflow-x-auto pb-4">
      {PIPELINE_COLUMNS.map((status) => (
        <KanbanColumn
          key={status}
          status={status}
          batches={batches.filter((b) => b.status === status)}
        />
      ))}
    </div>
  )
}

export function BatchesPage() {
  const [search, setSearch] = useState('')
  const [statusFilter, setStatusFilter] = useState<BatchStatus | 'all'>('all')
  const [view, setView] = useState<'grid' | 'kanban'>(() => {
    const stored = localStorage.getItem('batches-view')
    return stored === 'kanban' ? 'kanban' : 'grid'
  })

  function handleSetView(v: 'grid' | 'kanban') {
    localStorage.setItem('batches-view', v)
    setView(v)
  }

  const { data: batches, isLoading } = useQuery({
    queryKey: ['batches'],
    queryFn: () => listBatches(100),
  })

  const matchesSearch = (b: Batch) =>
    !search ||
    b.source_label?.toLowerCase().includes(search.toLowerCase()) ||
    String(b.id).includes(search)

  // Grid view: search + status filter combined.
  const filtered = (batches ?? []).filter(
    (b) => matchesSearch(b) && (statusFilter === 'all' || b.status === statusFilter)
  )

  // Kanban view: only search applies — the columns themselves are the
  // status breakdown, so the status filter pills don't apply here.
  const searchFiltered = (batches ?? []).filter(matchesSearch)

  return (
    <div className="space-y-5">
      <PageHeader
        title="Batches"
        description="Manage your card scan batches and track pipeline progress."
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

      <Toolbar className="border-b border-border pb-4">
        <SearchBar
          placeholder="Search batches…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="max-w-xs"
        />
        {view === 'grid' && (
          <>
            <div className="h-5 w-px bg-border" />
            <div className="flex flex-wrap items-center gap-1">
              {STATUS_FILTERS.map((f) => (
                <button
                  key={f.value}
                  onClick={() => setStatusFilter(f.value)}
                  className={cn(
                    'rounded-full px-2.5 py-1 text-caption font-medium transition-colors duration-150',
                    statusFilter === f.value
                      ? 'bg-interactive text-interactive-text'
                      : 'text-muted-foreground hover:bg-muted hover:text-primary'
                  )}
                >
                  {f.label}
                </button>
              ))}
            </div>
          </>
        )}

        <ToolbarSpacer />

        <div className="flex items-center gap-1 rounded-lg border border-border bg-surface p-0.5">
          <IconButton
            label="Grid view"
            variant={view === 'grid' ? 'subtle' : 'ghost'}
            active={view === 'grid'}
            className="h-8 w-8"
            onClick={() => handleSetView('grid')}
          >
            <LayoutGrid className="h-4 w-4" />
          </IconButton>
          <IconButton
            label="Kanban view"
            variant={view === 'kanban' ? 'subtle' : 'ghost'}
            active={view === 'kanban'}
            className="h-8 w-8"
            onClick={() => handleSetView('kanban')}
          >
            <Columns className="h-4 w-4" />
          </IconButton>
        </div>
      </Toolbar>

      {isLoading ? (
        view === 'grid' ? (
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {Array.from({ length: 6 }).map((_, i) => (
              <Skeleton key={i} className="h-40 w-full rounded-xl" />
            ))}
          </div>
        ) : (
          <div className="flex gap-3 overflow-x-auto pb-2">
            {PIPELINE_COLUMNS.map((s) => (
              <Skeleton key={s} className="h-[420px] w-[280px] shrink-0 rounded-xl" />
            ))}
          </div>
        )
      ) : view === 'grid' && !filtered.length ? (
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
      ) : view === 'kanban' && !searchFiltered.length ? (
        <EmptyState
          icon={<Layers className="h-6 w-6" />}
          title={search ? 'No matching batches' : 'No batches yet'}
          description={
            search
              ? 'Try adjusting your search.'
              : 'Upload your first batch to start processing.'
          }
          action={
            !search ? (
              <UploadBatchDialog
                trigger={<Button variant="secondary" size="sm">Upload batch</Button>}
              />
            ) : undefined
          }
        />
      ) : view === 'grid' ? (
        <motion.div
          className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3"
          initial="hidden"
          animate="show"
          variants={{ hidden: {}, show: { transition: { staggerChildren: 0.04 } } }}
        >
          {filtered.map((b) => (
            <motion.div
              key={b.id}
              variants={{ hidden: { opacity: 0, y: 6 }, show: { opacity: 1, y: 0, transition: { duration: 0.18 } } }}
            >
              <BatchCard batch={b} />
            </motion.div>
          ))}
        </motion.div>
      ) : (
        <BatchKanbanBoard batches={searchFiltered} />
      )}
    </div>
  )
}
