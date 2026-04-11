"use client";

import { useEffect, useState } from "react";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { api, type ServiceCheck, type ServiceStatusResponse } from "@/lib/api";

function StatusIcon({ status }: { status: string }) {
  if (status === "ok") {
    return <div className="h-3 w-3 rounded-full bg-green-500" title="Connected" />;
  }
  if (status === "not_configured") {
    return <div className="h-3 w-3 rounded-full bg-yellow-500" title="Not configured" />;
  }
  return <div className="h-3 w-3 rounded-full bg-red-500" title="Error" />;
}

function StatusBadge({ status }: { status: string }) {
  const styles: Record<string, string> = {
    ok: "bg-green-500/10 text-green-500 border-green-500/30",
    error: "bg-red-500/10 text-red-500 border-red-500/30",
    not_configured: "bg-yellow-500/10 text-yellow-500 border-yellow-500/30",
  };
  const labels: Record<string, string> = {
    ok: "Connected",
    error: "Error",
    not_configured: "Not Configured",
  };
  return (
    <span className={`rounded-full border px-2.5 py-0.5 text-xs font-medium ${styles[status] || styles.error}`}>
      {labels[status] || status}
    </span>
  );
}

function ServiceCard({ service }: { service: ServiceCheck }) {
  const [expanded, setExpanded] = useState(false);
  const hasDetails = service.details && Object.keys(service.details).length > 0;

  return (
    <div
      className={`rounded-lg border p-4 ${
        service.status === "ok"
          ? "border-green-500/20"
          : service.status === "not_configured"
          ? "border-yellow-500/20 bg-yellow-500/5"
          : "border-red-500/20 bg-red-500/5"
      }`}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="flex items-center gap-3 min-w-0">
          <StatusIcon status={service.status} />
          <div className="min-w-0">
            <h3 className="text-sm font-semibold">{service.name}</h3>
            <p className="text-xs text-muted-foreground mt-0.5 break-words">{service.message}</p>
          </div>
        </div>
        <div className="flex items-center gap-2 shrink-0">
          <StatusBadge status={service.status} />
          {hasDetails && (
            <Button
              variant="ghost"
              size="sm"
              className="h-6 px-2 text-xs"
              onClick={() => setExpanded(!expanded)}
            >
              {expanded ? "Hide" : "Details"}
            </Button>
          )}
        </div>
      </div>
      {expanded && hasDetails && (
        <div className="mt-3 rounded-md bg-muted/50 p-3">
          <dl className="grid grid-cols-2 gap-x-4 gap-y-1 text-xs">
            {Object.entries(service.details!).map(([key, value]) => (
              <div key={key} className="contents">
                <dt className="text-muted-foreground font-medium">{key.replace(/_/g, " ")}</dt>
                <dd className="font-mono">{String(value)}</dd>
              </div>
            ))}
          </dl>
        </div>
      )}
    </div>
  );
}

export default function StatusPage() {
  const [data, setData] = useState<ServiceStatusResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [checking, setChecking] = useState(false);
  const [lastChecked, setLastChecked] = useState<Date | null>(null);

  const checkServices = async () => {
    setChecking(true);
    try {
      const result = await api.status.services();
      setData(result);
      setLastChecked(new Date());
    } catch {
      // If even the status endpoint fails, show minimal error
      setData({
        overall: "error",
        services: [
          { name: "API Server", status: "error", message: "Cannot reach the backend API", details: null },
        ],
      });
    } finally {
      setLoading(false);
      setChecking(false);
    }
  };

  useEffect(() => {
    checkServices();
  }, []);

  const overallStyles: Record<string, { bg: string; text: string; label: string }> = {
    ok: { bg: "bg-green-500/10 border-green-500/30", text: "text-green-500", label: "All Systems Operational" },
    degraded: { bg: "bg-yellow-500/10 border-yellow-500/30", text: "text-yellow-500", label: "Some Services Need Configuration" },
    error: { bg: "bg-red-500/10 border-red-500/30", text: "text-red-500", label: "Service Issues Detected" },
  };

  if (loading) {
    return (
      <div className="flex h-64 items-center justify-center">
        <div className="flex flex-col items-center gap-2">
          <div className="h-6 w-6 animate-spin rounded-full border-2 border-primary border-t-transparent" />
          <p className="text-muted-foreground">Checking services...</p>
        </div>
      </div>
    );
  }

  const overall = overallStyles[data?.overall || "error"] || overallStyles.error;
  const infrastructure = data?.services.filter((s) =>
    ["API Server", "PostgreSQL", "Redis", "Celery Workers"].includes(s.name)
  ) || [];
  const external = data?.services.filter((s) =>
    !["API Server", "PostgreSQL", "Redis", "Celery Workers"].includes(s.name)
  ) || [];

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-3xl font-bold tracking-tight">Service Status</h2>
          <p className="text-muted-foreground">
            Connection status for all external services and infrastructure
          </p>
        </div>
        <div className="flex items-center gap-3">
          {lastChecked && (
            <span className="text-xs text-muted-foreground">
              Last checked: {lastChecked.toLocaleTimeString()}
            </span>
          )}
          <Button onClick={checkServices} disabled={checking} size="sm">
            {checking ? "Checking..." : "Refresh"}
          </Button>
        </div>
      </div>

      {/* Overall status banner */}
      <Card className={`${overall.bg} border`}>
        <CardContent className="flex items-center gap-3 py-4">
          <div className={`text-2xl font-bold ${overall.text}`}>
            {data?.overall === "ok" ? "●" : data?.overall === "degraded" ? "◐" : "○"}
          </div>
          <div>
            <p className={`text-lg font-semibold ${overall.text}`}>{overall.label}</p>
            <p className="text-sm text-muted-foreground">
              {data?.services.filter((s) => s.status === "ok").length} of {data?.services.length} services connected
            </p>
          </div>
        </CardContent>
      </Card>

      {/* Infrastructure */}
      <Card>
        <CardHeader>
          <CardTitle>Infrastructure</CardTitle>
          <CardDescription>
            Core services that must be running for the platform to operate
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-3">
          {infrastructure.map((s) => (
            <ServiceCard key={s.name} service={s} />
          ))}
        </CardContent>
      </Card>

      {/* External Services */}
      <Card>
        <CardHeader>
          <CardTitle>External Services</CardTitle>
          <CardDescription>
            API connections for trading, AI analysis, and data collection.
            Services marked &quot;Not Configured&quot; need API keys added to your .env file.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-3">
          {external.map((s) => (
            <ServiceCard key={s.name} service={s} />
          ))}
        </CardContent>
      </Card>

      {/* Help text for not-configured services */}
      {data?.services.some((s) => s.status === "not_configured") && (
        <Card className="border-dashed">
          <CardHeader>
            <CardTitle className="text-base">Setup Guide</CardTitle>
          </CardHeader>
          <CardContent className="space-y-2 text-sm text-muted-foreground">
            <p>Services marked &quot;Not Configured&quot; need API keys in your <code className="rounded bg-muted px-1 py-0.5">.env</code> file:</p>
            <ul className="list-disc pl-5 space-y-1">
              {data.services.some((s) => s.name.includes("Alpaca") && s.status === "not_configured") && (
                <li><strong>Alpaca</strong>: Sign up at <code>alpaca.markets</code> → set <code>ALPACA_API_KEY</code> and <code>ALPACA_SECRET_KEY</code></li>
              )}
              {data.services.some((s) => s.name.includes("Claude") && s.status === "not_configured") && (
                <li><strong>Anthropic</strong>: Get a key at <code>console.anthropic.com</code> → set <code>ANTHROPIC_API_KEY</code></li>
              )}
              {data.services.some((s) => s.name.includes("Finnhub") && s.status === "not_configured") && (
                <li><strong>Finnhub</strong>: Free key at <code>finnhub.io</code> → set <code>FINNHUB_API_KEY</code></li>
              )}
              {data.services.some((s) => s.name.includes("FRED") && s.status === "not_configured") && (
                <li><strong>FRED</strong>: Free key at <code>fred.stlouisfed.org</code> → set <code>FRED_API_KEY</code></li>
              )}
              {data.services.some((s) => s.name.includes("EDGAR") && s.status === "not_configured") && (
                <li><strong>SEC EDGAR</strong>: No key needed — set <code>SEC_EDGAR_USER_AGENT</code> to <code>&quot;YourName your@email.com&quot;</code></li>
              )}
            </ul>
            <p className="mt-2">After updating <code>.env</code>, restart with: <code>docker compose restart api worker scheduler</code></p>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
