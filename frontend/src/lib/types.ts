// Mirrors backend/app/schemas.py and backend/app/models/* exactly.
// Keep in sync with the FastAPI backend — do not invent fields.

export type UserRole = "admin" | "reviewer";

export type BatchStatus =
  | "extracting"
  | "cropping"
  | "rotation_review"
  | "duplicate_review"
  | "complete";

export type ScanSide = "front" | "back";

export type ScanStatus = "pending" | "cropped" | "crop_failed";

export type DuplicateStatus = "pending" | "confirmed_duplicate" | "rejected";

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
}

export interface BatchCounts {
  scans: number;
  cropped: number;
  crop_failed: number;
  pending_rotation: number;
  pending_duplicate_review: number;
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
  rotation_degrees: number;
  is_duplicate: boolean;
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
  status: string;
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
  structural_score: number | null;
  color_score: number | null;
  filename_match: boolean;
  kept: BatchDuplicateCrop;    // card_crop_a — stays in export
  removed: BatchDuplicateCrop; // card_crop_b — excluded from export
}


