import { NavLink } from "react-router-dom";
import {
  LayoutGrid,
  Layers,
  RotateCw,
  Copy,
  BookOpen,
  Settings,
  Wifi,
} from "lucide-react";
import { useQuery } from "@tanstack/react-query";
import { Avatar } from "@/components/ui/avatar";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import { useAuth } from "@/lib/auth";
import { getDuplicateQueueCount, getRotationQueueCount } from "@/lib/api";

const NAV_ITEMS = [
  { to: "/", label: "Dashboard", icon: LayoutGrid, end: true },
  { to: "/batches", label: "Batches", icon: Layers },
  { to: "/rotation-review", label: "Rotation Review", icon: RotateCw, queue: "rotation" as const },
  { to: "/duplicate-review", label: "Duplicate Review", icon: Copy, queue: "duplicate" as const },
  { to: "/card-log", label: "Card Log", icon: BookOpen },
];

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
    <aside className="fixed left-6 top-6 bottom-6 z-30 flex w-[280px] flex-col rounded-3xl border border-border bg-surface p-4 shadow-float">
      <div className="flex items-center gap-2.5 px-2 pb-6 pt-2">
        <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-primary text-primary-foreground font-semibold">
          CT
        </div>
        <div>
          <p className="text-card-title leading-tight text-primary">Card Tool</p>
          <p className="text-caption text-muted-foreground">Processing pipeline</p>
        </div>
      </div>

      <nav className="flex flex-1 flex-col gap-1">
        {NAV_ITEMS.map((item) => {
          const count = item.queue ? queueCounts[item.queue] : 0;
          return (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.end}
              className={({ isActive }) =>
                cn(
                  "group flex items-center justify-between rounded-xl px-3 py-2.5 text-body font-medium transition-colors duration-150",
                  isActive
                    ? "bg-muted text-primary"
                    : "text-muted-foreground hover:bg-muted/60 hover:text-primary"
                )
              }
            >
              <span className="flex items-center gap-3">
                <item.icon className="h-[18px] w-[18px]" strokeWidth={2} />
                {item.label}
              </span>
              {count > 0 && (
                <Badge variant={item.queue === "rotation" ? "lavender" : "peach"}>
                  {count}
                </Badge>
              )}
            </NavLink>
          );
        })}
      </nav>

      <div className="flex flex-col gap-1 border-t border-border pt-3">
        <NavLink
          to="/settings"
          className={({ isActive }) =>
            cn(
              "flex items-center gap-3 rounded-xl px-3 py-2.5 text-body font-medium transition-colors duration-150",
              isActive
                ? "bg-muted text-primary"
                : "text-muted-foreground hover:bg-muted/60 hover:text-primary"
            )
          }
        >
          <Settings className="h-[18px] w-[18px]" strokeWidth={2} />
          Settings
        </NavLink>

        <div className="mt-2 flex items-center gap-2 rounded-xl bg-muted px-3 py-2 text-caption text-accent-mint-foreground">
          <Wifi className="h-3.5 w-3.5" />
          System operational
        </div>

        <button
          onClick={logout}
          className="mt-2 flex items-center gap-3 rounded-xl px-3 py-2.5 text-left transition-colors duration-150 hover:bg-muted"
        >
          <Avatar name={user?.name ?? "?"} />
          <div className="min-w-0 flex-1">
            <p className="truncate text-body font-medium text-primary">{user?.name}</p>
            <p className="text-caption text-muted-foreground">Sign out</p>
          </div>
        </button>
      </div>
    </aside>
  );
}
