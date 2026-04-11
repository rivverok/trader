"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { cn } from "@/lib/utils";
import {
  LayoutDashboard,
  Signal,
  PenLine,
  ArrowRightLeft,
  FlaskConical,
  Settings,
  BarChart3,
  Telescope,
  Eye,
  Activity,
  ListChecks,
  Brain,
} from "lucide-react";
import { AlertBell } from "@/components/alert-bell";

const navItems = [
  { href: "/overview", label: "Overview", icon: Eye },
  { href: "/", label: "Dashboard", icon: LayoutDashboard },
  { href: "/watchlist", label: "Watchlist", icon: Telescope },
  { href: "/signals", label: "Signals", icon: Signal },
  { href: "/analyst", label: "Analyst", icon: PenLine },
  { href: "/trades", label: "Trades", icon: ArrowRightLeft },
  { href: "/analytics", label: "Analytics", icon: BarChart3 },
  { href: "/models", label: "Models", icon: Brain },
  { href: "/backtest", label: "Backtest", icon: FlaskConical },
  { href: "/tasks", label: "Tasks", icon: ListChecks },
  { href: "/config", label: "Config", icon: Settings },
  { href: "/status", label: "Status", icon: Activity },
];

export function Sidebar() {
  const pathname = usePathname();

  return (
    <aside className="flex h-screen w-64 flex-col border-r bg-card">
      <div className="flex h-16 items-center justify-between border-b px-6">
        <div className="flex items-center gap-2">
          <div className="h-8 w-8 rounded-lg bg-primary flex items-center justify-center">
            <span className="text-primary-foreground font-bold text-sm">AT</span>
          </div>
          <div>
            <h1 className="text-lg font-bold leading-tight">AI Trader</h1>
            <p className="text-xs text-muted-foreground">Paper Trading</p>
          </div>
        </div>
        <AlertBell />
      </div>
      <nav className="flex-1 space-y-1 p-4">
        {navItems.map((item) => {
          const isActive =
            item.href === "/"
              ? pathname === "/"
              : pathname.startsWith(item.href);
          return (
            <Link
              key={item.href}
              href={item.href}
              className={cn(
                "flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium transition-colors",
                isActive
                  ? "bg-primary text-primary-foreground"
                  : "text-muted-foreground hover:bg-accent hover:text-accent-foreground"
              )}
            >
              <item.icon className="h-4 w-4" />
              {item.label}
            </Link>
          );
        })}
      </nav>
      <div className="border-t p-4">
        <div className="flex items-center gap-2">
          <div className="h-2 w-2 rounded-full bg-green-500" />
          <span className="text-xs text-muted-foreground">System Online</span>
        </div>
      </div>
    </aside>
  );
}
