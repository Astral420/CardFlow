import { Outlet } from "react-router-dom";
import { Sidebar } from "./sidebar";
import { SidebarProvider, useSidebar } from "@/lib/use-sidebar";
import { cn } from "@/lib/utils";

function ShellLayout() {
  const { collapsed } = useSidebar();

  return (
    <div className="min-h-screen bg-background">
      <Sidebar />
      <main
        className={cn(
          "min-h-screen transition-[padding-left] duration-200 ease-in-out",
          collapsed ? "pl-[56px]" : "pl-[232px]"
        )}
      >
        <div className="mx-auto w-full max-w-[1600px] px-8 py-6">
          <Outlet />
        </div>
      </main>
    </div>
  );
}

export function AppShell() {
  return (
    <SidebarProvider>
      <ShellLayout />
    </SidebarProvider>
  );
}
