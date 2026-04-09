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
  type Stock,
  type BacktestResultItem,
  type ModelItem,
} from "@/lib/api";

/* ── Helpers ──────────────────────────────────────────────────────── */

function fmtPct(v: number) {
  return `${(v * 100).toFixed(2)}%`;
}

function fmtNum(v: number, dec = 2) {
  return v.toFixed(dec);
}

function returnColor(v: number) {
  return v >= 0 ? "text-green-500" : "text-red-500";
}

/* ── Component ────────────────────────────────────────────────────── */

export default function BacktestPage() {
  // ── data ──
  const [stocks, setStocks] = useState<Stock[]>([]);
  const [results, setResults] = useState<BacktestResultItem[]>([]);
  const [models, setModels] = useState<ModelItem[]>([]);
  const [loading, setLoading] = useState(true);

  // ── form ──
  const [selectedSymbols, setSelectedSymbols] = useState<string[]>([]);
  const [startDate, setStartDate] = useState("2021-01-01");
  const [endDate, setEndDate] = useState("2025-12-31");
  const [initialCash, setInitialCash] = useState("100000");
  const [running, setRunning] = useState(false);
  const [runMsg, setRunMsg] = useState<string | null>(null);

  // ── retraining ──
  const [retraining, setRetraining] = useState(false);
  const [retrainMsg, setRetrainMsg] = useState<string | null>(null);

  // ── expanded result ──
  const [expandedId, setExpandedId] = useState<number | null>(null);

  // ── tab ──
  const [tab, setTab] = useState<"backtest" | "models">("backtest");

  /* ── load data ── */
  useEffect(() => {
    async function load() {
      try {
        const [s, r, m] = await Promise.all([
          api.stocks.list(true),
          api.ml.backtestResults(50),
          api.ml.models(),
        ]);
        setStocks(s);
        setResults(r);
        setModels(m);
        setSelectedSymbols(s.map((st) => st.symbol));
      } catch {
        /* empty — will show empty states */
      } finally {
        setLoading(false);
      }
    }
    load();
  }, []);

  /* ── actions ── */

  async function handleRunBacktest() {
    setRunning(true);
    setRunMsg(null);
    try {
      const resp = await api.ml.runBacktest({
        symbols: selectedSymbols.length ? selectedSymbols : undefined,
        start_date: startDate,
        end_date: endDate,
        initial_cash: parseFloat(initialCash) || 100_000,
      });
      setRunMsg(`Backtest queued (task ${resp.task_id})`);
      // Refresh results after a short delay
      setTimeout(async () => {
        try {
          const r = await api.ml.backtestResults(50);
          setResults(r);
        } catch { /* ignore */ }
      }, 5000);
    } catch (e) {
      setRunMsg(`Error: ${e instanceof Error ? e.message : "unknown"}`);
    } finally {
      setRunning(false);
    }
  }

  async function handleRetrain() {
    setRetraining(true);
    setRetrainMsg(null);
    try {
      const resp = await api.ml.retrain(
        selectedSymbols.length ? selectedSymbols : undefined,
        5,
      );
      setRetrainMsg(`Retraining queued (task ${resp.task_id})`);
      setTimeout(async () => {
        try {
          const m = await api.ml.models();
          setModels(m);
        } catch { /* ignore */ }
      }, 10000);
    } catch (e) {
      setRetrainMsg(`Error: ${e instanceof Error ? e.message : "unknown"}`);
    } finally {
      setRetraining(false);
    }
  }

  async function handleActivateModel(modelId: number) {
    try {
      await api.ml.activateModel(modelId);
      const m = await api.ml.models();
      setModels(m);
    } catch { /* ignore */ }
  }

  function toggleSymbol(sym: string) {
    setSelectedSymbols((prev) =>
      prev.includes(sym) ? prev.filter((s) => s !== sym) : [...prev, sym],
    );
  }

  if (loading) {
    return (
      <div className="flex h-64 items-center justify-center">
        <p className="text-muted-foreground">Loading...</p>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* ── Header ── */}
      <div>
        <h2 className="text-3xl font-bold tracking-tight">Backtest Console</h2>
        <p className="text-muted-foreground">
          Run strategies against historical data, compare results, and manage ML
          models
        </p>
      </div>

      {/* ── Tab selector ── */}
      <div className="flex gap-2">
        <Button
          variant={tab === "backtest" ? "default" : "outline"}
          size="sm"
          onClick={() => setTab("backtest")}
        >
          Backtesting
        </Button>
        <Button
          variant={tab === "models" ? "default" : "outline"}
          size="sm"
          onClick={() => setTab("models")}
        >
          Model Management
        </Button>
      </div>

      {/* ══════════ BACKTEST TAB ══════════ */}
      {tab === "backtest" && (
        <>
          {/* ── Run Backtest Form ── */}
          <Card>
            <CardHeader>
              <CardTitle>Run Backtest</CardTitle>
              <CardDescription>
                Select symbols and configure parameters to run a new backtest
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              {/* Symbol chips */}
              <div>
                <label className="mb-1 block text-sm font-medium">
                  Symbols
                </label>
                <div className="flex flex-wrap gap-2">
                  {stocks.map((s) => (
                    <button
                      key={s.symbol}
                      onClick={() => toggleSymbol(s.symbol)}
                      className={`rounded-full border px-3 py-1 text-xs font-medium transition-colors ${
                        selectedSymbols.includes(s.symbol)
                          ? "border-primary bg-primary/10 text-primary"
                          : "border-border text-muted-foreground hover:border-primary/50"
                      }`}
                    >
                      {s.symbol}
                    </button>
                  ))}
                  {stocks.length === 0 && (
                    <span className="text-xs text-muted-foreground">
                      No watchlist stocks — add some first
                    </span>
                  )}
                </div>
              </div>

              {/* Date range + cash */}
              <div className="grid grid-cols-3 gap-4">
                <div>
                  <label className="mb-1 block text-sm font-medium">
                    Start Date
                  </label>
                  <input
                    type="date"
                    value={startDate}
                    onChange={(e) => setStartDate(e.target.value)}
                    className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
                  />
                </div>
                <div>
                  <label className="mb-1 block text-sm font-medium">
                    End Date
                  </label>
                  <input
                    type="date"
                    value={endDate}
                    onChange={(e) => setEndDate(e.target.value)}
                    className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
                  />
                </div>
                <div>
                  <label className="mb-1 block text-sm font-medium">
                    Initial Cash ($)
                  </label>
                  <input
                    type="number"
                    value={initialCash}
                    onChange={(e) => setInitialCash(e.target.value)}
                    className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
                  />
                </div>
              </div>

              {/* Run button */}
              <div className="flex items-center gap-4">
                <Button
                  onClick={handleRunBacktest}
                  disabled={running || selectedSymbols.length === 0}
                >
                  {running ? "Running..." : "Run Backtest"}
                </Button>
                {runMsg && (
                  <span className="text-sm text-muted-foreground">
                    {runMsg}
                  </span>
                )}
              </div>
            </CardContent>
          </Card>

          {/* ── Results Table ── */}
          <Card>
            <CardHeader>
              <CardTitle>Backtest Results</CardTitle>
              <CardDescription>
                {results.length} result{results.length !== 1 ? "s" : ""}
              </CardDescription>
            </CardHeader>
            <CardContent>
              {results.length === 0 ? (
                <div className="flex h-32 items-center justify-center rounded-md border border-dashed">
                  <p className="text-sm text-muted-foreground">
                    No backtest results yet — run a backtest above
                  </p>
                </div>
              ) : (
                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="border-b text-left text-muted-foreground">
                        <th className="pb-2 pr-4 font-medium">Strategy</th>
                        <th className="pb-2 pr-4 font-medium">Symbols</th>
                        <th className="pb-2 pr-4 font-medium">Period</th>
                        <th className="pb-2 pr-4 font-medium text-right">
                          Return
                        </th>
                        <th className="pb-2 pr-4 font-medium text-right">
                          Sharpe
                        </th>
                        <th className="pb-2 pr-4 font-medium text-right">
                          Max DD
                        </th>
                        <th className="pb-2 pr-4 font-medium text-right">
                          Win Rate
                        </th>
                        <th className="pb-2 pr-4 font-medium text-right">
                          Profit Factor
                        </th>
                        <th className="pb-2 pr-4 font-medium text-right">
                          Trades
                        </th>
                        <th className="pb-2 pr-4 font-medium text-right">
                          Benchmark
                        </th>
                        <th className="pb-2 font-medium">Date</th>
                      </tr>
                    </thead>
                    <tbody>
                      {results.map((r) => (
                        <>
                          <tr
                            key={r.id}
                            className="cursor-pointer border-b border-border/50 hover:bg-muted/50"
                            onClick={() =>
                              setExpandedId(
                                expandedId === r.id ? null : r.id,
                              )
                            }
                          >
                            <td className="py-2 pr-4 font-medium">
                              {r.strategy_name}
                            </td>
                            <td className="py-2 pr-4 text-xs">
                              {r.symbols.length > 30
                                ? r.symbols.slice(0, 30) + "..."
                                : r.symbols}
                            </td>
                            <td className="py-2 pr-4 text-xs text-muted-foreground">
                              {r.start_date.slice(0, 10)} →{" "}
                              {r.end_date.slice(0, 10)}
                            </td>
                            <td
                              className={`py-2 pr-4 text-right font-mono font-medium ${returnColor(r.total_return)}`}
                            >
                              {fmtPct(r.total_return)}
                            </td>
                            <td className="py-2 pr-4 text-right font-mono">
                              {fmtNum(r.sharpe_ratio)}
                            </td>
                            <td className="py-2 pr-4 text-right font-mono text-red-400">
                              {fmtPct(r.max_drawdown)}
                            </td>
                            <td className="py-2 pr-4 text-right font-mono">
                              {fmtPct(r.win_rate)}
                            </td>
                            <td className="py-2 pr-4 text-right font-mono">
                              {fmtNum(r.profit_factor)}
                            </td>
                            <td className="py-2 pr-4 text-right font-mono">
                              {r.trades_count}
                            </td>
                            <td
                              className={`py-2 pr-4 text-right font-mono ${r.benchmark_return != null ? returnColor(r.benchmark_return) : ""}`}
                            >
                              {r.benchmark_return != null
                                ? fmtPct(r.benchmark_return)
                                : "—"}
                            </td>
                            <td className="py-2 text-xs text-muted-foreground">
                              {new Date(r.created_at).toLocaleDateString()}
                            </td>
                          </tr>

                          {/* Expanded detail row */}
                          {expandedId === r.id && (
                            <tr key={`${r.id}-detail`}>
                              <td colSpan={11} className="p-4">
                                <div className="grid grid-cols-2 gap-6">
                                  {/* Performance Summary */}
                                  <div className="space-y-2">
                                    <h4 className="text-sm font-semibold">
                                      Performance Summary
                                    </h4>
                                    <div className="grid grid-cols-2 gap-2 text-sm">
                                      <div>
                                        <span className="text-muted-foreground">
                                          Model:
                                        </span>{" "}
                                        {r.model_name ?? "N/A"}{" "}
                                        {r.model_version ?? ""}
                                      </div>
                                      <div>
                                        <span className="text-muted-foreground">
                                          Trades:
                                        </span>{" "}
                                        {r.trades_count}
                                      </div>
                                      <div>
                                        <span className="text-muted-foreground">
                                          Return:
                                        </span>{" "}
                                        <span className={returnColor(r.total_return)}>
                                          {fmtPct(r.total_return)}
                                        </span>
                                      </div>
                                      <div>
                                        <span className="text-muted-foreground">
                                          Benchmark:
                                        </span>{" "}
                                        <span
                                          className={
                                            r.benchmark_return != null
                                              ? returnColor(r.benchmark_return)
                                              : ""
                                          }
                                        >
                                          {r.benchmark_return != null
                                            ? fmtPct(r.benchmark_return)
                                            : "—"}
                                        </span>
                                      </div>
                                      <div>
                                        <span className="text-muted-foreground">
                                          Alpha:
                                        </span>{" "}
                                        <span
                                          className={returnColor(
                                            r.total_return -
                                              (r.benchmark_return ?? 0),
                                          )}
                                        >
                                          {fmtPct(
                                            r.total_return -
                                              (r.benchmark_return ?? 0),
                                          )}
                                        </span>
                                      </div>
                                      <div>
                                        <span className="text-muted-foreground">
                                          Sharpe:
                                        </span>{" "}
                                        {fmtNum(r.sharpe_ratio)}
                                      </div>
                                    </div>
                                  </div>

                                  {/* Risk Metrics */}
                                  <div className="space-y-2">
                                    <h4 className="text-sm font-semibold">
                                      Risk Metrics
                                    </h4>
                                    <div className="grid grid-cols-2 gap-2 text-sm">
                                      <div>
                                        <span className="text-muted-foreground">
                                          Max Drawdown:
                                        </span>{" "}
                                        <span className="text-red-400">
                                          {fmtPct(r.max_drawdown)}
                                        </span>
                                      </div>
                                      <div>
                                        <span className="text-muted-foreground">
                                          Win Rate:
                                        </span>{" "}
                                        {fmtPct(r.win_rate)}
                                      </div>
                                      <div>
                                        <span className="text-muted-foreground">
                                          Profit Factor:
                                        </span>{" "}
                                        {fmtNum(r.profit_factor)}
                                      </div>
                                      <div>
                                        <span className="text-muted-foreground">
                                          Symbols:
                                        </span>{" "}
                                        {r.symbols}
                                      </div>
                                    </div>

                                    {/* Per-symbol report */}
                                    {r.report_json &&
                                      typeof r.report_json === "object" && (
                                        <div className="mt-3">
                                          <h4 className="mb-1 text-sm font-semibold">
                                            Per-Symbol Breakdown
                                          </h4>
                                          <div className="max-h-48 overflow-y-auto rounded border border-border p-2 text-xs font-mono">
                                            <pre>
                                              {JSON.stringify(
                                                r.report_json,
                                                null,
                                                2,
                                              )}
                                            </pre>
                                          </div>
                                        </div>
                                      )}
                                  </div>
                                </div>
                              </td>
                            </tr>
                          )}
                        </>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </CardContent>
          </Card>
        </>
      )}

      {/* ══════════ MODELS TAB ══════════ */}
      {tab === "models" && (
        <>
          {/* ── Actions ── */}
          <Card>
            <CardHeader>
              <CardTitle>Model Management</CardTitle>
              <CardDescription>
                View trained models, activate for inference, or trigger
                retraining
              </CardDescription>
            </CardHeader>
            <CardContent>
              <div className="flex items-center gap-4">
                <Button
                  onClick={handleRetrain}
                  disabled={retraining}
                  variant="outline"
                >
                  {retraining ? "Queuing..." : "Retrain Model"}
                </Button>
                {retrainMsg && (
                  <span className="text-sm text-muted-foreground">
                    {retrainMsg}
                  </span>
                )}
              </div>
            </CardContent>
          </Card>

          {/* ── Models List ── */}
          {models.length === 0 ? (
            <Card>
              <CardContent className="py-8">
                <div className="flex h-32 items-center justify-center rounded-md border border-dashed">
                  <p className="text-sm text-muted-foreground">
                    No trained models yet — run training on your GPU PC or
                    trigger retraining above
                  </p>
                </div>
              </CardContent>
            </Card>
          ) : (
            <div className="grid gap-4 md:grid-cols-2">
              {models.map((m) => (
                <Card
                  key={m.id}
                  className={
                    m.is_active ? "border-primary/50 bg-primary/5" : ""
                  }
                >
                  <CardHeader className="pb-2">
                    <div className="flex items-center justify-between">
                      <CardTitle className="text-base">
                        {m.model_name}{" "}
                        <span className="text-xs font-normal text-muted-foreground">
                          v{m.version}
                        </span>
                      </CardTitle>
                      {m.is_active ? (
                        <span className="rounded-full bg-green-500/10 px-2 py-0.5 text-xs font-medium text-green-500">
                          ACTIVE
                        </span>
                      ) : (
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => handleActivateModel(m.id)}
                        >
                          Activate
                        </Button>
                      )}
                    </div>
                    <CardDescription>
                      Trained{" "}
                      {new Date(m.training_date).toLocaleDateString()} on{" "}
                      {m.symbols_trained}
                    </CardDescription>
                  </CardHeader>
                  <CardContent>
                    <div className="grid grid-cols-2 gap-2 text-sm">
                      <div>
                        <span className="text-muted-foreground">
                          Features:
                        </span>{" "}
                        {m.feature_count}
                      </div>
                      <div>
                        <span className="text-muted-foreground">
                          File:
                        </span>{" "}
                        <span className="font-mono text-xs">
                          {m.file_path.split("/").pop()}
                        </span>
                      </div>

                      {/* Validation metrics */}
                      {m.validation_metrics && (
                        <>
                          {m.validation_metrics.accuracy != null && (
                            <div>
                              <span className="text-muted-foreground">
                                Accuracy:
                              </span>{" "}
                              {fmtPct(
                                m.validation_metrics.accuracy as number,
                              )}
                            </div>
                          )}
                          {m.validation_metrics.f1_weighted != null && (
                            <div>
                              <span className="text-muted-foreground">
                                F1 (weighted):
                              </span>{" "}
                              {fmtNum(
                                m.validation_metrics.f1_weighted as number,
                                3,
                              )}
                            </div>
                          )}
                          {m.validation_metrics.sharpe != null && (
                            <div>
                              <span className="text-muted-foreground">
                                Sharpe:
                              </span>{" "}
                              {fmtNum(
                                m.validation_metrics.sharpe as number,
                              )}
                            </div>
                          )}
                          {m.validation_metrics.total_return != null && (
                            <div>
                              <span className="text-muted-foreground">
                                Backtest Return:
                              </span>{" "}
                              <span
                                className={returnColor(
                                  m.validation_metrics
                                    .total_return as number,
                                )}
                              >
                                {fmtPct(
                                  m.validation_metrics
                                    .total_return as number,
                                )}
                              </span>
                            </div>
                          )}
                        </>
                      )}
                    </div>

                    {/* Full validation metrics JSON */}
                    {m.validation_metrics && (
                      <details className="mt-3">
                        <summary className="cursor-pointer text-xs text-muted-foreground hover:text-foreground">
                          Full validation metrics
                        </summary>
                        <pre className="mt-1 max-h-40 overflow-y-auto rounded border border-border p-2 text-xs font-mono">
                          {JSON.stringify(m.validation_metrics, null, 2)}
                        </pre>
                      </details>
                    )}
                  </CardContent>
                </Card>
              ))}
            </div>
          )}
        </>
      )}
    </div>
  );
}
