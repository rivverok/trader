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
import {
  api,
  type DataCollectionStatusResponse,
  type SnapshotListResponse,
} from "@/lib/api";
import { Database, Download, Play, Clock, BarChart3, Layers } from "lucide-react";

export default function DataCollectionPage() {
  const [status, setStatus] = useState<DataCollectionStatusResponse | null>(null);
  const [snapshots, setSnapshots] = useState<SnapshotListResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [triggering, setTriggering] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchData = async () => {
    try {
      const [s, snaps] = await Promise.all([
        api.dataCollection.status(),
        api.dataCollection.snapshots(),
      ]);
      setStatus(s);
      setSnapshots(snaps);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load data");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchData();
    const interval = setInterval(fetchData, 30000);
    return () => clearInterval(interval);
  }, []);

  const handleTriggerSnapshot = async () => {
    setTriggering(true);
    try {
      await api.dataCollection.triggerSnapshot();
      await fetchData();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to trigger snapshot");
    } finally {
      setTriggering(false);
    }
  };

  const handleExport = (format: "json" | "parquet") => {
    const baseUrl = process.env.NEXT_PUBLIC_API_URL || "/api";
    window.open(`${baseUrl}/data-collection/export?format=${format}`, "_blank");
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-[50vh]">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary" />
      </div>
    );
  }

  const coverageEntries = status?.coverage
    ? Object.entries(status.coverage).sort((a, b) => b[1] - a[1])
    : [];

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold">Data Collection</h1>
          <p className="text-muted-foreground mt-1">
            RL training data — state snapshots captured daily at market close
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Button
            variant="outline"
            size="sm"
            onClick={() => handleExport("json")}
            disabled={!status?.total_snapshots}
          >
            <Download className="h-4 w-4 mr-1" />
            JSON
          </Button>
          <Button
            variant="outline"
            size="sm"
            onClick={() => handleExport("parquet")}
            disabled={!status?.total_snapshots}
          >
            <Download className="h-4 w-4 mr-1" />
            Parquet
          </Button>
          <Button
            size="sm"
            onClick={handleTriggerSnapshot}
            disabled={triggering}
          >
            <Play className="h-4 w-4 mr-1" />
            {triggering ? "Capturing..." : "Capture Now"}
          </Button>
        </div>
      </div>

      {error && (
        <div className="rounded-lg border border-red-500/20 bg-red-500/5 p-4 text-sm text-red-500">
          {error}
        </div>
      )}

      {/* Stats cards */}
      <div className="grid gap-4 md:grid-cols-4">
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Total Snapshots</CardTitle>
            <Database className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">
              {status?.total_snapshots ?? 0}
            </div>
            <p className="text-xs text-muted-foreground">
              captured for RL training
            </p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Stock Coverage</CardTitle>
            <BarChart3 className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{coverageEntries.length}</div>
            <p className="text-xs text-muted-foreground">
              unique symbols tracked
            </p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Date Range</CardTitle>
            <Clock className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-sm font-bold">
              {status?.date_range?.first
                ? new Date(status.date_range.first).toLocaleDateString()
                : "—"}
            </div>
            <p className="text-xs text-muted-foreground">
              to{" "}
              {status?.date_range?.last
                ? new Date(status.date_range.last).toLocaleDateString()
                : "—"}
            </p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Latest Snapshot</CardTitle>
            <Layers className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-sm font-bold">
              {status?.latest_snapshot
                ? new Date(status.latest_snapshot.timestamp).toLocaleString()
                : "None"}
            </div>
            <p className="text-xs text-muted-foreground">
              {status?.latest_snapshot
                ? `${status.latest_snapshot.stock_count} stocks · ${status.latest_snapshot.snapshot_type}`
                : "No snapshots yet"}
            </p>
          </CardContent>
        </Card>
      </div>

      {/* Coverage breakdown */}
      {coverageEntries.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle>Stock Coverage</CardTitle>
            <CardDescription>
              Number of snapshots per symbol
            </CardDescription>
          </CardHeader>
          <CardContent>
            <div className="flex flex-wrap gap-2">
              {coverageEntries.map(([symbol, count]) => (
                <div
                  key={symbol}
                  className="flex items-center gap-1.5 rounded-md border px-2.5 py-1 text-sm"
                >
                  <span className="font-medium">{symbol}</span>
                  <span className="text-muted-foreground text-xs">
                    {count}
                  </span>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      )}

      {/* Snapshots list */}
      <Card>
        <CardHeader>
          <CardTitle>Recent Snapshots</CardTitle>
          <CardDescription>
            {snapshots?.total ?? 0} total snapshots
          </CardDescription>
        </CardHeader>
        <CardContent>
          {snapshots?.snapshots.length ? (
            <div className="space-y-2">
              <div className="grid grid-cols-5 gap-4 text-xs font-medium text-muted-foreground px-3 pb-2">
                <span>ID</span>
                <span>Timestamp</span>
                <span>Type</span>
                <span>Stocks</span>
                <span>Portfolio Value</span>
              </div>
              {snapshots.snapshots.map((snap) => (
                <div
                  key={snap.id}
                  className="grid grid-cols-5 gap-4 rounded-md border px-3 py-2 text-sm"
                >
                  <span className="font-mono text-muted-foreground">
                    #{snap.id}
                  </span>
                  <span>
                    {new Date(snap.timestamp).toLocaleString()}
                  </span>
                  <span className="capitalize">{snap.snapshot_type.replace("_", " ")}</span>
                  <span>{snap.stock_count}</span>
                  <span>
                    {snap.portfolio_value != null
                      ? `$${snap.portfolio_value.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
                      : "—"}
                  </span>
                </div>
              ))}
            </div>
          ) : (
            <p className="text-sm text-muted-foreground py-8 text-center">
              No snapshots yet. Click &quot;Capture Now&quot; to take the first snapshot,
              or wait for the daily scheduled capture at 4:05 PM ET.
            </p>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
