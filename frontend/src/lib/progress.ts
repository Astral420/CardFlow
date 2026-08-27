/**
 * getBatchProgress — derive a 0-100 progress value from a BatchDetail.
 *
 * Stages and their progress ranges:
 *   extracting        → 20  (fixed — we have no sub-item counts yet)
 *   cropping          → 20–60  (scales with cropped + crop_failed / total)
 *   rotation_review   → 60–80  (scales with confirmed / total_cropped)
 *   duplicate_review  → 80–98  (scales with resolved / total_pending_dup)
 *   complete          → 100
 *
 * duplicate_review caps at 98 intentionally — 100 is reserved for complete
 * so we never show a full bar while items are still unresolved.
 */

import type { Batch, BatchDetail } from './types'

export function getBatchProgress(batch: BatchDetail | Batch): number {
  const { status } = batch

  if (status === 'complete' || status === 'deleting') return 100

  const counts = 'counts' in batch && batch.counts ? batch.counts : undefined
  if (!counts) {
    return status === 'duplicate_review' ? 80 :
      status === 'rotation_review' ? 60 :
      status === 'cropping' ? 40 : 20
  }

  if (status === 'duplicate_review') {
    const total = counts.total_duplicate_candidates ?? counts.pending_duplicate_review
    const pending = counts.pending_duplicate_review
    if (total <= 0 || pending === 0) return 98

    const resolved = Math.max(0, total - pending)
    const ratio = Math.max(0, Math.min(1, resolved / total))
    return Math.min(98, Math.round(80 + ratio * 18))
  }

  if (status === 'rotation_review') {
    // `skipped` scans (already properly cropped, crop transform was a
    // no-op) still go through rotation review exactly like `cropped` ones
    // do — both need to be counted here.
    const total = counts.cropped + counts.skipped
    const pending = counts.pending_rotation
    if (total <= 0) return 60
    const confirmed = Math.max(0, total - pending)
    const ratio = Math.max(0, Math.min(1, confirmed / total))
    return Math.min(80, Math.round(60 + ratio * 20))
  }

  if (status === 'cropping') {
    const total = counts.scans
    if (total <= 0) return 20
    const done = counts.cropped + counts.skipped + counts.crop_failed
    const ratio = Math.max(0, Math.min(1, done / total))
    return Math.min(60, Math.round(20 + ratio * 40))
  }

  // extracting (and any unrecognised status)
  return 20
}
