import { NavLink, Link, useLocation } from "react-router-dom";
import {
  LayoutGrid,
  Layers,
  RotateCw,
  Copy,
  BookOpen,
  Settings,
  LogOut,
  LogIn,
  ChevronLeft,
  Sun,
  Moon,
} from "lucide-react";
import { useQuery } from "@tanstack/react-query";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import { useAuth } from "@/lib/auth";
import { useTheme } from "@/lib/use-theme";
import { useSidebar } from "@/lib/use-sidebar";
import { getDuplicateQueueCount, getRotationQueueCount, listBatches } from "@/lib/api";

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

function NavRow({
  item,
  count,
  collapsed,
}: {
  item: NavItem;
  count: number;
  collapsed: boolean;
}) {
  return (
    <NavLink
      to={item.to}
      end={item.end}
      title={collapsed ? item.label : undefined}
      className={({ isActive }) =>
        cn(
          "group relative flex items-center rounded-lg py-[7px] text-body font-medium transition-colors duration-150",
          collapsed
            ? "w-full justify-center px-0"
            : "justify-between px-2.5",
          isActive
            ? "bg-muted text-primary"
            : "text-muted-foreground hover:bg-muted/70 hover:text-primary"
        )
      }
    >
      {collapsed ? (
        // Icon-only: perfectly centred in the rail
        <>
          <item.icon className="h-[16px] w-[16px] shrink-0" strokeWidth={2} />
          {count > 0 && (
            <span className="absolute right-1.5 top-1 h-1.5 w-1.5 rounded-full bg-accent-peach-solid" />
          )}
        </>
      ) : (
        // Full row with label and optional badge
        <>
          <span className="flex items-center gap-2.5">
            <item.icon className="h-[16px] w-[16px] shrink-0" strokeWidth={2} />
            {item.label}
          </span>
          {count > 0 && (
            <Badge
              variant={item.queue === "rotation" ? "lavender" : "peach"}
              className="px-1.5 py-0 text-[10px]"
            >
              {count}
            </Badge>
          )}
        </>
      )}
    </NavLink>
  );
}

export function Sidebar() {
  const { user, logout } = useAuth();
  const { theme, toggleTheme } = useTheme();
  const { collapsed, toggle } = useSidebar();
  const location = useLocation();

  // ── Batch awareness for conditional queue-count polling ──
  // Subscribes to the shared ['batches'] cache (also used by dashboard
  // and batches page). The 30s fallback refetchInterval only kicks in
  // when the sidebar is the sole observer — otherwise React Query
  // deduplicates with whatever interval the active page uses.
  const { data: batches } = useQuery({
    queryKey: ["batches"],
    queryFn: () => listBatches(),
    refetchInterval: 30_000,
    enabled: !!user,
  });

  const hasActivePipeline =
    batches?.some(
      (b) => b.status !== "complete" && b.status !== "deleting"
    ) ?? false;

  // ── Queue-count badges — only poll when there's pipeline activity ──
  const rotationCount = useQuery({
    queryKey: ["queue-count", "rotation"],
    queryFn: getRotationQueueCount,
    refetchInterval: hasActivePipeline ? 15_000 : false,
    enabled: !!user,
  });
  const duplicateCount = useQuery({
    queryKey: ["queue-count", "duplicate"],
    queryFn: getDuplicateQueueCount,
    refetchInterval: hasActivePipeline ? 15_000 : false,
    enabled: !!user,
  });

  const queueCounts = {
    rotation: rotationCount.data?.count ?? 0,
    duplicate: duplicateCount.data?.count ?? 0,
  };

  return (
    <aside
      className={cn(
        "fixed inset-y-0 left-0 z-30 flex flex-col border-r border-border bg-surface transition-[width] duration-200 ease-in-out",
        collapsed ? "w-[56px]" : "w-[232px]"
      )}
    >
      {/* ── Header ─────────────────────────────────────────────────────────── */}
      <div
        className={cn(
          "flex border-b border-border transition-all duration-200",
          collapsed
            ? "items-center justify-center px-2 py-3.5"
            : "items-center justify-between px-3.5 py-4"
        )}
      >
        {collapsed ? (
          /* Collapsed mode: logo centered; hovering reveals ChevronRight */
          <button
            id="sidebar-expand-toggle"
            onClick={toggle}
            title="Expand sidebar"
            className="group relative flex h-9 w-9 shrink-0 items-center justify-center rounded-lg transition-colors duration-150 hover:bg-muted"
          >
            <img
              src="/favicon.png"
              alt="CardFlow Logo"
              className="h-8 w-8 rounded-md object-contain transition-opacity duration-150 group-hover:opacity-0"
            />
            <ChevronLeft
              className="absolute inset-0 m-auto h-4 w-4 rotate-180 text-primary opacity-0 transition-opacity duration-150 group-hover:opacity-100"
              strokeWidth={2.5}
            />
          </button>
        ) : (
          /* Expanded mode: Logo + Text on left, ChevronLeft on right */
          <>
            <div className="flex items-center gap-2.5 min-w-0 flex-1">
              <img
                src="/favicon.png"
                alt="CardFlow Logo"
                className="h-8 w-8 shrink-0 rounded-md object-contain"
              />
              <div className="min-w-0 flex-1">
                <p className="truncate text-card-title leading-tight text-primary">CardFlow</p>
                <p className="truncate text-caption text-muted-foreground">Processing pipeline</p>
              </div>
            </div>

            <button
              id="sidebar-collapse-toggle"
              onClick={toggle}
              title="Collapse sidebar"
              className="flex h-7 w-7 shrink-0 items-center justify-center rounded-lg text-muted-foreground transition-colors duration-150 hover:bg-muted hover:text-primary"
            >
              <ChevronLeft className="h-4 w-4 shrink-0" strokeWidth={2.5} />
            </button>
          </>
        )}
      </div>

      {/* ── Nav ────────────────────────────────────────────────────────────── */}
      <nav className="flex flex-1 flex-col gap-4 overflow-y-auto overflow-x-hidden px-2 py-4">
        {NAV_GROUPS.map((group) => (
          <div key={group.label} className="flex flex-col gap-0.5">
            {/* Group label — hidden when collapsed */}
            <p
              className={cn(
                "px-2.5 pb-1 text-caption font-semibold uppercase tracking-wider text-muted-foreground/70 transition-all duration-200",
                collapsed ? "h-0 overflow-hidden opacity-0 pb-0" : "h-auto opacity-100"
              )}
            >
              {group.label}
            </p>
            {group.items.map((item) => (
              <NavRow
                key={item.to}
                item={item}
                count={item.queue ? queueCounts[item.queue] : 0}
                collapsed={collapsed}
              />
            ))}
          </div>
        ))}

        {/* Administration section */}
        <div className="mt-auto flex flex-col gap-0.5 pt-2">
          <p
            className={cn(
              "px-2.5 pb-1 text-caption font-semibold uppercase tracking-wider text-muted-foreground/70 transition-all duration-200",
              collapsed ? "h-0 overflow-hidden opacity-0 pb-0" : "h-auto opacity-100"
            )}
          >
            Administration
          </p>
          <NavRow
            item={{ to: "/settings", label: "Settings", icon: Settings }}
            count={0}
            collapsed={collapsed}
          />
        </div>
      </nav>

      {/* ── Footer ─────────────────────────────────────────────────────────── */}
      <div
        className={cn(
          "flex border-t border-border p-2",
          collapsed ? "flex-col items-center gap-2" : "flex-col gap-2"
        )}
      >
        {/* Dark mode toggle */}
        <button
          id="dark-mode-toggle"
          onClick={toggleTheme}
          title={theme === "dark" ? "Switch to light mode" : "Switch to dark mode"}
          className={cn(
            "flex items-center rounded-lg py-2 text-caption font-medium text-muted-foreground transition-colors duration-150 hover:bg-muted hover:text-primary",
            collapsed ? "w-full justify-center px-0" : "w-full gap-2 px-2.5"
          )}
        >
          {theme === "dark" ? (
            <Sun className="h-3.5 w-3.5 shrink-0" strokeWidth={2} />
          ) : (
            <Moon className="h-3.5 w-3.5 shrink-0" strokeWidth={2} />
          )}
          {!collapsed && (
            <span>{theme === "dark" ? "Light mode" : "Dark mode"}</span>
          )}
        </button>

        {/* User / logout, or Sign in for Guests */}
        {user ? (
          <button
            onClick={logout}
            title={collapsed ? `${user.name} — Sign out` : undefined}
            className={cn(
              "flex w-full items-center rounded-lg py-2 text-left transition-colors duration-150 hover:bg-muted",
              collapsed ? "justify-center px-0" : "justify-between px-2.5"
            )}
          >
            {!collapsed && (
              <div className="min-w-0">
                <p className="truncate text-caption font-medium text-primary">{user.name}</p>
                <p className="truncate text-caption text-muted-foreground">Sign out</p>
              </div>
            )}
            <LogOut className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
          </button>
        ) : (
          <Link
            to="/login"
            state={{ from: location.pathname }}
            title={collapsed ? "Sign in" : undefined}
            className={cn(
              "flex w-full items-center rounded-lg py-2 text-left transition-colors duration-150 hover:bg-muted",
              collapsed ? "justify-center px-0" : "justify-between px-2.5"
            )}
          >
            {!collapsed && (
              <p className="truncate text-caption font-medium text-primary">Sign in</p>
            )}
            <LogIn className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
          </Link>
        )}
      </div>
    </aside>
  );
}
