import { cn } from "@/lib/utils";

const PALETTE = [
  "bg-accent-lavender text-accent-lavender-foreground",
  "bg-accent-blue text-accent-blue-foreground",
  "bg-accent-peach text-accent-peach-foreground",
  "bg-accent-mint text-accent-mint-foreground",
];

function colorFor(name: string) {
  const idx = name.charCodeAt(0) % PALETTE.length;
  return PALETTE[idx];
}

export function Avatar({ name, className }: { name: string; className?: string }) {
  const initials = name
    .split(" ")
    .map((part) => part[0])
    .slice(0, 2)
    .join("")
    .toUpperCase();

  return (
    <div
      className={cn(
        "flex h-9 w-9 shrink-0 items-center justify-center rounded-full text-caption font-semibold",
        colorFor(name),
        className
      )}
    >
      {initials}
    </div>
  );
}
