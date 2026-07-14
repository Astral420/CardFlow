import { forwardRef, type ButtonHTMLAttributes } from "react";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@/lib/utils";

const buttonVariants = cva(
  "inline-flex items-center justify-center gap-2 whitespace-nowrap rounded-xl text-body font-medium transition-all duration-150 ease-out disabled:pointer-events-none disabled:opacity-40 select-none",
  {
    variants: {
      variant: {
        primary:
          "bg-primary text-primary-foreground shadow-soft hover:bg-[#1f2937] active:scale-[0.98]",
        secondary:
          "bg-transparent text-primary border border-border hover:bg-muted active:scale-[0.98]",
        ghost: "bg-transparent text-primary hover:bg-muted active:scale-[0.98]",
        subtle: "bg-muted text-primary hover:bg-[#e9eaef] active:scale-[0.98]",
        destructive:
          "bg-accent-rose-solid text-white hover:opacity-90 active:scale-[0.98]",
      },
      size: {
        sm: "h-8 px-3 text-caption",
        md: "h-10 px-4",
        lg: "h-12 px-6 text-section",
        icon: "h-10 w-10",
      },
    },
    defaultVariants: {
      variant: "primary",
      size: "md",
    },
  }
);

export interface ButtonProps
  extends ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof buttonVariants> {}

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant, size, ...props }, ref) => (
    <button
      ref={ref}
      className={cn(buttonVariants({ variant, size }), className)}
      {...props}
    />
  )
);
Button.displayName = "Button";
