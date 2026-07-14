import { cn } from "@/lib/utils";

export function Kbd({ children, className }: { children: React.ReactNode; className?: string }) {
  return (
    <kbd
      className={cn(
        "inline-flex h-6 min-w-[24px] items-center justify-center rounded-md border border-border bg-muted px-1.5 text-caption font-semibold text-primary shadow-[inset_0_-1px_0_rgba(17,24,39,0.06)]",
        className
      )}
    >
      {children}
    </kbd>
  );
}

export function ShortcutHint({
  keys,
  label,
  className,
}: {
  keys: string[];
  label: string;
  className?: string;
}) {
  return (
    <div className={cn("flex items-center gap-2", className)}>
      <div className="flex items-center gap-1">
        {keys.map((k) => (
          <Kbd key={k}>{k}</Kbd>
        ))}
      </div>
      <span className="text-caption text-muted-foreground">{label}</span>
    </div>
  );
}
