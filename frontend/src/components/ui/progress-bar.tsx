import { motion } from "framer-motion";
import { cn } from "@/lib/utils";

export function ProgressBar({
  value,
  className,
  barClassName,
  animated = true,
}: {
  value: number;
  className?: string;
  barClassName?: string;
  animated?: boolean;
}) {
  const clamped = Math.max(0, Math.min(100, value));
  const isActive = clamped > 0 && clamped < 100;

  return (
    <div className={cn("relative h-1.5 w-full overflow-hidden rounded-full bg-muted", className)}>
      <motion.div
        initial={false}
        animate={{ width: `${clamped}%` }}
        transition={{
          type: "spring",
          stiffness: 85,
          damping: 16,
          mass: 0.7,
        }}
        className={cn(
          "relative h-full overflow-hidden rounded-full bg-interactive",
          barClassName
        )}
      >
        {/* Active shimmer sweep effect for in-flight processing */}
        {isActive && animated && (
          <motion.div
            className="absolute inset-0 bg-gradient-to-r from-transparent via-white/35 to-transparent"
            initial={{ x: "-100%" }}
            animate={{ x: "100%" }}
            transition={{
              repeat: Infinity,
              duration: 1.4,
              ease: "easeInOut",
            }}
          />
        )}
      </motion.div>
    </div>
  );
}
