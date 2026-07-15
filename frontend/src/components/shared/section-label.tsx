import type { ReactNode } from "react";
import { cn } from "@/lib/utils";

/**
 * The small uppercase eyebrow label used above card groups, tab panels,
 * and info blocks throughout the dashboard (e.g. "PIPELINE STATUS",
 * "RECENT BATCHES", "SHORTCUTS"). Extracted because the raw class string
 * was being retyped in 5+ page files.
 */
export function SectionLabel({
  children,
  className,
  trailing,
}: {
  children: ReactNode;
  className?: string;
  trailing?: ReactNode;
}) {
  if (trailing) {
    return (
      <div className="flex items-center justify-between">
        <p className={cn("text-caption font-semibold uppercase tracking-wider text-muted-foreground", className)}>
          {children}
        </p>
        {trailing}
      </div>
    );
  }

  return (
    <p className={cn("text-caption font-semibold uppercase tracking-wider text-muted-foreground", className)}>
      {children}
    </p>
  );
}
