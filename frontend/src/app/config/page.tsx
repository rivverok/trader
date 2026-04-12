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
import { api, type RiskStatus, type SignalWeights, type SystemStatus, type BackupStatus } from "@/lib/api";

export default function ConfigPage() {
  const [risk, setRisk] = useState<RiskStatus | null>(null);
  const [weights, setWeights] = useState<SignalWeights | null>(null);
  const [system, setSystem] = useState<SystemStatus | null>(null);
  const [backup, setBackup] = useState<BackupStatus | null>(null);
  const [loading, setLoading] = useState(true);

  // Editable risk config
  const [riskForm, setRiskForm] = useState({
    max_trade_dollars: 1000,
    max_position_pct: 10,
    max_sector_pct: 25,
    daily_loss_limit: 500,
    max_drawdown_pct: 15,
    min_confidence: 0.6,
  });

  // Editable weights
  const [weightForm, setWeightForm] = useState({ ml: 0.3, claude: 0.4, analyst: 0.3 });

  const [savingRisk, setSavingRisk] = useState(false);
  const [savingWeights, setSavingWeights] = useState(false);
  const [riskMsg, setRiskMsg] = useState<string | null>(null);
  const [weightMsg, setWeightMsg] = useState<string | null>(null);

  useEffect(() => {
    async function load() {
      try {
        const [r, w, s] = await Promise.all([
          api.risk.status(),
          api.config.getWeights(),
          api.system.status(),
        ]);
        setRisk(r);
        setWeights(w);
        setSystem(s);

        api.system.backupStatus().then(setBackup).catch(() => {});
        setRiskForm({
          max_trade_dollars: r.max_trade_dollars,
          max_position_pct: r.max_position_pct,
          max_sector_pct: r.max_sector_pct,
          daily_loss_limit: r.daily_loss_limit,
          max_drawdown_pct: r.max_drawdown_pct,
          min_confidence: r.min_confidence,
        });
        setWeightForm({ ml: w.ml, claude: w.claude, analyst: w.analyst });
      } catch {
        /* empty */
      } finally {
        setLoading(false);
      }
    }
    load();
  }, []);

  async function saveRiskConfig() {
    setSavingRisk(true);
    setRiskMsg(null);
    try {
      await api.risk.updateConfig(riskForm);
      setRiskMsg("Saved");
      const r = await api.risk.status();
      setRisk(r);
    } catch (e) {
      setRiskMsg(`Error: ${e instanceof Error ? e.message : "unknown"}`);
    } finally {
      setSavingRisk(false);
    }
  }

  async function saveWeights() {
    setSavingWeights(true);
    setWeightMsg(null);
    try {
      const w = await api.config.updateWeights(weightForm);
      setWeights(w);
      setWeightForm({ ml: w.ml, claude: w.claude, analyst: w.analyst });
      setWeightMsg("Saved (normalized to sum 1.0)");
    } catch (e) {
      setWeightMsg(`Error: ${e instanceof Error ? e.message : "unknown"}`);
    } finally {
      setSavingWeights(false);
    }
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
      <div>
        <h2 className="text-3xl font-bold tracking-tight">Configuration</h2>
        <p className="text-muted-foreground">
          System settings, risk parameters, and signal weights
        </p>
      </div>

      {/* ── Growth Mode ── */}
      {system && (
        <Card className={system.growth_mode ? "border-primary/50 bg-primary/5" : ""}>
          <CardHeader>
            <div className="flex items-center justify-between">
              <div>
                <CardTitle>Growth Mode</CardTitle>
                <CardDescription>
                  Seed the account and let the system manage it hands-off.
                  It will invest, sell, and reinvest with the goal of growing
                  account value. Enables auto-execute and portfolio-proportional
                  position sizing.
                </CardDescription>
              </div>
              <Button
                variant={system.growth_mode ? "destructive" : "default"}
                size="sm"
                onClick={async () => {
                  const next = !system.growth_mode;
                  const res = await api.system.toggleAutonomousMode(next);
                  setSystem((prev) =>
                    prev
                      ? {
                          ...prev,
                          growth_mode: res.growth_mode,
                          auto_execute: res.auto_execute,
                        }
                      : prev
                  );
                }}
              >
                {system.growth_mode ? "Disable" : "Enable"}
              </Button>
            </div>
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-3 gap-6">
              <div className="space-y-1">
                <div className="text-sm text-muted-foreground">Status</div>
                <div
                  className={`text-lg font-bold ${system.growth_mode ? "text-primary" : "text-muted-foreground"}`}
                >
                  {system.growth_mode ? "ACTIVE" : "Off"}
                </div>
              </div>
              <div className="space-y-1">
                <div className="text-sm text-muted-foreground">
                  Portfolio Value
                </div>
                <div className="text-lg font-bold">
                  ${system.portfolio_value.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                </div>
              </div>
              <div className="space-y-1">
                <div className="text-sm text-muted-foreground">
                  Buying Power
                </div>
                <div className="text-lg font-bold">
                  ${system.buying_power.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                </div>
              </div>
            </div>
            {system.growth_mode && (
              <p className="mt-4 rounded-md bg-primary/10 px-3 py-2 text-sm text-primary">
                The system is fully managing this account. Trades are
                auto-approved, sized at up to 10% of portfolio per trade
                (scaled by confidence), and all gains are reinvested.
              </p>
            )}
          </CardContent>
        </Card>
      )}

      {/* ── Risk Dashboard ── */}
      {risk && (
        <Card
          className={
            risk.trading_halted ? "border-red-500/50 bg-red-500/5" : ""
          }
        >
          <CardHeader>
            <div className="flex items-center justify-between">
              <div>
                <CardTitle>Risk Dashboard</CardTitle>
                <CardDescription>
                  Current risk state and circuit breaker status
                </CardDescription>
              </div>
              {risk.trading_halted && (
                <Button
                  variant="destructive"
                  size="sm"
                  onClick={async () => {
                    await api.risk.resume();
                    const r = await api.risk.status();
                    setRisk(r);
                  }}
                >
                  Resume Trading
                </Button>
              )}
            </div>
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-4 gap-6">
              {/* Drawdown gauge */}
              <div className="space-y-1">
                <div className="text-sm text-muted-foreground">
                  Current Drawdown
                </div>
                <div className="text-2xl font-bold text-red-400">
                  {risk.current_drawdown_pct.toFixed(2)}%
                </div>
                <div className="h-2 w-full rounded-full bg-muted">
                  <div
                    className="h-2 rounded-full bg-red-500"
                    style={{
                      width: `${Math.min(100, (risk.current_drawdown_pct / risk.max_drawdown_pct) * 100)}%`,
                    }}
                  />
                </div>
                <div className="text-xs text-muted-foreground">
                  Max: {risk.max_drawdown_pct}%
                </div>
              </div>

              {/* Daily loss tracker */}
              <div className="space-y-1">
                <div className="text-sm text-muted-foreground">
                  Daily Realized Loss
                </div>
                <div className="text-2xl font-bold text-red-400">
                  ${risk.daily_realized_loss.toFixed(2)}
                </div>
                <div className="h-2 w-full rounded-full bg-muted">
                  <div
                    className="h-2 rounded-full bg-orange-500"
                    style={{
                      width: `${Math.min(100, (risk.daily_realized_loss / risk.daily_loss_limit) * 100)}%`,
                    }}
                  />
                </div>
                <div className="text-xs text-muted-foreground">
                  Limit: ${risk.daily_loss_limit}
                </div>
              </div>

              {/* Positions */}
              <div className="space-y-1">
                <div className="text-sm text-muted-foreground">
                  Position Exposure
                </div>
                <div className="text-2xl font-bold">
                  ${risk.total_position_value.toFixed(0)}
                </div>
                <div className="text-xs text-muted-foreground">
                  {risk.positions_count} position
                  {risk.positions_count !== 1 ? "s" : ""}
                </div>
              </div>

              {/* Circuit breaker */}
              <div className="space-y-1">
                <div className="text-sm text-muted-foreground">
                  Circuit Breaker
                </div>
                <div
                  className={`text-2xl font-bold ${risk.trading_halted ? "text-red-500" : "text-green-500"}`}
                >
                  {risk.trading_halted ? "HALTED" : "ACTIVE"}
                </div>
                {risk.halt_reason && (
                  <div className="text-xs text-red-400">
                    {risk.halt_reason}
                  </div>
                )}
              </div>
            </div>

            {/* Sector exposure */}
            {Object.keys(risk.sector_exposure).length > 0 && (
              <div className="mt-6">
                <h4 className="mb-2 text-sm font-semibold">
                  Sector Exposure
                </h4>
                <div className="flex flex-wrap gap-2">
                  {Object.entries(risk.sector_exposure).map(
                    ([sector, value]) => (
                      <div
                        key={sector}
                        className="rounded-lg border border-border px-3 py-1 text-sm"
                      >
                        <span className="text-muted-foreground">
                          {sector}:
                        </span>{" "}
                        <span className="font-medium">
                          ${value.toFixed(0)}
                        </span>
                        {risk.portfolio_peak_value > 0 && (
                          <span className="ml-1 text-xs text-muted-foreground">
                            (
                            {((value / risk.portfolio_peak_value) * 100).toFixed(
                              1,
                            )}
                            %)
                          </span>
                        )}
                      </div>
                    ),
                  )}
                </div>
              </div>
            )}
          </CardContent>
        </Card>
      )}

      <div className="grid gap-6 md:grid-cols-2">
        {/* ── Signal Weights ── */}
        <Card>
          <CardHeader>
            <CardTitle>Signal Weights</CardTitle>
            <CardDescription>
              How much each signal source influences trading decisions
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            {(["ml", "claude", "analyst"] as const).map((key) => (
              <div key={key} className="space-y-1">
                <div className="flex justify-between text-sm">
                  <label className="font-medium capitalize">
                    {key === "ml" ? "ML Technical" : key === "claude" ? "Claude Analysis" : "Analyst Input"}
                  </label>
                  <span className="text-muted-foreground">
                    {(weightForm[key] * 100).toFixed(0)}%
                  </span>
                </div>
                <input
                  type="range"
                  min={0}
                  max={100}
                  value={Math.round(weightForm[key] * 100)}
                  onChange={(e) =>
                    setWeightForm((prev) => ({
                      ...prev,
                      [key]: parseInt(e.target.value) / 100,
                    }))
                  }
                  className="w-full"
                />
              </div>
            ))}
            <div className="flex items-center gap-3">
              <Button
                onClick={saveWeights}
                disabled={savingWeights}
                size="sm"
              >
                {savingWeights ? "Saving..." : "Save Weights"}
              </Button>
              {weightMsg && (
                <span className="text-xs text-muted-foreground">
                  {weightMsg}
                </span>
              )}
            </div>
          </CardContent>
        </Card>

        {/* ── Risk Parameters ── */}
        <Card>
          <CardHeader>
            <CardTitle>Risk Parameters</CardTitle>
            <CardDescription>
              Hard limits enforced on every trade — not overridable by AI
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-3">
            {[
              {
                key: "max_trade_dollars" as const,
                label: "Max $ Per Trade",
                prefix: "$",
                step: 100,
              },
              {
                key: "max_position_pct" as const,
                label: "Max Position %",
                suffix: "%",
                step: 1,
              },
              {
                key: "max_sector_pct" as const,
                label: "Max Sector %",
                suffix: "%",
                step: 1,
              },
              {
                key: "daily_loss_limit" as const,
                label: "Daily Loss Limit",
                prefix: "$",
                step: 50,
              },
              {
                key: "max_drawdown_pct" as const,
                label: "Max Drawdown %",
                suffix: "%",
                step: 1,
              },
              {
                key: "min_confidence" as const,
                label: "Min Confidence",
                step: 0.05,
              },
            ].map(({ key, label, prefix, suffix, step }) => (
              <div
                key={key}
                className="flex items-center justify-between gap-4"
              >
                <label className="text-sm font-medium">{label}</label>
                <div className="flex items-center gap-1">
                  {prefix && (
                    <span className="text-sm text-muted-foreground">
                      {prefix}
                    </span>
                  )}
                  <input
                    type="number"
                    step={step}
                    value={riskForm[key]}
                    onChange={(e) =>
                      setRiskForm((prev) => ({
                        ...prev,
                        [key]: parseFloat(e.target.value) || 0,
                      }))
                    }
                    className="w-24 rounded-md border border-input bg-background px-2 py-1 text-right text-sm"
                  />
                  {suffix && (
                    <span className="text-sm text-muted-foreground">
                      {suffix}
                    </span>
                  )}
                </div>
              </div>
            ))}
            <div className="flex items-center gap-3 pt-2">
              <Button
                onClick={saveRiskConfig}
                disabled={savingRisk}
                size="sm"
              >
                {savingRisk ? "Saving..." : "Save Risk Config"}
              </Button>
              {riskMsg && (
                <span className="text-xs text-muted-foreground">
                  {riskMsg}
                </span>
              )}
            </div>
          </CardContent>
        </Card>
      </div>

      {/* ── Backup Status ── */}
      <Card>
        <CardHeader>
          <CardTitle>Database Backups</CardTitle>
          <CardDescription>
            Automatic daily backups to USB drive. Runs every day at 2 AM.
          </CardDescription>
        </CardHeader>
        <CardContent>
          {backup?.status ? (
            <div className="flex items-center gap-3">
              <div
                className={`h-3 w-3 rounded-full ${
                  backup.status === "success" ? "bg-green-500" : "bg-red-500"
                }`}
              />
              <div>
                <div className="flex items-center gap-2">
                  <span className="text-sm font-medium">
                    Last backup:{" "}
                    {backup.time
                      ? new Date(backup.time).toLocaleString()
                      : "Unknown"}
                  </span>
                  <span
                    className={`rounded-full px-2 py-0.5 text-xs font-medium uppercase ${
                      backup.status === "success"
                        ? "bg-green-500/10 text-green-500"
                        : "bg-red-500/10 text-red-500"
                    }`}
                  >
                    {backup.status}
                  </span>
                </div>
                {backup.message && (
                  <p className="text-sm text-muted-foreground">
                    {backup.message}
                  </p>
                )}
              </div>
            </div>
          ) : (
            <p className="text-sm text-muted-foreground">
              No backup has run yet. Backups run automatically every day at 2
              AM.
            </p>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
