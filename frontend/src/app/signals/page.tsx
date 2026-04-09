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
  type StockAnalysis,
  type MLSignalItem,
  type UsageSummary,
} from "@/lib/api";

function sentimentColor(score: number): string {
  if (score >= 0.3) return "text-green-500";
  if (score <= -0.3) return "text-red-500";
  return "text-yellow-500";
}

function sentimentLabel(score: number): string {
  if (score >= 0.3) return "Bullish";
  if (score <= -0.3) return "Bearish";
  return "Neutral";
}

function signalColor(signal: string): string {
  if (signal === "buy") return "text-green-500";
  if (signal === "sell") return "text-red-500";
  return "text-yellow-500";
}

function signalBadge(signal: string) {
  const color =
    signal === "buy"
      ? "bg-green-500/10 text-green-500"
      : signal === "sell"
      ? "bg-red-500/10 text-red-500"
      : "bg-yellow-500/10 text-yellow-500";
  return (
    <span className={`rounded-full px-2 py-0.5 text-xs font-medium uppercase ${color}`}>
      {signal}
    </span>
  );
}

function confidenceBar(confidence: number) {
  const pct = Math.round(confidence * 100);
  return (
    <div className="flex items-center gap-2">
      <div className="h-2 w-24 rounded-full bg-muted">
        <div
          className="h-2 rounded-full bg-primary"
          style={{ width: `${pct}%` }}
        />
      </div>
      <span className="text-xs text-muted-foreground">{pct}%</span>
    </div>
  );
}

export default function SignalsPage() {
  const [stocks, setStocks] = useState<Stock[]>([]);
  const [analyses, setAnalyses] = useState<Record<string, StockAnalysis>>({});
  const [mlSignals, setMlSignals] = useState<Record<string, MLSignalItem[]>>({});
  const [usage, setUsage] = useState<UsageSummary | null>(null);
  const [selectedSymbol, setSelectedSymbol] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const load = async () => {
      try {
        const watchlist = await api.stocks.list(true);
        setStocks(watchlist);

        const analysisResults: Record<string, StockAnalysis> = {};
        const signalResults: Record<string, MLSignalItem[]> = {};
        for (const s of watchlist) {
          try {
            analysisResults[s.symbol] = await api.analysis.forStock(s.symbol);
          } catch {}
          try {
            signalResults[s.symbol] = await api.ml.signals(s.symbol, 5);
          } catch {}
        }
        setAnalyses(analysisResults);
        setMlSignals(signalResults);

        if (watchlist.length > 0) {
          setSelectedSymbol(watchlist[0].symbol);
        }

        const u = await api.analysis.usage();
        setUsage(u);
      } catch {
      } finally {
        setLoading(false);
      }
    };
    load();
  }, []);

  const triggerAnalysis = async (task: string) => {
    try {
      await api.analysis.trigger(task);
    } catch {
      // Silently fail
    }
  };

  const selectedAnalysis = selectedSymbol ? analyses[selectedSymbol] : null;

  return (
    <div className="space-y-8">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-3xl font-bold tracking-tight">Signals</h2>
          <p className="text-muted-foreground">
            ML model signals and Claude analysis for watchlist stocks
          </p>
        </div>
        <div className="flex gap-2">
          <Button size="sm" variant="outline" onClick={() => triggerAnalysis("sentiment")}>
            Run Sentiment
          </Button>
          <Button size="sm" variant="outline" onClick={() => triggerAnalysis("synthesis")}>
            Run Synthesis
          </Button>
        </div>
      </div>

      {loading ? (
        <div className="flex h-64 items-center justify-center">
          <p className="text-muted-foreground">Loading analysis data...</p>
        </div>
      ) : stocks.length === 0 ? (
        <Card>
          <CardContent className="flex h-64 items-center justify-center">
            <p className="text-muted-foreground">
              Add stocks to your watchlist on the Dashboard to see signals.
            </p>
          </CardContent>
        </Card>
      ) : (
        <>
          {/* Stock selector + overview cards */}
          <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
            {stocks.map((stock) => {
              const a = analyses[stock.symbol];
              const synth = a?.latest_synthesis;
              const latestMl = mlSignals[stock.symbol]?.[0];
              return (
                <Card
                  key={stock.symbol}
                  className={`cursor-pointer transition-colors hover:border-primary ${
                    selectedSymbol === stock.symbol ? "border-primary" : ""
                  }`}
                  onClick={() => setSelectedSymbol(stock.symbol)}
                >
                  <CardHeader className="pb-2">
                    <CardDescription>{stock.name || stock.symbol}</CardDescription>
                    <CardTitle className="flex items-center justify-between text-xl">
                      {stock.symbol}
                      <div className="flex gap-1.5">
                        {latestMl && signalBadge(latestMl.signal)}
                        {synth ? (
                          <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${
                            synth.overall_sentiment >= 0.3
                              ? "bg-green-500/10 text-green-500"
                              : synth.overall_sentiment <= -0.3
                              ? "bg-red-500/10 text-red-500"
                              : "bg-yellow-500/10 text-yellow-500"
                          }`}>
                            {sentimentLabel(synth.overall_sentiment)}
                          </span>
                        ) : null}
                      </div>
                    </CardTitle>
                  </CardHeader>
                  <CardContent>
                    <div className="space-y-1">
                      {latestMl && (
                        <div className="flex items-center justify-between text-sm">
                          <span className="text-muted-foreground">ML Signal</span>
                          <span className={signalColor(latestMl.signal)}>
                            {latestMl.signal.toUpperCase()} ({Math.round(latestMl.confidence * 100)}%)
                          </span>
                        </div>
                      )}
                      {synth && (
                        <div className="flex items-center justify-between text-sm">
                          <span className="text-muted-foreground">Claude</span>
                          <span className={sentimentColor(synth.overall_sentiment)}>
                            {synth.overall_sentiment >= 0 ? "+" : ""}
                            {synth.overall_sentiment.toFixed(2)}
                          </span>
                        </div>
                      )}
                      {!latestMl && !synth && (
                        <p className="text-xs text-muted-foreground">No signals yet</p>
                      )}
                    </div>
                  </CardContent>
                </Card>
              );
            })}
          </div>

          {/* Selected stock detail */}
          {selectedSymbol && (
            <div className="grid gap-4 md:grid-cols-2">
              {/* ML Signal detail */}
              {mlSignals[selectedSymbol] && mlSignals[selectedSymbol].length > 0 && (
                <Card>
                  <CardHeader>
                    <CardTitle>ML Model Signal</CardTitle>
                    <CardDescription>
                      {mlSignals[selectedSymbol][0].model_name} v{mlSignals[selectedSymbol][0].model_version}
                    </CardDescription>
                  </CardHeader>
                  <CardContent className="space-y-4">
                    {/* Latest signal */}
                    <div className="flex items-center justify-between">
                      <div>
                        <p className="text-2xl font-bold">
                          <span className={signalColor(mlSignals[selectedSymbol][0].signal)}>
                            {mlSignals[selectedSymbol][0].signal.toUpperCase()}
                          </span>
                        </p>
                        <p className="text-sm text-muted-foreground">
                          {new Date(mlSignals[selectedSymbol][0].created_at).toLocaleString()}
                        </p>
                      </div>
                      <div className="text-right">
                        <p className="text-sm text-muted-foreground">Confidence</p>
                        {confidenceBar(mlSignals[selectedSymbol][0].confidence)}
                      </div>
                    </div>

                    {/* Feature importances */}
                    {mlSignals[selectedSymbol][0].feature_importances && (
                      <div>
                        <h4 className="mb-2 text-sm font-medium text-muted-foreground">
                          Top Features
                        </h4>
                        <div className="space-y-1.5">
                          {Object.entries(mlSignals[selectedSymbol][0].feature_importances)
                            .sort(([, a], [, b]) => b - a)
                            .slice(0, 8)
                            .map(([name, value]) => (
                              <div key={name} className="flex items-center gap-2">
                                <span className="w-32 truncate text-xs text-muted-foreground">
                                  {name}
                                </span>
                                <div className="h-1.5 flex-1 rounded-full bg-muted">
                                  <div
                                    className="h-1.5 rounded-full bg-primary"
                                    style={{ width: `${Math.min(value * 100 * 5, 100)}%` }}
                                  />
                                </div>
                                <span className="text-xs text-muted-foreground">
                                  {(value * 100).toFixed(1)}%
                                </span>
                              </div>
                            ))}
                        </div>
                      </div>
                    )}

                    {/* Signal history */}
                    {mlSignals[selectedSymbol].length > 1 && (
                      <div>
                        <h4 className="mb-2 text-sm font-medium text-muted-foreground">
                          Recent Signals
                        </h4>
                        <div className="space-y-1">
                          {mlSignals[selectedSymbol].slice(1).map((s) => (
                            <div key={s.id} className="flex items-center justify-between text-xs">
                              <span className={signalColor(s.signal)}>
                                {s.signal.toUpperCase()}
                              </span>
                              <span className="text-muted-foreground">
                                {Math.round(s.confidence * 100)}%
                              </span>
                              <span className="text-muted-foreground">
                                {new Date(s.created_at).toLocaleDateString()}
                              </span>
                            </div>
                          ))}
                        </div>
                      </div>
                    )}
                  </CardContent>
                </Card>
              )}

              {/* Claude Synthesis detail */}
              {analyses[selectedSymbol]?.latest_synthesis && (
                <Card>
                  <CardHeader>
                    <CardTitle>
                      Claude Synthesis
                    </CardTitle>
                    <CardDescription>
                      Model: {analyses[selectedSymbol].latest_synthesis!.claude_model_used} |{" "}
                      {new Date(analyses[selectedSymbol].latest_synthesis!.created_at).toLocaleString()}
                    </CardDescription>
                  </CardHeader>
                  <CardContent className="space-y-4">
                    <div className="flex items-center justify-between">
                      <div>
                        <p className="text-2xl font-bold">
                          <span className={sentimentColor(analyses[selectedSymbol].latest_synthesis!.overall_sentiment)}>
                            {sentimentLabel(analyses[selectedSymbol].latest_synthesis!.overall_sentiment)}
                          </span>
                        </p>
                        <p className="text-sm text-muted-foreground">
                          Score: {analyses[selectedSymbol].latest_synthesis!.overall_sentiment >= 0 ? "+" : ""}
                          {analyses[selectedSymbol].latest_synthesis!.overall_sentiment.toFixed(2)}
                        </p>
                      </div>
                      <div className="text-right">
                        <p className="text-sm text-muted-foreground">Confidence</p>
                        {confidenceBar(analyses[selectedSymbol].latest_synthesis!.confidence)}
                      </div>
                    </div>
                    {analyses[selectedSymbol].latest_synthesis!.reasoning_chain && (
                      <div>
                        <h4 className="mb-1 text-sm font-medium text-muted-foreground">
                          Reasoning Chain
                        </h4>
                        <p className="whitespace-pre-wrap text-sm">
                          {analyses[selectedSymbol].latest_synthesis!.reasoning_chain}
                        </p>
                      </div>
                    )}
                    <div className="grid gap-4 md:grid-cols-3">
                      {analyses[selectedSymbol].latest_synthesis!.key_factors && (
                        <div>
                          <h4 className="mb-1 text-sm font-medium text-muted-foreground">
                            Key Factors
                          </h4>
                          <ul className="space-y-1 text-sm">
                            {analyses[selectedSymbol].latest_synthesis!.key_factors!.map((f, i) => (
                              <li key={i} className="flex items-start gap-1">
                                <span className="text-primary">â€¢</span> {f}
                              </li>
                            ))}
                          </ul>
                        </div>
                      )}
                      {analyses[selectedSymbol].latest_synthesis!.risks && (
                        <div>
                          <h4 className="mb-1 text-sm font-medium text-red-400">
                            Risks
                          </h4>
                          <ul className="space-y-1 text-sm">
                            {analyses[selectedSymbol].latest_synthesis!.risks!.map((r, i) => (
                              <li key={i} className="flex items-start gap-1">
                                <span className="text-red-400">â€¢</span> {r}
                              </li>
                            ))}
                          </ul>
                        </div>
                      )}
                      {analyses[selectedSymbol].latest_synthesis!.opportunities && (
                        <div>
                          <h4 className="mb-1 text-sm font-medium text-green-400">
                            Opportunities
                          </h4>
                          <ul className="space-y-1 text-sm">
                            {analyses[selectedSymbol].latest_synthesis!.opportunities!.map((o, i) => (
                              <li key={i} className="flex items-start gap-1">
                                <span className="text-green-400">â€¢</span> {o}
                              </li>
                            ))}
                          </ul>
                        </div>
                      )}
                    </div>
                  </CardContent>
                </Card>
              )}

              {/* News sentiment feed */}
              <Card>
                <CardHeader>
                  <CardTitle>News Sentiment</CardTitle>
                  <CardDescription>
                    {(selectedAnalysis?.recent_news ?? []).length} analyzed articles
                  </CardDescription>
                </CardHeader>
                <CardContent>
                  {(selectedAnalysis?.recent_news ?? []).length === 0 ? (
                    <p className="text-sm text-muted-foreground">
                      No analyzed news yet. Run sentiment analysis.
                    </p>
                  ) : (
                    <div className="max-h-96 space-y-3 overflow-y-auto">
                      {(selectedAnalysis?.recent_news ?? []).map((n) => (
                        <div key={n.id} className="rounded-md border p-3">
                          <div className="flex items-start justify-between gap-2">
                            <p className="text-sm font-medium leading-tight">
                              {n.headline}
                            </p>
                            <span
                              className={`shrink-0 rounded-full px-2 py-0.5 text-xs font-medium ${
                                n.sentiment_score >= 0.3
                                  ? "bg-green-500/10 text-green-500"
                                  : n.sentiment_score <= -0.3
                                  ? "bg-red-500/10 text-red-500"
                                  : "bg-yellow-500/10 text-yellow-500"
                              }`}
                            >
                              {n.sentiment_score >= 0 ? "+" : ""}
                              {n.sentiment_score.toFixed(2)}
                            </span>
                          </div>
                          <p className="mt-1 text-xs text-muted-foreground">
                            {n.summary}
                          </p>
                          <div className="mt-1 flex gap-2 text-xs text-muted-foreground">
                            <span>Impact: {n.impact_severity}</span>
                            {n.material_event && (
                              <span className="font-medium text-yellow-500">
                                Material Event
                              </span>
                            )}
                            <span>
                              {new Date(n.published_at).toLocaleDateString()}
                            </span>
                          </div>
                        </div>
                      ))}
                    </div>
                  )}
                </CardContent>
              </Card>

              {/* Filing analyses */}
              <Card>
                <CardHeader>
                  <CardTitle>SEC Filing Analysis</CardTitle>
                  <CardDescription>
                    {(selectedAnalysis?.filing_analyses ?? []).length} analyzed filings
                  </CardDescription>
                </CardHeader>
                <CardContent>
                  {(selectedAnalysis?.filing_analyses ?? []).length === 0 ? (
                    <p className="text-sm text-muted-foreground">
                      No analyzed filings yet.
                    </p>
                  ) : (
                    <div className="space-y-4">
                      {(selectedAnalysis?.filing_analyses ?? []).map((f) => (
                        <div key={f.id} className="rounded-md border p-3 space-y-2">
                          <div className="flex items-center justify-between">
                            <span className="text-sm font-medium">
                              {f.filing_type}
                            </span>
                            <span className="text-xs text-muted-foreground">
                              {new Date(f.filed_date).toLocaleDateString()}
                            </span>
                          </div>
                          {f.revenue_trend && (
                            <div className="text-sm">
                              <span className="text-muted-foreground">
                                Revenue:{" "}
                              </span>
                              {f.revenue_trend}
                            </div>
                          )}
                          {f.margin_analysis && (
                            <div className="text-sm">
                              <span className="text-muted-foreground">
                                Margins:{" "}
                              </span>
                              {f.margin_analysis}
                            </div>
                          )}
                          {f.guidance_sentiment != null && (
                            <div className="text-sm">
                              <span className="text-muted-foreground">
                                Guidance:{" "}
                              </span>
                              <span className={sentimentColor(f.guidance_sentiment)}>
                                {f.guidance_sentiment >= 0 ? "+" : ""}
                                {f.guidance_sentiment.toFixed(2)}
                              </span>
                            </div>
                          )}
                          {f.key_findings && f.key_findings.length > 0 && (
                            <ul className="text-xs text-muted-foreground space-y-0.5">
                              {f.key_findings.map((finding, i) => (
                                <li key={i}>â€¢ {finding}</li>
                              ))}
                            </ul>
                          )}
                        </div>
                      ))}
                    </div>
                  )}
                </CardContent>
              </Card>
            </div>
          )}

          {/* Usage summary */}
          {usage && (
            <Card>
              <CardHeader>
                <CardTitle>Claude API Usage (30 days)</CardTitle>
                <CardDescription>
                  {usage.total_calls_30d} calls | Estimated cost: $
                  {usage.total_cost_30d.toFixed(2)}
                </CardDescription>
              </CardHeader>
              <CardContent>
                {usage.daily_breakdown.length === 0 ? (
                  <p className="text-sm text-muted-foreground">
                    No Claude API calls recorded yet.
                  </p>
                ) : (
                  <div className="overflow-x-auto">
                    <table className="w-full text-sm">
                      <thead>
                        <tr className="border-b text-left text-muted-foreground">
                          <th className="pb-2 font-medium">Date</th>
                          <th className="pb-2 font-medium">Task</th>
                          <th className="pb-2 font-medium">Model</th>
                          <th className="pb-2 font-medium text-right">Calls</th>
                          <th className="pb-2 font-medium text-right">Tokens</th>
                          <th className="pb-2 font-medium text-right">Cost</th>
                        </tr>
                      </thead>
                      <tbody>
                        {usage.daily_breakdown.slice(0, 20).map((d, i) => (
                          <tr key={i} className="border-b last:border-0">
                            <td className="py-2">{d.date}</td>
                            <td className="py-2">{d.task_type}</td>
                            <td className="py-2 text-muted-foreground">
                              {d.model.split("-").slice(-1)[0]}
                            </td>
                            <td className="py-2 text-right">{d.call_count}</td>
                            <td className="py-2 text-right font-mono">
                              {(d.total_input_tokens + d.total_output_tokens).toLocaleString()}
                            </td>
                            <td className="py-2 text-right font-mono">
                              ${d.total_cost.toFixed(4)}
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
        </>
      )}
    </div>
  );
}
