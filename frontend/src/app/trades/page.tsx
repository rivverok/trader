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
  type ProposedTradeItem,
  type ExecutedTradeItem,
  type RiskStatus,
} from "@/lib/api";

function statusBadge(status: string) {
  const colors: Record<string, string> = {
    proposed: "bg-blue-500/10 text-blue-500",
    queued: "bg-yellow-500/10 text-yellow-500",
    approved: "bg-green-500/10 text-green-500",
    rejected: "bg-red-500/10 text-red-500",
    executed: "bg-purple-500/10 text-purple-500",
    expired: "bg-muted text-muted-foreground",
  };
  return (
    <span
      className={`rounded-full px-2 py-0.5 text-xs font-medium uppercase ${colors[status] || "bg-muted text-muted-foreground"}`}
    >
      {status}
    </span>
  );
}

function actionBadge(action: string) {
  return (
    <span
      className={`rounded-full px-2 py-0.5 text-xs font-bold uppercase ${
        action === "buy"
          ? "bg-green-500/10 text-green-500"
          : "bg-red-500/10 text-red-500"
      }`}
    >
      {action}
    </span>
  );
}

export default function TradesPage() {
  const [trades, setTrades] = useState<ProposedTradeItem[]>([]);
  const [executedTrades, setExecutedTrades] = useState<ExecutedTradeItem[]>([]);
  const [risk, setRisk] = useState<RiskStatus | null>(null);
  const [systemMode, setSystemMode] = useState<string>("data_collection");
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState<string | undefined>(undefined);
  const [expandedId, setExpandedId] = useState<number | null>(null);
  const [tab, setTab] = useState<"proposals" | "history" | "manual">("proposals");
  // Manual trade form
  const [manualSymbol, setManualSymbol] = useState("");
  const [manualAction, setManualAction] = useState<"buy" | "sell">("buy");
  const [manualShares, setManualShares] = useState("");
  const [manualOrderType, setManualOrderType] = useState("market");
  const [manualPrice, setManualPrice] = useState("");
  const [manualResult, setManualResult] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    loadData();
  }, [filter]);

  async function loadData() {
    setLoading(true);
    try {
      const [t, r, e] = await Promise.all([
        api.trades.proposed(filter, 100),
        api.risk.status(),
        api.portfolio.trades(undefined, 100),
      ]);
      setTrades(t);
      setRisk(r);
      setExecutedTrades(e);
      api.dataCollection.getMode().then((m) => setSystemMode(m.mode)).catch(() => {});
    } catch {
      /* empty */
    } finally {
      setLoading(false);
    }
  }

  async function handleApprove(id: number) {
    try {
      await api.trades.approve(id);
      await loadData();
    } catch {
      /* empty */
    }
  }

  async function handleReject(id: number) {
    try {
      await api.trades.reject(id);
      await loadData();
    } catch {
      /* empty */
    }
  }

  if (loading && trades.length === 0) {
    return (
      <div className="flex h-64 items-center justify-center">
        <p className="text-muted-foreground">Loading...</p>
      </div>
    );
  }

  const proposedCount = trades.filter((t) => t.status === "proposed").length;

  async function handleManualTrade() {
    if (!manualSymbol || !manualShares) return;
    setSubmitting(true);
    setManualResult(null);
    try {
      const result = await api.system.manualTrade({
        symbol: manualSymbol.toUpperCase(),
        action: manualAction,
        shares: parseFloat(manualShares),
        order_type: manualOrderType,
        price_target: manualPrice ? parseFloat(manualPrice) : undefined,
      });
      if (result.risk_check_passed) {
        setManualResult(`Trade executed (ID: ${result.trade_id})`);
        setManualSymbol("");
        setManualShares("");
        setManualPrice("");
        await loadData();
      } else {
        setManualResult(`Rejected: ${result.risk_check_reason}`);
      }
    } catch (e: any) {
      setManualResult(`Error: ${e.message}`);
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-3xl font-bold tracking-tight">Trades</h2>
        <p className="text-muted-foreground">
          Proposals, execution history, and manual trade entry
        </p>
      </div>

      {/* ── Risk alert banner ── */}
      {risk?.trading_halted && (
        <div className="rounded-lg border border-red-500/50 bg-red-500/10 p-4">
          <div className="flex items-center justify-between">
            <div>
              <h3 className="font-semibold text-red-500">Trading Halted</h3>
              <p className="text-sm text-red-400">{risk.halt_reason}</p>
            </div>
            <Button
              variant="destructive"
              size="sm"
              onClick={async () => {
                await api.risk.resume();
                await loadData();
              }}
            >
              Resume Trading
            </Button>
          </div>
        </div>
      )}

      {/* ── Data collection mode banner ── */}
      {systemMode !== "trading" && (
        <div className="rounded-lg border border-blue-500/50 bg-blue-500/10 p-4">
          <h3 className="font-semibold text-blue-400">Data Collection Mode</h3>
          <p className="text-sm text-blue-300">
            Trading is disabled. The system is collecting data and capturing state
            snapshots for RL training. Switch to trading mode on the Configuration
            page when an RL model is loaded.
          </p>
        </div>
      )}

      {/* ── Tab bar ── */}
      <div className="flex items-center gap-2 border-b pb-2">
        {(
          [
            { label: "Proposals", value: "proposals" as const },
            { label: "Trade History", value: "history" as const },
            { label: "Manual Trade", value: "manual" as const },
          ] as const
        ).map(({ label, value }) => (
          <Button
            key={value}
            variant={tab === value ? "default" : "ghost"}
            size="sm"
            onClick={() => setTab(value)}
          >
            {label}
          </Button>
        ))}
      </div>

      {/* ── Proposals tab ── */}
      {tab === "proposals" && (
        <>
          {/* Filter bar */}
          <div className="flex items-center gap-2">
            {[
              { label: "All", value: undefined },
              { label: `Proposed (${proposedCount})`, value: "proposed" },
              { label: "Queued", value: "queued" },
              { label: "Approved", value: "approved" },
              { label: "Rejected", value: "rejected" },
              { label: "Executed", value: "executed" },
            ].map(({ label, value }) => (
              <Button
                key={label}
                variant={filter === value ? "default" : "outline"}
                size="sm"
                onClick={() => setFilter(value)}
              >
                {label}
              </Button>
            ))}

          </div>

          <Card>
            <CardHeader>
              <CardTitle>Proposals</CardTitle>
              <CardDescription>
                {trades.length} trade{trades.length !== 1 ? "s" : ""}
              </CardDescription>
            </CardHeader>
            <CardContent>
              <div className="mb-4 rounded-md border border-border/50 bg-muted/30 p-3 text-sm text-muted-foreground">
                <strong className="text-foreground">How it works:</strong> The AI analyzes watchlist stocks every 30 min → proposes trades → auto-approves during market hours → executes.
                Approve/Reject buttons are optional overrides. Queued trades are automatically re-checked at market open.
              </div>

              {trades.length === 0 ? (
                <div className="flex h-32 items-center justify-center rounded-md border border-dashed">
                  <p className="text-sm text-muted-foreground">
                    No trade proposals yet — the decision engine runs every 30
                    minutes during market hours
                  </p>
                </div>
              ) : (
                <div className="space-y-3">
                  {trades.map((t) => (
                    <div
                      key={t.id}
                      className="rounded-lg border border-border p-4"
                    >
                      <div className="flex items-center justify-between">
                        <div className="flex items-center gap-3">
                          <span className="text-lg font-bold">{t.symbol}</span>
                          {actionBadge(t.action)}
                          {statusBadge(t.status)}
                          <span className="text-sm text-muted-foreground">
                            {t.shares} shares @ {t.order_type}
                            {t.price_target
                              ? ` $${t.price_target.toFixed(2)}`
                              : ""}
                          </span>
                        </div>
                        <div className="flex items-center gap-2">
                          <div className="flex items-center gap-2">
                            <div className="h-2 w-20 rounded-full bg-muted">
                              <div
                                className="h-2 rounded-full bg-primary"
                                style={{
                                  width: `${Math.round(t.confidence * 100)}%`,
                                }}
                              />
                            </div>
                            <span className="text-xs text-muted-foreground">
                              {(t.confidence * 100).toFixed(0)}%
                            </span>
                          </div>
                          {(t.status === "proposed" || t.status === "queued") && (
                            <>
                              <Button
                                size="sm"
                                onClick={() => handleApprove(t.id)}
                              >
                                Approve
                              </Button>
                              <Button
                                variant="outline"
                                size="sm"
                                onClick={() => handleReject(t.id)}
                              >
                                Reject
                              </Button>
                            </>
                          )}
                          <Button
                            variant="ghost"
                            size="sm"
                            onClick={() =>
                              setExpandedId(expandedId === t.id ? null : t.id)
                            }
                          >
                            {expandedId === t.id ? "▲" : "▼"}
                          </Button>
                        </div>
                      </div>

                      {t.status === "queued" && (
                        <div className="mt-2 text-sm text-yellow-400">
                          Queued{t.risk_check_reason && t.risk_check_reason !== "ok" ? ` — ${t.risk_check_reason}` : " — will be re-checked at market open"}
                        </div>
                      )}

                      {expandedId === t.id && (
                        <div className="mt-4 space-y-3 border-t border-border/50 pt-3">
                          {t.reasoning_chain && (
                            <div>
                              <h4 className="text-sm font-semibold">
                                Reasoning Chain
                              </h4>
                              <p className="mt-1 text-sm text-muted-foreground">
                                {t.reasoning_chain}
                              </p>
                            </div>
                          )}
                          <div className="grid grid-cols-3 gap-4 text-sm">
                            <div>
                              <span className="text-muted-foreground">
                                ML Signal:
                              </span>{" "}
                              {t.ml_signal_id ? `#${t.ml_signal_id}` : "N/A"}
                            </div>
                            <div>
                              <span className="text-muted-foreground">
                                Synthesis:
                              </span>{" "}
                              {t.synthesis_id ? `#${t.synthesis_id}` : "N/A"}
                            </div>
                            <div>
                              <span className="text-muted-foreground">
                                Analyst:
                              </span>{" "}
                              {t.analyst_input_id
                                ? `#${t.analyst_input_id}`
                                : "N/A"}
                            </div>
                          </div>
                          <div className="text-xs text-muted-foreground">
                            Created:{" "}
                            {new Date(t.created_at).toLocaleString()}
                          </div>
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              )}
            </CardContent>
          </Card>
        </>
      )}

      {/* ── Trade History tab ── */}
      {tab === "history" && (
        <Card>
          <CardHeader>
            <CardTitle>Executed Trades</CardTitle>
            <CardDescription>
              {executedTrades.length} trade{executedTrades.length !== 1 ? "s" : ""} — full audit trail
            </CardDescription>
          </CardHeader>
          <CardContent>
            {executedTrades.length === 0 ? (
              <div className="flex h-32 items-center justify-center rounded-md border border-dashed">
                <p className="text-sm text-muted-foreground">
                  No trades executed yet
                </p>
              </div>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b text-left text-muted-foreground">
                      <th className="pb-2 font-medium">Symbol</th>
                      <th className="pb-2 font-medium">Action</th>
                      <th className="pb-2 font-medium text-right">Shares</th>
                      <th className="pb-2 font-medium text-right">Price</th>
                      <th className="pb-2 font-medium text-right">Fill Price</th>
                      <th className="pb-2 font-medium text-right">Slippage</th>
                      <th className="pb-2 font-medium">Type</th>
                      <th className="pb-2 font-medium">Status</th>
                      <th className="pb-2 font-medium">Time</th>
                    </tr>
                  </thead>
                  <tbody>
                    {executedTrades.map((t) => (
                      <tr key={t.id} className="border-b last:border-0">
                        <td className="py-2 font-semibold">{t.symbol}</td>
                        <td className="py-2">{actionBadge(t.action)}</td>
                        <td className="py-2 text-right font-mono">{t.shares.toFixed(2)}</td>
                        <td className="py-2 text-right font-mono">${t.price.toFixed(2)}</td>
                        <td className="py-2 text-right font-mono">
                          {t.fill_price ? `$${t.fill_price.toFixed(2)}` : "—"}
                        </td>
                        <td className="py-2 text-right font-mono">
                          {t.slippage != null ? `${t.slippage.toFixed(4)}%` : "—"}
                        </td>
                        <td className="py-2 text-xs text-muted-foreground">{t.order_type}</td>
                        <td className="py-2">{statusBadge(t.status)}</td>
                        <td className="py-2 text-xs text-muted-foreground">
                          {t.fill_time
                            ? new Date(t.fill_time).toLocaleString()
                            : new Date(t.created_at).toLocaleString()}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </CardContent>
        </Card>
      )}

      {/* ── Manual Trade tab ── */}
      {tab === "manual" && (
        <Card>
          <CardHeader>
            <CardTitle>Place Manual Trade</CardTitle>
            <CardDescription>
              Bypass the decision engine — still goes through risk checks
            </CardDescription>
          </CardHeader>
          <CardContent>
            <div className="max-w-md space-y-4">
              <div>
                <label className="mb-1 block text-sm font-medium">Symbol</label>
                <input
                  type="text"
                  placeholder="AAPL"
                  value={manualSymbol}
                  onChange={(e) => setManualSymbol(e.target.value.toUpperCase())}
                  className="h-9 w-full rounded-md border bg-background px-3 text-sm uppercase"
                  maxLength={10}
                />
              </div>

              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="mb-1 block text-sm font-medium">Action</label>
                  <div className="flex gap-2">
                    <Button
                      size="sm"
                      variant={manualAction === "buy" ? "default" : "outline"}
                      onClick={() => setManualAction("buy")}
                      className="flex-1"
                    >
                      Buy
                    </Button>
                    <Button
                      size="sm"
                      variant={manualAction === "sell" ? "default" : "outline"}
                      onClick={() => setManualAction("sell")}
                      className="flex-1"
                    >
                      Sell
                    </Button>
                  </div>
                </div>

                <div>
                  <label className="mb-1 block text-sm font-medium">Shares</label>
                  <input
                    type="number"
                    placeholder="1"
                    value={manualShares}
                    onChange={(e) => setManualShares(e.target.value)}
                    className="h-9 w-full rounded-md border bg-background px-3 text-sm"
                    min={0.01}
                    step={1}
                  />
                </div>
              </div>

              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="mb-1 block text-sm font-medium">Order Type</label>
                  <select
                    value={manualOrderType}
                    onChange={(e) => setManualOrderType(e.target.value)}
                    className="h-9 w-full rounded-md border bg-background px-3 text-sm"
                  >
                    <option value="market">Market</option>
                    <option value="limit">Limit</option>
                    <option value="bracket">Bracket</option>
                  </select>
                </div>

                <div>
                  <label className="mb-1 block text-sm font-medium">
                    Price Target {manualOrderType === "market" && "(optional)"}
                  </label>
                  <input
                    type="number"
                    placeholder="0.00"
                    value={manualPrice}
                    onChange={(e) => setManualPrice(e.target.value)}
                    className="h-9 w-full rounded-md border bg-background px-3 text-sm"
                    min={0}
                    step={0.01}
                  />
                </div>
              </div>

              <Button
                className="w-full"
                onClick={handleManualTrade}
                disabled={submitting || !manualSymbol || !manualShares}
              >
                {submitting ? "Placing Order..." : `Place ${manualAction.toUpperCase()} Order`}
              </Button>

              {manualResult && (
                <div
                  className={`rounded-md border p-3 text-sm ${
                    manualResult.startsWith("Error") || manualResult.startsWith("Rejected")
                      ? "border-red-500/50 bg-red-500/10 text-red-400"
                      : "border-green-500/50 bg-green-500/10 text-green-400"
                  }`}
                >
                  {manualResult}
                </div>
              )}
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
