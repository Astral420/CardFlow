import type { ReactNode } from "react";
import { Card, CardHeader, CardContent } from "@/components/ui/card";
import { cn } from "@/lib/utils";

type Accent = "lavender" | "blue" | "peach" | "mint" | "rose";

// Icon color per accent — bare, no container, top-right placement.
// mint maps to the system-status green; others use muted.
const ICON_COLOR: Record<Accent, string> = {
  lavender: "text-muted-foreground",
  blue:     "text-muted-foreground",
  peach:    "text-muted-foreground",
  mint:     "text-accent-mint-solid",
  rose:     "text-muted-foreground",
};

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
  accent?: Accent;
  hint?: string;
  className?: string;
}) {
  return (
    <Card className={cn("flex flex-col", className)}>
      <CardHeader>
        <p className="text-caption text-muted-foreground">{label}</p>
        {icon && (
          <span className={cn("h-4 w-4 shrink-0", ICON_COLOR[accent])}>
            {icon}
          </span>
        )}
      </CardHeader>
      <CardContent className="pt-2 pb-4">
        <p className="text-3xl font-bold leading-tight tracking-tight text-primary">
          {value}
        </p>
        {hint && (
          <p className="mt-1 text-caption text-muted-foreground">{hint}</p>
        )}
      </CardContent>
    </Card>
  );
}
