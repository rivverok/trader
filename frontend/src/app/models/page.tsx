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
import { api, type ModelItem, type TaskInfo } from "@/lib/api";

function StatusBadge({ active }: { active: boolean }) {
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-xs font-medium ${
        active
          ? "border-green-500/30 bg-green-500/10 text-green-500"
          : "border-gray-500/30 bg-gray-500/10 text-gray-400"
      }`}
    >
      <span className={`h-1.5 w-1.5 rounded-full ${active ? "bg-green-500" : "bg-gray-400"}`} />
      {active ? "Active" : "Inactive"}
    </span>
  );
}

function TrainingPanel({ taskId }: { taskId: string }) {
  const [info, setInfo] = useState<TaskInfo | null>(null);
  const [done, setDone] = useState(false);
  const [elapsed, setElapsed] = useState(0);
  const [startTime] = useState(() => Date.now());

  useEffect(() => {
    const timer = setInterval(() => setElapsed(Math.floor((Date.now() - startTime) / 1000)), 1000);
    return () => clearInterval(timer);
  }, [startTime]);

  useEffect(() => {
    if (done) return;
    const poll = async () => {
      try {
        const data = await api.tasks.get(taskId);
        setInfo(data);
        if (data.status === "SUCCESS" || data.status === "FAILURE" || data.status === "REVOKED") {
          setDone(true);
        }
      } catch {
        // ignore
      }
    };
    poll();
    const timer = setInterval(poll, 2000);
    return () => clearInterval(timer);
  }, [taskId, done]);

  const progress = info?.progress;
  const pct =
    progress?.total_symbols && progress?.symbol_index
      ? Math.round(
          ((progress.symbol_index - 1 + (progress.fold_index && progress.total_folds ? progress.fold_index / progress.total_folds : 0)) /
            progress.total_symbols) *
            100
        )
      : 0;

  const fmtTime = (s: number) => {
    const m = Math.floor(s / 60);
    const sec = s % 60;
    return m > 0 ? `${m}m ${sec}s` : `${sec}s`;
  };

  const estimatedTotal =
    pct > 5 ? Math.round(elapsed / (pct / 100)) : null;
  const estimatedRemaining = estimatedTotal ? estimatedTotal - elapsed : null;

  if (done && info?.status === "SUCCESS") {
    return (
      <div className="rounded-lg border border-green-500/30 bg-green-500/5 p-4">
        <div className="flex items-center gap-2 mb-1">
          <span className="h-2 w-2 rounded-full bg-green-500" />
          <span className="text-sm font-medium text-green-500">Training Complete</span>
          <span className="text-xs text-muted-foreground ml-auto">Took {fmtTime(elapsed)}</span>
        </div>
        <p className="text-xs text-muted-foreground">
          {info.result ? formatTrainResult(info.result) : "Model trained successfully. Refresh to see updated model."}
        </p>
      </div>
    );
  }

  if (done && info?.status === "FAILURE") {
    return (
      <div className="rounded-lg border border-red-500/30 bg-red-500/5 p-4">
        <div className="flex items-center gap-2 mb-1">
          <span className="h-2 w-2 rounded-full bg-red-500" />
          <span className="text-sm font-medium text-red-500">Training Failed</span>
        </div>
        <p className="text-xs text-red-400">{info.error || "Unknown error"}</p>
      </div>
    );
  }

  return (
    <div className="rounded-lg border border-blue-500/30 bg-blue-500/5 p-4 space-y-3">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span className="h-2 w-2 rounded-full bg-blue-500 animate-pulse" />
          <span className="text-sm font-medium">Training in Progress</span>
        </div>
        <span className="text-xs text-muted-foreground font-mono tabular-nums">{fmtTime(elapsed)}</span>
      </div>

      {progress?.current_symbol ? (
        <>
          <div className="flex items-center justify-between text-xs">
            <span className="text-muted-foreground">
              Training <span className="font-mono font-medium text-foreground">{progress.current_symbol}</span>
              {progress.symbol_index && progress.total_symbols && (
                <span className="ml-1">({progress.symbol_index}/{progress.total_symbols} stocks)</span>
              )}
              {progress.fold_index && progress.total_folds && (
                <span className="ml-1 text-muted-foreground">· fold {progress.fold_index}/{progress.total_folds}</span>
              )}
            </span>
            <span className="font-mono tabular-nums text-muted-foreground">{pct}%</span>
          </div>
          <div className="h-2 w-full rounded-full bg-muted overflow-hidden">
            <div className="h-full rounded-full bg-blue-500 transition-all duration-500" style={{ width: `${pct}%` }} />
          </div>
          <div className="flex items-center justify-between text-xs text-muted-foreground">
            {progress.best_score != null && progress.best_score > 0 ? (
              <span>
                Best so far: <span className="font-mono text-foreground">{progress.best_model_type}</span> F1={progress.best_score.toFixed(4)}
              </span>
            ) : (
              <span>Evaluating models…</span>
            )}
            {estimatedRemaining && estimatedRemaining > 0 && (
              <span className="font-mono tabular-nums">~{fmtTime(estimatedRemaining)} remaining</span>
            )}
          </div>
        </>
      ) : (
        <div className="text-xs text-muted-foreground">
          {info?.status === "PENDING" ? "Queued, waiting for worker…" : "Loading data and preparing features…"}
        </div>
      )}
    </div>
  );
}

function formatTrainResult(raw: string): string {
  try {
    const jsonStr = raw.replace(/'/g, '"').replace(/\bTrue\b/g, "true").replace(/\bFalse\b/g, "false").replace(/\bNone\b/g, "null");
    const obj = JSON.parse(jsonStr);
    return `${obj.model} ${obj.version} — F1: ${Number(obj.f1_macro).toFixed(4)}, ${obj.features} features`;
  } catch {
    return raw.slice(0, 200);
  }
}

function MetricCard({ label, value, sub }: { label: string; value: string; sub?: string }) {
  return (
    <div className="rounded-lg border p-3">
      <p className="text-xs text-muted-foreground">{label}</p>
      <p className="text-lg font-bold font-mono tabular-nums mt-0.5">{value}</p>
      {sub && <p className="text-xs text-muted-foreground mt-0.5">{sub}</p>}
    </div>
  );
}

function FoldMetricsTable({ metrics }: { metrics: Array<Record<string, unknown>> }) {
  if (!metrics || metrics.length === 0) return null;

  // Group by symbol
  const bySymbol: Record<string, Array<Record<string, unknown>>> = {};
  for (const m of metrics) {
    const sym = m.symbol as string;
    if (!bySymbol[sym]) bySymbol[sym] = [];
    bySymbol[sym].push(m);
  }

  return (
    <div className="rounded-md border overflow-hidden">
      <table className="w-full text-xs">
        <thead>
          <tr className="border-b bg-muted/50">
            <th className="text-left p-2 font-medium">Symbol</th>
            <th className="text-left p-2 font-medium">Fold</th>
            <th className="text-left p-2 font-medium">Model</th>
            <th className="text-right p-2 font-medium">F1</th>
            <th className="text-right p-2 font-medium">Accuracy</th>
            <th className="text-right p-2 font-medium">Precision</th>
            <th className="text-right p-2 font-medium">Recall</th>
            <th className="text-right p-2 font-medium">Train</th>
            <th className="text-right p-2 font-medium">Test</th>
          </tr>
        </thead>
        <tbody>
          {Object.entries(bySymbol).map(([symbol, folds]) =>
            folds.map((f, i) => (
              <tr key={`${symbol}-${i}`} className="border-b last:border-0">
                {i === 0 && (
                  <td className="p-2 font-mono font-medium" rowSpan={folds.length}>
                    {symbol}
                  </td>
                )}
                <td className="p-2 text-muted-foreground">{String(f.fold)}</td>
                <td className="p-2 font-mono">{String(f.model_type)}</td>
                <td className="p-2 text-right font-mono tabular-nums">{Number(f.f1_macro).toFixed(4)}</td>
                <td className="p-2 text-right font-mono tabular-nums">{Number(f.accuracy).toFixed(4)}</td>
                <td className="p-2 text-right font-mono tabular-nums">{Number(f.precision_macro).toFixed(4)}</td>
                <td className="p-2 text-right font-mono tabular-nums">{Number(f.recall_macro).toFixed(4)}</td>
                <td className="p-2 text-right font-mono tabular-nums text-muted-foreground">{String(f.train_rows)}</td>
                <td className="p-2 text-right font-mono tabular-nums text-muted-foreground">{String(f.test_rows)}</td>
              </tr>
            ))
          )}
        </tbody>
      </table>
    </div>
  );
}

function FeatureImportanceBar({ features }: { features: Record<string, number> }) {
  const sorted = Object.entries(features).sort(([, a], [, b]) => b - a).slice(0, 15);
  const max = sorted[0]?.[1] || 1;

  return (
    <div className="space-y-1.5">
      {sorted.map(([name, importance]) => (
        <div key={name} className="flex items-center gap-2 text-xs">
          <span className="w-32 truncate text-right font-mono text-muted-foreground" title={name}>
            {name}
          </span>
          <div className="flex-1 h-4 bg-muted rounded overflow-hidden">
            <div
              className="h-full bg-primary/60 rounded"
              style={{ width: `${(importance / max) * 100}%` }}
            />
          </div>
          <span className="w-12 text-right font-mono tabular-nums text-muted-foreground">
            {importance.toFixed(0)}
          </span>
        </div>
      ))}
    </div>
  );
}

export default function ModelsPage() {
  const [models, setModels] = useState<ModelItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [trainingTaskId, setTrainingTaskId] = useState<string | null>(null);
  const [triggering, setTriggering] = useState(false);
  const [expandedId, setExpandedId] = useState<number | null>(null);
  const [activating, setActivating] = useState<number | null>(null);

  const refresh = useCallback(async () => {
    try {
      const data = await api.ml.models();
      setModels(data);
    } catch {
      // ignore
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const handleRetrain = async () => {
    setTriggering(true);
    try {
      const result = await api.ml.retrain();
      setTrainingTaskId(result.task_id);
    } catch {
      // ignore
    } finally {
      setTriggering(false);
    }
  };

  const handleActivate = async (modelId: number) => {
    setActivating(modelId);
    try {
      await api.ml.activateModel(modelId);
      await refresh();
    } catch {
      // ignore
    } finally {
      setActivating(null);
    }
  };

  const activeModel = models.find((m) => m.is_active);
  const metrics = activeModel?.validation_metrics as Record<string, unknown> | null;
  const foldMetrics = (metrics?.fold_metrics ?? []) as Array<Record<string, unknown>>;
  const topFeatures = (metrics?.top_features ?? {}) as Record<string, number>;
  const bestF1 = metrics?.best_f1_macro as number | undefined;

  // Compute average metrics across all folds for the active model
  const avgMetrics =
    foldMetrics.length > 0
      ? {
          f1: foldMetrics.reduce((s, f) => s + Number(f.f1_macro), 0) / foldMetrics.length,
          accuracy: foldMetrics.reduce((s, f) => s + Number(f.accuracy), 0) / foldMetrics.length,
          precision: foldMetrics.reduce((s, f) => s + Number(f.precision_macro), 0) / foldMetrics.length,
          recall: foldMetrics.reduce((s, f) => s + Number(f.recall_macro), 0) / foldMetrics.length,
        }
      : null;

  const symbolCount = activeModel?.symbols_trained.split(",").length ?? 0;

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-3xl font-bold tracking-tight">ML Models</h2>
          <p className="text-muted-foreground">
            Trained models, metrics, and retraining
          </p>
        </div>
        <div className="flex gap-2">
          <Button onClick={refresh} variant="outline" size="sm">
            Refresh
          </Button>
          <Button onClick={handleRetrain} disabled={triggering || !!trainingTaskId} size="sm">
            {triggering ? "Starting…" : trainingTaskId ? "Training…" : "Retrain Model"}
          </Button>
        </div>
      </div>

      {/* Training progress */}
      {trainingTaskId && (
        <TrainingPanel taskId={trainingTaskId} />
      )}

      {/* Active model summary */}
      {activeModel ? (
        <Card>
          <CardHeader>
            <div className="flex items-center justify-between">
              <div>
                <CardTitle className="text-base">Active Model</CardTitle>
                <CardDescription className="font-mono">
                  {activeModel.model_name} {activeModel.version}
                </CardDescription>
              </div>
              <StatusBadge active={true} />
            </div>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
              <MetricCard
                label="Best F1 (macro)"
                value={bestF1 != null ? bestF1.toFixed(4) : "—"}
                sub="Walk-forward best"
              />
              <MetricCard
                label="Avg Accuracy"
                value={avgMetrics ? avgMetrics.accuracy.toFixed(4) : "—"}
                sub="Across all folds"
              />
              <MetricCard
                label="Features"
                value={String(activeModel.feature_count)}
                sub="Technical indicators"
              />
              <MetricCard
                label="Stocks"
                value={String(symbolCount)}
                sub={new Date(activeModel.training_date).toLocaleDateString(undefined, {
                  month: "short",
                  day: "numeric",
                  year: "numeric",
                  hour: "numeric",
                  minute: "2-digit",
                })}
              />
            </div>

            {/* Top features */}
            {Object.keys(topFeatures).length > 0 && (
              <div>
                <h3 className="text-sm font-medium mb-2">Top Feature Importances</h3>
                <FeatureImportanceBar features={topFeatures} />
              </div>
            )}
          </CardContent>
        </Card>
      ) : (
        !loading && (
          <Card>
            <CardContent className="py-8 text-center">
              <p className="text-muted-foreground">No trained model yet. Click &quot;Retrain Model&quot; to train one.</p>
            </CardContent>
          </Card>
        )
      )}

      {/* All models history */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Model History</CardTitle>
          <CardDescription>All trained models — click to expand metrics</CardDescription>
        </CardHeader>
        <CardContent>
          {loading ? (
            <p className="text-sm text-muted-foreground py-4 text-center">Loading…</p>
          ) : models.length === 0 ? (
            <p className="text-sm text-muted-foreground py-4 text-center">No models trained yet</p>
          ) : (
            <div className="space-y-2">
              {models.map((m) => {
                const isExpanded = expandedId === m.id;
                const mMetrics = m.validation_metrics as Record<string, unknown> | null;
                const mFolds = (mMetrics?.fold_metrics ?? []) as Array<Record<string, unknown>>;
                const mFeatures = (mMetrics?.top_features ?? {}) as Record<string, number>;
                const mBestF1 = mMetrics?.best_f1_macro as number | undefined;
                const promoted = mMetrics?.auto_promoted as boolean | undefined;

                return (
                  <div key={m.id} className="rounded-lg border">
                    <button
                      className="flex w-full items-center justify-between p-3 text-left hover:bg-muted/50 transition-colors"
                      onClick={() => setExpandedId(isExpanded ? null : m.id)}
                    >
                      <div className="flex items-center gap-3 min-w-0">
                        <StatusBadge active={m.is_active} />
                        <div className="min-w-0">
                          <span className="font-mono text-sm font-medium">{m.model_name}</span>
                          <span className="text-xs text-muted-foreground ml-2">{m.version}</span>
                          <div className="flex gap-3 text-xs text-muted-foreground mt-0.5">
                            <span>
                              {new Date(m.training_date).toLocaleDateString(undefined, {
                                month: "short",
                                day: "numeric",
                                hour: "numeric",
                                minute: "2-digit",
                              })}
                            </span>
                            <span>{m.feature_count} features</span>
                            <span>{m.symbols_trained.split(",").length} stocks</span>
                            {mBestF1 != null && <span>F1: {mBestF1.toFixed(4)}</span>}
                            {promoted === false && (
                              <span className="text-yellow-500">not promoted (lower F1)</span>
                            )}
                          </div>
                        </div>
                      </div>
                      <div className="flex items-center gap-2 shrink-0">
                        {!m.is_active && (
                          <Button
                            variant="outline"
                            size="sm"
                            className="h-7 px-2 text-xs"
                            disabled={activating === m.id}
                            onClick={(e) => {
                              e.stopPropagation();
                              handleActivate(m.id);
                            }}
                          >
                            {activating === m.id ? "…" : "Activate"}
                          </Button>
                        )}
                        <span className="text-xs text-muted-foreground">{isExpanded ? "▲" : "▼"}</span>
                      </div>
                    </button>
                    {isExpanded && (
                      <div className="border-t p-3 space-y-4">
                        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                          <MetricCard label="Best F1" value={mBestF1?.toFixed(4) ?? "—"} />
                          <MetricCard label="Features" value={String(m.feature_count)} />
                          <MetricCard label="Stocks" value={String(m.symbols_trained.split(",").length)} />
                          <MetricCard
                            label="Symbols"
                            value=""
                            sub={m.symbols_trained.split(",").join(", ")}
                          />
                        </div>
                        {Object.keys(mFeatures).length > 0 && (
                          <div>
                            <h4 className="text-sm font-medium mb-2">Feature Importances</h4>
                            <FeatureImportanceBar features={mFeatures} />
                          </div>
                        )}
                        {mFolds.length > 0 && (
                          <div>
                            <h4 className="text-sm font-medium mb-2">Walk-Forward Fold Metrics</h4>
                            <FoldMetricsTable metrics={mFolds} />
                          </div>
                        )}
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
