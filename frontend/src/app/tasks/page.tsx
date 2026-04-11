"use client";

import { useEffect, useState, useCallback } from "react";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import {
  api,
  type ActiveTask,
  type ScheduledTask,
  type TaskListResponse,
  type TaskInfo,
  type DataStatusResponse,
} from "@/lib/api";

function StatusDot({ status }: { status: string }) {
  const color: Record<string, string> = {
    STARTED: "bg-blue-500 animate-pulse",
    QUEUED: "bg-yellow-500",
    SUCCESS: "bg-green-500",
    WARNING: "bg-yellow-500",
    FAILURE: "bg-red-500",
    REVOKED: "bg-gray-500",
    PENDING: "bg-gray-400",
    RETRY: "bg-orange-500",
  };
  return <div className={`h-2.5 w-2.5 rounded-full ${color[status] || "bg-gray-400"}`} />;
}

function StatusBadge({ status }: { status: string }) {
  const styles: Record<string, string> = {
    STARTED: "bg-blue-500/10 text-blue-500 border-blue-500/30",
    QUEUED: "bg-yellow-500/10 text-yellow-500 border-yellow-500/30",
    SUCCESS: "bg-green-500/10 text-green-500 border-green-500/30",
    WARNING: "bg-yellow-500/10 text-yellow-500 border-yellow-500/30",
    FAILURE: "bg-red-500/10 text-red-500 border-red-500/30",
    REVOKED: "bg-gray-500/10 text-gray-400 border-gray-500/30",
    PENDING: "bg-gray-500/10 text-gray-400 border-gray-500/30",
  };
  const labels: Record<string, string> = { WARNING: "ERRORS" };
  return (
    <span className={`rounded-full border px-2 py-0.5 text-xs font-medium ${styles[status] || styles.PENDING}`}>
      {labels[status] || status}
    </span>
  );
}

/** Check if a Celery SUCCESS result actually contains errors */
function hasResultErrors(result: string | undefined): boolean {
  if (!result) return false;
  const formatted = formatResult(result);
  return /errors:\s*[1-9]/.test(formatted) || /analyzed:\s*0/.test(formatted);
}

function TaskName({ name }: { name: string }) {
  // Strip "app.tasks." prefix for readability
  const short = name.replace(/^app\.tasks\.\w+\./, "");
  return <span className="font-mono text-sm">{short}</span>;
}

function formatResult(raw: string): string {
  try {
    const jsonStr = raw
      .replace(/'/g, '"')
      .replace(/\bTrue\b/g, "true")
      .replace(/\bFalse\b/g, "false")
      .replace(/\bNone\b/g, "null");
    const obj = JSON.parse(jsonStr);

    // Show concise summary, skip verbose fields
    const skip = new Set(["status", "batch_id", "error"]);
    const shorten = new Set(["market_assessment", "watchlist_health"]);
    return Object.entries(obj)
      .filter(([k]) => !skip.has(k))
      .map(([k, v]) => {
        const label = k.replace(/_/g, " ");
        if (Array.isArray(v)) return `${label}: ${v.length > 0 ? v.join(", ") : "none"}`;
        if (shorten.has(k) && typeof v === "string" && v.length > 80) return `${label}: ${v.slice(0, 80)}…`;
        if (typeof v === "object" && v !== null) {
          // e.g. strategies: {movers: 18, earnings: 15, ...}
          return `${label}: ${Object.entries(v).map(([sk, sv]) => `${sk}=${sv}`).join(", ")}`;
        }
        return `${label}: ${v}`;
      })
      .join(" · ");
  } catch {
    return raw.slice(0, 200);
  }
}

function formatSchedule(raw: string): string {
  // Plain number = interval in seconds
  const secs = Number(raw);
  if (!isNaN(secs) && secs > 0) {
    if (secs < 60) return `Every ${secs}s`;
    if (secs < 3600) return `Every ${Math.round(secs / 60)} min`;
    const h = Math.floor(secs / 3600);
    const m = Math.round((secs % 3600) / 60);
    return m > 0 ? `Every ${h}h ${m}m` : `Every ${h}h`;
  }

  // Crontab: "<crontab: 0,30 9-16 * * mon-fri (m/h/dM/MY/d)>"
  const cronMatch = raw.match(/<crontab:\s*([^(]+)\(/);
  if (cronMatch) {
    const parts = cronMatch[1].trim().split(/\s+/);
    const [minute, hour, , , dow] = parts;

    const fmtTime = () => {
      const hours = hour || "*";
      const mins = minute || "0";
      if (hours === "*") return mins === "0" ? "every hour" : `every hour at :${mins.padStart(2, "0")}`;
      if (hours.includes("-")) {
        const [start, end] = hours.split("-").map(Number);
        const startFmt = start <= 12 ? `${start || 12}` : `${start - 12}`;
        const endFmt = end <= 12 ? `${end || 12}` : `${end - 12}`;
        const startAP = start < 12 ? "AM" : "PM";
        const endAP = end < 12 ? "AM" : "PM";
        const minLabel = mins === "0" ? "" : mins.includes(",") ? ` at :${mins}` : ` at :${mins.padStart(2, "0")}`;
        return `${startFmt}${startAP}–${endFmt}${endAP}${minLabel}`;
      }
      const h = Number(hours);
      const ampm = h < 12 ? "AM" : "PM";
      const h12 = h === 0 ? 12 : h > 12 ? h - 12 : h;
      const minLabel = mins === "0" ? "" : `:${mins.padStart(2, "0")}`;
      return `${h12}${minLabel} ${ampm}`;
    };

    const fmtDow = () => {
      if (!dow || dow === "*") return "";
      const dayMap: Record<string, string> = {
        mon: "Mon", tue: "Tue", wed: "Wed", thu: "Thu", fri: "Fri", sat: "Sat", sun: "Sun",
        "0": "Sun", "1": "Mon", "2": "Tue", "3": "Wed", "4": "Thu", "5": "Fri", "6": "Sat",
      };
      if (dow === "mon-fri" || dow === "1-5") return "weekdays";
      if (dow === "sat,sun" || dow === "0,6" || dow === "6,0") return "weekends";
      return dow.split(",").map((d) => dayMap[d.toLowerCase()] || d).join(", ");
    };

    const timePart = fmtTime();
    const dowPart = fmtDow();
    return dowPart ? `${dowPart}, ${timePart}` : timePart;
  }

  return raw;
}

function ActiveTaskRow({
  task,
  onCancel,
  cancelling,
}: {
  task: ActiveTask;
  onCancel: (id: string) => void;
  cancelling: boolean;
}) {
  return (
    <div className="flex items-center justify-between rounded-lg border p-3">
      <div className="flex items-center gap-3 min-w-0 flex-1">
        <StatusDot status={task.status} />
        <div className="min-w-0">
          <TaskName name={task.name} />
          <div className="flex gap-3 text-xs text-muted-foreground mt-0.5">
            <span>Worker: {task.worker.split("@")[1] || task.worker}</span>
            {task.started_at && (
              <span>Started: {new Date(task.started_at).toLocaleTimeString()}</span>
            )}
          </div>
        </div>
      </div>
      <div className="flex items-center gap-2 shrink-0">
        <StatusBadge status={task.status} />
        <Button
          variant="destructive"
          size="sm"
          className="h-7 px-2 text-xs"
          disabled={cancelling}
          onClick={() => onCancel(task.task_id)}
        >
          {cancelling ? "..." : "Cancel"}
        </Button>
      </div>
    </div>
  );
}

function TrainingProgress({ progress }: { progress: NonNullable<TaskInfo["progress"]> }) {
  const { current_symbol, symbol_index, total_symbols, fold_index, total_folds, best_score, best_model_type } = progress;
  const pct = total_symbols && symbol_index
    ? Math.round(((symbol_index - 1) + (fold_index && total_folds ? fold_index / total_folds : 0)) / total_symbols * 100)
    : 0;

  return (
    <div className="border-t px-3 pb-3 pt-2 space-y-2">
      <div className="flex items-center justify-between text-xs">
        <span className="text-muted-foreground">
          Training <span className="font-mono font-medium text-foreground">{current_symbol}</span>
          {symbol_index && total_symbols && (
            <span className="ml-1">({symbol_index}/{total_symbols} stocks)</span>
          )}
          {fold_index && total_folds && (
            <span className="ml-1">· fold {fold_index}/{total_folds}</span>
          )}
        </span>
        <span className="font-mono tabular-nums text-muted-foreground">{pct}%</span>
      </div>
      <div className="h-1.5 w-full rounded-full bg-muted overflow-hidden">
        <div
          className="h-full rounded-full bg-blue-500 transition-all duration-500"
          style={{ width: `${pct}%` }}
        />
      </div>
      {best_score != null && best_score > 0 && (
        <div className="text-xs text-muted-foreground">
          Best so far: <span className="font-mono text-foreground">{best_model_type}</span> F1={best_score.toFixed(4)}
        </div>
      )}
    </div>
  );
}

function TrackedTaskRow({
  taskId,
  onRetry,
  onCancel,
}: {
  taskId: string;
  onRetry: (id: string) => void;
  onCancel: (id: string) => void;
}) {
  const [info, setInfo] = useState<TaskInfo | null>(null);
  const [polling, setPolling] = useState(true);

  useEffect(() => {
    let timer: ReturnType<typeof setInterval>;
    const poll = async () => {
      try {
        const data = await api.tasks.get(taskId);
        setInfo(data);
        if (data.status === "SUCCESS" || data.status === "FAILURE" || data.status === "REVOKED") {
          setPolling(false);
        }
      } catch {
        // ignore poll errors
      }
    };
    poll();
    if (polling) {
      timer = setInterval(poll, 2000);
    }
    return () => clearInterval(timer);
  }, [taskId, polling]);

  if (!info) {
    return (
      <div className="flex items-center gap-3 rounded-lg border p-3">
        <StatusDot status="PENDING" />
        <span className="text-sm text-muted-foreground">Starting...</span>
        <StatusBadge status="PENDING" />
      </div>
    );
  }

  const displayStatus = info.status === "SUCCESS" && hasResultErrors(info.result ?? undefined) ? "WARNING" : info.status;
  const isTraining = info.progress && (info.status === "PROGRESS" || info.status === "STARTED");

  return (
    <div className="rounded-lg border">
      <div className="flex items-center justify-between p-3">
        <div className="flex items-center gap-3 min-w-0 flex-1">
          <StatusDot status={displayStatus === "PROGRESS" ? "STARTED" : displayStatus} />
          <div className="min-w-0">
            <TaskName name={info.name || "task"} />
            <div className="text-xs text-muted-foreground mt-0.5">
              {info.error && <span className="text-red-400">{info.error}</span>}
              {info.result && info.status === "SUCCESS" && (
                <span className={`break-all ${displayStatus === "WARNING" ? "text-yellow-400" : "text-green-400"}`}>
                  {formatResult(info.result)}
                </span>
              )}
            </div>
          </div>
        </div>
        <div className="flex items-center gap-2 shrink-0">
          <StatusBadge status={displayStatus === "PROGRESS" ? "STARTED" : displayStatus} />
          {info.status === "FAILURE" && (
            <Button
              variant="outline"
              size="sm"
              className="h-7 px-2 text-xs"
              onClick={() => onRetry(taskId)}
            >
              Retry
            </Button>
          )}
          {(info.status === "PENDING" || info.status === "STARTED" || info.status === "PROGRESS") && (
            <Button
              variant="destructive"
              size="sm"
              className="h-7 px-2 text-xs"
              onClick={() => onCancel(taskId)}
            >
              Cancel
            </Button>
          )}
        </div>
      </div>
      {isTraining && info.progress && (
        <TrainingProgress progress={info.progress} />
      )}
    </div>
  );
}

function ScheduleRow({
  task,
  onUpdated,
}: {
  task: ScheduledTask;
  onUpdated: () => void;
}) {
  const [editing, setEditing] = useState(false);
  const [saving, setSaving] = useState(false);
  const [intervalMin, setIntervalMin] = useState("");
  const [scheduleType, setScheduleType] = useState<"interval" | "crontab">("interval");
  const [cronMinute, setCronMinute] = useState("0");
  const [cronHour, setCronHour] = useState("*");
  const [cronDow, setCronDow] = useState("*");

  const startEdit = () => {
    // Pre-fill from current schedule
    const secs = Number(task.schedule);
    if (!isNaN(secs) && secs > 0) {
      setScheduleType("interval");
      setIntervalMin(String(Math.round(secs / 60)));
    } else {
      setScheduleType("crontab");
      // Parse crontab string
      const cronMatch = task.schedule.match(/<crontab:\s*([^(]+)\(/);
      if (cronMatch) {
        const parts = cronMatch[1].trim().split(/\s+/);
        setCronMinute(parts[0] || "0");
        setCronHour(parts[1] || "*");
        setCronDow(parts[4] || "*");
      }
    }
    setEditing(true);
  };

  const handleToggle = async () => {
    setSaving(true);
    try {
      await api.tasks.updateSchedule(task.key, { enabled: !task.enabled });
      onUpdated();
    } catch {
      // ignore
    } finally {
      setSaving(false);
    }
  };

  const handleSave = async () => {
    setSaving(true);
    try {
      if (scheduleType === "interval") {
        const mins = parseInt(intervalMin, 10);
        if (isNaN(mins) || mins < 1) return;
        await api.tasks.updateSchedule(task.key, {
          enabled: task.enabled,
          interval_seconds: mins * 60,
        });
      } else {
        await api.tasks.updateSchedule(task.key, {
          enabled: task.enabled,
          crontab: { minute: cronMinute, hour: cronHour, day_of_week: cronDow },
        });
      }
      setEditing(false);
      onUpdated();
    } catch {
      // ignore
    } finally {
      setSaving(false);
    }
  };

  const handleReset = async () => {
    setSaving(true);
    try {
      await api.tasks.resetSchedule(task.key);
      setEditing(false);
      onUpdated();
    } catch {
      // ignore
    } finally {
      setSaving(false);
    }
  };

  return (
    <>
      <tr className={`border-b last:border-0 ${!task.enabled ? "opacity-50" : ""}`}>
        <td className="p-3">
          <button
            onClick={handleToggle}
            disabled={saving}
            className={`h-4 w-8 rounded-full transition-colors relative ${task.enabled ? "bg-green-500" : "bg-muted-foreground/30"}`}
            title={task.enabled ? "Disable" : "Enable"}
          >
            <span className={`absolute top-0.5 h-3 w-3 rounded-full bg-white transition-transform ${task.enabled ? "left-4" : "left-0.5"}`} />
          </button>
        </td>
        <td className="p-3 font-mono text-xs">{task.name}</td>
        <td className="p-3 text-xs text-muted-foreground">{formatSchedule(task.schedule)}</td>
        <td className="p-3 text-xs text-muted-foreground">
          {task.last_run
            ? new Date(task.last_run).toLocaleString(undefined, {
                month: "short", day: "numeric", hour: "2-digit", minute: "2-digit",
              })
            : "\u2014"}
        </td>
        <td className="p-3 text-xs text-right tabular-nums text-muted-foreground">
          {task.total_run_count ?? "\u2014"}
        </td>
        <td className="p-3 text-right">
          <Button variant="ghost" size="sm" className="h-7 px-2 text-xs" onClick={startEdit}>
            Edit
          </Button>
        </td>
      </tr>
      {editing && (
        <tr className="border-b last:border-0 bg-muted/30">
          <td colSpan={6} className="p-4">
            <div className="flex flex-col gap-3 max-w-lg">
              <div className="flex gap-4 text-xs">
                <label className="flex items-center gap-1.5">
                  <input
                    type="radio"
                    name={`type-${task.key}`}
                    checked={scheduleType === "interval"}
                    onChange={() => setScheduleType("interval")}
                    className="accent-primary"
                  />
                  Interval
                </label>
                <label className="flex items-center gap-1.5">
                  <input
                    type="radio"
                    name={`type-${task.key}`}
                    checked={scheduleType === "crontab"}
                    onChange={() => setScheduleType("crontab")}
                    className="accent-primary"
                  />
                  Crontab
                </label>
              </div>

              {scheduleType === "interval" ? (
                <div className="flex items-center gap-2">
                  <label className="text-xs text-muted-foreground">Every</label>
                  <input
                    type="number"
                    min={1}
                    value={intervalMin}
                    onChange={(e) => setIntervalMin(e.target.value)}
                    className="w-20 rounded border bg-background px-2 py-1 text-xs"
                  />
                  <span className="text-xs text-muted-foreground">minutes</span>
                </div>
              ) : (
                <div className="flex flex-wrap items-center gap-3 text-xs">
                  <div className="flex items-center gap-1">
                    <label className="text-muted-foreground">Minute:</label>
                    <input
                      value={cronMinute}
                      onChange={(e) => setCronMinute(e.target.value)}
                      className="w-16 rounded border bg-background px-2 py-1"
                      placeholder="0"
                    />
                  </div>
                  <div className="flex items-center gap-1">
                    <label className="text-muted-foreground">Hour:</label>
                    <input
                      value={cronHour}
                      onChange={(e) => setCronHour(e.target.value)}
                      className="w-16 rounded border bg-background px-2 py-1"
                      placeholder="9-16"
                    />
                  </div>
                  <div className="flex items-center gap-1">
                    <label className="text-muted-foreground">Day:</label>
                    <input
                      value={cronDow}
                      onChange={(e) => setCronDow(e.target.value)}
                      className="w-20 rounded border bg-background px-2 py-1"
                      placeholder="mon-fri"
                    />
                  </div>
                </div>
              )}

              <div className="flex items-center gap-2">
                <Button size="sm" className="h-7 px-3 text-xs" onClick={handleSave} disabled={saving}>
                  {saving ? "Saving..." : "Save"}
                </Button>
                <Button variant="outline" size="sm" className="h-7 px-3 text-xs" onClick={handleReset} disabled={saving}>
                  Reset to Default
                </Button>
                <Button variant="ghost" size="sm" className="h-7 px-2 text-xs" onClick={() => setEditing(false)}>
                  Cancel
                </Button>
              </div>
            </div>
          </td>
        </tr>
      )}
    </>
  );
}

export default function TasksPage() {
  const [data, setData] = useState<TaskListResponse | null>(null);
  const [dataStatus, setDataStatus] = useState<DataStatusResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [cancelling, setCancelling] = useState<Record<string, boolean>>({});
  const [trackedIds, setTrackedIds] = useState<string[]>([]);
  const [triggering, setTriggering] = useState<Record<string, boolean>>({});
  const [triggerError, setTriggerError] = useState<Record<string, string>>({});


  const refreshDataStatus = useCallback(async () => {
    try {
      const result = await api.tasks.dataStatus();
      setDataStatus(result);
    } catch {
      // ignore
    }
  }, []);

  const refresh = useCallback(async () => {
    setRefreshing(true);
    try {
      const result = await api.tasks.list();
      setData(result);
      // Auto-track active retrain_model tasks for progress display
      const retrainTasks = (result.active || []).filter(
        (t) => t.name.includes("retrain_model")
      );
      if (retrainTasks.length > 0) {
        setTrackedIds((prev) => {
          const newIds = retrainTasks
            .map((t) => t.task_id)
            .filter((id) => !prev.includes(id));
          return newIds.length > 0 ? [...newIds, ...prev] : prev;
        });
      }
    } catch {
      // If tasks endpoint fails, show empty state
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useEffect(() => {
    // Load data status first (fast), then task list (slow)
    refreshDataStatus();
    refresh();
    const timer = setInterval(refresh, 5000);
    return () => clearInterval(timer);
  }, [refresh, refreshDataStatus]);

  const refreshAll = useCallback(() => {
    refresh();
  }, [refresh]);

  const handleCancel = async (taskId: string) => {
    setCancelling((p) => ({ ...p, [taskId]: true }));
    try {
      await api.tasks.cancel(taskId);
      setTimeout(refresh, 500);
    } catch {
      // ignore
    } finally {
      setCancelling((p) => ({ ...p, [taskId]: false }));
    }
  };

  const handleRetry = async (taskId: string) => {
    try {
      const result = await api.tasks.retry(taskId);
      if (result.success) {
        setTrackedIds((prev) => [result.task_id, ...prev]);
        setTimeout(refresh, 500);
      }
    } catch {
      // ignore
    }
  };

  // Also track tasks launched from this page
  const handleTrigger = async (
    label: string,
    action: () => Promise<{ task_id?: string }>
  ) => {
    setTriggering((p) => ({ ...p, [label]: true }));
    setTriggerError((p) => { const n = { ...p }; delete n[label]; return n; });
    try {
      const result = await action();
      if (result?.task_id) {
        setTrackedIds((prev) => [result.task_id as string, ...prev]);
      }
      setTimeout(() => { refresh(); refreshDataStatus(); }, 500);
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : "Failed to trigger";
      setTriggerError((p) => ({ ...p, [label]: msg }));
    } finally {
      setTriggering((p) => ({ ...p, [label]: false }));
    }
  };

  const activeTasks = data?.active || [];
  const reservedTasks = data?.reserved || [];
  const periodicTasks = data?.scheduled_periodic || [];
  const hasWork = activeTasks.length > 0 || reservedTasks.length > 0 || trackedIds.length > 0;

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-3xl font-bold tracking-tight">Tasks</h2>
          <p className="text-muted-foreground">
            Monitor, manage, and trigger background tasks
          </p>
        </div>
        <Button onClick={refresh} disabled={refreshing} size="sm">
          {refreshing ? "Refreshing..." : "Refresh"}
        </Button>
      </div>

      {/* Quick actions */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Quick Actions</CardTitle>
          <CardDescription>Trigger tasks — progress appears immediately below</CardDescription>
        </CardHeader>
        <CardContent>
          <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
            {[
              { label: "Discovery", desc: "Screen market movers & technicals, AI picks stocks for watchlist", action: () => api.discovery.trigger() },
              { label: "Economic Data", desc: "Pull GDP, CPI, rates, VIX and other macro indicators from FRED", action: () => api.collection.trigger("economic") },
              { label: "Daily Bars", desc: "Fetch today's OHLCV bars for all watchlist stocks from Alpaca", action: () => api.collection.trigger("daily_bars") },
              { label: "Backfill Prices", desc: "Pull 5 years of historical price data for ML training (slow)", action: () => api.collection.trigger("backfill") },
              { label: "News", desc: "Collect latest news articles for watchlist stocks from Finnhub", action: () => api.collection.trigger("news") },
              { label: "SEC Filings", desc: "Pull recent 10-K, 10-Q, and 8-K filings from EDGAR", action: () => api.collection.trigger("filings") },
              { label: "News Sentiment", desc: "Claude AI scores unanalyzed news articles for sentiment", action: () => api.analysis.trigger("sentiment") },
              { label: "Filing Analysis", desc: "Claude AI analyzes SEC filings for risks and opportunities", action: () => api.analysis.trigger("filings") },
              { label: "Context Synthesis", desc: "Claude AI creates holistic per-stock analysis from all data sources", action: () => api.analysis.trigger("synthesis") },
              { label: "ML Signals", desc: "Run ML model to generate buy/sell/hold predictions for all watchlist stocks", action: () => api.ml.generateSignals() },
              { label: "Retrain ML", desc: "Retrain XGBoost/LightGBM models on latest price and feature data", action: () => api.ml.retrain() },
              { label: "Decision Cycle", desc: "Aggregate all signals, ask Claude for trade recommendations, create proposals", action: () => api.trades.runDecisionCycle() },
            ].map((t) => (
              <div key={t.label} className="flex items-center justify-between rounded-lg border p-3">
                <div className="min-w-0 flex-1">
                  <p className="text-sm font-medium">{t.label}</p>
                  <p className="text-xs text-muted-foreground">{t.desc}</p>
                  {triggerError[t.label] && (
                    <p className="text-xs text-red-500 mt-0.5">{triggerError[t.label]}</p>
                  )}
                </div>
                <Button
                  variant="outline"
                  size="sm"
                  className={`ml-2 shrink-0 ${triggerError[t.label] ? "border-red-500/50 text-red-500" : ""}`}
                  disabled={!!triggering[t.label]}
                  onClick={() => handleTrigger(t.label, t.action as () => Promise<{ task_id?: string }>)}
                >
                  {triggering[t.label] ? "Starting…" : "Run"}
                </Button>
              </div>
            ))}
          </div>
        </CardContent>
      </Card>

      {/* Active & Queued tasks */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">
            Active & Queued
            {hasWork && (
              <span className="ml-2 text-xs font-normal text-muted-foreground">
                {activeTasks.length} running, {reservedTasks.length} queued
              </span>
            )}
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-2">
          {loading && !data && (
            <p className="text-sm text-muted-foreground py-4 text-center">
              Checking worker status...
            </p>
          )}
          {!loading && !hasWork && (
            <p className="text-sm text-muted-foreground py-4 text-center">
              No active tasks. Use Quick Actions above to trigger tasks.
            </p>
          )}

          {/* Tasks currently executing on workers */}
          {activeTasks.map((t) => (
            <ActiveTaskRow
              key={t.task_id}
              task={t}
              onCancel={handleCancel}
              cancelling={!!cancelling[t.task_id]}
            />
          ))}

          {/* Tasks queued on workers */}
          {reservedTasks.map((t) => (
            <ActiveTaskRow
              key={t.task_id}
              task={t}
              onCancel={handleCancel}
              cancelling={!!cancelling[t.task_id]}
            />
          ))}

          {/* Tracked tasks by ID (from triggers on this page) */}
          {trackedIds
            .filter(
              (id) =>
                !activeTasks.some((t) => t.task_id === id) &&
                !reservedTasks.some((t) => t.task_id === id)
            )
            .map((id) => (
              <TrackedTaskRow
                key={id}
                taskId={id}
                onRetry={handleRetry}
                onCancel={handleCancel}
              />
            ))}
        </CardContent>
      </Card>

      {/* Data Status */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Data Status</CardTitle>
          <CardDescription>Current state of all data sources in the database</CardDescription>
        </CardHeader>
        <CardContent>
          {!dataStatus ? (
            <p className="text-sm text-muted-foreground py-2">Loading...</p>
          ) : (
            <div className="rounded-md border">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b bg-muted/50">
                    <th className="text-left p-3 font-medium">Source</th>
                    <th className="text-right p-3 font-medium">Rows</th>
                    <th className="text-left p-3 font-medium">Latest Data</th>
                    <th className="text-left p-3 font-medium">Details</th>
                  </tr>
                </thead>
                <tbody>
                  {dataStatus.sources.map((s) => (
                    <tr key={s.name} className="border-b last:border-0">
                      <td className="p-3 font-medium">{s.name}</td>
                      <td className="p-3 text-right font-mono tabular-nums">
                        {s.rows.toLocaleString()}
                      </td>
                      <td className="p-3 text-xs text-muted-foreground">
                        {s.latest
                          ? new Date(s.latest).toLocaleDateString(undefined, {
                              month: "short",
                              day: "numeric",
                              year: "numeric",
                            })
                          : "—"}
                      </td>
                      <td className="p-3 text-xs text-muted-foreground">
                        {s.detail || "—"}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Scheduled periodic tasks */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Scheduled Tasks</CardTitle>
          <CardDescription>
            Celery Beat runs these automatically. Showing {periodicTasks.length} tasks.
            Toggle, edit, or reset schedules — changes apply automatically.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="rounded-md border">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b bg-muted/50">
                  <th className="w-8 p-3"></th>
                  <th className="text-left p-3 font-medium">Task</th>
                  <th className="text-left p-3 font-medium">Schedule</th>
                  <th className="text-left p-3 font-medium">Last Run</th>
                  <th className="text-right p-3 font-medium">Runs</th>
                  <th className="text-right p-3 font-medium">Actions</th>
                </tr>
              </thead>
              <tbody>
                {periodicTasks.map((t) => (
                  <ScheduleRow
                    key={t.key}
                    task={t}
                    onUpdated={refreshAll}
                  />
                ))}
                {periodicTasks.length === 0 && (
                  <tr>
                    <td colSpan={6} className="p-3 text-center text-muted-foreground">
                      No scheduled tasks found
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
