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
import { api, type Stock, type AnalystInputItem } from "@/lib/api";

export default function AnalystPage() {
  const [stocks, setStocks] = useState<Stock[]>([]);
  const [inputs, setInputs] = useState<AnalystInputItem[]>([]);
  const [loading, setLoading] = useState(true);

  // Form state
  const [selectedSymbol, setSelectedSymbol] = useState("");
  const [thesis, setThesis] = useState("");
  const [conviction, setConviction] = useState(5);
  const [timeHorizon, setTimeHorizon] = useState("");
  const [catalysts, setCatalysts] = useState("");
  const [overrideFlag, setOverrideFlag] = useState("none");
  const [saving, setSaving] = useState(false);
  const [editingId, setEditingId] = useState<number | null>(null);

  useEffect(() => {
    async function load() {
      try {
        const [s, i] = await Promise.all([
          api.stocks.list(true),
          api.analyst.list(false),
        ]);
        setStocks(s);
        setInputs(i);
        if (s.length > 0 && !selectedSymbol) setSelectedSymbol(s[0].symbol);
      } catch {
        /* empty */
      } finally {
        setLoading(false);
      }
    }
    load();
  }, []);

  function resetForm() {
    setThesis("");
    setConviction(5);
    setTimeHorizon("");
    setCatalysts("");
    setOverrideFlag("none");
    setEditingId(null);
  }

  function startEdit(inp: AnalystInputItem) {
    setEditingId(inp.id);
    setSelectedSymbol(inp.symbol);
    setThesis(inp.thesis);
    setConviction(inp.conviction);
    setTimeHorizon(inp.time_horizon_days?.toString() || "");
    setCatalysts(inp.catalysts || "");
    setOverrideFlag(inp.override_flag);
  }

  async function handleSubmit() {
    if (!thesis.trim() || !selectedSymbol) return;
    setSaving(true);
    try {
      if (editingId) {
        await api.analyst.update(editingId, {
          thesis,
          conviction,
          time_horizon_days: timeHorizon ? parseInt(timeHorizon) : undefined,
          catalysts: catalysts || undefined,
          override_flag: overrideFlag,
        });
      } else {
        await api.analyst.create({
          symbol: selectedSymbol,
          thesis,
          conviction,
          time_horizon_days: timeHorizon ? parseInt(timeHorizon) : undefined,
          catalysts: catalysts || undefined,
          override_flag: overrideFlag,
        });
      }
      const i = await api.analyst.list(false);
      setInputs(i);
      resetForm();
    } catch {
      /* empty */
    } finally {
      setSaving(false);
    }
  }

  async function handleDelete(id: number) {
    try {
      await api.analyst.delete(id);
      setInputs((prev) => prev.filter((i) => i.id !== id));
      if (editingId === id) resetForm();
    } catch {
      /* empty */
    }
  }

  async function handleToggleActive(inp: AnalystInputItem) {
    try {
      await api.analyst.update(inp.id, { is_active: !inp.is_active });
      const i = await api.analyst.list(false);
      setInputs(i);
    } catch {
      /* empty */
    }
  }

  function convictionColor(c: number) {
    if (c >= 8) return "text-green-500";
    if (c >= 5) return "text-yellow-500";
    return "text-red-500";
  }

  function overrideBadge(flag: string) {
    if (flag === "avoid")
      return (
        <span className="rounded-full bg-red-500/10 px-2 py-0.5 text-xs font-medium text-red-500">
          AVOID
        </span>
      );
    if (flag === "boost")
      return (
        <span className="rounded-full bg-green-500/10 px-2 py-0.5 text-xs font-medium text-green-500">
          BOOST
        </span>
      );
    return null;
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
        <h2 className="text-3xl font-bold tracking-tight">
          Analyst Workbench
        </h2>
        <p className="text-muted-foreground">
          Enter your personal analysis, thesis notes, and conviction scores
        </p>
      </div>

      {/* ── Input Form ── */}
      <Card>
        <CardHeader>
          <CardTitle>
            {editingId ? "Edit Analyst Input" : "New Analyst Input"}
          </CardTitle>
          <CardDescription>
            Your insights are weighted alongside ML and Claude signals in
            trading decisions
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          {/* Stock selector + Override */}
          <div className="grid grid-cols-3 gap-4">
            <div>
              <label className="mb-1 block text-sm font-medium">Stock</label>
              <select
                value={selectedSymbol}
                onChange={(e) => setSelectedSymbol(e.target.value)}
                disabled={!!editingId}
                className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
              >
                {stocks.map((s) => (
                  <option key={s.symbol} value={s.symbol}>
                    {s.symbol} — {s.name || "Unknown"}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label className="mb-1 block text-sm font-medium">
                Conviction (1-10)
              </label>
              <input
                type="range"
                min={1}
                max={10}
                value={conviction}
                onChange={(e) => setConviction(parseInt(e.target.value))}
                className="w-full"
              />
              <div
                className={`text-center text-lg font-bold ${convictionColor(conviction)}`}
              >
                {conviction}
              </div>
            </div>
            <div>
              <label className="mb-1 block text-sm font-medium">
                Override Flag
              </label>
              <select
                value={overrideFlag}
                onChange={(e) => setOverrideFlag(e.target.value)}
                className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
              >
                <option value="none">None</option>
                <option value="boost">Boost (favor buying)</option>
                <option value="avoid">Avoid (force sell/hold)</option>
              </select>
            </div>
          </div>

          {/* Thesis */}
          <div>
            <label className="mb-1 block text-sm font-medium">Thesis</label>
            <textarea
              value={thesis}
              onChange={(e) => setThesis(e.target.value)}
              rows={3}
              placeholder="Your investment thesis for this stock..."
              className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
            />
          </div>

          {/* Catalysts + Time Horizon */}
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="mb-1 block text-sm font-medium">
                Catalysts
              </label>
              <textarea
                value={catalysts}
                onChange={(e) => setCatalysts(e.target.value)}
                rows={2}
                placeholder="Upcoming events, earnings, product launches..."
                className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
              />
            </div>
            <div>
              <label className="mb-1 block text-sm font-medium">
                Time Horizon (days)
              </label>
              <input
                type="number"
                value={timeHorizon}
                onChange={(e) => setTimeHorizon(e.target.value)}
                placeholder="e.g. 30, 90, 365"
                className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
              />
            </div>
          </div>

          {/* Actions */}
          <div className="flex gap-3">
            <Button
              onClick={handleSubmit}
              disabled={saving || !thesis.trim()}
            >
              {saving
                ? "Saving..."
                : editingId
                  ? "Update Input"
                  : "Add Input"}
            </Button>
            {editingId && (
              <Button variant="outline" onClick={resetForm}>
                Cancel
              </Button>
            )}
          </div>
        </CardContent>
      </Card>

      {/* ── Active Inputs ── */}
      <Card>
        <CardHeader>
          <CardTitle>Analyst Inputs</CardTitle>
          <CardDescription>
            {inputs.filter((i) => i.is_active).length} active input
            {inputs.filter((i) => i.is_active).length !== 1 ? "s" : ""} across{" "}
            {new Set(inputs.filter((i) => i.is_active).map((i) => i.symbol))
              .size}{" "}
            stock{new Set(inputs.filter((i) => i.is_active).map((i) => i.symbol)).size !== 1 ? "s" : ""}
          </CardDescription>
        </CardHeader>
        <CardContent>
          {inputs.length === 0 ? (
            <div className="flex h-32 items-center justify-center rounded-md border border-dashed">
              <p className="text-sm text-muted-foreground">
                No analyst inputs yet — add your first thesis above
              </p>
            </div>
          ) : (
            <div className="space-y-3">
              {inputs.map((inp) => (
                <div
                  key={inp.id}
                  className={`rounded-lg border p-4 ${
                    inp.is_active
                      ? "border-border"
                      : "border-border/50 opacity-50"
                  }`}
                >
                  <div className="flex items-start justify-between">
                    <div className="flex items-center gap-3">
                      <span className="text-lg font-bold">{inp.symbol}</span>
                      <span
                        className={`text-sm font-medium ${convictionColor(inp.conviction)}`}
                      >
                        Conviction: {inp.conviction}/10
                      </span>
                      {overrideBadge(inp.override_flag)}
                      {!inp.is_active && (
                        <span className="rounded-full bg-muted px-2 py-0.5 text-xs text-muted-foreground">
                          INACTIVE
                        </span>
                      )}
                    </div>
                    <div className="flex gap-2">
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => handleToggleActive(inp)}
                      >
                        {inp.is_active ? "Deactivate" : "Activate"}
                      </Button>
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => startEdit(inp)}
                      >
                        Edit
                      </Button>
                      <Button
                        variant="ghost"
                        size="sm"
                        className="text-red-400 hover:text-red-500"
                        onClick={() => handleDelete(inp.id)}
                      >
                        Delete
                      </Button>
                    </div>
                  </div>
                  <p className="mt-2 text-sm">{inp.thesis}</p>
                  <div className="mt-2 flex gap-4 text-xs text-muted-foreground">
                    {inp.catalysts && <span>Catalysts: {inp.catalysts}</span>}
                    {inp.time_horizon_days && (
                      <span>Horizon: {inp.time_horizon_days}d</span>
                    )}
                    <span>
                      Updated: {new Date(inp.updated_at).toLocaleDateString()}
                    </span>
                  </div>
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
