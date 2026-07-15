import { useCallback, useEffect } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { RotateCw, CheckCircle, SkipForward, ImageOff } from 'lucide-react'
import { motion, AnimatePresence } from 'framer-motion'
import { Link } from 'react-router-dom'
import {
  getNextRotation,
  getRotationQueueCount,
  rotateCrop,
  confirmCrop,
} from '@/lib/api'
import { Button } from '@/components/ui/button'
import { ShortcutHint } from '@/components/ui/kbd'
import { Skeleton } from '@/components/ui/skeleton'
import { Badge } from '@/components/ui/badge'
import { Card } from '@/components/ui/card'
import { useToast } from '@/components/ui/toast'
import { PageHeader } from '@/components/shared/page-header'
import { SectionLabel } from '@/components/shared/section-label'
import type { CropQueueItem, RotationNext } from '@/lib/types'

function CardImagePanel({
  label,
  crop,
  onRotate,
  disabled,
}: {
  label: 'Front' | 'Back'
  crop: CropQueueItem | null | undefined
  onRotate: (cropId: number, degrees: number) => void
  disabled: boolean
}) {
  const isConfirmed = Boolean(crop?.rotation_confirmed_at)
  const canRotate = Boolean(crop) && !isConfirmed && !disabled

  return (
    <div className="flex flex-1 flex-col items-center gap-3">
      <div className="flex items-center gap-2">
        <Badge variant={label === 'Front' ? 'blue' : 'neutral'}>{label}</Badge>
        {crop && (
          <Badge variant={isConfirmed ? 'mint' : 'lavender'}>
            {isConfirmed ? 'Confirmed' : 'Pending'}
          </Badge>
        )}
      </div>

      <div className="relative flex min-h-[320px] w-full max-w-[460px] items-center justify-center overflow-hidden rounded-xl border border-border bg-muted p-3 shadow-soft">
        {crop?.image_url ? (
          <motion.img
            src={crop.image_url}
            alt={`${label} image`}
            className="max-h-[58vh] max-w-full object-contain"
            style={{ rotate: crop.rotation_degrees }}
            transition={{ duration: 0.2, ease: 'easeInOut' }}
            animate={{ rotate: crop.rotation_degrees }}
          />
        ) : (
          <div className="flex aspect-[2.5/3.5] w-full items-center justify-center">
            <ImageOff className="h-12 w-12 text-muted-foreground/30" />
          </div>
        )}
      </div>

      <div className="flex flex-wrap justify-center gap-2">
        <Button
          variant="secondary"
          size="sm"
          onClick={() => crop && onRotate(crop.crop_id, 90)}
          disabled={!canRotate}
          className="gap-1.5"
        >
          <RotateCw className="h-3.5 w-3.5" />
          {label} 90 deg
        </Button>
        <Button
          variant="secondary"
          size="sm"
          onClick={() => crop && onRotate(crop.crop_id, 180)}
          disabled={!canRotate}
          className="gap-1.5"
        >
          <RotateCw className="h-3.5 w-3.5" />
          {label} 180 deg
        </Button>
      </div>
    </div>
  )
}

export function RotationReviewPage() {
  const queryClient = useQueryClient()
  const { toast } = useToast()

  const { data: current, isLoading } = useQuery({
    queryKey: ['rotation-next'],
    queryFn: () => getNextRotation(),
  })

  const { data: queueCount } = useQuery({
    queryKey: ['queue-count', 'rotation'],
    queryFn: getRotationQueueCount,
    refetchInterval: 15_000,
  })

  const rotateMutation = useMutation({
    mutationFn: async ({ cropId, degrees }: { cropId: number; degrees: number }) => {
      return rotateCrop(cropId, degrees)
    },
    onSuccess: (updated) => {
      queryClient.setQueryData<RotationNext | null>(['rotation-next'], (old) => {
        if (!old) return old

        const replace = (crop: CropQueueItem | null) =>
          crop?.crop_id === updated.crop_id ? updated : crop

        return {
          ...old,
          front: replace(old.front),
          back: replace(old.back),
        }
      })
    },
    onError: () => {
      toast({ title: 'Rotate failed', variant: 'error' })
    },
  })

  const confirmMutation = useMutation({
    mutationFn: async () => {
      const cropId =
        (!current?.front?.rotation_confirmed_at && current?.front?.crop_id) ||
        (!current?.back?.rotation_confirmed_at && current?.back?.crop_id)

      if (!cropId) return null
      return confirmCrop(cropId)
    },
    onSuccess: (next) => {
      queryClient.setQueryData(['rotation-next'], next)
      queryClient.invalidateQueries({ queryKey: ['queue-count', 'rotation'] })
    },
    onError: () => {
      toast({ title: 'Confirm failed', variant: 'error' })
    },
  })

  const skipMutation = useMutation({
    mutationFn: async () => {
      queryClient.invalidateQueries({ queryKey: ['rotation-next'] })
    },
  })

  const handleRotate = useCallback(
    (cropId: number, degrees: number) => {
      if (!rotateMutation.isPending) rotateMutation.mutate({ cropId, degrees })
    },
    [rotateMutation]
  )

  const handleConfirm = useCallback(() => {
    if (!confirmMutation.isPending) confirmMutation.mutate()
  }, [confirmMutation])

  const handleSkip = useCallback(() => {
    skipMutation.mutate()
  }, [skipMutation])

  useEffect(() => {
    function handleKey(e: KeyboardEvent) {
      if (e.target instanceof HTMLInputElement || e.target instanceof HTMLTextAreaElement) return
      if (e.code === 'Space') { e.preventDefault(); handleConfirm() }
      if (e.code === 'KeyF' && current?.front?.crop_id && !current.front.rotation_confirmed_at) {
        handleRotate(current.front.crop_id, 90)
      }
      if (e.code === 'KeyB' && current?.back?.crop_id && !current.back.rotation_confirmed_at) {
        handleRotate(current.back.crop_id, 90)
      }
      if (e.code === 'ArrowRight') handleSkip()
    }

    window.addEventListener('keydown', handleKey)
    return () => window.removeEventListener('keydown', handleKey)
  }, [current, handleConfirm, handleRotate, handleSkip])

  const isEmpty = !isLoading && !current

  return (
    <div className="flex h-[calc(100vh-48px)] flex-col">
      <PageHeader
        title="Rotation Review"
        description="Rotate front and back independently, then confirm each pending side."
        actions={
          queueCount && queueCount.count > 0 ? (
            <Badge variant="lavender" className="text-body px-3 py-1.5">
              {queueCount.count} remaining
            </Badge>
          ) : undefined
        }
      />

      {isLoading ? (
        <div className="flex flex-1 gap-8">
          <Skeleton className="flex-1 rounded-xl" />
          <Skeleton className="flex-1 rounded-xl" />
          <Skeleton className="w-56 rounded-xl" />
        </div>
      ) : isEmpty ? (
        <div className="flex flex-1 items-center justify-center">
          <div className="flex flex-col items-center gap-4 text-center">
            <div className="flex h-16 w-16 items-center justify-center rounded-xl bg-accent-mint text-accent-mint-foreground">
              <CheckCircle className="h-8 w-8" />
            </div>
            <div>
              <p className="text-section text-primary">Queue is empty</p>
              <p className="mt-1 text-body text-muted-foreground">
                All cards have been reviewed.
              </p>
            </div>
            <Link to="/">
              <Button variant="secondary">Back to Dashboard</Button>
            </Link>
          </div>
        </div>
      ) : (
        <div className="flex flex-1 gap-6 overflow-hidden">
          <AnimatePresence mode="wait">
            <motion.div
              key={`${current?.front?.crop_id}-${current?.back?.crop_id}`}
              initial={{ opacity: 0, x: -8 }}
              animate={{ opacity: 1, x: 0 }}
              exit={{ opacity: 0, x: 8 }}
              transition={{ duration: 0.18 }}
              className="flex flex-1 items-center justify-center gap-8"
            >
              <CardImagePanel
                label="Front"
                crop={current?.front}
                onRotate={handleRotate}
                disabled={rotateMutation.isPending || confirmMutation.isPending}
              />
              <CardImagePanel
                label="Back"
                crop={current?.back}
                onRotate={handleRotate}
                disabled={rotateMutation.isPending || confirmMutation.isPending}
              />
            </motion.div>
          </AnimatePresence>

          <div className="flex w-56 shrink-0 flex-col gap-4">
            <Card className="space-y-3 p-4">
              <div>
                <SectionLabel>Filename</SectionLabel>
                <p className="mt-1 break-all text-body font-medium text-primary">
                  {current?.original_filename ?? '-'}
                </p>
              </div>
              <div>
                <SectionLabel>Batch</SectionLabel>
                <p className="mt-1 text-body text-primary">#{current?.batch_id ?? '-'}</p>
              </div>
              <div>
                <SectionLabel>Queue</SectionLabel>
                <p className="mt-1 text-body text-primary">{queueCount?.count ?? '-'} remaining</p>
              </div>
              {current?.front?.crop_id && (
                <div>
                  <SectionLabel>Front Crop ID</SectionLabel>
                  <p className="mt-1 text-body text-primary">#{current.front.crop_id}</p>
                </div>
              )}
              {current?.back?.crop_id && (
                <div>
                  <SectionLabel>Back Crop ID</SectionLabel>
                  <p className="mt-1 text-body text-primary">#{current.back.crop_id}</p>
                </div>
              )}
            </Card>

            <Card className="space-y-2 p-4">
              <SectionLabel className="mb-2">Shortcuts</SectionLabel>
              <ShortcutHint keys={['Space']} label="Confirm next pending" />
              <ShortcutHint keys={['F']} label="Front 90 deg" />
              <ShortcutHint keys={['B']} label="Back 90 deg" />
              <ShortcutHint keys={['Right']} label="Skip" />
            </Card>
          </div>
        </div>
      )}

      {!isEmpty && !isLoading && (
        <div className="mt-4 flex items-center justify-center gap-3 border-t border-border pt-4">
          <Button
            size="md"
            onClick={handleConfirm}
            disabled={confirmMutation.isPending || rotateMutation.isPending}
            className="gap-2 min-w-[190px]"
          >
            <CheckCircle className="h-4 w-4" />
            {confirmMutation.isPending ? 'Confirming...' : 'Confirm next pending'}
            <ShortcutHint keys={['Space']} label="" className="ml-1" />
          </Button>
          <Button
            variant="ghost"
            size="md"
            onClick={handleSkip}
            disabled={confirmMutation.isPending}
            className="gap-2"
          >
            <SkipForward className="h-4 w-4" />
            Skip
            <ShortcutHint keys={['Right']} label="" className="ml-1" />
          </Button>
        </div>
      )}
    </div>
  )
}
