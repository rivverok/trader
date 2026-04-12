"use client";

import { useEffect, useMemo, useState } from "react";
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
  type PortfolioResponse,
  type PortfolioSnapshot,
  type PerformanceMetrics,
  type ExecutedTradeItem,
  type ProposedTradeItem,
  type SystemStatus,
  type StockAnalysis,
  type DiscoveryLogItem,
  type Stock,
} from "@/lib/api";
import {
  AreaChart,
  Area,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  ReferenceLine,
  Cell,
} from "recharts";

// ── Helpers ─────────────────────────────────────────────────────────

function fmt(n: number, decimals = 2): string {
  return n.toFixed(decimals);
}
function fmtDollar(n: number): string {
  return n >= 0 ? `$${n.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}` : `-$${Math.abs(n).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}
function fmtCompact(n: number): string {
  if (Math.abs(n) >= 1_000_000) return `$${(n / 1_000_000).toFixed(1)}M`;
  if (Math.abs(n) >= 1_000) return `$${(n / 1_000).toFixed(1)}K`;
  return `$${n.toFixed(0)}`;
}
function pctColor(val: number): string {
  if (val > 0) return "text-green-400";
  if (val < 0) return "text-red-400";
  return "text-muted-foreground";
}
function pctBg(val: number): string {
  if (val > 0) return "bg-green-500/10 text-green-400";
  if (val < 0) return "bg-red-500/10 text-red-400";
  return "bg-muted text-muted-foreground";
}

// ── Custom tooltip ──────────────────────────────────────────────────

function EquityTooltip({ active, payload, label }: any) {
  if (!active || !payload?.length) return null;
  return (
    <div className="rounded-lg border bg-card p-3 shadow-lg">
      <p className="text-xs text-muted-foreground">{label}</p>
      <p className="text-sm font-bold">{fmtDollar(payload[0].value)}</p>
    </div>
  );
}

function PnLTooltip({ active, payload, label }: any) {
  if (!active || !payload?.length) return null;
  const val = payload[0].value;
  return (
    <div className="rounded-lg border bg-card p-3 shadow-lg">
      <p className="text-xs text-muted-foreground">{label}</p>
      <p className={`text-sm font-bold ${val >= 0 ? "text-green-400" : "text-red-400"}`}>
        {val >= 0 ? "+" : ""}{fmtDollar(val)}
      </p>
    </div>
  );
}

function PriceTooltip({ active, payload, label }: any) {
  if (!active || !payload?.length) return null;
  return (
    <div className="rounded-lg border bg-card p-3 shadow-lg">
      <p className="text-xs text-muted-foreground">{label}</p>
      <p className="text-sm font-bold">${payload[0].value.toFixed(2)}</p>
    </div>
  );
}

// ── Main page ───────────────────────────────────────────────────────

export default function OverviewPage() {
  const [portfolio, setPortfolio] = useState<PortfolioResponse | null>(null);
  const [history, setHistory] = useState<PortfolioSnapshot[]>([]);
  const [performance, setPerformance] = useState<PerformanceMetrics | null>(null);
  const [systemStatus, setSystemStatus] = useState<SystemStatus | null>(null);
  const [recentTrades, setRecentTrades] = useState<ExecutedTradeItem[]>([]);
  const [proposals, setProposals] = useState<ProposedTradeItem[]>([]);
  const [discoveryLog, setDiscoveryLog] = useState<DiscoveryLogItem[]>([]);
  const [stocks, setStocks] = useState<Stock[]>([]);
  const [analyses, setAnalyses] = useState<Record<string, StockAnalysis>>({});
  const [positionPrices, setPositionPrices] = useState<Record<string, { timestamp: string; close: number }[]>>({});

  const [activeTab, setActiveTab] = useState("portfolio");
  const [loading, setLoading] = useState(true);

  // Compute YTD days from Jan 1 of current year
  const ytdDays = useMemo(() => {
    const now = new Date();
    const jan1 = new Date(now.getFullYear(), 0, 1);
    return Math.ceil((now.getTime() - jan1.getTime()) / 86_400_000) + 1;
  }, []);

  const refresh = () => {
    Promise.allSettled([
      api.portfolio.get().then(setPortfolio),
      api.portfolio.history(ytdDays).then(setHistory),
      api.analytics.performance().then(setPerformance),
      api.system.status().then(setSystemStatus),
      api.portfolio.trades(undefined, 20).then(setRecentTrades),
      api.trades.proposed(undefined, 15).then(setProposals),
      api.discovery.log(10).then(setDiscoveryLog),
      api.stocks.list(true).then((list) => {
        setStocks(list);
        const results: Record<string, StockAnalysis> = {};
        Promise.allSettled(
          list.map((s) =>
            api.analysis.forStock(s.symbol).then((a) => {
              results[s.symbol] = a;
            })
          )
        ).then(() => setAnalyses(results));
      }),
    ]).finally(() => setLoading(false));
  };

  // Load price history for held positions
  useEffect(() => {
    if (!portfolio?.positions.length) return;
    const symbols = portfolio.positions.map((p) => p.symbol);
    const prices: Record<string, { timestamp: string; close: number }[]> = {};
    Promise.allSettled(
      symbols.map((sym) =>
        api.stocks.prices(sym, "1Day", 120).then((bars) => {
          prices[sym] = bars.map((b) => ({
            timestamp: b.timestamp.slice(0, 10),
            close: b.close,
          }));
        })
      )
    ).then(() => setPositionPrices(prices));
  }, [portfolio?.positions.length]);

  useEffect(() => {
    refresh();
    const interval = setInterval(refresh, 30000);
    return () => clearInterval(interval);
  }, []);

  // ── Derived data ──────────────────────────────────────────────────

  const equityData = useMemo(
    () =>
      history.map((s) => ({
        date: new Date(s.timestamp).toLocaleDateString("en-US", { month: "short", day: "numeric" }),
        value: s.total_value,
        raw: s.timestamp,
      })),
    [history]
  );

  const dailyPnlData = useMemo(() => {
    if (history.length < 2) return [];
    return history.slice(1).map((s, i) => ({
      date: new Date(s.timestamp).toLocaleDateString("en-US", { month: "short", day: "numeric" }),
      pnl: s.total_value - history[i].total_value,
    }));
  }, [history]);

  const ytdReturn = useMemo(() => {
    if (history.length < 2) return null;
    const start = history[0].total_value;
    const end = history[history.length - 1].total_value;
    if (start === 0) return null;
    return ((end - start) / start) * 100;
  }, [history]);

  const ytdPnl = useMemo(() => {
    if (history.length < 2) return null;
    return history[history.length - 1].total_value - history[0].total_value;
  }, [history]);

  const positions = portfolio?.positions ?? [];
  const heldSymbols = positions.map((p) => p.symbol);

  const tabs = [
    { id: "portfolio", label: "Portfolio" },
    ...positions.map((p) => ({ id: p.symbol, label: p.symbol })),
    { id: "decisions", label: "AI Decisions" },
  ];

  if (loading) {
    return (
      <div className="flex h-96 items-center justify-center">
        <div className="text-center space-y-2">
          <div className="h-8 w-8 animate-spin rounded-full border-4 border-primary border-t-transparent mx-auto" />
          <p className="text-muted-foreground">Loading overview...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* ── Header + System Status Bar ─────────────────────────── */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">Overview</h1>
          <p className="text-muted-foreground">
            {new Date().toLocaleDateString("en-US", {
              weekday: "long",
              year: "numeric",
              month: "long",
              day: "numeric",
            })}
          </p>
        </div>
        {systemStatus && (
          <div className="flex items-center gap-3">
            <StatusPill
              label={
                systemStatus.trading_halted
                  ? "HALTED"
                  : systemStatus.trading_paused
                  ? "PAUSED"
                  : "ACTIVE"
              }
              color={
                systemStatus.trading_halted
                  ? "red"
                  : systemStatus.trading_paused
                  ? "yellow"
                  : "green"
              }
            />
            {systemStatus.auto_execute && <StatusPill label="Auto-Execute" color="blue" />}
            {systemStatus.system_mode === "data_collection" && <StatusPill label="Data Collection" color="blue" />}
            {systemStatus.system_mode === "trading" && <StatusPill label="RL Trading" color="purple" />}
            {systemStatus.system_paused && <StatusPill label="System Paused" color="yellow" />}
          </div>
        )}
      </div>

      {/* ── Hero Stats Row ────────────────────────────────────── */}
      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
        <Card className="border-l-4 border-l-primary">
          <CardHeader className="pb-1">
            <CardDescription className="text-xs">Portfolio Value</CardDescription>
          </CardHeader>
          <CardContent>
            <div className="text-3xl font-bold font-mono">
              {portfolio ? fmtDollar(portfolio.total_value) : "—"}
            </div>
            <p className="mt-1 text-xs text-muted-foreground">
              Cash: {portfolio ? fmtDollar(portfolio.cash) : "—"} | Invested: {portfolio ? fmtDollar(portfolio.positions_value) : "—"}
            </p>
          </CardContent>
        </Card>

        <Card className={`border-l-4 ${(ytdReturn ?? 0) >= 0 ? "border-l-green-500" : "border-l-red-500"}`}>
          <CardHeader className="pb-1">
            <CardDescription className="text-xs">YTD Return</CardDescription>
          </CardHeader>
          <CardContent>
            <div className={`text-3xl font-bold font-mono ${pctColor(ytdReturn ?? 0)}`}>
              {ytdReturn != null ? `${ytdReturn >= 0 ? "+" : ""}${fmt(ytdReturn, 1)}%` : "—"}
            </div>
            <p className={`mt-1 text-xs ${pctColor(ytdPnl ?? 0)}`}>
              {ytdPnl != null ? `${ytdPnl >= 0 ? "+" : ""}${fmtDollar(ytdPnl)}` : "—"}
            </p>
          </CardContent>
        </Card>

        <Card className={`border-l-4 ${(portfolio?.daily_pnl ?? 0) >= 0 ? "border-l-green-500" : "border-l-red-500"}`}>
          <CardHeader className="pb-1">
            <CardDescription className="text-xs">Today&apos;s P&amp;L</CardDescription>
          </CardHeader>
          <CardContent>
            <div className={`text-3xl font-bold font-mono ${pctColor(portfolio?.daily_pnl ?? 0)}`}>
              {portfolio ? `${portfolio.daily_pnl >= 0 ? "+" : ""}${fmtDollar(portfolio.daily_pnl)}` : "—"}
            </div>
            <p className="mt-1 text-xs text-muted-foreground">
              Cumulative: {portfolio ? `${portfolio.cumulative_pnl >= 0 ? "+" : ""}${fmtDollar(portfolio.cumulative_pnl)}` : "—"}
            </p>
          </CardContent>
        </Card>

        <Card className="border-l-4 border-l-blue-500">
          <CardHeader className="pb-1">
            <CardDescription className="text-xs">Performance</CardDescription>
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-2 gap-x-4 gap-y-1">
              <Stat label="Sharpe" value={performance ? fmt(performance.sharpe_ratio) : "—"} />
              <Stat label="Win Rate" value={performance ? `${fmt(performance.win_rate * 100, 0)}%` : "—"} />
              <Stat label="Trades" value={performance ? String(performance.total_trades) : "—"} />
              <Stat label="Drawdown" value={performance ? `${fmt(performance.max_drawdown_pct, 1)}%` : "—"} valueColor="text-red-400" />
            </div>
          </CardContent>
        </Card>
      </div>

      {/* ── Tab Row ───────────────────────────────────────────── */}
      <div className="flex items-center gap-1 border-b overflow-x-auto pb-px">
        {tabs.map((tab) => (
          <button
            key={tab.id}
            onClick={() => setActiveTab(tab.id)}
            className={`whitespace-nowrap px-4 py-2 text-sm font-medium border-b-2 transition-colors ${
              activeTab === tab.id
                ? "border-primary text-primary"
                : "border-transparent text-muted-foreground hover:text-foreground"
            }`}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {/* ── Portfolio Tab ─────────────────────────────────────── */}
      {activeTab === "portfolio" && (
        <div className="space-y-6">
          {/* YTD Equity Curve */}
          {equityData.length > 1 && (
            <Card>
              <CardHeader className="pb-2">
                <CardTitle>YTD Equity Curve</CardTitle>
                <CardDescription>
                  {equityData[0]?.date} — {equityData[equityData.length - 1]?.date}
                  {" • "}
                  {equityData.length} data points
                </CardDescription>
              </CardHeader>
              <CardContent>
                <ResponsiveContainer width="100%" height={320}>
                  <AreaChart data={equityData} margin={{ top: 5, right: 20, bottom: 5, left: 10 }}>
                    <defs>
                      <linearGradient id="equityGrad" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="0%" stopColor="hsl(var(--primary))" stopOpacity={0.3} />
                        <stop offset="100%" stopColor="hsl(var(--primary))" stopOpacity={0} />
                      </linearGradient>
                    </defs>
                    <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" />
                    <XAxis
                      dataKey="date"
                      tick={{ fontSize: 11, fill: "hsl(var(--muted-foreground))" }}
                      tickLine={false}
                      interval="preserveStartEnd"
                    />
                    <YAxis
                      tick={{ fontSize: 11, fill: "hsl(var(--muted-foreground))" }}
                      tickLine={false}
                      tickFormatter={fmtCompact}
                      width={60}
                    />
                    <Tooltip content={<EquityTooltip />} />
                    <Area
                      type="monotone"
                      dataKey="value"
                      stroke="hsl(var(--primary))"
                      strokeWidth={2}
                      fill="url(#equityGrad)"
                    />
                  </AreaChart>
                </ResponsiveContainer>
              </CardContent>
            </Card>
          )}

          {/* Daily P&L + Monthly Returns side by side */}
          <div className="grid gap-6 lg:grid-cols-2">
            {dailyPnlData.length > 1 && (
              <Card>
                <CardHeader className="pb-2">
                  <CardTitle className="text-base">Daily P&amp;L</CardTitle>
                </CardHeader>
                <CardContent>
                  <ResponsiveContainer width="100%" height={220}>
                    <BarChart data={dailyPnlData} margin={{ top: 5, right: 10, bottom: 5, left: 10 }}>
                      <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" />
                      <XAxis
                        dataKey="date"
                        tick={{ fontSize: 10, fill: "hsl(var(--muted-foreground))" }}
                        tickLine={false}
                        interval="preserveStartEnd"
                      />
                      <YAxis
                        tick={{ fontSize: 10, fill: "hsl(var(--muted-foreground))" }}
                        tickLine={false}
                        tickFormatter={fmtCompact}
                        width={50}
                      />
                      <Tooltip content={<PnLTooltip />} />
                      <ReferenceLine y={0} stroke="hsl(var(--muted-foreground))" strokeDasharray="3 3" />
                      <Bar dataKey="pnl" radius={[2, 2, 0, 0]}>
                        {dailyPnlData.map((entry, i) => (
                          <Cell
                            key={i}
                            fill={entry.pnl >= 0 ? "hsl(142, 71%, 45%)" : "hsl(0, 84%, 60%)"}
                          />
                        ))}
                      </Bar>
                    </BarChart>
                  </ResponsiveContainer>
                </CardContent>
              </Card>
            )}

            {performance && Object.keys(performance.monthly_returns).length > 0 && (
              <Card>
                <CardHeader className="pb-2">
                  <CardTitle className="text-base">Monthly Returns</CardTitle>
                </CardHeader>
                <CardContent>
                  <div className="grid grid-cols-4 gap-2">
                    {Object.entries(performance.monthly_returns)
                      .sort(([a], [b]) => a.localeCompare(b))
                      .map(([month, ret]) => (
                        <div
                          key={month}
                          className={`rounded-lg p-3 text-center ${pctBg(ret)}`}
                        >
                          <div className="text-[10px] opacity-70 uppercase">{month}</div>
                          <div className="text-sm font-bold">{ret >= 0 ? "+" : ""}{fmt(ret, 1)}%</div>
                        </div>
                      ))}
                  </div>
                </CardContent>
              </Card>
            )}
          </div>

          {/* Positions Table */}
          {positions.length > 0 && (
            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-base">Open Positions</CardTitle>
                <CardDescription>{positions.length} position{positions.length !== 1 ? "s" : ""}</CardDescription>
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
                        <th className="pb-2 font-medium text-right">P&L</th>
                        <th className="pb-2 font-medium text-right">Return</th>
                        <th className="pb-2 font-medium text-right">AI Sentiment</th>
                      </tr>
                    </thead>
                    <tbody>
                      {positions.map((p) => {
                        const returnPct = p.avg_cost_basis > 0 ? ((p.current_value / (p.shares * p.avg_cost_basis)) - 1) * 100 : 0;
                        const synth = analyses[p.symbol]?.latest_synthesis;
                        return (
                          <tr
                            key={p.stock_id}
                            className="border-b last:border-0 hover:bg-accent/50 cursor-pointer transition-colors"
                            onClick={() => setActiveTab(p.symbol)}
                          >
                            <td className="py-3 font-bold">{p.symbol}</td>
                            <td className="py-3 text-right font-mono">{p.shares.toFixed(2)}</td>
                            <td className="py-3 text-right font-mono">${p.avg_cost_basis.toFixed(2)}</td>
                            <td className="py-3 text-right font-mono">{fmtDollar(p.current_value)}</td>
                            <td className={`py-3 text-right font-mono ${pctColor(p.unrealized_pnl)}`}>
                              {p.unrealized_pnl >= 0 ? "+" : ""}{fmtDollar(p.unrealized_pnl)}
                            </td>
                            <td className={`py-3 text-right font-mono ${pctColor(returnPct)}`}>
                              {returnPct >= 0 ? "+" : ""}{fmt(returnPct, 1)}%
                            </td>
                            <td className="py-3 text-right">
                              {synth ? (
                                <SentimentBadge value={synth.overall_sentiment} />
                              ) : (
                                <span className="text-xs text-muted-foreground">—</span>
                              )}
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              </CardContent>
            </Card>
          )}

          {/* Recent Trades */}
          {recentTrades.length > 0 && (
            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-base">Recent Trades</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="space-y-2">
                  {recentTrades.slice(0, 8).map((t) => (
                    <div key={t.id} className="flex items-center justify-between rounded-lg border p-3">
                      <div className="flex items-center gap-3">
                        <span className={`rounded px-2 py-0.5 text-xs font-bold uppercase ${t.action === "buy" ? "bg-green-500/15 text-green-400" : "bg-red-500/15 text-red-400"}`}>
                          {t.action}
                        </span>
                        <span className="font-bold">{t.symbol}</span>
                        <span className="text-sm text-muted-foreground">
                          {t.shares} shares @ ${t.fill_price?.toFixed(2) ?? t.price.toFixed(2)}
                        </span>
                      </div>
                      <span className="text-xs text-muted-foreground">
                        {new Date(t.fill_time ?? t.created_at).toLocaleDateString()}
                      </span>
                    </div>
                  ))}
                </div>
              </CardContent>
            </Card>
          )}
        </div>
      )}

      {/* ── Individual Stock Tabs ─────────────────────────────── */}
      {heldSymbols.includes(activeTab) && (
        <StockDetail
          symbol={activeTab}
          position={positions.find((p) => p.symbol === activeTab)!}
          analysis={analyses[activeTab]}
          prices={positionPrices[activeTab] ?? []}
          trades={recentTrades.filter((t) => t.symbol === activeTab)}
          proposals={proposals.filter((t) => t.symbol === activeTab)}
        />
      )}

      {/* ── AI Decisions Tab ──────────────────────────────────── */}
      {activeTab === "decisions" && (
        <div className="space-y-6">
          {/* Recent Proposals */}
          <Card>
            <CardHeader>
              <CardTitle>Recent AI Trade Decisions</CardTitle>
              <CardDescription>Latest proposals from the decision engine</CardDescription>
            </CardHeader>
            <CardContent>
              {proposals.length === 0 ? (
                <p className="text-sm text-muted-foreground py-8 text-center">
                  No trade proposals yet — the decision engine runs every 30 min during market hours
                </p>
              ) : (
                <div className="space-y-3">
                  {proposals.map((t) => (
                    <div key={t.id} className="rounded-lg border p-4 space-y-2">
                      <div className="flex items-center justify-between">
                        <div className="flex items-center gap-3">
                          <span className="font-bold text-lg">{t.symbol}</span>
                          <span className={`rounded px-2 py-0.5 text-xs font-bold uppercase ${t.action === "buy" ? "bg-green-500/15 text-green-400" : "bg-red-500/15 text-red-400"}`}>
                            {t.action}
                          </span>
                          <ProposalStatus status={t.status} />
                          <span className="text-sm text-muted-foreground">
                            {t.shares} shares
                          </span>
                        </div>
                        <div className="flex items-center gap-2">
                          <ConfidenceBar value={t.confidence} />
                          <span className="text-xs text-muted-foreground">
                            {new Date(t.created_at).toLocaleString()}
                          </span>
                        </div>
                      </div>
                      {t.reasoning_chain && (
                        <p className="text-sm text-muted-foreground leading-relaxed">
                          {t.reasoning_chain}
                        </p>
                      )}
                    </div>
                  ))}
                </div>
              )}
            </CardContent>
          </Card>

          {/* Discovery Log */}
          <Card>
            <CardHeader>
              <CardTitle>Watchlist Discovery</CardTitle>
              <CardDescription>AI stock discovery decisions</CardDescription>
            </CardHeader>
            <CardContent>
              {discoveryLog.length === 0 ? (
                <p className="text-sm text-muted-foreground py-8 text-center">No discovery runs yet</p>
              ) : (
                <div className="space-y-3">
                  {discoveryLog.map((entry) => (
                    <div key={entry.id} className="flex items-start gap-3 rounded-lg border p-3">
                      <span className={`mt-0.5 rounded px-2 py-0.5 text-xs font-bold uppercase ${
                        entry.action === "add" ? "bg-green-500/15 text-green-400" :
                        entry.action === "remove" ? "bg-red-500/15 text-red-400" :
                        "bg-yellow-500/15 text-yellow-400"
                      }`}>
                        {entry.action}
                      </span>
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2">
                          <span className="font-bold">{entry.symbol}</span>
                          <span className="text-xs text-muted-foreground">
                            {new Date(entry.created_at).toLocaleDateString()}
                          </span>
                        </div>
                        <p className="text-sm text-muted-foreground mt-1">{entry.reasoning}</p>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </CardContent>
          </Card>
        </div>
      )}
    </div>
  );
}

// ── Stock Detail Sub-component ──────────────────────────────────────

function StockDetail({
  symbol,
  position,
  analysis,
  prices,
  trades,
  proposals,
}: {
  symbol: string;
  position: { shares: number; avg_cost_basis: number; current_value: number; unrealized_pnl: number; realized_pnl: number };
  analysis?: StockAnalysis;
  prices: { timestamp: string; close: number }[];
  trades: ExecutedTradeItem[];
  proposals: ProposedTradeItem[];
}) {
  const synth = analysis?.latest_synthesis;
  const returnPct = position.avg_cost_basis > 0
    ? ((position.current_value / (position.shares * position.avg_cost_basis)) - 1) * 100
    : 0;

  const priceData = prices.map((p) => ({
    date: new Date(p.timestamp).toLocaleDateString("en-US", { month: "short", day: "numeric" }),
    price: p.close,
  }));

  const priceChange = prices.length >= 2
    ? ((prices[prices.length - 1].close - prices[0].close) / prices[0].close) * 100
    : 0;

  return (
    <div className="space-y-6">
      {/* Position Stats */}
      <div className="grid gap-4 md:grid-cols-5">
        <StatCard label="Shares" value={position.shares.toFixed(2)} />
        <StatCard label="Avg Cost" value={`$${position.avg_cost_basis.toFixed(2)}`} />
        <StatCard label="Current Value" value={fmtDollar(position.current_value)} />
        <StatCard
          label="Unrealized P&L"
          value={`${position.unrealized_pnl >= 0 ? "+" : ""}${fmtDollar(position.unrealized_pnl)}`}
          valueColor={pctColor(position.unrealized_pnl)}
        />
        <StatCard
          label="Return"
          value={`${returnPct >= 0 ? "+" : ""}${fmt(returnPct, 1)}%`}
          valueColor={pctColor(returnPct)}
        />
      </div>

      {/* Price Chart */}
      {priceData.length > 1 && (
        <Card>
          <CardHeader className="pb-2">
            <div className="flex items-center justify-between">
              <div>
                <CardTitle>{symbol} Price</CardTitle>
                <CardDescription>Last {priceData.length} trading days</CardDescription>
              </div>
              <span className={`text-lg font-bold font-mono ${pctColor(priceChange)}`}>
                {priceChange >= 0 ? "+" : ""}{fmt(priceChange, 1)}%
              </span>
            </div>
          </CardHeader>
          <CardContent>
            <ResponsiveContainer width="100%" height={280}>
              <AreaChart data={priceData} margin={{ top: 5, right: 20, bottom: 5, left: 10 }}>
                <defs>
                  <linearGradient id={`priceGrad-${symbol}`} x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor={priceChange >= 0 ? "hsl(142, 71%, 45%)" : "hsl(0, 84%, 60%)"} stopOpacity={0.3} />
                    <stop offset="100%" stopColor={priceChange >= 0 ? "hsl(142, 71%, 45%)" : "hsl(0, 84%, 60%)"} stopOpacity={0} />
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" />
                <XAxis
                  dataKey="date"
                  tick={{ fontSize: 11, fill: "hsl(var(--muted-foreground))" }}
                  tickLine={false}
                  interval="preserveStartEnd"
                />
                <YAxis
                  tick={{ fontSize: 11, fill: "hsl(var(--muted-foreground))" }}
                  tickLine={false}
                  tickFormatter={(v: number) => `$${v}`}
                  width={60}
                  domain={["auto", "auto"]}
                />
                <Tooltip content={<PriceTooltip />} />
                <Area
                  type="monotone"
                  dataKey="price"
                  stroke={priceChange >= 0 ? "hsl(142, 71%, 45%)" : "hsl(0, 84%, 60%)"}
                  strokeWidth={2}
                  fill={`url(#priceGrad-${symbol})`}
                />
              </AreaChart>
            </ResponsiveContainer>
          </CardContent>
        </Card>
      )}

      <div className="grid gap-6 lg:grid-cols-2">
        {/* AI Analysis */}
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-base">AI Analysis</CardTitle>
            {synth && (
              <CardDescription>
                {synth.claude_model_used} • {new Date(synth.created_at).toLocaleString()}
              </CardDescription>
            )}
          </CardHeader>
          <CardContent>
            {synth ? (
              <div className="space-y-4">
                <div className="flex items-center gap-4">
                  <SentimentBadge value={synth.overall_sentiment} large />
                  <ConfidenceBar value={synth.confidence} />
                </div>
                {synth.reasoning_chain && (
                  <p className="text-sm text-muted-foreground leading-relaxed">
                    {synth.reasoning_chain}
                  </p>
                )}
                {synth.key_factors && synth.key_factors.length > 0 && (
                  <div>
                    <h4 className="text-xs font-semibold uppercase text-muted-foreground mb-1">Key Factors</h4>
                    <ul className="space-y-1">
                      {synth.key_factors.map((f, i) => (
                        <li key={i} className="text-sm flex items-start gap-2">
                          <span className="text-primary mt-1">•</span> {f}
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
                <div className="grid grid-cols-2 gap-4">
                  {synth.risks && synth.risks.length > 0 && (
                    <div>
                      <h4 className="text-xs font-semibold uppercase text-red-400 mb-1">Risks</h4>
                      <ul className="space-y-1">
                        {synth.risks.map((r, i) => (
                          <li key={i} className="text-xs text-muted-foreground">• {r}</li>
                        ))}
                      </ul>
                    </div>
                  )}
                  {synth.opportunities && synth.opportunities.length > 0 && (
                    <div>
                      <h4 className="text-xs font-semibold uppercase text-green-400 mb-1">Opportunities</h4>
                      <ul className="space-y-1">
                        {synth.opportunities.map((o, i) => (
                          <li key={i} className="text-xs text-muted-foreground">• {o}</li>
                        ))}
                      </ul>
                    </div>
                  )}
                </div>
              </div>
            ) : (
              <p className="text-sm text-muted-foreground py-4 text-center">No AI analysis available yet</p>
            )}
          </CardContent>
        </Card>

        {/* Trade History + Proposals for this stock */}
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-base">Trade Activity</CardTitle>
            <CardDescription>
              {trades.length} executed • {proposals.length} proposed
            </CardDescription>
          </CardHeader>
          <CardContent>
            <div className="space-y-2 max-h-80 overflow-y-auto">
              {[...proposals.map((p) => ({
                  id: `p-${p.id}`,
                  action: p.action,
                  shares: p.shares,
                  price: p.price_target,
                  time: p.created_at,
                  type: "proposal" as const,
                  status: p.status,
                  reasoning: p.reasoning_chain,
                  confidence: p.confidence,
                })),
                ...trades.map((t) => ({
                  id: `t-${t.id}`,
                  action: t.action,
                  shares: t.shares,
                  price: t.fill_price ?? t.price,
                  time: t.fill_time ?? t.created_at,
                  type: "trade" as const,
                  status: t.status,
                  reasoning: null as string | null,
                  confidence: null as number | null,
                })),
              ]
                .sort((a, b) => new Date(b.time).getTime() - new Date(a.time).getTime())
                .map((item) => (
                  <div key={item.id} className="rounded-lg border p-3 space-y-1">
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-2">
                        <span className={`rounded px-2 py-0.5 text-xs font-bold uppercase ${item.action === "buy" ? "bg-green-500/15 text-green-400" : "bg-red-500/15 text-red-400"}`}>
                          {item.action}
                        </span>
                        <span className="text-sm">
                          {item.shares} shares
                          {item.price ? ` @ $${item.price.toFixed(2)}` : ""}
                        </span>
                        {item.type === "proposal" && <ProposalStatus status={item.status} />}
                      </div>
                      <span className="text-xs text-muted-foreground">
                        {new Date(item.time).toLocaleDateString()}
                      </span>
                    </div>
                    {item.reasoning && (
                      <p className="text-xs text-muted-foreground">{item.reasoning}</p>
                    )}
                  </div>
                ))}
              {trades.length === 0 && proposals.length === 0 && (
                <p className="text-sm text-muted-foreground py-4 text-center">No activity yet</p>
              )}
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}

// ── Shared UI Components ─────────────────────────────────────────────

function StatusPill({ label, color }: { label: string; color: "green" | "yellow" | "red" | "blue" | "purple" }) {
  const colors = {
    green: "bg-green-500/15 text-green-400 border-green-500/30",
    yellow: "bg-yellow-500/15 text-yellow-400 border-yellow-500/30",
    red: "bg-red-500/15 text-red-400 border-red-500/30",
    blue: "bg-blue-500/15 text-blue-400 border-blue-500/30",
    purple: "bg-purple-500/15 text-purple-400 border-purple-500/30",
  };
  return (
    <span className={`rounded-full border px-3 py-1 text-xs font-medium ${colors[color]}`}>
      {label}
    </span>
  );
}

function Stat({ label, value, valueColor }: { label: string; value: string; valueColor?: string }) {
  return (
    <div>
      <div className="text-[10px] text-muted-foreground uppercase">{label}</div>
      <div className={`text-sm font-bold font-mono ${valueColor ?? ""}`}>{value}</div>
    </div>
  );
}

function StatCard({ label, value, valueColor }: { label: string; value: string; valueColor?: string }) {
  return (
    <Card>
      <CardContent className="pt-4 pb-3">
        <div className="text-xs text-muted-foreground">{label}</div>
        <div className={`text-xl font-bold font-mono mt-1 ${valueColor ?? ""}`}>{value}</div>
      </CardContent>
    </Card>
  );
}

function SentimentBadge({ value, large }: { value: number; large?: boolean }) {
  const label = value >= 0.3 ? "Bullish" : value <= -0.3 ? "Bearish" : "Neutral";
  const color = value >= 0.3 ? "bg-green-500/15 text-green-400" : value <= -0.3 ? "bg-red-500/15 text-red-400" : "bg-yellow-500/15 text-yellow-400";
  return (
    <span className={`rounded-full px-2 py-0.5 font-medium ${color} ${large ? "text-sm px-3 py-1" : "text-xs"}`}>
      {label} ({value >= 0 ? "+" : ""}{fmt(value, 2)})
    </span>
  );
}

function ConfidenceBar({ value }: { value: number }) {
  return (
    <div className="flex items-center gap-2">
      <div className="h-2 w-16 rounded-full bg-muted">
        <div
          className="h-2 rounded-full bg-primary transition-all"
          style={{ width: `${Math.round(value * 100)}%` }}
        />
      </div>
      <span className="text-xs text-muted-foreground">{(value * 100).toFixed(0)}%</span>
    </div>
  );
}

function ProposalStatus({ status }: { status: string }) {
  const colors: Record<string, string> = {
    proposed: "bg-blue-500/15 text-blue-400",
    approved: "bg-green-500/15 text-green-400",
    rejected: "bg-red-500/15 text-red-400",
    executed: "bg-purple-500/15 text-purple-400",
  };
  return (
    <span className={`rounded px-2 py-0.5 text-xs font-medium uppercase ${colors[status] ?? "bg-muted text-muted-foreground"}`}>
      {status}
    </span>
  );
}
