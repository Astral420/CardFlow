import { Search } from "lucide-react";
import { type InputHTMLAttributes } from "react";
import { cn } from "@/lib/utils";

export function SearchBar({
  className,
  ...props
}: InputHTMLAttributes<HTMLInputElement>) {
  return (
    <div className={cn("relative", className)}>
      <Search className="pointer-events-none absolute left-3 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
      <input
        className="h-9 w-full rounded-lg border border-border bg-surface pl-9 pr-3 text-body text-primary placeholder:text-muted-foreground/70 outline-none transition-colors duration-150 focus:border-primary/30 focus:ring-2 focus:ring-primary/10"
        {...props}
      />
    </div>
  );
}
