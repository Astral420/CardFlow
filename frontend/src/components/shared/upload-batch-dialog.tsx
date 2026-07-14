import { useRef, useState, type DragEvent } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import { UploadCloud, FileArchive } from "lucide-react";
import { Dialog, DialogContent, DialogTrigger } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { useToast } from "@/components/ui/toast";
import { uploadBatch, apiErrorMessage } from "@/lib/api";
import { cn } from "@/lib/utils";

export function UploadBatchDialog({ trigger }: { trigger: React.ReactNode }) {
  const [open, setOpen] = useState(false);
  const [file, setFile] = useState<File | null>(null);
  const [sourceLabel, setSourceLabel] = useState("");
  const [isDragging, setIsDragging] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { toast } = useToast();

  const mutation = useMutation({
    mutationFn: () => uploadBatch(file!, sourceLabel || undefined),
    onSuccess: ({ batch_id }) => {
      toast({
        title: "Batch upload started",
        description: "Extraction and cropping are running in the background.",
        variant: "success",
      });
      queryClient.invalidateQueries({ queryKey: ["batches"] });
      setOpen(false);
      setFile(null);
      setSourceLabel("");
      navigate(`/batches/${batch_id}`);
    },
    onError: (err) => {
      toast({ title: "Upload failed", description: apiErrorMessage(err), variant: "error" });
    },
  });

  function handleDrop(e: DragEvent<HTMLDivElement>) {
    e.preventDefault();
    setIsDragging(false);
    const dropped = e.dataTransfer.files?.[0];
    if (dropped) setFile(dropped);
  }

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>{trigger}</DialogTrigger>
      <DialogContent title="Upload a batch" description="Upload a zip of raw scans to start the processing pipeline.">
        <div className="flex flex-col gap-4">
          <div
            onDragOver={(e) => {
              e.preventDefault();
              setIsDragging(true);
            }}
            onDragLeave={() => setIsDragging(false)}
            onDrop={handleDrop}
            onClick={() => inputRef.current?.click()}
            className={cn(
              "flex cursor-pointer flex-col items-center justify-center gap-2 rounded-2xl border-2 border-dashed px-6 py-10 text-center transition-colors duration-150",
              isDragging ? "border-primary bg-muted" : "border-border hover:bg-muted/50"
            )}
          >
            {file ? (
              <>
                <FileArchive className="h-7 w-7 text-primary" />
                <p className="text-body font-medium text-primary">{file.name}</p>
                <p className="text-caption text-muted-foreground">
                  {(file.size / (1024 * 1024)).toFixed(1)} MB — click to change
                </p>
              </>
            ) : (
              <>
                <UploadCloud className="h-7 w-7 text-muted-foreground" />
                <p className="text-body font-medium text-primary">
                  Drop a .zip of scans here
                </p>
                <p className="text-caption text-muted-foreground">or click to browse</p>
              </>
            )}
            <input
              ref={inputRef}
              type="file"
              accept=".zip"
              className="hidden"
              onChange={(e) => setFile(e.target.files?.[0] ?? null)}
            />
          </div>

          <div className="space-y-1.5">
            <label className="text-caption font-medium text-muted-foreground">
              Source label (optional)
            </label>
            <Input
              placeholder="e.g. client-2024-holiday-lot"
              value={sourceLabel}
              onChange={(e) => setSourceLabel(e.target.value)}
            />
          </div>

          <Button
            size="lg"
            disabled={!file || mutation.isPending}
            onClick={() => mutation.mutate()}
          >
            {mutation.isPending ? "Uploading…" : "Start processing"}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
