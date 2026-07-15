import type { ReactNode } from "react";
import { cn } from "@/lib/utils";

/**
 * Compact toolbar row for search / filters / sort / quick actions.
 * Controls placed inside should stay within the 36-40px height range
 * (Input, SearchBar, and Button all default within that range already).
 */
export function Toolbar({
  children,
  className,
}: {
  children: ReactNode;
  className?: string;
}) {
  return (
    <div className={cn("flex flex-wrap items-center gap-2.5", className)}>
      {children}
    </div>
  );
}

export function ToolbarSpacer() {
  return <div className="flex-1" />;
}
