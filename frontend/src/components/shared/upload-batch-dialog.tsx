import {
  cloneElement,
  isValidElement,
  useMemo,
  useRef,
  useState,
  type DragEvent,
  type ChangeEvent,
} from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import {
  UploadCloud,
  FileArchive,
  CheckCircle2,
  AlertCircle,
  AlertTriangle,
  Plus,
  X,
  Layers,
} from "lucide-react";
import { Dialog, DialogContent, DialogTrigger } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { useToast } from "@/components/ui/toast";
import { uploadBatch, uploadImages, apiErrorMessage } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { cn } from "@/lib/utils";

const MAX_FILE_SIZE_BYTES = 25 * 1024 * 1024; // 25 MB
const MAX_TOTAL_SIZE_BYTES = 500 * 1024 * 1024; // 500 MB
const MAX_IMAGE_COUNT = 200;

const IMAGE_EXTENSIONS = new Set(["jpg", "jpeg", "png"]);
const SIDE_RE = /^(.+)-(front|back)\.(jpe?g|png)$/i;

type DialogMode = "idle" | "zip" | "images";

interface ImageValidation {
  file: File;
  stem: string | null;
  side: "front" | "back" | null;
  isNameValid: boolean;
  isSizeValid: boolean;
  errorMessage: string | null;
}

function formatBytes(bytes: number): string {
  if (bytes < 1024 * 1024) {
    return `${(bytes / 1024).toFixed(0)} KB`;
  }
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function validateImageFile(file: File): ImageValidation {
  const match = file.name.match(SIDE_RE);
  const isNameValid = !!match;
  const stem = match ? match[1].toLowerCase() : null;
  const side = match ? (match[2].toLowerCase() as "front" | "back") : null;
  const isSizeValid = file.size <= MAX_FILE_SIZE_BYTES;

  let errorMessage: string | null = null;
  if (!isNameValid) {
    errorMessage = "Filename must match {id}-front or {id}-back (.jpg/.png)";
  } else if (!isSizeValid) {
    errorMessage = "File exceeds 25 MB limit";
  }

  return {
    file,
    stem,
    side,
    isNameValid,
    isSizeValid,
    errorMessage,
  };
}

export function UploadBatchDialog({ trigger }: { trigger: React.ReactNode }) {
  const { canEdit } = useAuth();
  const [open, setOpen] = useState(false);
  const [mode, setMode] = useState<DialogMode>("idle");
  const [zipFile, setZipFile] = useState<File | null>(null);
  const [imageFiles, setImageFiles] = useState<File[]>([]);
  const [sourceLabel, setSourceLabel] = useState("");
  const [rejectionError, setRejectionError] = useState<string | null>(null);
  const [isDragging, setIsDragging] = useState(false);

  const mainInputRef = useRef<HTMLInputElement>(null);
  const addMoreInputRef = useRef<HTMLInputElement>(null);
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { toast } = useToast();

  const resetState = () => {
    setMode("idle");
    setZipFile(null);
    setImageFiles([]);
    setSourceLabel("");
    setRejectionError(null);
    setIsDragging(false);
    if (mainInputRef.current) mainInputRef.current.value = "";
    if (addMoreInputRef.current) addMoreInputRef.current.value = "";
  };

  const handleOpenChange = (nextOpen: boolean) => {
    setOpen(nextOpen);
    if (!nextOpen) {
      resetState();
    }
  };

  const zipMutation = useMutation({
    mutationFn: () => uploadBatch(zipFile!, sourceLabel || undefined),
    onSuccess: ({ batch_id }) => {
      toast({
        title: "Batch upload started",
        description: "Extraction and cropping are running in the background.",
        variant: "success",
      });
      queryClient.invalidateQueries({ queryKey: ["batches"] });
      setOpen(false);
      resetState();
      navigate(`/batches/${batch_id}`);
    },
    onError: (err) => {
      toast({
        title: "Upload failed",
        description: apiErrorMessage(err),
        variant: "error",
      });
    },
  });

  const imagesMutation = useMutation({
    mutationFn: () => uploadImages(imageFiles, sourceLabel || undefined),
    onSuccess: ({ batch_id }) => {
      toast({
        title: "Batch upload started",
        description: "Cropping is running in the background.",
        variant: "success",
      });
      queryClient.invalidateQueries({ queryKey: ["batches"] });
      setOpen(false);
      resetState();
      navigate(`/batches/${batch_id}`);
    },
    onError: (err) => {
      toast({
        title: "Upload failed",
        description: apiErrorMessage(err),
        variant: "error",
      });
    },
  });

  const isSubmitting = zipMutation.isPending || imagesMutation.isPending;

  // Process incoming files (from drop or file input)
  const processIncomingFiles = (incomingList: FileList | File[], isAppending = false) => {
    setRejectionError(null);
    const filesArray = Array.from(incomingList);
    if (filesArray.length === 0) return;

    const zips: File[] = [];
    const images: File[] = [];

    for (const f of filesArray) {
      const ext = f.name.includes(".") ? f.name.split(".").pop()!.toLowerCase() : "";
      if (ext === "zip") {
        zips.push(f);
      } else if (IMAGE_EXTENSIONS.has(ext)) {
        images.push(f);
      }
    }

    if (zips.length > 0 && images.length > 0) {
      setRejectionError("Please upload either a ZIP archive or image files, not both.");
      return;
    }

    if (zips.length > 0) {
      if (isAppending && mode === "images") {
        setRejectionError("Please upload either a ZIP archive or image files, not both.");
        return;
      }
      setMode("zip");
      setZipFile(zips[0]);
      setImageFiles([]);
      return;
    }

    if (images.length > 0) {
      if (isAppending || mode === "images") {
        setImageFiles((prev) => {
          // Append and deduplicate by filename
          const existingNames = new Set(prev.map((p) => p.name));
          const toAdd = images.filter((img) => !existingNames.has(img.name));
          return [...prev, ...toAdd];
        });
      } else {
        setImageFiles(images);
      }
      setMode("images");
      setZipFile(null);
      return;
    }

    // No valid zip or image files
    setRejectionError("No supported files found. Upload .jpg, .jpeg, or .png images, or a .zip archive.");
  };

  const handleDrop = (e: DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    setIsDragging(false);
    if (e.dataTransfer.files) {
      processIncomingFiles(e.dataTransfer.files, mode === "images");
    }
  };

  const handleMainInputChange = (e: ChangeEvent<HTMLInputElement>) => {
    if (e.target.files) {
      processIncomingFiles(e.target.files, false);
    }
  };

  const handleAddMoreChange = (e: ChangeEvent<HTMLInputElement>) => {
    if (e.target.files) {
      processIncomingFiles(e.target.files, true);
    }
    if (addMoreInputRef.current) addMoreInputRef.current.value = "";
  };

  const handleRemoveImage = (indexToRemove: number) => {
    setImageFiles((prev) => {
      const next = prev.filter((_, idx) => idx !== indexToRemove);
      if (next.length === 0) {
        setMode("idle");
      }
      return next;
    });
  };

  // Image validations and metrics
  const validations: ImageValidation[] = useMemo(
    () => imageFiles.map(validateImageFile),
    [imageFiles]
  );

  const totalImageBytes = useMemo(
    () => imageFiles.reduce((acc, f) => acc + f.size, 0),
    [imageFiles]
  );

  const detectedPairsCount = useMemo(() => {
    const stems = new Map<string, { front: boolean; back: boolean }>();
    for (const v of validations) {
      if (v.stem && v.side) {
        const current = stems.get(v.stem) || { front: false, back: false };
        if (v.side === "front") current.front = true;
        if (v.side === "back") current.back = true;
        stems.set(v.stem, current);
      }
    }
    let count = 0;
    for (const s of stems.values()) {
      if (s.front && s.back) count++;
    }
    return count;
  }, [validations]);

  const invalidFilesCount = useMemo(
    () => validations.filter((v) => !v.isNameValid || !v.isSizeValid).length,
    [validations]
  );

  const isOverFileCountLimit = imageFiles.length > MAX_IMAGE_COUNT;
  const isOverTotalSizeLimit = totalImageBytes > MAX_TOTAL_SIZE_BYTES;

  const hasImageErrors =
    invalidFilesCount > 0 || isOverFileCountLimit || isOverTotalSizeLimit || imageFiles.length === 0;

  const handleSubmit = () => {
    if (mode === "zip" && zipFile) {
      zipMutation.mutate();
    } else if (mode === "images" && !hasImageErrors) {
      imagesMutation.mutate();
    }
  };

  // Guests can view every page this trigger appears on, but can't upload.
  if (!canEdit) {
    return isValidElement(trigger)
      ? cloneElement(trigger as React.ReactElement<{ disabled?: boolean }>, { disabled: true })
      : trigger;
  }

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogTrigger asChild>{trigger}</DialogTrigger>
      <DialogContent
        title="Upload a batch"
        description="Upload scans to start the processing pipeline."
        className="max-w-lg"
      >
        <div className="flex flex-col gap-4">
          {/* Rejection Alert Banner */}
          {rejectionError && (
            <div className="flex items-center justify-between rounded-lg border border-accent-rose-foreground/20 bg-accent-rose px-3 py-2 text-caption text-accent-rose-foreground">
              <div className="flex items-center gap-2">
                <AlertCircle className="h-4 w-4 shrink-0" />
                <span>{rejectionError}</span>
              </div>
              <button
                type="button"
                onClick={() => setRejectionError(null)}
                className="rounded p-0.5 hover:bg-accent-rose-foreground/10"
              >
                <X className="h-3.5 w-3.5" />
              </button>
            </div>
          )}

          {/* Idle Mode Dropzone */}
          {mode === "idle" && (
            <div
              onDragOver={(e) => {
                e.preventDefault();
                setIsDragging(true);
              }}
              onDragLeave={() => setIsDragging(false)}
              onDrop={handleDrop}
              onClick={() => mainInputRef.current?.click()}
              className={cn(
                "flex cursor-pointer flex-col items-center justify-center gap-2 rounded-xl border-2 border-dashed px-6 py-10 text-center transition-colors duration-150",
                isDragging ? "border-primary bg-muted" : "border-border hover:bg-muted/50"
              )}
            >
              <UploadCloud className="h-8 w-8 text-muted-foreground" />
              <div className="space-y-0.5">
                <p className="text-body font-medium text-primary">Drop files here</p>
                <p className="text-caption text-muted-foreground">
                  ZIP archive or JPG/PNG images
                </p>
              </div>
              <p className="text-caption font-medium text-accent-lavender-solid">
                or click to browse
              </p>
              <input
                ref={mainInputRef}
                type="file"
                accept=".zip,.jpg,.jpeg,.png"
                multiple
                className="hidden"
                onChange={handleMainInputChange}
              />
            </div>
          )}

          {/* ZIP Mode */}
          {mode === "zip" && zipFile && (
            <div
              onDragOver={(e) => {
                e.preventDefault();
                setIsDragging(true);
              }}
              onDragLeave={() => setIsDragging(false)}
              onDrop={handleDrop}
              onClick={() => mainInputRef.current?.click()}
              className={cn(
                "flex cursor-pointer flex-col items-center justify-center gap-2 rounded-xl border-2 border-dashed px-6 py-8 text-center transition-colors duration-150",
                isDragging ? "border-primary bg-muted" : "border-border hover:bg-muted/50"
              )}
            >
              <FileArchive className="h-8 w-8 text-accent-lavender-solid" />
              <p className="text-body font-medium text-primary truncate max-w-sm">
                {zipFile.name}
              </p>
              <p className="text-caption text-muted-foreground">
                {formatBytes(zipFile.size)} — click or drop to change
              </p>
              <input
                ref={mainInputRef}
                type="file"
                accept=".zip,.jpg,.jpeg,.png"
                multiple
                className="hidden"
                onChange={handleMainInputChange}
              />
            </div>
          )}

          {/* Images Mode */}
          {mode === "images" && (
            <div
              className="flex flex-col gap-2.5"
              onDragOver={(e) => {
                e.preventDefault();
                setIsDragging(true);
              }}
              onDragLeave={() => setIsDragging(false)}
              onDrop={handleDrop}
            >
              {/* Summary Bar */}
              <div className="flex items-center justify-between gap-2 px-0.5">
                <div className="flex flex-wrap items-center gap-1.5 text-caption text-muted-foreground font-medium">
                  <span className="text-primary font-semibold">
                    {imageFiles.length} {imageFiles.length === 1 ? "image" : "images"}
                  </span>
                  <span>·</span>
                  <span>{formatBytes(totalImageBytes)}</span>
                  <span>·</span>
                  <span className="inline-flex items-center gap-1 text-accent-lavender-foreground bg-accent-lavender px-2 py-0.5 rounded-full font-medium">
                    <Layers className="h-3 w-3" />
                    {detectedPairsCount} {detectedPairsCount === 1 ? "pair" : "pairs"} detected
                  </span>
                </div>
                <div className="flex items-center gap-1.5 shrink-0">
                  <Button
                    type="button"
                    variant="secondary"
                    size="sm"
                    className="h-7 px-2.5 text-caption font-medium gap-1"
                    onClick={() => addMoreInputRef.current?.click()}
                  >
                    <Plus className="h-3.5 w-3.5" />
                    Add more
                  </Button>
                  <Button
                    type="button"
                    variant="ghost"
                    size="sm"
                    className="h-7 px-2 text-caption text-muted-foreground hover:text-primary"
                    onClick={resetState}
                  >
                    Reset
                  </Button>
                  <input
                    ref={addMoreInputRef}
                    type="file"
                    accept=".jpg,.jpeg,.png"
                    multiple
                    className="hidden"
                    onChange={handleAddMoreChange}
                  />
                </div>
              </div>

              {/* Scrollable File List */}
              <div
                className={cn(
                  "relative max-h-56 overflow-y-auto rounded-xl border bg-surface/60 divide-y divide-border/60 transition-colors",
                  isDragging ? "border-primary bg-muted/30" : "border-border"
                )}
              >
                {validations.map((item, idx) => {
                  const isError = !item.isNameValid;
                  const isWarning = item.isNameValid && !item.isSizeValid;
                  const isValid = item.isNameValid && item.isSizeValid;

                  return (
                    <div
                      key={`${item.file.name}-${idx}`}
                      className="group flex flex-col p-2.5 transition-colors hover:bg-muted/40"
                    >
                      <div className="flex items-center justify-between gap-2">
                        <div className="flex items-center gap-2.5 min-w-0">
                          {isValid && (
                            <CheckCircle2 className="h-4 w-4 shrink-0 text-accent-mint-solid" />
                          )}
                          {isWarning && (
                            <AlertTriangle className="h-4 w-4 shrink-0 text-accent-peach-solid" />
                          )}
                          {isError && (
                            <AlertCircle className="h-4 w-4 shrink-0 text-accent-rose-solid" />
                          )}
                          <span
                            className="text-body font-medium text-primary truncate max-w-[280px]"
                            title={item.file.name}
                          >
                            {item.file.name}
                          </span>
                        </div>

                        <div className="flex items-center gap-2 shrink-0">
                          <span className="text-caption text-muted-foreground">
                            {formatBytes(item.file.size)}
                          </span>
                          <button
                            type="button"
                            onClick={() => handleRemoveImage(idx)}
                            className="rounded p-1 text-muted-foreground opacity-60 hover:opacity-100 hover:bg-muted hover:text-primary transition-all"
                            title="Remove file"
                          >
                            <X className="h-3.5 w-3.5" />
                          </button>
                        </div>
                      </div>

                      {/* Error / Warning Helper Line */}
                      {item.errorMessage && (
                        <div className="mt-1 pl-6.5 text-caption font-medium">
                          <span
                            className={cn(
                              isError && "text-accent-rose-foreground",
                              isWarning && "text-accent-peach-foreground"
                            )}
                          >
                            ↳ {item.errorMessage}
                          </span>
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>

              {/* Total limit warnings if applicable */}
              {isOverFileCountLimit && (
                <p className="text-caption text-accent-rose-foreground font-medium pl-0.5">
                  • Maximum {MAX_IMAGE_COUNT} images allowed at once (currently {imageFiles.length})
                </p>
              )}
              {isOverTotalSizeLimit && (
                <p className="text-caption text-accent-rose-foreground font-medium pl-0.5">
                  • Total upload exceeds 500 MB limit ({formatBytes(totalImageBytes)})
                </p>
              )}
            </div>
          )}

          {/* Source Label Input (Shared across ZIP and Images mode) */}
          <div className="space-y-1.5">
            <label className="text-caption font-medium text-muted-foreground">
              Source label (optional)
            </label>
            <Input
              placeholder="e.g. client-2024-holiday-lot"
              value={sourceLabel}
              onChange={(e) => setSourceLabel(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !isSubmitting) {
                  e.preventDefault();
                  if (mode === "zip" && zipFile) handleSubmit();
                  else if (mode === "images" && !hasImageErrors) handleSubmit();
                }
              }}
            />
          </div>

          {/* Action CTA Button */}
          <div className="space-y-2 pt-1">
            <Button
              size="lg"
              className="w-full"
              disabled={
                isSubmitting ||
                (mode === "idle" && true) ||
                (mode === "zip" && !zipFile) ||
                (mode === "images" && hasImageErrors)
              }
              onClick={handleSubmit}
            >
              {isSubmitting ? "Uploading…" : "Start processing"}
            </Button>

            {/* Error status hint when button is disabled due to errors in Images mode */}
            {mode === "images" && hasImageErrors && imageFiles.length > 0 && (
              <p className="text-center text-caption font-medium text-accent-rose-foreground animate-fade-in">
                {invalidFilesCount > 0
                  ? `${invalidFilesCount} ${
                      invalidFilesCount === 1 ? "file has errors" : "files have errors"
                    } — fix to continue`
                  : isOverFileCountLimit
                  ? `Exceeds max file count (${imageFiles.length}/${MAX_IMAGE_COUNT})`
                  : isOverTotalSizeLimit
                  ? `Exceeds max total size (${formatBytes(totalImageBytes)}/500 MB)`
                  : ""}
              </p>
            )}
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}
