import type { ReactNode } from "react";
import { Dialog, DialogContent } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";

interface ConfirmDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: string;
  description?: string;
  confirmLabel?: string;
  cancelLabel?: string;
  destructive?: boolean;
  isLoading?: boolean;
  loadingLabel?: string;
  error?: string | null;
  onConfirm: () => void;
  /** Extra body content rendered above the error/button row, e.g. the
   * "this is irreversible" warning copy specific to the calling flow. */
  children?: ReactNode;
}

/**
 * Generic centered confirm/cancel modal built on the app's existing Radix
 * Dialog primitive (components/ui/dialog.tsx) -- same overlay, card, and
 * animation as every other dialog in the app (AddReviewerDialog,
 * UploadBatchDialog, etc). Intentionally has no opinion about *what* it's
 * confirming; callers supply the copy and the mutation.
 *
 * While isLoading is true, the dialog can't be dismissed -- Escape, the
 * overlay click, the header's X button, and the Cancel button are all
 * routed through the same onOpenChange, so gating it here is enough to
 * lock every close path during the in-flight request.
 */
export function ConfirmDialog({
  open,
  onOpenChange,
  title,
  description,
  confirmLabel = "Confirm",
  cancelLabel = "Cancel",
  destructive = false,
  isLoading = false,
  loadingLabel = "Working…",
  error,
  onConfirm,
  children,
}: ConfirmDialogProps) {
  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        if (!isLoading) onOpenChange(next);
      }}
    >
      <DialogContent title={title} description={description}>
        <div className="flex flex-col gap-4">
          {children}

          {error && (
            <p className="rounded-xl bg-accent-rose px-3 py-2 text-caption text-accent-rose-foreground">
              {error}
            </p>
          )}

          <div className="flex justify-end gap-2">
            <Button
              variant="secondary"
              size="md"
              disabled={isLoading}
              onClick={() => onOpenChange(false)}
            >
              {cancelLabel}
            </Button>
            <Button
              variant={destructive ? "destructive" : "primary"}
              size="md"
              disabled={isLoading}
              onClick={onConfirm}
            >
              {isLoading ? loadingLabel : confirmLabel}
            </Button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}
