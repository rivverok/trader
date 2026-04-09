"use client";

import { useEffect, useState } from "react";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import {
  api,
  type PerformanceMetrics,
  type AttributionData,
} from "@/lib/api";

function fmt(n: number, decimals = 2): string {
  return n.toFixed(decimals);
}

function fmtDollar(n: number): string {
  return n >= 0
    ? `$${n.toFixed(2)}`
    : `-$${Math.abs(n).toFixed(2)}`;
}

function pctColor(val: number): string {
  if (val > 0) return "text-green-500";
  if (val < 0) return "text-red-500";
  return "text-muted-foreground";
}

export default function AnalyticsPage() {
  const [performance, setPerformance] = useState<PerformanceMetrics | null>(null);
  const [attribution, setAttribution] = useState<AttributionData | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.analytics.performance().then(setPerformance).catch((e) => setError(e.message));
    api.analytics.attribution().then(setAttribution).catch((e) => setError(e.message));
  }, []);

  return (
    <div className="space-y-8">
      <div>
        <h2 className="text-3xl font-bold tracking-tight">Analytics</h2>
        <p className="text-muted-foreground">
          Trade performance metrics and signal attribution
        </p>
      </div>

      {error && (
        <div className="rounded-md bg-destructive/10 p-4 text-destructive text-sm">
          {error}
        </div>
      )}

      {/* ── Key Metrics ───────────────────────────────────────── */}
      {performance && (
        <>
          <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
            <Card>
              <CardHeader className="pb-2">
                <CardDescription>Total P&L</CardDescription>
                <CardTitle className={pctColor(performance.total_pnl)}>
                  {fmtDollar(performance.total_pnl)}
                </CardTitle>
              </CardHeader>
            </Card>
            <Card>
              <CardHeader className="pb-2">
                <CardDescription>Win Rate</CardDescription>
                <CardTitle>
                  {fmt(performance.win_rate * 100, 1)}%
                  <span className="text-sm font-normal text-muted-foreground ml-2">
                    ({performance.winning_trades}W / {performance.losing_trades}L)
                  </span>
                </CardTitle>
              </CardHeader>
            </Card>
            <Card>
              <CardHeader className="pb-2">
                <CardDescription>Sharpe Ratio</CardDescription>
                <CardTitle>{fmt(performance.sharpe_ratio)}</CardTitle>
              </CardHeader>
            </Card>
            <Card>
              <CardHeader className="pb-2">
                <CardDescription>Max Drawdown</CardDescription>
                <CardTitle className="text-red-500">
                  {fmt(performance.max_drawdown_pct, 1)}%
                </CardTitle>
              </CardHeader>
            </Card>
          </div>

          <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
            <Card>
              <CardHeader className="pb-2">
                <CardDescription>Total Trades</CardDescription>
                <CardTitle>{performance.total_trades}</CardTitle>
              </CardHeader>
            </Card>
            <Card>
              <CardHeader className="pb-2">
                <CardDescription>Profit Factor</CardDescription>
                <CardTitle>{fmt(performance.profit_factor)}</CardTitle>
              </CardHeader>
            </Card>
            <Card>
              <CardHeader className="pb-2">
                <CardDescription>Avg Return</CardDescription>
                <CardTitle className={pctColor(performance.avg_return_pct)}>
                  {fmt(performance.avg_return_pct, 2)}%
                </CardTitle>
              </CardHeader>
            </Card>
            <Card>
              <CardHeader className="pb-2">
                <CardDescription>Calmar Ratio</CardDescription>
                <CardTitle>{fmt(performance.calmar_ratio)}</CardTitle>
              </CardHeader>
            </Card>
          </div>

          {/* ── Equity Curve ─────────────────────────────────── */}
          {performance.equity_curve.length > 1 && (
            <Card>
              <CardHeader>
                <CardTitle>Equity Curve</CardTitle>
                <CardDescription>Portfolio value over time</CardDescription>
              </CardHeader>
              <CardContent>
                <div className="h-64 flex items-end gap-px">
                  {(() => {
                    const pts = performance.equity_curve;
                    const min = Math.min(...pts.map((p) => p.value));
                    const max = Math.max(...pts.map((p) => p.value));
                    const range = max - min || 1;
                    // Sample at most 120 bars
                    const step = Math.max(1, Math.floor(pts.length / 120));
                    const sampled = pts.filter((_, i) => i % step === 0);
                    return sampled.map((p, i) => {
                      const pct = ((p.value - min) / range) * 100;
                      const isGain =
                        p.value >= (sampled[i - 1]?.value ?? p.value);
                      return (
                        <div
                          key={i}
                          className={`flex-1 rounded-t ${isGain ? "bg-green-500" : "bg-red-500"}`}
                          style={{ height: `${Math.max(pct, 2)}%` }}
                          title={`${p.timestamp.slice(0, 10)}: ${fmtDollar(p.value)}`}
                        />
                      );
                    });
                  })()}
                </div>
              </CardContent>
            </Card>
          )}

          {/* ── Monthly Returns Heatmap ──────────────────────── */}
          {Object.keys(performance.monthly_returns).length > 0 && (
            <Card>
              <CardHeader>
                <CardTitle>Monthly Returns</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="grid grid-cols-6 gap-2">
                  {Object.entries(performance.monthly_returns)
                    .sort(([a], [b]) => a.localeCompare(b))
                    .map(([month, ret]) => (
                      <div
                        key={month}
                        className={`rounded p-3 text-center text-sm font-medium ${
                          ret > 0
                            ? "bg-green-500/20 text-green-400"
                            : ret < 0
                              ? "bg-red-500/20 text-red-400"
                              : "bg-muted text-muted-foreground"
                        }`}
                      >
                        <div className="text-xs opacity-70">{month}</div>
                        <div>{fmt(ret, 1)}%</div>
                      </div>
                    ))}
                </div>
              </CardContent>
            </Card>
          )}
        </>
      )}

      {/* ── Signal Attribution ────────────────────────────────── */}
      {attribution && (
        <Card>
          <CardHeader>
            <CardTitle>Signal Attribution</CardTitle>
            <CardDescription>
              P&L breakdown by signal source (ML model, Claude analysis, analyst input)
            </CardDescription>
          </CardHeader>
          <CardContent>
            <div className="grid gap-6 md:grid-cols-3">
              {(["ml", "claude", "analyst"] as const).map((source) => {
                const d = attribution[source];
                return (
                  <div key={source} className="space-y-2 rounded-lg border p-4">
                    <h4 className="text-lg font-semibold capitalize">{source}</h4>
                    <div className="grid grid-cols-2 gap-y-1 text-sm">
                      <span className="text-muted-foreground">Trades</span>
                      <span className="text-right">{d.total_trades}</span>
                      <span className="text-muted-foreground">Win Rate</span>
                      <span className="text-right">{fmt(d.win_rate * 100, 1)}%</span>
                      <span className="text-muted-foreground">Total P&L</span>
                      <span className={`text-right ${pctColor(d.total_pnl)}`}>
                        {fmtDollar(d.total_pnl)}
                      </span>
                      <span className="text-muted-foreground">Avg P&L</span>
                      <span className={`text-right ${pctColor(d.avg_pnl)}`}>
                        {fmtDollar(d.avg_pnl)}
                      </span>
                      <span className="text-muted-foreground">Gross Profit</span>
                      <span className="text-right text-green-500">
                        {fmtDollar(d.gross_profit)}
                      </span>
                      <span className="text-muted-foreground">Gross Loss</span>
                      <span className="text-right text-red-500">
                        {fmtDollar(d.gross_loss)}
                      </span>
                    </div>
                  </div>
                );
              })}
            </div>
          </CardContent>
        </Card>
      )}

      {!performance && !error && (
        <div className="text-center text-muted-foreground py-12">
          Loading analytics…
        </div>
      )}
    </div>
  );
}
