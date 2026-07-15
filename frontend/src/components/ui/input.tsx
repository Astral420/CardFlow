import { forwardRef, type InputHTMLAttributes } from "react";
import { cn } from "@/lib/utils";

export const Input = forwardRef<HTMLInputElement, InputHTMLAttributes<HTMLInputElement>>(
  ({ className, ...props }, ref) => (
    <input
      ref={ref}
      className={cn(
        "h-9 w-full rounded-lg border border-border bg-surface px-3 text-body text-primary placeholder:text-muted-foreground/70 outline-none transition-colors duration-150 focus:border-primary/30 focus:ring-2 focus:ring-primary/10",
        className
      )}
      {...props}
    />
  )
);
Input.displayName = "Input";
