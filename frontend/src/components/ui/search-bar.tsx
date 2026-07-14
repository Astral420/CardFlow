import { Search } from "lucide-react";
import { type InputHTMLAttributes } from "react";
import { cn } from "@/lib/utils";

export function SearchBar({
  className,
  ...props
}: InputHTMLAttributes<HTMLInputElement>) {
  return (
    <div className={cn("relative", className)}>
      <Search className="pointer-events-none absolute left-3.5 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
      <input
        className="h-10 w-full rounded-xl border border-border bg-surface pl-10 pr-3.5 text-body text-primary placeholder:text-muted-foreground/70 transition-colors duration-150 focus:border-primary/30"
        {...props}
      />
    </div>
  );
}
