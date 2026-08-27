// Mirrors backend/app/schemas.py and backend/app/models/* exactly.
// Keep in sync with the FastAPI backend — do not invent fields.

export type UserRole = "admin" | "reviewer";

export type BatchStatus =
  | "extracting"
  | "cropping"
  | "rotation_review"
  | "duplicate_review"
  | "complete"
  | "deleting";

export type ScanSide = "front" | "back";

export type ScanStatus = "pending" | "cropped" | "skipped" | "crop_failed";

export type DuplicateStatus =
  | "pending"
  | "confirmed_duplicate"
  | "intentional_duplicate"
  | "rejected";

export interface User {
  id: number;
  name: string;
  role: UserRole;
  created_at: string;
}

export interface CreateUserPayload {
  name: string;
  password: string;
}

export interface Batch {
  id: number;
  created_at: string;
  source_label: string | null;
  status: BatchStatus;
  counts?: BatchCounts;
}

export interface BatchCounts {
  scans: number;
  cropped: number;
  skipped: number;
  crop_failed: number;
  pending_rotation: number;
  pending_duplicate_review: number;
  total_duplicate_candidates?: number;
}

export interface BatchDetail extends Batch {
  counts: BatchCounts;
}

export interface RawScan {
  id: number;
  original_filename: string;
  side: ScanSide;
  status: ScanStatus;
  thumbnail_url: string | null;
  raw_image_url: string | null;
  crop_failure_reason: "crop_error" | "bad_aspect_ratio" | null;
  crop_id: number | null;
  rotation_confirmed_at: string | null;
  rotation_degrees: number;
  is_duplicate: boolean;
  is_intentional_duplicate: boolean;
}

export interface CropQueueItem {
  crop_id: number;
  original_filename: string;
  side: ScanSide;
  image_url: string;
  rotation_degrees: number;
  rotation_confirmed_at: string | null;
}

export interface RotationNext {
  batch_id: number;
  original_filename: string;
  front: CropQueueItem | null;
  back: CropQueueItem | null;
}

export interface QueueCount {
  count: number;
}

export interface CardPair {
  pairing_key: string;
  front: CropQueueItem | null;
  back: CropQueueItem | null;
}

export interface DuplicateCandidate {
  candidate_id: number;
  // Both crops in a pair always belong to the same batch (duplicate
  // detection only ever compares within-batch); lets the review queue
  // (intentionally global, not batch-scoped) show which batch is being
  // reviewed.
  batch_id: number;
  source_label: string | null;
  status: DuplicateStatus;
  structural_score: number | null;
  color_score: number | null;
  filename_match: boolean;
  crop_a: CropQueueItem;
  crop_b: CropQueueItem;
  card_a: CardPair;
  card_b: CardPair;
}

export interface CardCrop {
  id: number;
  original_filename: string;
  side: ScanSide;
  status: ScanStatus;
  batch_id: number;
  image_url: string | null;
  aspect_ratio_ok: boolean | null;
  rotation_confirmed_at: string | null;
}

export interface CardCropDetail extends CardCrop {
  front_image_url: string | null;
  back_image_url: string | null;
  hash_0: string | null;
  hash_90: string | null;
  hash_180: string | null;
  hash_270: string | null;
  duplicate_history: DuplicateCandidate[];
}

export interface BatchDuplicateCrop {
  crop_id: number;
  original_filename: string;
  side: ScanSide;
  image_url: string | null;
  rotation_degrees: number;
}

export interface BatchDuplicatePair {
  candidate_id: number;
  status: DuplicateStatus; // confirmed_duplicate or intentional_duplicate
  structural_score: number | null;
  color_score: number | null;
  filename_match: boolean;
  kept: BatchDuplicateCrop;    // card_crop_a — stays in export
  // card_crop_b. For status="confirmed_duplicate" this side is excluded
  // from export; for status="intentional_duplicate" it is NOT (both sides
  // ship — see backend app.api.batches.export_batch_zip).
  removed: BatchDuplicateCrop;
}

