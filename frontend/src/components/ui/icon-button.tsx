import { forwardRef, type ButtonHTMLAttributes } from "react";
import { cn } from "@/lib/utils";

export interface IconButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: "ghost" | "subtle" | "primary";
  active?: boolean;
  label: string;
}

export const IconButton = forwardRef<HTMLButtonElement, IconButtonProps>(
  ({ className, variant = "ghost", active, label, ...props }, ref) => (
    <button
      ref={ref}
      aria-label={label}
      title={label}
      className={cn(
        "inline-flex h-9 w-9 items-center justify-center rounded-full transition-all duration-150 ease-out active:scale-95",
        variant === "ghost" && "text-muted-foreground hover:bg-muted hover:text-primary",
        variant === "subtle" && "bg-muted text-primary hover:bg-[#e9eaef]",
        variant === "primary" && "bg-primary text-primary-foreground shadow-soft hover:bg-[#1f2937]",
        active && "bg-muted text-primary",
        className
      )}
      {...props}
    />
  )
);
IconButton.displayName = "IconButton";
