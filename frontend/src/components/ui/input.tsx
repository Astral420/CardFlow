import { forwardRef, type InputHTMLAttributes } from "react";
import { cn } from "@/lib/utils";

export const Input = forwardRef<HTMLInputElement, InputHTMLAttributes<HTMLInputElement>>(
  ({ className, ...props }, ref) => (
    <input
      ref={ref}
      className={cn(
        "h-10 w-full rounded-xl border border-border bg-surface px-3.5 text-body text-primary placeholder:text-muted-foreground/70 transition-colors duration-150 focus:border-primary/30",
        className
      )}
      {...props}
    />
  )
);
Input.displayName = "Input";
