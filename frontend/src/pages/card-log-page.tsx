import { useEffect, useState, useRef } from 'react'
import { useQuery } from '@tanstack/react-query'
import { ImageOff, BookOpen, ExternalLink } from 'lucide-react'
import { motion } from 'framer-motion'
import { listCards, listBatches, getCard } from '@/lib/api'
import { ScanStatusBadge, DuplicateStatusBadge } from '@/components/shared/status-badge'
import { EmptyState } from '@/components/shared/empty-state'
import { PageHeader } from '@/components/shared/page-header'
import { SectionLabel } from '@/components/shared/section-label'
import { Toolbar } from '@/components/shared/toolbar'
import { Badge } from '@/components/ui/badge'
import { SearchBar } from '@/components/ui/search-bar'
import { Skeleton } from '@/components/ui/skeleton'
import { Dialog, DialogContent } from '@/components/ui/dialog'
import { cn } from '@/lib/utils'
import type { CardCrop } from '@/lib/types'

const PAGE_SIZE = 48

const selectClass = cn(
  'h-9 rounded-lg border border-border bg-surface px-3 text-body text-primary outline-none',
  'transition-colors duration-150 focus:border-primary/30 focus:ring-2 focus:ring-primary/10'
)

function CardThumb({ card, onClick }: { card: CardCrop; onClick: () => void }) {
  return (
    <motion.div
      initial={{ opacity: 0, scale: 0.97 }}
      animate={{ opacity: 1, scale: 1 }}
      transition={{ duration: 0.15 }}
      className="group relative cursor-pointer overflow-hidden rounded-xl border border-border bg-muted transition-all duration-150 hover:-translate-y-px hover:shadow-soft"
      onClick={onClick}
      role="button"
      tabIndex={0}
      onKeyDown={(e) => e.key === 'Enter' && onClick()}
    >
      {card.image_url ? (
        <img
          src={card.image_url}
          alt={card.original_filename}
          className="aspect-[2.5/3.5] w-full object-cover"
          loading="lazy"
        />
      ) : (
        <div className="flex aspect-[2.5/3.5] w-full items-center justify-center bg-muted">
          <ImageOff className="h-6 w-6 text-muted-foreground/40" />
        </div>
      )}
      <div className="absolute inset-0 bg-primary/60 opacity-0 transition-opacity duration-150 group-hover:opacity-100" />
      <div className="absolute bottom-0 left-0 right-0 translate-y-2 bg-gradient-to-t from-primary/90 to-transparent p-3 opacity-0 transition-all duration-150 group-hover:translate-y-0 group-hover:opacity-100">
        <p className="truncate text-[10px] font-medium text-white">{card.original_filename}</p>
      </div>
      <div className="absolute right-1.5 top-1.5">
        <Badge variant={card.side === 'front' ? 'blue' : 'neutral'} className="text-[10px]">
          {card.side}
        </Badge>
      </div>
    </motion.div>
  )
}

function CardDetailDrawer({ cropId, onClose }: { cropId: number; onClose: () => void }) {
  const { data: detail, isLoading } = useQuery({
    queryKey: ['card-detail', cropId],
    queryFn: () => getCard(cropId),
  })

  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent
        title={detail?.original_filename ?? 'Card Detail'}
        description={detail ? `Crop #${detail.id} — ${detail.side} face` : 'Loading…'}
        className="max-w-2xl"
      >
        {isLoading ? (
          <div className="flex gap-6">
            <Skeleton className="h-64 w-44 rounded-lg" />
            <div className="flex-1 space-y-3">
              <Skeleton className="h-5 w-24 rounded-lg" />
              <Skeleton className="h-5 w-32 rounded-lg" />
              <Skeleton className="h-5 w-40 rounded-lg" />
            </div>
          </div>
        ) : detail ? (
          <div className="flex gap-6">
            {detail.image_url ? (
              <img
                src={detail.image_url}
                alt={detail.original_filename}
                className="h-64 w-auto rounded-lg border border-border bg-muted object-contain"
              />
            ) : (
              <div className="flex h-64 w-44 items-center justify-center rounded-lg border border-border bg-muted">
                <ImageOff className="h-10 w-10 text-muted-foreground/40" />
              </div>
            )}
            <div className="flex flex-1 flex-col gap-3 overflow-auto">
              <div>
                <SectionLabel>Status</SectionLabel>
                <div className="mt-1 flex flex-wrap gap-2">
                  <ScanStatusBadge status={detail.status} />
                </div>
              </div>
              <div>
                <SectionLabel>Side</SectionLabel>
                <Badge className="mt-1" variant={detail.side === 'front' ? 'blue' : 'neutral'}>{detail.side}</Badge>
              </div>
              <div>
                <SectionLabel>Batch</SectionLabel>
                <p className="mt-1 text-body text-primary">#{detail.batch_id}</p>
              </div>
              <div>
                <SectionLabel>Rotation confirmed</SectionLabel>
                <p className="mt-1 text-body text-primary">
                  {detail.rotation_confirmed_at
                    ? new Date(detail.rotation_confirmed_at).toLocaleString()
                    : 'Not yet'}
                </p>
              </div>
              {detail.aspect_ratio_ok != null && (
                <div>
                  <SectionLabel>Aspect ratio</SectionLabel>
                  <Badge className="mt-1" variant={detail.aspect_ratio_ok ? 'mint' : 'rose'}>
                    {detail.aspect_ratio_ok ? 'OK' : 'Out of tolerance'}
                  </Badge>
                </div>
              )}
              {detail.duplicate_history?.length > 0 && (
                <div>
                  <SectionLabel>Duplicate flags</SectionLabel>
                  <div className="mt-1 space-y-1">
                    {detail.duplicate_history.map((d) => (
                      <DuplicateStatusBadge key={d.candidate_id} status={d.status as any} />
                    ))}
                  </div>
                </div>
              )}
              {detail.image_url && (
                <a
                  href={detail.image_url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="mt-auto inline-flex items-center gap-2 text-caption font-medium text-muted-foreground hover:text-primary transition-colors"
                >
                  <ExternalLink className="h-3.5 w-3.5" />
                  Open full image
                </a>
              )}
            </div>
          </div>
        ) : null}
      </DialogContent>
    </Dialog>
  )
}

export function CardLogPage() {
  const [search, setSearch] = useState('')
  const [batchFilter, setBatchFilter] = useState<number | undefined>(undefined)
  const [statusFilter, setStatusFilter] = useState<string | undefined>(undefined)
  const [offset, setOffset] = useState(0)
  const [allCards, setAllCards] = useState<CardCrop[]>([])
  const [selectedCropId, setSelectedCropId] = useState<number | null>(null)
  const loaderRef = useRef<HTMLDivElement>(null)

  const { data: batches } = useQuery({
    queryKey: ['batches'],
    queryFn: () => listBatches(100),
  })

  const { data: page, isLoading, isFetching } = useQuery({
    queryKey: ['cards', search, batchFilter, statusFilter, offset],
    queryFn: () => listCards({
      search: search || undefined,
      batch_id: batchFilter,
      status: statusFilter,
      limit: PAGE_SIZE,
      offset,
    }),
    placeholderData: (prev) => prev,
  })

  // Accumulate pages for infinite scroll
  useEffect(() => {
    if (offset === 0) {
      setAllCards(page ?? [])
    } else if (page?.length) {
      setAllCards((prev) => {
        const ids = new Set(prev.map((c) => c.id))
        return [...prev, ...page.filter((c) => !ids.has(c.id))]
      })
    }
  }, [page, offset])

  // Reset on filter change
  useEffect(() => {
    setOffset(0)
    setAllCards([])
  }, [search, batchFilter, statusFilter])

  // Intersection observer for infinite scroll
  useEffect(() => {
    if (!loaderRef.current) return
    const observer = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting && !isFetching && (page?.length ?? 0) === PAGE_SIZE) {
          setOffset((o) => o + PAGE_SIZE)
        }
      },
      { threshold: 0.5 }
    )
    observer.observe(loaderRef.current)
    return () => observer.disconnect()
  }, [isFetching, page])

  return (
    <div className="space-y-5">
      <PageHeader
        title="Card Log"
        description="Browse and search all processed cards across batches."
      />

      <Toolbar className="border-b border-border pb-4">
        <SearchBar
          placeholder="Search by filename…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="max-w-xs"
        />

        <select
          value={batchFilter ?? ''}
          onChange={(e) => setBatchFilter(e.target.value ? Number(e.target.value) : undefined)}
          className={selectClass}
        >
          <option value="">All Batches</option>
          {batches?.map((b) => (
            <option key={b.id} value={b.id}>
              {b.source_label ?? `Batch #${b.id}`}
            </option>
          ))}
        </select>

        <select
          value={statusFilter ?? ''}
          onChange={(e) => setStatusFilter(e.target.value || undefined)}
          className={selectClass}
        >
          <option value="">All Statuses</option>
          <option value="pending">Pending</option>
          <option value="cropped">Cropped</option>
          <option value="crop_failed">Crop Failed</option>
        </select>
      </Toolbar>

      {/* Card count */}
      {!isLoading && (
        <p className="text-caption text-muted-foreground">
          {allCards.length} card{allCards.length !== 1 ? 's' : ''} shown
          {(page?.length ?? 0) === PAGE_SIZE && ' — scroll for more'}
        </p>
      )}

      {/* Gallery grid */}
      {isLoading && offset === 0 ? (
        <div className="grid grid-cols-3 gap-3 sm:grid-cols-4 md:grid-cols-6 lg:grid-cols-8 xl:grid-cols-10">
          {Array.from({ length: 20 }).map((_, i) => (
            <Skeleton key={i} className="aspect-[2.5/3.5] rounded-xl" />
          ))}
        </div>
      ) : !allCards.length ? (
        <EmptyState
          icon={<BookOpen className="h-6 w-6" />}
          title="No cards found"
          description="Try adjusting your search or filters."
        />
      ) : (
        <div className="grid grid-cols-3 gap-3 sm:grid-cols-4 md:grid-cols-6 lg:grid-cols-8 xl:grid-cols-10">
          {allCards.map((card) => (
            <CardThumb
              key={card.id}
              card={card}
              onClick={() => setSelectedCropId(card.id)}
            />
          ))}
        </div>
      )}

      {/* Infinite scroll loader */}
      <div ref={loaderRef} className="flex justify-center py-4">
        {isFetching && offset > 0 && (
          <div className="h-6 w-6 animate-spin rounded-full border-2 border-border border-t-primary" />
        )}
      </div>

      {/* Detail drawer */}
      {selectedCropId && (
        <CardDetailDrawer
          cropId={selectedCropId}
          onClose={() => setSelectedCropId(null)}
        />
      )}
    </div>
  )
}
