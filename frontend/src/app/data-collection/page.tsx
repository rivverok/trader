"use client";

import { useEffect, useState } from "react";
import { api, type TrainingStatus } from "@/lib/api";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";

const TABLE_LABELS: Record<string, string> = {
  prices: "Price Bars",
  signals: "ML Signals",
  sentiment: "News Sentiment",
  synthesis: "Context Synthesis",
  economic: "Economic Indicators",
  portfolio: "Portfolio Snapshots",
};

function fmtNum(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}K`;
  return n.toLocaleString();
}

function fmtDate(iso: string | null): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
  });
}

function ProgressBar({
  pct,
  color,
  label,
}: {
  pct: number;
  color: string;
  label: string;
}) {
  return (
    <div className="space-y-1">
      <div className="flex justify-between text-xs">
        <span className="text-muted-foreground">{label}</span>
        <span className="font-medium">{pct}%</span>
      </div>
      <div className="h-2.5 w-full rounded-full bg-muted">
        <div
          className={`h-2.5 rounded-full transition-all ${color}`}
          style={{ width: `${Math.min(100, pct)}%` }}
        />
      </div>
    </div>
  );
}

export default function DataCollectionPage() {
  const [data, setData] = useState<TrainingStatus | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const refresh = () => {
    setLoading(true);
    api.training
      .status()
      .then(setData)
      .catch((e) => setError(e instanceof Error ? e.message : "Failed to load"))
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    refresh();
    const timer = setInterval(refresh, 30_000);
    return () => clearInterval(timer);
  }, []);

  if (loading && !data)
    return (
      <div className="p-8 text-muted-foreground">Loading collection data...</div>
    );
  if (error)
    return <div className="p-8 text-red-400">Error: {error}</div>;
  if (!data) return null;

  const r = data.readiness;
  const stockSymbols = Object.keys(data.per_stock_signals).sort();

  return (
    <div className="space-y-6 p-6 md:p-8">
      <div>
        <h2 className="text-3xl font-bold tracking-tight">Data Collection</h2>
        <p className="text-muted-foreground">
          Collection progress and RL training readiness for{" "}
          {data.stock_count} watchlist stocks
        </p>
      </div>

      {/* ── Training Readiness ── */}
      <Card
        className={
          r.ready_recommended
            ? "border-green-500/50 bg-green-500/5"
            : r.ready_minimum
              ? "border-yellow-500/50 bg-yellow-500/5"
              : ""
        }
      >
        <CardHeader>
          <CardTitle className="text-xl">Training Readiness</CardTitle>
          <CardDescription>
            {r.ready_recommended
              ? "Recommended data threshold reached — ready to train a strong model"
              : r.ready_minimum
                ? "Minimum data reached — can start experimental training"
                : `Collecting data — ${r.current_days} of ${r.min_days_target} trading days (minimum)`}
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
            <div>
              <div className="text-sm text-muted-foreground">Collection Started</div>
              <div className="text-lg font-semibold">
                {fmtDate(r.collection_start)}
              </div>
            </div>
            <div>
              <div className="text-sm text-muted-foreground">Trading Days</div>
              <div className="text-lg font-semibold">{r.current_days}</div>
            </div>
            <div>
              <div className="text-sm text-muted-foreground">Binding Constraint</div>
              <div className="text-lg font-semibold capitalize">
                {r.binding_constraint ?? "—"}
              </div>
            </div>
            <div>
              <div className="text-sm text-muted-foreground">Status</div>
              <div
                className={`text-lg font-semibold ${
                  r.ready_recommended
                    ? "text-green-400"
                    : r.ready_minimum
                      ? "text-yellow-400"
                      : "text-blue-400"
                }`}
              >
                {r.ready_recommended
                  ? "Ready"
                  : r.ready_minimum
                    ? "Minimum Met"
                    : "Collecting"}
              </div>
            </div>
          </div>

          <ProgressBar
            pct={r.pct_to_minimum}
            color="bg-yellow-500"
            label={`Minimum viable (${r.min_days_target} days / ~3 months)`}
          />
          <ProgressBar
            pct={r.pct_to_recommended}
            color="bg-green-500"
            label={`Recommended (${r.good_days_target} days / ~6 months)`}
          />

          {/* Target dates */}
          {(!r.ready_minimum || !r.ready_recommended) && (
            <div className="mt-2 grid grid-cols-1 gap-3 rounded-md border border-muted bg-muted/30 p-4 md:grid-cols-2">
              {!r.ready_minimum && r.est_minimum_date && (
                <div>
                  <div className="text-xs text-muted-foreground">
                    Estimated minimum ready
                  </div>
                  <div className="text-sm font-semibold text-yellow-400">
                    {fmtDate(r.est_minimum_date)}
                  </div>
                </div>
              )}
              {!r.ready_recommended && r.est_recommended_date && (
                <div>
                  <div className="text-xs text-muted-foreground">
                    Estimated recommended ready
                  </div>
                  <div className="text-sm font-semibold text-green-400">
                    {fmtDate(r.est_recommended_date)}
                  </div>
                </div>
              )}
            </div>
          )}

          {/* Per-feature day breakdown */}
          <div className="mt-2">
            <div className="text-sm font-medium text-muted-foreground mb-2">
              Days per feature type
            </div>
            <div className="grid grid-cols-2 gap-2 md:grid-cols-4">
              {Object.entries(r.feature_days).map(([key, days]) => (
                <div
                  key={key}
                  className={`rounded-md border px-3 py-2 text-center ${
                    key === r.binding_constraint
                      ? "border-yellow-500/50 bg-yellow-500/5"
                      : ""
                  }`}
                >
                  <div className="text-xs text-muted-foreground capitalize">
                    {key}
                  </div>
                  <div className="text-lg font-bold">{days}</div>
                </div>
              ))}
            </div>
          </div>
        </CardContent>
      </Card>

      {/* ── Data Tables ── */}
      <Card>
        <CardHeader>
          <CardTitle className="text-xl">Data Inventory</CardTitle>
          <CardDescription>Row counts and date ranges per table</CardDescription>
        </CardHeader>
        <CardContent>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b text-left text-muted-foreground">
                  <th className="pb-2 pr-4 font-medium">Table</th>
                  <th className="pb-2 pr-4 font-medium text-right">Rows</th>
                  <th className="pb-2 pr-4 font-medium">First Record</th>
                  <th className="pb-2 pr-4 font-medium">Last Record</th>
                  <th className="pb-2 font-medium text-right">Trading Days</th>
                </tr>
              </thead>
              <tbody>
                {Object.entries(data.tables).map(([key, t]) => (
                  <tr key={key} className="border-b border-muted/50">
                    <td className="py-2 pr-4 font-medium">
                      {TABLE_LABELS[key] ?? key}
                    </td>
                    <td className="py-2 pr-4 text-right tabular-nums">
                      {fmtNum(t.count)}
                    </td>
                    <td className="py-2 pr-4 text-muted-foreground">
                      {fmtDate(t.first)}
                    </td>
                    <td className="py-2 pr-4 text-muted-foreground">
                      {fmtDate(t.last)}
                    </td>
                    <td className="py-2 text-right tabular-nums">{t.trading_days}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </CardContent>
      </Card>

      {/* ── Per-Stock Coverage + Daily Rate ── */}
      <div className="grid gap-6 md:grid-cols-2">
        {/* Stock coverage */}
        <Card>
          <CardHeader>
            <CardTitle className="text-xl">Per-Stock Signals</CardTitle>
            <CardDescription>ML signal count per watchlist stock</CardDescription>
          </CardHeader>
          <CardContent>
            {stockSymbols.length === 0 ? (
              <p className="text-sm text-muted-foreground">
                No signals generated yet
              </p>
            ) : (
              <div className="grid grid-cols-2 gap-2">
                {stockSymbols.map((sym) => (
                  <div
                    key={sym}
                    className="flex items-center justify-between rounded-md border px-3 py-1.5"
                  >
                    <span className="font-mono text-sm font-medium">{sym}</span>
                    <span className="text-sm tabular-nums text-muted-foreground">
                      {data.per_stock_signals[sym]}
                    </span>
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>

        {/* Daily collection rate */}
        <Card>
          <CardHeader>
            <CardTitle className="text-xl">Daily Collection Rate</CardTitle>
            <CardDescription>Price bars collected per day (last 7 days)</CardDescription>
          </CardHeader>
          <CardContent>
            {data.daily_collection_rate.length === 0 ? (
              <p className="text-sm text-muted-foreground">
                No recent price data collected
              </p>
            ) : (
              <div className="space-y-2">
                {data.daily_collection_rate.map((d) => {
                  const maxCount = Math.max(
                    ...data.daily_collection_rate.map((x) => x.count)
                  );
                  const pct = maxCount > 0 ? (d.count / maxCount) * 100 : 0;
                  return (
                    <div key={d.date} className="space-y-0.5">
                      <div className="flex justify-between text-xs">
                        <span className="text-muted-foreground">
                          {new Date(d.date + "T00:00:00").toLocaleDateString(
                            "en-US",
                            { weekday: "short", month: "short", day: "numeric" }
                          )}
                        </span>
                        <span className="font-medium tabular-nums">
                          {fmtNum(d.count)}
                        </span>
                      </div>
                      <div className="h-1.5 w-full rounded-full bg-muted">
                        <div
                          className="h-1.5 rounded-full bg-blue-500 transition-all"
                          style={{ width: `${pct}%` }}
                        />
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
