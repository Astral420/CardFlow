import type { ReactNode } from "react";
import { Card } from "@/components/ui/card";
import { cn } from "@/lib/utils";

export function StatCard({
  label,
  value,
  icon,
  accent = "lavender",
  hint,
  className,
}: {
  label: string;
  value: ReactNode;
  icon?: ReactNode;
  accent?: "lavender" | "blue" | "peach" | "mint" | "rose";
  hint?: string;
  className?: string;
}) {
  return (
    <Card className={cn("flex items-center gap-4 p-5", className)}>
      {icon && (
        <div
          className={cn(
            "flex h-11 w-11 shrink-0 items-center justify-center rounded-xl",
            `bg-accent-${accent} text-accent-${accent}-foreground`
          )}
        >
          {icon}
        </div>
      )}
      <div className="min-w-0">
        <p className="text-caption text-muted-foreground">{label}</p>
        <p className="text-page-title leading-tight text-primary">{value}</p>
        {hint && <p className="mt-0.5 text-caption text-muted-foreground">{hint}</p>}
      </div>
    </Card>
  );
}
