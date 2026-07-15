import type { ReactNode } from "react";
import { Card } from "@/components/ui/card";
import { cn } from "@/lib/utils";

type Accent = "lavender" | "blue" | "peach" | "mint" | "rose";

// Explicit class map — Tailwind's compiler can only pick up statically
// written class names, so string-templating `bg-accent-${accent}` would
// silently produce no styles at build time.
const ACCENT_CLASSES: Record<Accent, string> = {
  lavender: "bg-accent-lavender text-accent-lavender-foreground",
  blue: "bg-accent-blue text-accent-blue-foreground",
  peach: "bg-accent-peach text-accent-peach-foreground",
  mint: "bg-accent-mint text-accent-mint-foreground",
  rose: "bg-accent-rose text-accent-rose-foreground",
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
    <Card className={cn("flex items-center gap-4 p-4", className)}>
      {icon && (
        <div
          className={cn(
            "flex h-10 w-10 shrink-0 items-center justify-center rounded-lg",
            ACCENT_CLASSES[accent]
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
