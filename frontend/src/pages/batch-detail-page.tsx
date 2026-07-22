import { useState } from 'react'
import { useParams, Link } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  ArrowLeft, ImageOff, Maximize2, ExternalLink, Download, AlertTriangle,
  Loader2, Images, Copy, CheckCircle2, ArrowRight,
} from 'lucide-react'
import { motion, AnimatePresence } from 'framer-motion'
import {
  getBatch, getBatchScans, getBatchDuplicates, forceAdvanceBatch,
  exportBatchZip, apiErrorMessage,
} from '@/lib/api'
import { BatchStatusBadge, ScanStatusBadge } from '@/components/shared/status-badge'
import { EmptyState } from '@/components/shared/empty-state'
import { SectionLabel } from '@/components/shared/section-label'
import { Skeleton } from '@/components/ui/skeleton'
import { ProgressBar } from '@/components/ui/progress-bar'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent } from '@/components/ui/dialog'
import { cn } from '@/lib/utils'
import { RotatedImage, FullscreenLightbox } from '@/components/shared/image-lightbox'
import type { BatchDuplicatePair, RawScan } from '@/lib/types'

// --- All-Scans tab ---

function ScanThumbnail({ scan, onClick }: { scan: RawScan; onClick: () => void }) {
  return (
    <motion.div
      initial={{ opacity: 0, scale: 0.97 }}
      animate={{ opacity: 1, scale: 1 }}
      transition={{ duration: 0.16 }}
      className={`group relative cursor-pointer overflow-hidden rounded-xl border bg-muted transition-all duration-150 hover:-translate-y-px hover:shadow-soft ${scan.is_duplicate ? 'border-accent-rose-solid/40 opacity-50' : 'border-border'
        }`}
      onClick={onClick}
      role="button"
      tabIndex={0}
      onKeyDown={(e) => e.key === 'Enter' && onClick()}
    >
      {scan.thumbnail_url ? (
        <RotatedImage
          src={scan.thumbnail_url}
          alt={scan.original_filename}
          rotationDegrees={scan.rotation_degrees}
          className="aspect-[2.5/3.5] w-full"
        />
      ) : (
        <div className="flex aspect-[2.5/3.5] w-full items-center justify-center bg-muted">
          <ImageOff className="h-8 w-8 text-muted-foreground/40" />
        </div>
      )}

      {/* Hover overlay */}
      <div className="absolute inset-0 flex items-center justify-center bg-primary/60 opacity-0 transition-opacity duration-150 group-hover:opacity-100">
        <Maximize2 className="h-6 w-6 text-white" />
      </div>

      {/* Filename tooltip bar */}
      <div className="absolute bottom-0 left-0 right-0 bg-gradient-to-t from-primary/80 to-transparent p-3 opacity-0 transition-opacity duration-150 group-hover:opacity-100">
        <p className="truncate text-caption font-medium text-white">{scan.original_filename}</p>
      </div>

      {/* Side chip — top-right */}
      <div className="absolute right-3 top-3 pointer-events-none select-none">
        <span className="inline-flex items-center rounded-md bg-slate-950/80 px-2 py-0.5 text-[10px] font-mono font-semibold uppercase tracking-wider leading-none text-slate-200 backdrop-blur-md border border-slate-700/60 shadow-md">
          {scan.side}
        </span>
      </div>

      {/* Duplicate chip — top-left */}
      {scan.is_duplicate && (
        <div className="absolute left-3 top-3 pointer-events-none select-none">
          <span className="inline-flex items-center rounded-md bg-slate-950/80 px-2 py-0.5 text-[10px] font-mono font-semibold uppercase tracking-wider leading-none text-accent-rose-solid backdrop-blur-md border border-slate-700/60 shadow-md">
            Dup
          </span>
        </div>
      )}
    </motion.div>
  )
}


function InspectorDrawer({ scan, onClose }: { scan: RawScan; onClose: () => void }) {
  const [isLightboxOpen, setIsLightboxOpen] = useState(false)

  return (
    <Dialog open onOpenChange={(open) => {
      if (!open && !isLightboxOpen) onClose()
    }}>
      <DialogContent
        title={scan.original_filename}
        description={`Scan #${scan.id} \u2014 ${scan.side} face`}
        className="max-w-2xl"
      >
        <div className="flex gap-5">
          {/* ── Left: image panel ── */}
          <div className="flex shrink-0 flex-col gap-2">
            {scan.thumbnail_url ? (
              <button
                type="button"
                onClick={() => setIsLightboxOpen(true)}
                className="group relative h-64 w-44 overflow-hidden rounded-xl border border-border bg-muted focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-border"
                aria-label="Open full image"
              >
                <RotatedImage
                  src={scan.thumbnail_url}
                  alt={scan.original_filename}
                  rotationDegrees={scan.rotation_degrees}
                  className="h-full w-full"
                />
                {/* Zoom overlay */}
                <div className="absolute inset-0 flex flex-col items-center justify-center gap-1.5 bg-primary/0 opacity-0 transition-all duration-200 group-hover:bg-primary/40 group-hover:opacity-100">
                  <div className="flex h-9 w-9 items-center justify-center rounded-full bg-surface/90 shadow-float backdrop-blur-sm">
                    <Maximize2 className="h-4 w-4 text-primary" />
                  </div>
                  <span className="text-[10px] font-semibold text-white drop-shadow">Expand</span>
                </div>
              </button>
            ) : (
              <div className="flex h-64 w-44 items-center justify-center rounded-xl border border-border bg-muted">
                <ImageOff className="h-10 w-10 text-muted-foreground/40" />
              </div>
            )}
            {scan.thumbnail_url && (
              <a
                href={scan.thumbnail_url}
                target="_blank"
                rel="noopener noreferrer"
                className="flex items-center justify-center gap-1.5 rounded-lg border border-border bg-muted/60 px-2.5 py-1.5 text-caption font-medium text-muted-foreground transition-colors hover:bg-muted hover:text-primary"
              >
                <ExternalLink className="h-3 w-3" />
                Open full image
              </a>
            )}
          </div>

          {/* ── Right: metadata column ── */}
          <div className="flex min-w-0 flex-1 flex-col divide-y divide-border rounded-xl border border-border bg-muted/30 overflow-hidden">
            {/* Status */}
            <div className="flex items-center justify-between px-3.5 py-2.5">
              <span className="text-caption font-semibold uppercase tracking-wider text-muted-foreground">Status</span>
              <ScanStatusBadge status={scan.status} />
            </div>

            {/* Side */}
            <div className="flex items-center justify-between px-3.5 py-2.5">
              <span className="text-caption font-semibold uppercase tracking-wider text-muted-foreground">Side</span>
              <span className="text-body font-medium text-primary capitalize">{scan.side}</span>
            </div>

            {/* Duplicate flag — only if flagged */}
            {scan.is_duplicate && (
              <div className="flex items-center justify-between px-3.5 py-2.5">
                <span className="text-caption font-semibold uppercase tracking-wider text-muted-foreground">Duplicate</span>
                <Badge variant="rose">Confirmed</Badge>
              </div>
            )}

            {/* Rotation — only if non-zero */}
            {scan.rotation_degrees !== 0 && (
              <div className="flex items-center justify-between px-3.5 py-2.5">
                <span className="text-caption font-semibold uppercase tracking-wider text-muted-foreground">Rotation</span>
                <span className="text-body font-medium text-primary">{scan.rotation_degrees}°</span>
              </div>
            )}

            {/* Scan ID */}
            <div className="flex items-center justify-between px-3.5 py-2.5">
              <span className="text-caption font-semibold uppercase tracking-wider text-muted-foreground">Scan ID</span>
              <span className="rounded-md bg-muted px-2 py-0.5 font-mono text-caption text-primary">#{scan.id}</span>
            </div>

            {/* Filename — full-width row */}
            <div className="flex flex-col gap-1 px-3.5 py-2.5">
              <span className="text-caption font-semibold uppercase tracking-wider text-muted-foreground">Filename</span>
              <p className="break-all text-body text-primary leading-snug">{scan.original_filename}</p>
            </div>
          </div>
        </div>
      </DialogContent>
      
      {scan.thumbnail_url && (
        <FullscreenLightbox
          isOpen={isLightboxOpen}
          onClose={() => setIsLightboxOpen(false)}
          src={scan.thumbnail_url}
          alt={scan.original_filename}
          rotationDegrees={scan.rotation_degrees}
        />
      )}
    </Dialog>
  )
}

// --- Duplicates tab ---

function ScoreBar({ label, value }: { label: string; value: number | null }) {
  const pct = value != null ? Math.round(value * 100) : null
  const color =
    pct == null ? 'bg-muted-foreground/40'
      : pct >= 90 ? 'bg-accent-rose-solid'
        : pct >= 70 ? 'bg-accent-peach-solid'
          : 'bg-accent-mint-solid'
  return (
    <div className="space-y-1">
      <div className="flex justify-between">
        <span className="text-caption text-muted-foreground">{label}</span>
        <span className="text-caption font-semibold text-primary">
          {pct != null ? `${pct}%` : 'N/A'}
        </span>
      </div>
      <div className="h-1.5 w-full overflow-hidden rounded-full bg-muted">
        <div
          className={`h-full rounded-full transition-all duration-500 ${color}`}
          style={{ width: pct != null ? `${pct}%` : '0%' }}
        />
      </div>
    </div>
  )
}

function DuplicatePairCard({ pair }: { pair: BatchDuplicatePair }) {
  const avgScore =
    pair.structural_score != null && pair.color_score != null
      ? (pair.structural_score + pair.color_score) / 2
      : pair.structural_score ?? pair.color_score ?? null

  const confidenceVariant: 'neutral' | 'rose' | 'peach' | 'mint' =
    avgScore == null ? 'neutral'
      : avgScore >= 0.9 ? 'rose'
        : avgScore >= 0.7 ? 'peach'
          : 'mint'

  const confidenceLabel =
    avgScore == null ? 'Unknown'
      : avgScore >= 0.9 ? 'High confidence'
        : avgScore >= 0.7 ? 'Medium'
          : 'Low confidence'

  return (
    <motion.div
      initial={{ opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.18 }}
      className="overflow-hidden rounded-xl border border-border bg-surface shadow-soft"
    >
      {/* Header */}
      <div className="flex items-center justify-between gap-3 border-b border-border bg-muted/40 px-4 py-2.5">
        <div className="flex items-center gap-2 min-w-0">
          <Copy className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
          <span className="text-caption font-semibold text-primary truncate">
            Candidate #{pair.candidate_id}
          </span>
          {pair.filename_match && (
            <Badge variant="blue" className="text-[10px] shrink-0">Filename match</Badge>
          )}
        </div>
        <Badge variant={confidenceVariant} className="text-[10px] shrink-0">
          {confidenceLabel}
        </Badge>
      </div>

      {/* Card pair */}
      <div className="flex">
        {/* Kept */}
        <div className="flex-1 p-4 space-y-3">
          <div className="flex items-center gap-2">
            <CheckCircle2 className="h-3.5 w-3.5 text-accent-mint-foreground" />
            <SectionLabel>Kept</SectionLabel>
            <Badge variant="mint" className="text-[10px]">{pair.kept.side}</Badge>
          </div>
          {pair.kept.image_url ? (
            <RotatedImage
              src={pair.kept.image_url}
              alt={pair.kept.original_filename}
              rotationDegrees={pair.kept.rotation_degrees}
              className="aspect-[2.5/3.5] w-full rounded-lg border border-border"
            />
          ) : (
            <div className="flex aspect-[2.5/3.5] w-full items-center justify-center rounded-lg border border-border bg-muted">
              <ImageOff className="h-8 w-8 text-muted-foreground/30" />
            </div>
          )}
          <p className="truncate text-caption text-muted-foreground" title={pair.kept.original_filename}>
            {pair.kept.original_filename}
          </p>
          {pair.kept.rotation_degrees !== 0 && (
            <p className="text-caption text-muted-foreground">↻ {pair.kept.rotation_degrees}°</p>
          )}
        </div>

        {/* Arrow divider */}
        <div className="flex items-center justify-center shrink-0 w-8">
          <ArrowRight className="h-4 w-4 text-muted-foreground/40" />
        </div>

        {/* Removed */}
        <div className="flex-1 p-4 space-y-3 border-l border-border bg-accent-rose/10">
          <div className="flex items-center gap-2">
            <AlertTriangle className="h-3.5 w-3.5 text-accent-rose-foreground" />
            <SectionLabel>Removed</SectionLabel>
            <Badge variant="rose" className="text-[10px]">{pair.removed.side}</Badge>
          </div>
          {pair.removed.image_url ? (
            <RotatedImage
              src={pair.removed.image_url}
              alt={pair.removed.original_filename}
              rotationDegrees={pair.removed.rotation_degrees}
              className="aspect-[2.5/3.5] w-full rounded-lg border border-accent-rose-solid/30 opacity-70"
            />
          ) : (
            <div className="flex aspect-[2.5/3.5] w-full items-center justify-center rounded-lg border border-border bg-muted">
              <ImageOff className="h-8 w-8 text-muted-foreground/30" />
            </div>
          )}
          <p className="truncate text-caption text-muted-foreground" title={pair.removed.original_filename}>
            {pair.removed.original_filename}
          </p>
          {pair.removed.rotation_degrees !== 0 && (
            <p className="text-caption text-muted-foreground">↻ {pair.removed.rotation_degrees}°</p>
          )}
        </div>
      </div>

      {/* Score footer */}
      <div className="border-t border-border bg-muted/40 px-4 py-3 grid grid-cols-2 gap-4">
        <ScoreBar label="Structural similarity" value={pair.structural_score} />
        <ScoreBar label="Color similarity" value={pair.color_score} />
      </div>
    </motion.div>
  )
}

// Natural sort: parse pairing stem into text/number chunks, front before back
function naturalSortKey(filename: string, side: string): Array<string | number> {
  // Strip -front / -back suffix to get the pairing stem
  const stem = filename.replace(/-(?:front|back)\.[^.]+$/i, '').toLowerCase()
  const parts: Array<string | number> = []
  for (const chunk of stem.split(/(\d+)/)) {
    parts.push(chunk === '' ? '' : /^\d+$/.test(chunk) ? parseInt(chunk, 10) : chunk)
  }
  parts.push(side.toLowerCase() === 'front' ? 0 : 1)
  return parts
}

function compareNatural(a: RawScan, b: RawScan): number {
  const ka = naturalSortKey(a.original_filename, a.side)
  const kb = naturalSortKey(b.original_filename, b.side)
  for (let i = 0; i < Math.max(ka.length, kb.length); i++) {
    const av = ka[i] ?? ''
    const bv = kb[i] ?? ''
    if (av < bv) return -1
    if (av > bv) return 1
  }
  return 0
}

// --- Main page ---

type TabId = 'scans' | 'duplicates'

export function BatchDetailPage() {
  const { id } = useParams<{ id: string }>()
  const batchId = Number(id)
  const [selectedScan, setSelectedScan] = useState<RawScan | null>(null)
  const [exportError, setExportError] = useState<string | null>(null)
  const [isExporting, setIsExporting] = useState(false)
  const [activeTab, setActiveTab] = useState<TabId>('scans')
  const [mountId] = useState(() => Math.random().toString(36).slice(2, 9))
  const queryClient = useQueryClient()

  const { data: batch, isLoading: batchLoading } = useQuery({
    queryKey: ['batch', batchId],
    queryFn: () => getBatch(batchId),
    enabled: !!batchId,
  })

  const { data: scans, isLoading: scansLoading } = useQuery({
    queryKey: ['batch-scans', batchId],
    queryFn: () => getBatchScans(batchId),
    enabled: !!batchId,
  })

  const { data: duplicates, isLoading: duplicatesLoading } = useQuery({
    queryKey: ['batch-duplicates', batchId],
    queryFn: () => getBatchDuplicates(batchId),
    enabled: !!batchId,
  })

  const forceAdvanceMutation = useMutation({
    mutationFn: () => forceAdvanceBatch(batchId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['batch', batchId] })
      queryClient.invalidateQueries({ queryKey: ['batch-scans', batchId] })
    },
  })

  const handleExport = async () => {
    setExportError(null)
    setIsExporting(true)
    try {
      const label = batch?.source_label ?? `batch_${batchId}`
      await exportBatchZip(batchId, `${label}.zip`)
    } catch (err) {
      setExportError(apiErrorMessage(err))
    } finally {
      setIsExporting(false)
    }
  }

  const progressValue =
    !batch ? 0 :
      batch.status === 'complete' ? 100 :
        batch.status === 'duplicate_review' ? 80 :
          batch.status === 'rotation_review' ? 60 :
            batch.status === 'cropping' ? 40 :
              batch.status === 'extracting' ? 20 : 0

  const showForceAdvance =
    batch?.status === 'cropping' &&
    (batch.counts.crop_failed > 0 || batch.counts.cropped > 0)

  const hasCroppedImages = (batch?.counts.cropped ?? 0) > 0
  const duplicateCount = duplicates?.length ?? 0

  // Sort scans: card number naturally (1, 2, 10 not 1, 10, 2), then front before back
  const sortedScans = scans ? [...scans].sort(compareNatural) : undefined

  const TABS: { id: TabId; label: string; count?: number }[] = [
    { id: 'scans', label: 'All Scans', count: scans?.length },
    { id: 'duplicates', label: 'Duplicates', count: duplicateCount },
  ]

  return (
    <div className="space-y-5">
      <Link
        to="/batches"
        className="inline-flex items-center gap-2 text-caption font-medium text-muted-foreground transition-colors hover:text-primary"
      >
        <ArrowLeft className="h-3.5 w-3.5" />
        All Batches
      </Link>

      {batchLoading ? (
        <div className="space-y-3">
          <Skeleton className="h-9 w-64 rounded-lg" />
          <Skeleton className="h-5 w-40 rounded-lg" />
          <Skeleton className="h-3 w-full rounded-full" />
        </div>
      ) : batch ? (
        <div className="rounded-xl border border-border bg-surface p-5 shadow-soft">
          <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
            <div className="space-y-2">
              <div className="flex items-center gap-3 flex-wrap">
                <h1 className="text-page-title text-primary">
                  {batch.source_label ?? `Batch #${batch.id}`}
                </h1>
                <BatchStatusBadge status={batch.status} />
              </div>
              <p className="text-caption text-muted-foreground">
                Created{' '}
                {new Date(batch.created_at).toLocaleDateString('en-US', {
                  month: 'long', day: 'numeric', year: 'numeric',
                })}
              </p>
            </div>
            <div className="flex flex-wrap items-center gap-2">
              {hasCroppedImages && (
                <Button
                  variant="secondary"
                  size="sm"
                  onClick={handleExport}
                  disabled={isExporting}
                  className="gap-2"
                >
                  {isExporting ? (
                    <Loader2 className="h-3.5 w-3.5 animate-spin" />
                  ) : (
                    <Download className="h-3.5 w-3.5" />
                  )}
                  {isExporting ? 'Preparing\u2026' : 'Download ZIP'}
                </Button>
              )}
              {showForceAdvance && (
                <Button
                  variant="secondary"
                  size="sm"
                  onClick={() => forceAdvanceMutation.mutate()}
                  disabled={forceAdvanceMutation.isPending}
                  className="gap-2 border-accent-peach-solid/40 bg-accent-peach text-accent-peach-foreground hover:bg-accent-peach/70"
                >
                  {forceAdvanceMutation.isPending ? (
                    <Loader2 className="h-3.5 w-3.5 animate-spin" />
                  ) : (
                    <AlertTriangle className="h-3.5 w-3.5" />
                  )}
                  Force Advance
                </Button>
              )}
            </div>
          </div>

          <AnimatePresence>
            {forceAdvanceMutation.isError && (
              <motion.p
                initial={{ opacity: 0, y: -4 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0 }}
                className="mt-2 text-caption text-accent-rose-foreground"
              >
                {apiErrorMessage(forceAdvanceMutation.error)}
              </motion.p>
            )}
            {exportError && (
              <motion.p
                initial={{ opacity: 0, y: -4 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0 }}
                className="mt-2 text-caption text-accent-rose-foreground"
              >
                {exportError}
              </motion.p>
            )}
          </AnimatePresence>

          <div className="mt-4 grid grid-cols-2 gap-2.5 sm:grid-cols-5">
            {[
              { label: 'Total Scans', value: batch.counts.scans },
              { label: 'Cropped', value: batch.counts.cropped },
              { label: 'Crop Failed', value: batch.counts.crop_failed, highlight: batch.counts.crop_failed > 0 },
              { label: 'Pending Rotation', value: batch.counts.pending_rotation },
              { label: 'Pending Dupe', value: batch.counts.pending_duplicate_review },
            ].map(({ label, value, highlight }) => (
              <div
                key={label}
                className={cn(
                  'rounded-lg px-3 py-2 text-center transition-colors',
                  highlight ? 'bg-accent-peach ring-1 ring-accent-peach-solid/30' : 'bg-muted'
                )}
              >
                <p className={cn('text-section font-bold', highlight ? 'text-accent-peach-foreground' : 'text-primary')}>{value}</p>
                <p className="text-caption text-muted-foreground">{label}</p>
              </div>
            ))}
          </div>

          <div className="mt-4">
            <div className="mb-1.5 flex justify-between text-caption text-muted-foreground">
              <span>Pipeline progress</span>
              <span className="font-medium text-primary">{progressValue}%</span>
            </div>
            <ProgressBar value={progressValue} className="h-2" />
          </div>
        </div>
      ) : null}

      {/* Tabs */}
      <div>
        <div className="flex items-center gap-1 border-b border-border mb-5">
          {TABS.map((tab) => (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              className={`relative flex items-center gap-2 px-4 py-2.5 text-body font-medium transition-colors ${activeTab === tab.id
                  ? 'text-primary'
                  : 'text-muted-foreground hover:text-primary'
                }`}
            >
              {tab.id === 'scans' ? (
                <Images className="h-3.5 w-3.5" />
              ) : (
                <Copy className="h-3.5 w-3.5" />
              )}
              {tab.label}
              {tab.count != null && tab.count > 0 && (
                <span
                  className={`rounded-full px-1.5 py-0.5 text-[10px] font-semibold leading-none ${tab.id === 'duplicates'
                      ? 'bg-accent-rose text-accent-rose-foreground'
                      : 'bg-muted text-muted-foreground'
                    }`}
                >
                  {tab.count}
                </span>
              )}
              {activeTab === tab.id && (
                <div className="absolute bottom-0 left-0 right-0 h-0.5 rounded-full bg-accent-lavender-solid" />
              )}
            </button>
          ))}
        </div>

        <AnimatePresence mode="wait">
          {activeTab === 'scans' && (
            <motion.div
              key="scans"
              initial={{ opacity: 0, y: 4 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -4 }}
              transition={{ duration: 0.15 }}
            >
              <div className="mb-3">
                <SectionLabel>
                  Scans {scans ? `(${scans.length})` : ''}
                  {duplicateCount > 0 && (
                    <span className="ml-2 normal-case font-normal text-muted-foreground/60">
                      — {(scans?.filter(s => !s.is_duplicate) ?? []).length} unique, {duplicateCount} duplicate
                    </span>
                  )}
                </SectionLabel>
              </div>
              {scansLoading ? (
                <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-6 xl:grid-cols-8">
                  {Array.from({ length: 16 }).map((_, i) => (
                    <Skeleton key={i} className="aspect-[2.5/3.5] rounded-xl" />
                  ))}
                </div>
              ) : !sortedScans?.length ? (
                <EmptyState
                  icon={<ImageOff className="h-6 w-6" />}
                  title="No scans yet"
                  description="Scans will appear here as the batch is extracted."
                />
              ) : (
                <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-6 xl:grid-cols-8">
                  {sortedScans.map((scan) => (
                    <ScanThumbnail
                      key={scan.id}
                      scan={scan}
                      onClick={() => setSelectedScan(scan)}
                    />
                  ))}
                </div>
              )}
            </motion.div>
          )}

          {activeTab === 'duplicates' && (
            <motion.div
              key="duplicates"
              initial={{ opacity: 0, y: 4 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -4 }}
              transition={{ duration: 0.15 }}
            >
              <div className="mb-4">
                <SectionLabel>
                  Confirmed Duplicates {duplicates ? `(${duplicates.length})` : ''}
                </SectionLabel>
                <p className="mt-0.5 text-caption text-muted-foreground">
                  These cards were confirmed as duplicates and are excluded from the ZIP export.
                  The left card is kept; the right is removed.
                </p>
              </div>
              {duplicatesLoading ? (
                <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
                  {Array.from({ length: 3 }).map((_, i) => (
                    <Skeleton key={i} className="h-96 rounded-xl" />
                  ))}
                </div>
              ) : !duplicates?.length ? (
                <EmptyState
                  icon={<CheckCircle2 className="h-6 w-6" />}
                  title="No confirmed duplicates"
                  description="Duplicate pairs confirmed during review will appear here."
                />
              ) : (
                <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
                  {duplicates.map((pair) => (
                    <DuplicatePairCard key={pair.candidate_id} pair={pair} />
                  ))}
                </div>
              )}
            </motion.div>
          )}
        </AnimatePresence>
      </div>

      {selectedScan && (
        <InspectorDrawer
          scan={selectedScan}
          onClose={() => setSelectedScan(null)}
        />
      )}
    </div>
  )
}
