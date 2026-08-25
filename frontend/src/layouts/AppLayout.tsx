import { useQuery } from "@tanstack/react-query";
import { LayoutDashboard, LogOut, Search, Sparkles } from "lucide-react";
import { NavLink, Outlet } from "react-router-dom";

import { fetchMe } from "@/features/auth/api";
import { cn } from "@/lib/utils";
import { useAuthStore } from "@/stores/authStore";

const navItems = [
  { to: "/dashboard", label: "Dashboard", icon: LayoutDashboard },
  { to: "/research/new", label: "New Research", icon: Search },
];

export function AppLayout() {
  const clear = useAuthStore((s) => s.clear);
  const { data: me } = useQuery({ queryKey: ["me"], queryFn: fetchMe });

  return (
    <div className="flex min-h-screen bg-background">
      <aside className="hidden w-64 shrink-0 border-r border-border bg-card md:flex md:flex-col">
        <div className="flex items-center gap-2 px-6 py-5">
          <Sparkles className="h-5 w-5 text-primary" />
          <span className="text-sm font-semibold tracking-tight">AI Research Platform</span>
        </div>
        <nav className="flex flex-1 flex-col gap-1 px-3">
          {navItems.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              className={({ isActive }) =>
                cn(
                  "flex items-center gap-2.5 rounded-md px-3 py-2 text-sm font-medium transition-colors",
                  isActive
                    ? "bg-accent text-accent-foreground"
                    : "text-muted-foreground hover:bg-accent hover:text-accent-foreground",
                )
              }
            >
              <item.icon className="h-4 w-4" />
              {item.label}
            </NavLink>
          ))}
        </nav>
        <div className="border-t border-border p-4">
          <div className="mb-2 truncate text-xs text-muted-foreground">
            {me ? (
              <>
                <div className="truncate font-medium text-foreground">{me.full_name}</div>
                <div className="truncate">{me.organization.name}</div>
              </>
            ) : (
              "Loading..."
            )}
          </div>
          <button
            onClick={clear}
            className="flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-sm text-muted-foreground transition-colors hover:bg-accent hover:text-accent-foreground"
          >
            <LogOut className="h-4 w-4" />
            Sign out
          </button>
        </div>
      </aside>
      <main className="flex-1 overflow-y-auto">
        <Outlet />
      </main>
    </div>
  );
}
