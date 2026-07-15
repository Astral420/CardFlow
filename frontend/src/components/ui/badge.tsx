import { type HTMLAttributes } from "react";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@/lib/utils";

const badgeVariants = cva(
  "inline-flex items-center gap-1.5 rounded-full px-2 py-0.5 text-caption font-medium leading-none",
  {
    variants: {
      variant: {
        neutral: "bg-muted text-muted-foreground",
        lavender: "bg-accent-lavender text-accent-lavender-foreground",
        blue: "bg-accent-blue text-accent-blue-foreground",
        peach: "bg-accent-peach text-accent-peach-foreground",
        mint: "bg-accent-mint text-accent-mint-foreground",
        rose: "bg-accent-rose text-accent-rose-foreground",
        dark: "bg-primary text-primary-foreground",
      },
    },
    defaultVariants: { variant: "neutral" },
  }
);

export interface BadgeProps
  extends HTMLAttributes<HTMLSpanElement>,
    VariantProps<typeof badgeVariants> {
  dot?: boolean;
}

export function Badge({ className, variant, dot, children, ...props }: BadgeProps) {
  return (
    <span className={cn(badgeVariants({ variant }), className)} {...props}>
      {dot && <span className="h-1.5 w-1.5 rounded-full bg-current opacity-70" />}
      {children}
    </span>
  );
}
