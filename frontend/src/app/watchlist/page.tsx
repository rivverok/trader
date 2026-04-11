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
  type DiscoveryLogItem,
  type WatchlistHint,
  type DiscoveryStatus,
} from "@/lib/api";

export default function WatchlistPage() {
  const [stocks, setStocks] = useState<Stock[]>([]);
  const [discoveryLog, setDiscoveryLog] = useState<DiscoveryLogItem[]>([]);
  const [hints, setHints] = useState<WatchlistHint[]>([]);
  const [discoveryStatus, setDiscoveryStatus] = useState<DiscoveryStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [triggering, setTriggering] = useState(false);
  const [submittingHint, setSubmittingHint] = useState(false);
  const [hintText, setHintText] = useState("");
  const [hintSymbol, setHintSymbol] = useState("");

  const refresh = () => {
    Promise.allSettled([
      api.stocks.list(true).then(setStocks),
      api.discovery.log(30).then(setDiscoveryLog),
      api.discovery.hints(undefined, 30).then(setHints),
      api.discovery.status().then(setDiscoveryStatus),
    ]).finally(() => setLoading(false));
  };

  useEffect(() => {
    refresh();
    const interval = setInterval(refresh, 30000);
    return () => clearInterval(interval);
  }, []);

  const handleTriggerDiscovery = async () => {
    setTriggering(true);
    try {
      await api.discovery.trigger();
    } catch {
      // ignore
    }
    setTriggering(false);
  };

  const handleSubmitHint = async () => {
    if (!hintText.trim()) return;
    setSubmittingHint(true);
    try {
      await api.discovery.createHint(
        hintText.trim(),
        hintSymbol.trim() || undefined,
      );
      setHintText("");
      setHintSymbol("");
      refresh();
    } catch {
      // ignore
    }
    setSubmittingHint(false);
  };

  const actionColor = (action: string) => {
    switch (action) {
      case "add":
        return "text-green-400";
      case "remove":
        return "text-red-400";
      case "keep":
        return "text-yellow-400";
      default:
        return "text-muted-foreground";
    }
  };

  const statusColor = (status: string) =>
    status === "pending" ? "text-yellow-400" : "text-muted-foreground";

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <p className="text-muted-foreground">Loading watchlist...</p>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold">AI Watchlist</h1>
          <p className="text-muted-foreground">
            AI-managed stock discovery and watchlist curation
          </p>
        </div>
        <Button onClick={handleTriggerDiscovery} disabled={triggering}>
          {triggering ? "Running..." : "Run Discovery Now"}
        </Button>
      </div>

      {/* Discovery Status */}
      {discoveryStatus?.last_run && (
        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="text-base">Last Discovery Run</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="flex items-center gap-6 text-sm">
              <div>
                <span className="text-muted-foreground">Time: </span>
                {new Date(discoveryStatus.last_run).toLocaleString()}
              </div>
              {discoveryStatus.last_result.status ? (
                <div>
                  <span className="text-muted-foreground">Status: </span>
                  <span
                    className={
                      discoveryStatus.last_result.status === "ok"
                        ? "text-green-400"
                        : "text-red-400"
                    }
                  >
                    {String(discoveryStatus.last_result.status)}
                  </span>
                </div>
              ) : null}
              {discoveryStatus.last_result.market_assessment ? (
                <div className="flex-1">
                  <span className="text-muted-foreground">Market: </span>
                  {String(discoveryStatus.last_result.market_assessment)}
                </div>
              ) : null}
            </div>
          </CardContent>
        </Card>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Current Watchlist */}
        <Card className="lg:col-span-2">
          <CardHeader>
            <CardTitle>Active Watchlist ({stocks.length})</CardTitle>
            <CardDescription>
              Stocks the AI is actively tracking and analyzing
            </CardDescription>
          </CardHeader>
          <CardContent>
            {stocks.length === 0 ? (
              <p className="text-sm text-muted-foreground">
                No stocks on watchlist. Run discovery to let the AI build one.
              </p>
            ) : (
              <div className="space-y-2">
                {stocks.map((stock) => (
                  <div
                    key={stock.symbol}
                    className="flex items-center justify-between rounded-md border p-3"
                  >
                    <div className="flex items-center gap-3">
                      <div className="font-mono font-bold">{stock.symbol}</div>
                      <div className="text-sm text-muted-foreground">
                        {stock.name}
                      </div>
                      {stock.sector && (
                        <span className="rounded-full bg-accent px-2 py-0.5 text-xs">
                          {stock.sector}
                        </span>
                      )}
                    </div>
                    <div className="flex items-center gap-4 text-sm">
                      {stock.latest_price != null && (
                        <span className="font-mono">
                          ${stock.latest_price.toFixed(2)}
                        </span>
                      )}
                      {stock.daily_change_pct != null && (
                        <span
                          className={
                            stock.daily_change_pct >= 0
                              ? "text-green-400"
                              : "text-red-400"
                          }
                        >
                          {stock.daily_change_pct >= 0 ? "+" : ""}
                          {stock.daily_change_pct.toFixed(2)}%
                        </span>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>

        {/* Hint Input */}
        <Card>
          <CardHeader>
            <CardTitle>Suggest to AI</CardTitle>
            <CardDescription>
              Give the AI hints — sectors to explore, stocks to consider, themes
              to watch. The AI will factor these in but makes its own decisions.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-3">
            <div>
              <label className="text-sm text-muted-foreground">
                Symbol (optional)
              </label>
              <input
                type="text"
                value={hintSymbol}
                onChange={(e) => setHintSymbol(e.target.value.toUpperCase())}
                placeholder="e.g. NVDA"
                className="mt-1 w-full rounded-md border bg-background px-3 py-2 text-sm"
                maxLength={10}
              />
            </div>
            <div>
              <label className="text-sm text-muted-foreground">
                Your suggestion
              </label>
              <textarea
                value={hintText}
                onChange={(e) => setHintText(e.target.value)}
                placeholder="e.g. Look into EV sector, consider defensive stocks given rising rates, check out semiconductor companies..."
                className="mt-1 w-full rounded-md border bg-background px-3 py-2 text-sm"
                rows={3}
                maxLength={1000}
              />
            </div>
            <Button
              onClick={handleSubmitHint}
              disabled={submittingHint || !hintText.trim()}
              className="w-full"
            >
              {submittingHint ? "Submitting..." : "Submit Hint"}
            </Button>
          </CardContent>
        </Card>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Discovery Log */}
        <Card>
          <CardHeader>
            <CardTitle>Discovery Log</CardTitle>
            <CardDescription>
              AI decisions with reasoning — what was added, removed, and why
            </CardDescription>
          </CardHeader>
          <CardContent>
            {discoveryLog.length === 0 ? (
              <p className="text-sm text-muted-foreground">
                No discovery runs yet.
              </p>
            ) : (
              <div className="space-y-3 max-h-96 overflow-y-auto">
                {discoveryLog.map((entry) => (
                  <div
                    key={entry.id}
                    className="rounded-md border p-3 space-y-1"
                  >
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-2">
                        <span className={`font-bold uppercase text-xs ${actionColor(entry.action)}`}>
                          {entry.action}
                        </span>
                        <span className="font-mono font-bold">
                          {entry.symbol}
                        </span>
                      </div>
                      <span className="text-xs text-muted-foreground">
                        {new Date(entry.created_at).toLocaleDateString()}
                      </span>
                    </div>
                    <p className="text-sm text-muted-foreground">
                      {entry.reasoning}
                    </p>
                    {entry.confidence > 0 && (
                      <div className="text-xs text-muted-foreground">
                        Confidence: {(entry.confidence * 100).toFixed(0)}%
                      </div>
                    )}
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>

        {/* Hints */}
        <Card>
          <CardHeader>
            <CardTitle>Your Hints</CardTitle>
            <CardDescription>
              Suggestions you&apos;ve submitted and the AI&apos;s responses
            </CardDescription>
          </CardHeader>
          <CardContent>
            {hints.length === 0 ? (
              <p className="text-sm text-muted-foreground">
                No hints submitted yet.
              </p>
            ) : (
              <div className="space-y-3 max-h-96 overflow-y-auto">
                {hints.map((hint) => (
                  <div
                    key={hint.id}
                    className="rounded-md border p-3 space-y-1"
                  >
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-2">
                        {hint.symbol && (
                          <span className="font-mono font-bold text-sm">
                            {hint.symbol}
                          </span>
                        )}
                        <span className={`text-xs ${statusColor(hint.status)}`}>
                          {hint.status}
                        </span>
                      </div>
                      <span className="text-xs text-muted-foreground">
                        {new Date(hint.created_at).toLocaleDateString()}
                      </span>
                    </div>
                    <p className="text-sm">{hint.hint_text}</p>
                    {hint.ai_response && (
                      <p className="text-sm text-muted-foreground italic">
                        AI: {hint.ai_response}
                      </p>
                    )}
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
