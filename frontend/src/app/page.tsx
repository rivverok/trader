"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
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
  type HealthResponse,
  type Stock,
  type CollectionStatus,
  type StockAnalysis,
  type PortfolioResponse,
  type PortfolioSnapshot,
  type ExecutedTradeItem,
  type SystemStatus,
} from "@/lib/api";

export default function DashboardPage() {
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [stocks, setStocks] = useState<Stock[]>([]);
  const [collectionStatus, setCollectionStatus] = useState<CollectionStatus | null>(null);
  const [analyses, setAnalyses] = useState<Record<string, StockAnalysis>>({});
  const [portfolio, setPortfolio] = useState<PortfolioResponse | null>(null);
  const [portfolioError, setPortfolioError] = useState(false);
  const [history, setHistory] = useState<PortfolioSnapshot[]>([]);
  const [recentTrades, setRecentTrades] = useState<ExecutedTradeItem[]>([]);
  const [systemStatus, setSystemStatus] = useState<SystemStatus | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [newSymbol, setNewSymbol] = useState("");
  const [adding, setAdding] = useState(false);

  const refresh = () => {
    api.health().then(setHealth).catch((e) => setError(e.message));
    api.stocks.list(true).then((watchlist) => {
      setStocks(watchlist);
      const results: Record<string, StockAnalysis> = {};
      Promise.allSettled(
        watchlist.map((s) =>
          api.analysis.forStock(s.symbol).then((a) => {
            results[s.symbol] = a;
          })
        )
      ).then(() => setAnalyses(results));
    }).catch(() => {});
    api.collection.status().then(setCollectionStatus).catch(() => {});
    api.portfolio.get().then(setPortfolio).catch(() => {
      setPortfolioError(true);
      setPortfolio({ total_value: 0, cash: 0, positions_value: 0, daily_pnl: 0, cumulative_pnl: 0, buying_power: 0, positions: [], account_status: "unavailable" });
    });
    api.portfolio.history(30).then(setHistory).catch(() => {});
    api.portfolio.trades(undefined, 10).then(setRecentTrades).catch(() => {});
    api.system.status().then(setSystemStatus).catch(() => {});
  };

  useEffect(() => {
    refresh();
    const interval = setInterval(refresh, 30000); // refresh every 30s
    return () => clearInterval(interval);
  }, []);

  const addStock = async () => {
    if (!newSymbol.trim()) return;
    setAdding(true);
    try {
      await api.stocks.create(newSymbol.trim());
      setNewSymbol("");
      refresh();
    } catch (e: any) {
      setError(e.message);
    } finally {
      setAdding(false);
    }
  };

  return (
    <div className="space-y-8">
      <div>
        <h2 className="text-3xl font-bold tracking-tight">Dashboard</h2>
        <p className="text-muted-foreground">
          AI Trading Platform — Portfolio Overview
        </p>
      </div>

      {/* Portfolio overview + System status */}
      <div className="grid gap-4 md:grid-cols-4">
        <Card>
          <CardHeader className="pb-2">
            <CardDescription>Portfolio Value</CardDescription>
            <CardTitle className="text-2xl font-mono">
              {portfolio ? (
                portfolioError ? (
                  <span className="text-muted-foreground text-base">Not connected</span>
                ) : (
                  `$${portfolio.total_value.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
                )
              ) : (
                <span className="text-muted-foreground">Loading...</span>
              )}
            </CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-xs text-muted-foreground">
              {portfolio ? `Cash: $${portfolio.cash.toLocaleString(undefined, { minimumFractionDigits: 2 })}` : "—"}
            </p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2">
            <CardDescription>Daily P&L</CardDescription>
            <CardTitle className="text-2xl font-mono">
              {portfolio ? (
                <span className={portfolio.daily_pnl >= 0 ? "text-green-500" : "text-red-500"}>
                  {portfolio.daily_pnl >= 0 ? "+" : ""}${portfolio.daily_pnl.toFixed(2)}
                </span>
              ) : (
                <span className="text-muted-foreground">—</span>
              )}
            </CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-xs text-muted-foreground">
              {portfolio ? `Cumulative: ${portfolio.cumulative_pnl >= 0 ? "+" : ""}$${portfolio.cumulative_pnl.toFixed(2)}` : "—"}
            </p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2">
            <CardDescription>Positions</CardDescription>
            <CardTitle className="text-2xl">
              {portfolio ? portfolio.positions.length : "—"}
            </CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-xs text-muted-foreground">
              {portfolio ? `Value: $${portfolio.positions_value.toLocaleString(undefined, { minimumFractionDigits: 2 })}` : "—"}
            </p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2">
            <CardDescription>System</CardDescription>
            <CardTitle className="text-2xl">
              {systemStatus ? (
                systemStatus.trading_halted ? (
                  <span className="text-destructive">Halted</span>
                ) : systemStatus.trading_paused ? (
                  <span className="text-yellow-500">Paused</span>
                ) : (
                  <span className="text-green-500">Active</span>
                )
              ) : (
                <span className="text-muted-foreground">—</span>
              )}
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="flex items-center gap-2 text-xs text-muted-foreground">
              <span>Auto-execute: {systemStatus?.auto_execute ? "ON" : "OFF"}</span>
              {systemStatus?.autonomous_mode && <span>| <span className="text-primary font-medium">Autonomous</span></span>}
              {health && <span>| {health.trading_mode}</span>}
            </div>
          </CardContent>
        </Card>
      </div>

      {/* System controls */}
      {systemStatus && (
        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="text-base">System Controls</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="flex flex-wrap gap-3">
              {systemStatus.trading_paused ? (
                <Button size="sm" variant="default" onClick={() => api.system.resume().then(refresh)}>
                  Resume Trading
                </Button>
              ) : (
                <Button size="sm" variant="secondary" onClick={() => api.system.pause().then(refresh)}>
                  Pause Trading
                </Button>
              )}
              <Button
                size="sm"
                variant={systemStatus.auto_execute ? "secondary" : "default"}
                onClick={() => api.system.toggleAutoExecute(!systemStatus.auto_execute).then(refresh)}
              >
                {systemStatus.auto_execute ? "Disable Auto-Execute" : "Enable Auto-Execute"}
              </Button>
              <Button
                size="sm"
                variant={systemStatus.autonomous_mode ? "secondary" : "default"}
                onClick={() => api.system.toggleAutonomousMode(!systemStatus.autonomous_mode).then(refresh)}
              >
                {systemStatus.autonomous_mode ? "Disable Autonomous" : "Enable Autonomous"}
              </Button>
              <Button
                size="sm"
                variant="destructive"
                onClick={() => {
                  if (confirm("EMERGENCY STOP: This will close ALL positions and halt trading. Continue?")) {
                    api.system.emergencyStop().then(refresh);
                  }
                }}
              >
                Emergency Stop
              </Button>
              {systemStatus.trading_halted && (
                <Button size="sm" variant="outline" onClick={() => api.risk.resume().then(refresh)}>
                  Clear Halt
                </Button>
              )}
            </div>
            {systemStatus.trading_halted && systemStatus.halt_reason && (
              <p className="mt-2 text-sm text-destructive">{systemStatus.halt_reason}</p>
            )}
          </CardContent>
        </Card>
      )}

      {/* P&L Chart (simple text-based sparkline) */}
      {history.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle>Portfolio Value (30 days)</CardTitle>
            <CardDescription>
              {history.length} data points
            </CardDescription>
          </CardHeader>
          <CardContent>
            <div className="flex h-40 items-end gap-px">
              {(() => {
                const values = history.map((s) => s.total_value);
                const min = Math.min(...values);
                const max = Math.max(...values);
                const range = max - min || 1;
                // Sample ~60 bars max
                const step = Math.max(1, Math.floor(values.length / 60));
                const sampled = values.filter((_, i) => i % step === 0);
                return sampled.map((v, i) => {
                  const pct = ((v - min) / range) * 100;
                  const isLast = i === sampled.length - 1;
                  return (
                    <div
                      key={i}
                      className={`flex-1 rounded-t-sm ${isLast ? "bg-primary" : "bg-primary/40"}`}
                      style={{ height: `${Math.max(pct, 2)}%` }}
                      title={`$${v.toFixed(2)}`}
                    />
                  );
                });
              })()}
            </div>
            <div className="mt-1 flex justify-between text-xs text-muted-foreground">
              <span>{new Date(history[0].timestamp).toLocaleDateString()}</span>
              <span>{new Date(history[history.length - 1].timestamp).toLocaleDateString()}</span>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Positions table */}
      {portfolio && portfolio.positions.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle>Open Positions</CardTitle>
            <CardDescription>{portfolio.positions.length} position{portfolio.positions.length !== 1 ? "s" : ""}</CardDescription>
          </CardHeader>
          <CardContent>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b text-left text-muted-foreground">
                    <th className="pb-2 font-medium">Symbol</th>
                    <th className="pb-2 font-medium text-right">Shares</th>
                    <th className="pb-2 font-medium text-right">Avg Cost</th>
                    <th className="pb-2 font-medium text-right">Value</th>
                    <th className="pb-2 font-medium text-right">Unrealized P&L</th>
                    <th className="pb-2 font-medium text-right">Realized P&L</th>
                  </tr>
                </thead>
                <tbody>
                  {portfolio.positions.map((p) => (
                    <tr key={p.stock_id} className="border-b last:border-0">
                      <td className="py-2 font-semibold">{p.symbol}</td>
                      <td className="py-2 text-right font-mono">{p.shares.toFixed(2)}</td>
                      <td className="py-2 text-right font-mono">${p.avg_cost_basis.toFixed(2)}</td>
                      <td className="py-2 text-right font-mono">${p.current_value.toFixed(2)}</td>
                      <td className="py-2 text-right font-mono">
                        <span className={p.unrealized_pnl >= 0 ? "text-green-500" : "text-red-500"}>
                          {p.unrealized_pnl >= 0 ? "+" : ""}${p.unrealized_pnl.toFixed(2)}
                        </span>
                      </td>
                      <td className="py-2 text-right font-mono">
                        <span className={p.realized_pnl >= 0 ? "text-green-500" : "text-red-500"}>
                          {p.realized_pnl >= 0 ? "+" : ""}${p.realized_pnl.toFixed(2)}
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Add stock + Watchlist */}
      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <div>
              <CardTitle>Watchlist</CardTitle>
              <CardDescription>
                {stocks.length === 0
                  ? "No stocks added yet. Add a ticker symbol below."
                  : `${stocks.length} stock${stocks.length > 1 ? "s" : ""} tracked`}
              </CardDescription>
            </div>
            <div className="flex gap-2">
              <input
                type="text"
                placeholder="AAPL"
                value={newSymbol}
                onChange={(e) => setNewSymbol(e.target.value.toUpperCase())}
                onKeyDown={(e) => e.key === "Enter" && addStock()}
                className="h-9 w-28 rounded-md border bg-background px-3 text-sm uppercase"
                maxLength={10}
              />
              <Button size="sm" onClick={addStock} disabled={adding}>
                {adding ? "Adding..." : "Add Stock"}
              </Button>
            </div>
          </div>
        </CardHeader>
        <CardContent>
          {stocks.length === 0 ? (
            <div className="flex h-32 items-center justify-center rounded-md border border-dashed">
              <p className="text-sm text-muted-foreground">
                Add stocks with the input above to start collecting data
              </p>
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b text-left text-muted-foreground">
                    <th className="pb-2 font-medium">Symbol</th>
                    <th className="pb-2 font-medium">Name</th>
                    <th className="pb-2 font-medium">Sector</th>
                    <th className="pb-2 font-medium text-right">Price</th>
                    <th className="pb-2 font-medium text-right">Change</th>
                    <th className="pb-2 font-medium text-right">Sentiment</th>
                  </tr>
                </thead>
                <tbody>
                  {stocks.map((stock) => (
                    <tr key={stock.id} className="border-b last:border-0">
                      <td className="py-3">
                        <Link
                          href={`/stocks/${stock.symbol}`}
                          className="font-semibold text-primary hover:underline"
                        >
                          {stock.symbol}
                        </Link>
                      </td>
                      <td className="py-3 text-muted-foreground">
                        {stock.name || "—"}
                      </td>
                      <td className="py-3 text-muted-foreground">
                        {stock.sector || "—"}
                      </td>
                      <td className="py-3 text-right font-mono">
                        {stock.latest_price != null
                          ? `$${stock.latest_price.toFixed(2)}`
                          : "—"}
                      </td>
                      <td className="py-3 text-right font-mono">
                        {stock.daily_change_pct != null ? (
                          <span
                            className={
                              stock.daily_change_pct >= 0
                                ? "text-green-500"
                                : "text-red-500"
                            }
                          >
                            {stock.daily_change_pct >= 0 ? "+" : ""}
                            {stock.daily_change_pct.toFixed(2)}%
                          </span>
                        ) : (
                          "—"
                        )}
                      </td>
                      <td className="py-3 text-right">
                        {(() => {
                          const synth = analyses[stock.symbol]?.latest_synthesis;
                          if (!synth) return <span className="text-muted-foreground">—</span>;
                          const s = synth.overall_sentiment;
                          const label = s >= 0.3 ? "Bullish" : s <= -0.3 ? "Bearish" : "Neutral";
                          const color =
                            s >= 0.3
                              ? "bg-green-500/10 text-green-500"
                              : s <= -0.3
                              ? "bg-red-500/10 text-red-500"
                              : "bg-yellow-500/10 text-yellow-500";
                          return (
                            <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${color}`}>
                              {label}
                            </span>
                          );
                        })()}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Collection Pipeline Status */}
      <Card>
        <CardHeader>
          <CardTitle>Collection Pipeline</CardTitle>
          <CardDescription>
            Status of automated data collection tasks
          </CardDescription>
        </CardHeader>
        <CardContent>
          {collectionStatus && Object.keys(collectionStatus.tasks).length > 0 ? (
            <div className="space-y-3">
              {Object.entries(collectionStatus.tasks).map(([name, info]) => (
                <div key={name} className="flex items-center justify-between rounded-md border p-3">
                  <div>
                    <p className="text-sm font-medium">{name}</p>
                    <p className="text-xs text-muted-foreground">
                      Last run: {new Date(info.last_run).toLocaleString()}
                    </p>
                  </div>
                  <span
                    className={`rounded-full px-2 py-1 text-xs font-medium ${
                      info.last_result?.status === "ok"
                        ? "bg-green-500/10 text-green-500"
                        : info.last_result?.status === "error"
                        ? "bg-red-500/10 text-red-500"
                        : "bg-yellow-500/10 text-yellow-500"
                    }`}
                  >
                    {String(info.last_result?.status || "unknown")}
                  </span>
                </div>
              ))}
            </div>
          ) : (
            <div className="flex h-32 items-center justify-center rounded-md border border-dashed">
              <p className="text-sm text-muted-foreground">
                No collection tasks have run yet. Tasks start automatically via Celery Beat.
              </p>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Bottom row */}
      <div className="grid gap-4 md:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>Recent Trades</CardTitle>
            <CardDescription>
              {recentTrades.length > 0
                ? `Last ${recentTrades.length} executed trades`
                : "No trades executed yet."}
            </CardDescription>
          </CardHeader>
          <CardContent>
            {recentTrades.length === 0 ? (
              <div className="flex h-32 items-center justify-center rounded-md border border-dashed">
                <p className="text-sm text-muted-foreground">
                  Trades will appear here once executed
                </p>
              </div>
            ) : (
              <div className="space-y-2">
                {recentTrades.map((t) => (
                  <div key={t.id} className="flex items-center justify-between rounded-md border p-2">
                    <div className="flex items-center gap-2">
                      <span
                        className={`rounded-full px-2 py-0.5 text-xs font-bold uppercase ${
                          t.action === "buy"
                            ? "bg-green-500/10 text-green-500"
                            : "bg-red-500/10 text-red-500"
                        }`}
                      >
                        {t.action}
                      </span>
                      <span className="text-sm font-medium">{t.symbol}</span>
                      <span className="text-xs text-muted-foreground">
                        {t.shares} shares @ ${t.fill_price?.toFixed(2) || t.price.toFixed(2)}
                      </span>
                    </div>
                    <span
                      className={`rounded-full px-2 py-0.5 text-xs font-medium ${
                        t.status === "filled"
                          ? "bg-green-500/10 text-green-500"
                          : t.status === "pending"
                          ? "bg-yellow-500/10 text-yellow-500"
                          : "bg-muted text-muted-foreground"
                      }`}
                    >
                      {t.status}
                    </span>
                  </div>
                ))}
                <Link href="/trades" className="block text-center text-xs text-primary hover:underline pt-1">
                  View all trades →
                </Link>
              </div>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Active Signals</CardTitle>
            <CardDescription>
              {Object.values(analyses).filter((a) => a.latest_synthesis).length > 0
                ? "Latest Claude synthesis signals"
                : "No signals generated yet."}
            </CardDescription>
          </CardHeader>
          <CardContent>
            {Object.values(analyses).filter((a) => a.latest_synthesis).length === 0 ? (
              <div className="flex h-32 items-center justify-center rounded-md border border-dashed">
                <p className="text-sm text-muted-foreground">
                  Signals appear after Claude analysis runs
                </p>
              </div>
            ) : (
              <div className="space-y-2">
                {Object.values(analyses)
                  .filter((a) => a.latest_synthesis)
                  .map((a) => (
                    <div key={a.symbol} className="flex items-center justify-between rounded-md border p-2">
                      <span className="text-sm font-medium">{a.symbol}</span>
                      <span
                        className={`rounded-full px-2 py-0.5 text-xs font-medium ${
                          a.latest_synthesis!.overall_sentiment >= 0.3
                            ? "bg-green-500/10 text-green-500"
                            : a.latest_synthesis!.overall_sentiment <= -0.3
                            ? "bg-red-500/10 text-red-500"
                            : "bg-yellow-500/10 text-yellow-500"
                        }`}
                      >
                        {a.latest_synthesis!.overall_sentiment >= 0 ? "+" : ""}
                        {a.latest_synthesis!.overall_sentiment.toFixed(2)}
                      </span>
                    </div>
                  ))}
              </div>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
