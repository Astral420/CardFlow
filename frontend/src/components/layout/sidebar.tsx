import { NavLink } from "react-router-dom";
import {
  LayoutGrid,
  Layers,
  RotateCw,
  Copy,
  BookOpen,
  Settings,
  Circle,
} from "lucide-react";
import { useQuery } from "@tanstack/react-query";
import { Avatar } from "@/components/ui/avatar";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import { useAuth } from "@/lib/auth";
import { getDuplicateQueueCount, getRotationQueueCount } from "@/lib/api";

interface NavItem {
  to: string;
  label: string;
  icon: typeof LayoutGrid;
  end?: boolean;
  queue?: "rotation" | "duplicate";
}

interface NavGroup {
  label: string;
  items: NavItem[];
}

const NAV_GROUPS: NavGroup[] = [
  {
    label: "Overview",
    items: [{ to: "/", label: "Dashboard", icon: LayoutGrid, end: true }],
  },
  {
    label: "Processing",
    items: [{ to: "/batches", label: "Batches", icon: Layers }],
  },
  {
    label: "Review",
    items: [
      { to: "/rotation-review", label: "Rotation Review", icon: RotateCw, queue: "rotation" },
      { to: "/duplicate-review", label: "Duplicate Review", icon: Copy, queue: "duplicate" },
    ],
  },
  {
    label: "History",
    items: [{ to: "/card-log", label: "Card Log", icon: BookOpen }],
  },
];

function NavRow({ item, count }: { item: NavItem; count: number }) {
  return (
    <NavLink
      to={item.to}
      end={item.end}
      className={({ isActive }) =>
        cn(
          "group flex items-center justify-between rounded-lg px-2.5 py-[7px] text-body font-medium transition-colors duration-150",
          isActive
            ? "bg-muted text-primary"
            : "text-muted-foreground hover:bg-muted/70 hover:text-primary"
        )
      }
    >
      <span className="flex items-center gap-2.5">
        <item.icon className="h-[16px] w-[16px]" strokeWidth={2} />
        {item.label}
      </span>
      {count > 0 && (
        <Badge variant={item.queue === "rotation" ? "lavender" : "peach"} className="px-1.5 py-0 text-[10px]">
          {count}
        </Badge>
      )}
    </NavLink>
  );
}

export function Sidebar() {
  const { user, logout } = useAuth();

  const rotationCount = useQuery({
    queryKey: ["queue-count", "rotation"],
    queryFn: getRotationQueueCount,
    refetchInterval: 15000,
  });
  const duplicateCount = useQuery({
    queryKey: ["queue-count", "duplicate"],
    queryFn: getDuplicateQueueCount,
    refetchInterval: 15000,
  });

  const queueCounts = {
    rotation: rotationCount.data?.count ?? 0,
    duplicate: duplicateCount.data?.count ?? 0,
  };

  return (
    <aside className="fixed inset-y-0 left-0 z-30 flex w-[232px] flex-col border-r border-border bg-surface">
      <div className="flex items-center gap-2.5 border-b border-border px-4 py-4">
        <div className="flex h-7 w-7 items-center justify-center rounded-md bg-primary text-[11px] font-semibold text-primary-foreground">
          CF
        </div>
        <div className="min-w-0">
          <p className="truncate text-card-title leading-tight text-primary">CardFlow</p>
          <p className="truncate text-caption text-muted-foreground">Processing pipeline</p>
        </div>
      </div>

      <nav className="flex flex-1 flex-col gap-4 overflow-y-auto px-3 py-4">
        {NAV_GROUPS.map((group) => (
          <div key={group.label} className="flex flex-col gap-0.5">
            <p className="px-2.5 pb-1 text-caption font-semibold uppercase tracking-wider text-muted-foreground/70">
              {group.label}
            </p>
            {group.items.map((item) => (
              <NavRow key={item.to} item={item} count={item.queue ? queueCounts[item.queue] : 0} />
            ))}
          </div>
        ))}

        <div className="mt-auto flex flex-col gap-0.5 pt-2">
          <p className="px-2.5 pb-1 text-caption font-semibold uppercase tracking-wider text-muted-foreground/70">
            Administration
          </p>
          <NavRow item={{ to: "/settings", label: "Settings", icon: Settings }} count={0} />
        </div>
      </nav>

      <div className="flex flex-col gap-2 border-t border-border p-3">
        <div className="flex items-center gap-1.5 rounded-lg bg-accent-mint px-2.5 py-1.5 text-caption font-medium text-accent-mint-foreground">
          <Circle className="h-1.5 w-1.5 shrink-0 fill-current" />
          System operational
        </div>

        <button
          onClick={logout}
          className="flex items-center gap-2.5 rounded-lg px-2 py-1.5 text-left transition-colors duration-150 hover:bg-muted"
        >
          <Avatar name={user?.name ?? "?"} className="h-7 w-7 text-[10px]" />
          <div className="min-w-0 flex-1">
            <p className="truncate text-caption font-medium text-primary">{user?.name}</p>
            <p className="truncate text-caption text-muted-foreground">Sign out</p>
          </div>
        </button>
      </div>
    </aside>
  );
}
