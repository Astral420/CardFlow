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

import type { BatchDetail } from './types'

export function getBatchProgress(batch: BatchDetail): number {
  const { status, counts } = batch

  if (status === 'complete') return 100

  if (status === 'duplicate_review') {
    // We need a baseline total to scale against. Use the initial pending count
    // embedded in counts.pending_duplicate_review — when it equals the full
    // original total we have 0% progress within this stage; as it drains we
    // approach 98%.
    //
    // Guard: if pending_duplicate_review is 0 but we're still in this stage
    // (race condition before status flips), return 98.
    const pending = counts.pending_duplicate_review
    if (pending === 0) return 98

    // We don't have a "total duplicates" counter on BatchCounts. The best
    // approximation: when we enter duplicate_review, pending_duplicate_review
    // is the total. We can only compute relative progress once we have a
    // starting total. Since we lack that, we show 80% floor and scale by
    // how empty the queue is relative to a synthetic max.
    //
    // Practical approach: treat 0 pending as 98%, anything > 0 as 80%.
    // The bar will jump from 80→98 in one step when the queue drains.
    // For a smoother experience we'd need the backend to track the initial
    // total — that's an Option A concern.
    return 80
  }

  if (status === 'rotation_review') {
    const total = counts.cropped  // only cropped scans go to rotation review
    const pending = counts.pending_rotation
    if (total <= 0) return 60
    const confirmed = total - pending
    const ratio = confirmed / total
    return Math.round(60 + ratio * 20)
  }

  if (status === 'cropping') {
    const total = counts.scans
    if (total <= 0) return 20
    const done = counts.cropped + counts.crop_failed
    const ratio = done / total
    return Math.round(20 + ratio * 40)
  }

  // extracting (and any unrecognised status)
  return 20
}
