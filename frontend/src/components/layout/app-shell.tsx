import { Outlet } from "react-router-dom";
import { Sidebar } from "./sidebar";

export function AppShell() {
  return (
    <div className="min-h-screen bg-background">
      <Sidebar />
      <main className="min-h-screen pl-[232px]">
        <div className="mx-auto w-full max-w-[1600px] px-8 py-6">
          <Outlet />
        </div>
      </main>
    </div>
  );
}
