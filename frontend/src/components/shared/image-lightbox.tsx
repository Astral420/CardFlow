import { useState, useRef, useEffect } from 'react'
import { createPortal } from 'react-dom'
import { ZoomIn, ZoomOut, X } from 'lucide-react'
import { motion, AnimatePresence } from 'framer-motion'

// ---------------------------------------------------------------------------
// RotatedImage
// ---------------------------------------------------------------------------

export function RotatedImage({
  src,
  alt,
  rotationDegrees,
  className = '',
}: {
  src: string
  alt: string
  rotationDegrees: number
  className?: string
}) {
  return (
    <div className={`overflow-hidden flex items-center justify-center bg-muted ${className}`}>
      <img
        src={src}
        alt={alt}
        className="h-full w-full object-contain"
        style={{ transform: rotationDegrees ? `rotate(${rotationDegrees}deg)` : undefined }}
      />
    </div>
  )
}

// ---------------------------------------------------------------------------
// FullscreenLightbox
// ---------------------------------------------------------------------------

export function FullscreenLightbox({
  isOpen,
  onClose,
  src,
  alt,
  rotationDegrees,
}: {
  isOpen: boolean
  onClose: () => void
  src: string
  alt: string
  rotationDegrees: number
}) {
  const [scale, setScale] = useState(1)
  const containerRef = useRef<HTMLDivElement>(null)

  // Reset scale when opened
  useEffect(() => {
    if (isOpen) setScale(1)
  }, [isOpen])

  if (typeof document === 'undefined') return null

  return createPortal(
    <AnimatePresence>
      {isOpen && (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          className="fixed inset-0 z-[100] flex flex-col bg-black/95 backdrop-blur-sm pointer-events-auto"
          onPointerDown={(e) => e.stopPropagation()}
          onClick={(e) => e.stopPropagation()}
        >
          <div className="absolute right-4 top-4 z-10">
            <button
              onClick={onClose}
              className="rounded-full p-2 text-white/70 transition-colors hover:bg-white/10 hover:text-white"
            >
              <X className="h-6 w-6" />
            </button>
          </div>
          <div ref={containerRef} className="relative flex flex-1 items-center justify-center overflow-hidden">
            <motion.img
              src={src}
              alt={alt}
              drag
              dragConstraints={containerRef}
              dragElastic={0.2}
              className="max-h-[85vh] max-w-[90vw] cursor-grab object-contain active:cursor-grabbing"
              animate={{ scale, rotate: rotationDegrees || 0 }}
              transition={{ type: 'spring', stiffness: 300, damping: 30 }}
            />
            <div className="absolute bottom-8 left-1/2 flex -translate-x-1/2 items-center gap-2 rounded-xl bg-white/10 p-2 backdrop-blur-md">
              <button
                onClick={() => setScale((s) => Math.max(0.5, s - 0.5))}
                className="rounded-lg p-2 text-white transition-colors hover:bg-white/20 disabled:opacity-50"
                disabled={scale <= 0.5}
              >
                <ZoomOut className="h-5 w-5" />
              </button>
              <span className="w-12 text-center text-xs font-semibold text-white">
                {Math.round(scale * 100)}%
              </span>
              <button
                onClick={() => setScale((s) => Math.min(4, s + 0.5))}
                className="rounded-lg p-2 text-white transition-colors hover:bg-white/20 disabled:opacity-50"
                disabled={scale >= 4}
              >
                <ZoomIn className="h-5 w-5" />
              </button>
            </div>
          </div>
        </motion.div>
      )}
    </AnimatePresence>,
    document.body,
  )
}
