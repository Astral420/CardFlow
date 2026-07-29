import { Badge } from "@/components/ui/badge";
import type { BatchStatus, DuplicateStatus, ScanStatus } from "@/lib/types";

export const BATCH_STATUS_META: Record<
  BatchStatus,
  { label: string; variant: "lavender" | "blue" | "peach" | "mint" | "neutral" }
> = {
  extracting: { label: "Extracting", variant: "peach" },
  cropping: { label: "Cropping", variant: "blue" },
  rotation_review: { label: "Rotation review", variant: "lavender" },
  duplicate_review: { label: "Duplicate review", variant: "lavender" },
  complete: { label: "Complete", variant: "mint" },
};

export function BatchStatusBadge({ status }: { status: BatchStatus }) {
  const meta = BATCH_STATUS_META[status];
  return (
    <Badge variant={meta.variant}>
      {meta.label}
    </Badge>
  );
}

const SCAN_STATUS_META: Record<
  ScanStatus,
  { label: string; variant: "lavender" | "blue" | "peach" | "mint" | "rose" | "neutral" }
> = {
  pending: { label: "Pending", variant: "neutral" },
  cropped: { label: "Cropped", variant: "mint" },
  crop_failed: { label: "Crop failed", variant: "rose" },
};

export function ScanStatusBadge({ status }: { status: ScanStatus }) {
  const meta = SCAN_STATUS_META[status];
  return (
    <Badge variant={meta.variant}>
      {meta.label}
    </Badge>
  );
}

const DUPLICATE_STATUS_META: Record<
  DuplicateStatus,
  { label: string; variant: "lavender" | "blue" | "peach" | "mint" | "rose" | "neutral" }
> = {
  pending: { label: "Pending review", variant: "peach" },
  confirmed_duplicate: { label: "Confirmed duplicate", variant: "rose" },
  rejected: { label: "Not a duplicate", variant: "mint" },
};

export function DuplicateStatusBadge({ status }: { status: DuplicateStatus }) {
  // Guard against unknown status values from the API (e.g. legacy records)
  // to prevent a white-screen crash when meta is undefined.
  const meta = DUPLICATE_STATUS_META[status] ?? { label: status ?? "Unknown", variant: "neutral" as const };
  return (
    <Badge variant={meta.variant}>
      {meta.label}
    </Badge>
  );
}
