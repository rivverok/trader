"use client";

import { useEffect, useState, useRef, useCallback } from "react";
import { Bell } from "lucide-react";
import { api, type AlertItem } from "@/lib/api";
import { cn } from "@/lib/utils";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "/api";

export function AlertBell() {
  const [alerts, setAlerts] = useState<AlertItem[]>([]);
  const [unread, setUnread] = useState(0);
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  const refresh = useCallback(() => {
    api.alerts.unreadCount().then((r) => setUnread(r.count)).catch(() => {});
    api.alerts.list(false, 20).then(setAlerts).catch(() => {});
  }, []);

  useEffect(() => {
    refresh();
    const interval = setInterval(refresh, 15000);
    return () => clearInterval(interval);
  }, [refresh]);

  // WebSocket for real-time alerts
  useEffect(() => {
    const wsBase = API_BASE.replace(/^http/, "ws");
    let ws: WebSocket | null = null;
    try {
      ws = new WebSocket(`${wsBase}/alerts/ws`);
      ws.onmessage = () => refresh();
      ws.onerror = () => {};
    } catch {
      // WebSocket not available
    }
    return () => {
      ws?.close();
    };
  }, [refresh]);

  // Close dropdown on outside click
  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) {
        setOpen(false);
      }
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, []);

  const acknowledge = async (id: number) => {
    await api.alerts.acknowledge(id);
    refresh();
  };

  const acknowledgeAll = async () => {
    await api.alerts.acknowledgeAll();
    refresh();
  };

  const severityColor: Record<string, string> = {
    info: "text-blue-400",
    warning: "text-yellow-400",
    critical: "text-red-400",
  };

  return (
    <div className="relative" ref={ref}>
      <button
        onClick={() => setOpen(!open)}
        className="relative p-2 rounded-md hover:bg-accent transition-colors"
        aria-label="Alerts"
      >
        <Bell className="h-4 w-4" />
        {unread > 0 && (
          <span className="absolute -top-0.5 -right-0.5 flex h-4 w-4 items-center justify-center rounded-full bg-red-500 text-[10px] font-bold text-white">
            {unread > 99 ? "99+" : unread}
          </span>
        )}
      </button>

      {open && (
        <div className="absolute right-0 top-10 z-50 w-80 rounded-lg border bg-card shadow-lg">
          <div className="flex items-center justify-between border-b px-4 py-2">
            <span className="text-sm font-semibold">Alerts</span>
            {unread > 0 && (
              <button
                onClick={acknowledgeAll}
                className="text-xs text-primary hover:underline"
              >
                Mark all read
              </button>
            )}
          </div>
          <div className="max-h-80 overflow-y-auto">
            {alerts.length === 0 && (
              <div className="px-4 py-6 text-center text-sm text-muted-foreground">
                No alerts
              </div>
            )}
            {alerts.map((a) => (
              <div
                key={a.id}
                className={cn(
                  "flex items-start gap-3 border-b px-4 py-3 text-sm transition-colors hover:bg-accent/50",
                  !a.acknowledged && "bg-accent/20"
                )}
                onClick={() => !a.acknowledged && acknowledge(a.id)}
                role="button"
                tabIndex={0}
              >
                <div className="mt-0.5">
                  <div
                    className={cn(
                      "h-2 w-2 rounded-full",
                      a.severity === "critical"
                        ? "bg-red-500"
                        : a.severity === "warning"
                          ? "bg-yellow-500"
                          : "bg-blue-500"
                    )}
                  />
                </div>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2">
                    <span
                      className={cn(
                        "text-xs font-medium uppercase",
                        severityColor[a.severity] || "text-muted-foreground"
                      )}
                    >
                      {a.type.replace(/_/g, " ")}
                    </span>
                    <span className="text-xs text-muted-foreground ml-auto whitespace-nowrap">
                      {new Date(a.created_at).toLocaleTimeString()}
                    </span>
                  </div>
                  <p className="text-xs text-muted-foreground mt-0.5 line-clamp-2">
                    {a.message}
                  </p>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
