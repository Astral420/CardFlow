import { useState, useCallback, useEffect } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { CheckCircle2, X, SkipForward, ImageOff, AlertTriangle, Maximize2 } from 'lucide-react'
import { motion, AnimatePresence } from 'framer-motion'
import { Link } from 'react-router-dom'
import {
  getNextDuplicate,
  getDuplicateQueueCount,
  decideDuplicate,
} from '@/lib/api'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Card } from '@/components/ui/card'
import { ShortcutHint } from '@/components/ui/kbd'
import { Skeleton } from '@/components/ui/skeleton'
import { useToast } from '@/components/ui/toast'
import { PageHeader } from '@/components/shared/page-header'
import { SectionLabel } from '@/components/shared/section-label'
import { RotatedImage, FullscreenLightbox } from '@/components/shared/image-lightbox'
import { useAuth } from '@/lib/auth'
import type { CardPair, CropQueueItem } from '@/lib/types'

function SimilarityBar({ label, value }: { label: string; value: number | null }) {
  const pct = value != null ? Math.round(value * 100) : null
  const color =
    pct == null ? 'bg-muted-foreground' :
    pct >= 90 ? 'bg-accent-rose-solid' :
    pct >= 70 ? 'bg-accent-peach-solid' :
    'bg-accent-mint-solid'

  return (
    <div className="space-y-1.5">
      <div className="flex justify-between">
        <span className="text-caption text-muted-foreground">{label}</span>
        <span className="text-caption font-semibold text-primary">
          {pct != null ? `${pct}%` : 'N/A'}
        </span>
      </div>
      <div className="h-2 w-full overflow-hidden rounded-full bg-muted">
        <div
          className={`h-full rounded-full transition-all duration-500 ${color}`}
          style={{ width: pct != null ? `${pct}%` : '0%' }}
        />
      </div>
    </div>
  )
}

function SidePreview({
  crop,
  side,
  matchedCropId,
}: {
  crop: CropQueueItem | null | undefined
  side: 'front' | 'back'
  matchedCropId: number | null
}) {
  const [isLightboxOpen, setIsLightboxOpen] = useState(false)
  const isMatched = crop?.crop_id === matchedCropId

  return (
    <div
      className={`overflow-hidden rounded-xl border bg-muted shadow-soft ${
        isMatched ? 'border-primary ring-2 ring-primary/10' : 'border-border'
      }`}
    >
      <div className="flex items-center justify-between gap-2 border-b border-border bg-surface px-3 py-2">
        <Badge variant={side === 'front' ? 'blue' : 'neutral'} className="capitalize">
          {side}
        </Badge>
        {isMatched && (
          <span className="text-[10px] font-semibold uppercase tracking-wider text-primary">
            matched
          </span>
        )}
      </div>
      <div className="flex h-56 items-center justify-center bg-muted p-2">
        {crop?.image_url ? (
          <button
            type="button"
            onClick={() => setIsLightboxOpen(true)}
            className="group relative h-full w-full overflow-hidden rounded-lg focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-border"
            aria-label="Open full image"
          >
            <RotatedImage
              src={crop.image_url}
              alt={crop.original_filename}
              rotationDegrees={crop.rotation_degrees}
              className="h-full w-full"
            />
            {/* Zoom hover overlay */}
            <div className="absolute inset-0 flex flex-col items-center justify-center gap-1.5 bg-primary/0 opacity-0 transition-all duration-200 group-hover:bg-primary/40 group-hover:opacity-100">
              <div className="flex h-9 w-9 items-center justify-center rounded-full bg-surface/90 shadow-float backdrop-blur-sm">
                <Maximize2 className="h-4 w-4 text-primary" />
              </div>
              <span className="text-[10px] font-semibold text-white drop-shadow">Expand</span>
            </div>
          </button>
        ) : (
          <div className="flex h-full w-full items-center justify-center">
            <ImageOff className="h-10 w-10 text-muted-foreground/30" />
          </div>
        )}
      </div>
      <div className="border-t border-border bg-surface px-3 py-2">
        <p className="truncate text-caption font-medium text-primary">
          {crop?.original_filename ?? `${side} not found`}
        </p>
      </div>

      {crop?.image_url && (
        <FullscreenLightbox
          isOpen={isLightboxOpen}
          onClose={() => setIsLightboxOpen(false)}
          src={crop.image_url}
          alt={crop.original_filename}
          rotationDegrees={crop.rotation_degrees}
        />
      )}
    </div>
  )
}

function fallbackPair(crop: CropQueueItem): CardPair {
  return {
    pairing_key: crop.original_filename,
    front: crop.side === 'front' ? crop : null,
    back: crop.side === 'back' ? crop : null,
  }
}

function CardPairPreview({
  label,
  pair,
  fallbackCrop,
  matchedCropId,
}: {
  label: 'Card A' | 'Card B'
  pair: CardPair | null | undefined
  fallbackCrop: CropQueueItem
  matchedCropId: number
}) {
  const resolvedPair = pair ?? fallbackPair(fallbackCrop)

  return (
    <div className="flex min-w-0 flex-1 flex-col gap-3">
      <div className="flex items-center justify-between gap-3">
        <div className="flex min-w-0 items-center gap-2">
          <Badge variant={label === 'Card A' ? 'blue' : 'lavender'}>{label}</Badge>
          <p className="truncate text-body font-semibold text-primary">
            {resolvedPair.pairing_key}
          </p>
        </div>
      </div>
      <div className="grid min-w-0 grid-cols-1 gap-3 xl:grid-cols-2">
        <SidePreview crop={resolvedPair.front} side="front" matchedCropId={matchedCropId} />
        <SidePreview crop={resolvedPair.back} side="back" matchedCropId={matchedCropId} />
      </div>
    </div>
  )
}

export function DuplicateReviewPage() {
  const queryClient = useQueryClient()
  const { toast } = useToast()
  const { canEdit } = useAuth()

  const { data: current, isLoading } = useQuery({
    queryKey: ['duplicate-next'],
    queryFn: getNextDuplicate,
  })

  const { data: queueCount } = useQuery({
    queryKey: ['queue-count', 'duplicate'],
    queryFn: getDuplicateQueueCount,
    refetchInterval: 15_000,
  })

  const decideMutation = useMutation({
    mutationFn: (status: 'confirmed_duplicate' | 'rejected') =>
      decideDuplicate(current!.candidate_id, status),
    onSuccess: (next) => {
      queryClient.setQueryData(['duplicate-next'], next)
      queryClient.invalidateQueries({ queryKey: ['queue-count', 'duplicate'] })
      queryClient.invalidateQueries({ queryKey: ['batches'] })
    },
    onError: () => {
      toast({ title: 'Action failed', variant: 'error' })
    },
  })

  const skipMutation = useMutation({
    mutationFn: async () => {
      queryClient.invalidateQueries({ queryKey: ['duplicate-next'] })
    },
  })

  const handleConfirm = useCallback(() => {
    if (canEdit && !decideMutation.isPending && current) decideMutation.mutate('confirmed_duplicate')
  }, [decideMutation, current, canEdit])

  const handleReject = useCallback(() => {
    if (canEdit && !decideMutation.isPending && current) decideMutation.mutate('rejected')
  }, [decideMutation, current, canEdit])

  const handleSkip = useCallback(() => {
    skipMutation.mutate()
  }, [skipMutation])

  // Keyboard shortcuts
  useEffect(() => {
    function handleKey(e: KeyboardEvent) {
      if (e.target instanceof HTMLInputElement || e.target instanceof HTMLTextAreaElement) return
      if (e.code === 'KeyD') handleConfirm()
      if (e.code === 'KeyR') handleReject()
      if (e.code === 'Space') { e.preventDefault(); handleSkip() }
    }
    window.addEventListener('keydown', handleKey)
    return () => window.removeEventListener('keydown', handleKey)
  }, [handleConfirm, handleReject, handleSkip])

  const isEmpty = !isLoading && !current

  // Compute confidence label
  const structScore = current?.structural_score ?? null
  const colorScore = current?.color_score ?? null
  const avgScore = structScore != null && colorScore != null
    ? (structScore + colorScore) / 2
    : structScore ?? colorScore ?? null

  const confidenceBadge =
    avgScore == null ? { label: 'Unknown', variant: 'neutral' as const } :
    avgScore >= 0.9 ? { label: 'High confidence', variant: 'rose' as const } :
    avgScore >= 0.7 ? { label: 'Medium confidence', variant: 'peach' as const } :
    { label: 'Low confidence', variant: 'mint' as const }

  return (
    <div className="flex h-[calc(100vh-48px)] flex-col">
      <PageHeader
        title="Duplicate Review"
        description="Compare flagged card pairs and decide if they are duplicates."
        actions={
          queueCount && queueCount.count > 0 ? (
            <Badge variant="peach" className="text-body px-3 py-1.5">
              {queueCount.count} remaining
            </Badge>
          ) : undefined
        }
      />

      {isLoading ? (
        <div className="flex flex-1 gap-8">
          <Skeleton className="flex-1 rounded-xl" />
          <Skeleton className="w-64 rounded-xl" />
          <Skeleton className="flex-1 rounded-xl" />
        </div>
      ) : isEmpty ? (
        <div className="flex flex-1 items-center justify-center">
          <div className="flex flex-col items-center gap-4 text-center">
            <CheckCircle2 className="h-8 w-8 text-accent-mint-solid" />
            <div>
              <p className="text-section text-primary">Queue is empty</p>
              <p className="mt-1 text-body text-muted-foreground">
                No duplicate candidates need review right now.
              </p>
            </div>
            <Link to="/">
              <Button variant="secondary">Back to Dashboard</Button>
            </Link>
          </div>
        </div>
      ) : (
        <div className="flex flex-1 items-center gap-6 overflow-auto">
          <AnimatePresence mode="wait">
            <motion.div
              key={current?.candidate_id}
              initial={{ opacity: 0, scale: 0.98 }}
              animate={{ opacity: 1, scale: 1 }}
              exit={{ opacity: 0, scale: 0.98 }}
              transition={{ duration: 0.18 }}
              className="flex min-w-0 flex-1 items-start gap-6"
            >
              {/* Card A */}
              <CardPairPreview
                label="Card A"
                pair={current?.card_a}
                fallbackCrop={current!.crop_a}
                matchedCropId={current!.crop_a.crop_id}
              />

              {/* Score panel */}
              <div className="w-60 shrink-0 space-y-4">
                <Card className="space-y-4 p-4">
                  <div className="text-center">
                    <Badge variant={confidenceBadge.variant} className="text-caption px-3 py-1">
                      {confidenceBadge.label}
                    </Badge>
                  </div>
                  <SimilarityBar label="Structural" value={structScore} />
                  <SimilarityBar label="Color" value={colorScore} />
                  {current?.filename_match && (
                    <div className="flex items-center gap-2 rounded-lg bg-accent-blue p-2.5">
                      <AlertTriangle className="h-3.5 w-3.5 text-accent-blue-foreground" />
                      <div>
                        <p className="text-caption font-medium text-accent-blue-foreground">
                          Filename match
                        </p>
                        <p className="text-[10px] text-accent-blue-foreground/80">
                          Same pairing key
                        </p>
                      </div>
                    </div>
                  )}
                </Card>

                {/* Shortcuts */}
                <Card className="space-y-2 p-4">
                  <SectionLabel className="mb-2">Shortcuts</SectionLabel>
                  <ShortcutHint keys={['D']} label="Confirm duplicate" />
                  <ShortcutHint keys={['R']} label="Not a duplicate" />
                  <ShortcutHint keys={['Space']} label="Skip" />
                </Card>
              </div>

              {/* Card B */}
              <CardPairPreview
                label="Card B"
                pair={current?.card_b}
                fallbackCrop={current!.crop_b}
                matchedCropId={current!.crop_b.crop_id}
              />
            </motion.div>
          </AnimatePresence>
        </div>
      )}

      {/* Bottom toolbar */}
      {!isEmpty && !isLoading && (
        <div className="mt-4 flex items-center justify-center gap-3 border-t border-border pt-4">
          <Button
            variant="destructive"
            size="md"
            onClick={handleConfirm}
            disabled={!canEdit || decideMutation.isPending}
            className="gap-2 min-w-[180px]"
          >
            <CheckCircle2 className="h-4 w-4" />
            {decideMutation.isPending ? 'Saving...' : 'Confirm Duplicate'}
            <ShortcutHint keys={['D']} label="" className="ml-1" />
          </Button>
          <Button
            variant="secondary"
            size="md"
            onClick={handleReject}
            disabled={!canEdit || decideMutation.isPending}
            className="gap-2 min-w-[180px]"
          >
            <X className="h-4 w-4" />
            Not a Duplicate
            <ShortcutHint keys={['R']} label="" className="ml-1" />
          </Button>
          <Button
            variant="ghost"
            size="md"
            onClick={handleSkip}
            disabled={decideMutation.isPending}
            className="gap-2"
          >
            <SkipForward className="h-4 w-4" />
            Skip
            <ShortcutHint keys={['Space']} label="" className="ml-1" />
          </Button>
        </div>
      )}
    </div>
  )
}
