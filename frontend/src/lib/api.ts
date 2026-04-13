const API_BASE = process.env.NEXT_PUBLIC_API_URL || "/api";

export interface HealthResponse {
  status: string;
  trading_mode: string;
  database: string;
  redis: string;
}

export interface Stock {
  id: number;
  symbol: string;
  name: string | null;
  sector: string | null;
  industry: string | null;
  exchange: string | null;
  on_watchlist: boolean;
  latest_price: number | null;
  daily_change_pct: number | null;
}

export interface PriceBar {
  timestamp: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

export interface NewsArticle {
  id: number;
  headline: string;
  summary: string | null;
  source: string | null;
  url: string;
  published_at: string;
  sentiment_score: number | null;
  analyzed: boolean;
}

export interface EconomicIndicator {
  indicator_code: string;
  name: string;
  value: number;
  date: string;
  source: string;
}

export interface CollectionStatus {
  tasks: Record<string, { last_run: string; last_result: Record<string, unknown> }>;
}

export interface TriggerResponse {
  task_id: string;
  task_name: string;
}

// ── Analysis types ──────────────────────────────────────────────────

export interface NewsAnalysisItem {
  id: number;
  headline: string;
  published_at: string;
  sentiment_score: number;
  impact_severity: string;
  material_event: boolean;
  summary: string;
}

export interface FilingAnalysisItem {
  id: number;
  filing_type: string;
  filed_date: string;
  revenue_trend: string | null;
  margin_analysis: string | null;
  risk_changes: string | null;
  guidance_sentiment: number | null;
  key_findings: string[] | null;
}

export interface SynthesisItem {
  id: number;
  overall_sentiment: number;
  confidence: number;
  key_factors: string[] | null;
  risks: string[] | null;
  opportunities: string[] | null;
  reasoning_chain: string | null;
  claude_model_used: string;
  created_at: string;
}

export interface StockAnalysis {
  symbol: string;
  name: string | null;
  latest_synthesis: SynthesisItem | null;
  recent_news: NewsAnalysisItem[];
  filing_analyses: FilingAnalysisItem[];
}

export interface UsageDay {
  date: string;
  task_type: string;
  model: string;
  total_input_tokens: number;
  total_output_tokens: number;
  total_cost: number;
  call_count: number;
}

export interface UsageSummary {
  daily_breakdown: UsageDay[];
  total_cost_30d: number;
  total_calls_30d: number;
}

export interface AnalysisStatus {
  tasks: Record<string, { last_run: string; last_result: Record<string, unknown> }>;
}

// ── ML types ────────────────────────────────────────────────────────

export interface MLSignalItem {
  id: number;
  signal: "buy" | "sell" | "hold";
  confidence: number;
  model_name: string;
  model_version: string;
  feature_importances: Record<string, number> | null;
  created_at: string;
}

export interface ModelItem {
  id: number;
  model_name: string;
  version: string;
  file_path: string;
  training_date: string;
  symbols_trained: string;
  feature_count: number;
  validation_metrics: Record<string, unknown> | null;
  is_active: boolean;
  created_at: string;
}

export interface BacktestResultItem {
  id: number;
  strategy_name: string;
  model_name: string | null;
  model_version: string | null;
  symbols: string;
  start_date: string;
  end_date: string;
  total_return: number;
  sharpe_ratio: number;
  max_drawdown: number;
  win_rate: number;
  profit_factor: number;
  trades_count: number;
  benchmark_return: number | null;
  report_json: Record<string, unknown> | null;
  created_at: string;
}

// ── Decision Engine types ───────────────────────────────────────────

export interface AnalystInputItem {
  id: number;
  stock_id: number;
  symbol: string;
  thesis: string;
  conviction: number;
  time_horizon_days: number | null;
  catalysts: string | null;
  override_flag: "none" | "avoid" | "boost";
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface ProposedTradeItem {
  id: number;
  stock_id: number;
  symbol: string;
  action: "buy" | "sell";
  shares: number;
  price_target: number | null;
  order_type: string;
  ml_signal_id: number | null;
  synthesis_id: number | null;
  analyst_input_id: number | null;
  confidence: number;
  reasoning_chain: string | null;
  risk_check_passed: boolean | null;
  risk_check_reason: string | null;
  status: "proposed" | "queued" | "approved" | "rejected" | "executed" | "expired";
  created_at: string;
}

export interface RiskStatus {
  trading_halted: boolean;
  halt_reason: string | null;
  halted_at: string | null;
  daily_realized_loss: number;
  portfolio_peak_value: number;
  current_drawdown_pct: number;
  max_trade_dollars: number;
  max_position_pct: number;
  max_sector_pct: number;
  daily_loss_limit: number;
  max_drawdown_pct: number;
  min_confidence: number;
  total_position_value: number;
  positions_count: number;
  sector_exposure: Record<string, number>;
}

// ── Portfolio & Execution types ─────────────────────────────────────

export interface PositionItem {
  stock_id: number;
  symbol: string;
  shares: number;
  avg_cost_basis: number;
  current_value: number;
  unrealized_pnl: number;
  realized_pnl: number;
}

export interface PortfolioResponse {
  total_value: number;
  cash: number;
  positions_value: number;
  daily_pnl: number;
  cumulative_pnl: number;
  buying_power: number;
  positions: PositionItem[];
  account_status: string;
}

export interface PortfolioSnapshot {
  timestamp: string;
  total_value: number;
  cash: number;
  positions_value: number;
  daily_pnl: number;
  cumulative_pnl: number;
}

export interface ExecutedTradeItem {
  id: number;
  stock_id: number;
  symbol: string;
  proposed_trade_id: number | null;
  action: string;
  shares: number;
  price: number;
  order_type: string;
  fill_price: number | null;
  fill_time: string | null;
  slippage: number | null;
  commission: number | null;
  alpaca_order_id: string | null;
  status: string;
  created_at: string;
}

export interface SystemStatus {
  system_mode: string;
  trading_paused: boolean;
  system_paused: boolean;
  trading_halted: boolean;
  halt_reason: string | null;
  account_status: string;
  buying_power: number;
  portfolio_value: number;
}

export interface ManualTradeResponse {
  trade_id: number;
  proposed_trade_id: number;
  status: string;
  risk_check_passed: boolean;
  risk_check_reason: string;
}

export interface BackupStatus {
  status: string | null;
  time: string | null;
  message: string | null;
}

// ── Data Collection types ───────────────────────────────────────────

// ── RL Model types ──────────────────────────────────────────────────

export interface RLModel {
  id: number;
  name: string;
  version: string;
  algorithm: string;
  onnx_path: string;
  state_spec: Record<string, unknown> | null;
  action_spec: Record<string, unknown> | null;
  training_metadata: Record<string, unknown> | null;
  backtest_metrics: Record<string, unknown> | null;
  is_active: boolean;
  activated_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface RLModelListResponse {
  models: RLModel[];
  active_model_id: number | null;
}

// ── Training Status types ───────────────────────────────────────────

export interface TableStats {
  count: number;
  first: string | null;
  last: string | null;
  trading_days: number;
}

export interface TrainingReadiness {
  min_days_target: number;
  good_days_target: number;
  current_days: number;
  feature_days: Record<string, number>;
  binding_constraint: string | null;
  pct_to_minimum: number;
  pct_to_recommended: number;
  ready_minimum: boolean;
  ready_recommended: boolean;
  est_minimum_date: string | null;
  est_recommended_date: string | null;
  collection_start: string | null;
}

export interface TrainingStatus {
  stock_count: number;
  tables: Record<string, TableStats>;
  per_stock_signals: Record<string, number>;
  daily_collection_rate: { date: string; count: number }[];
  readiness: TrainingReadiness;
}

// ── Analytics types ─────────────────────────────────────────────────

export interface PerformanceMetrics {
  total_trades: number;
  winning_trades: number;
  losing_trades: number;
  win_rate: number;
  profit_factor: number;
  total_pnl: number;
  gross_profit: number;
  gross_loss: number;
  avg_return_pct: number;
  sharpe_ratio: number;
  max_drawdown_pct: number;
  calmar_ratio: number;
  monthly_returns: Record<string, number>;
  equity_curve: { timestamp: string; value: number }[];
}

export interface SourceAttribution {
  total_trades: number;
  win_count: number;
  loss_count: number;
  win_rate: number;
  total_pnl: number;
  avg_pnl: number;
  gross_profit: number;
  gross_loss: number;
}

export interface AttributionData {
  ml: SourceAttribution;
  claude: SourceAttribution;
  analyst: SourceAttribution;
}

// ── Alert types ─────────────────────────────────────────────────────

export interface AlertItem {
  id: number;
  type: string;
  severity: "info" | "warning" | "critical";
  message: string;
  acknowledged: boolean;
  created_at: string;
}

// ── Discovery types ─────────────────────────────────────────────────

export interface DiscoveryLogItem {
  id: number;
  batch_id: string;
  action: "add" | "remove" | "keep";
  symbol: string;
  reasoning: string;
  confidence: number;
  source: string;
  created_at: string;
}

export interface WatchlistHint {
  id: number;
  hint_text: string;
  symbol: string | null;
  status: "pending" | "considered";
  ai_response: string | null;
  created_at: string;
}

export interface DiscoveryStatus {
  last_run: string | null;
  last_result: Record<string, unknown>;
}

export interface ServiceCheck {
  name: string;
  status: "ok" | "error" | "not_configured";
  message: string;
  details: Record<string, unknown> | null;
}

export interface ServiceStatusResponse {
  overall: string;
  services: ServiceCheck[];
}

// ── Task management types ───────────────────────────────────────────
export interface ActiveTask {
  task_id: string;
  name: string;
  status: string;
  worker: string;
  started_at: string | null;
  args: string | null;
  kwargs: string | null;
}

export interface ScheduledTask {
  key: string;
  name: string;
  schedule: string;
  enabled: boolean;
  last_run: string | null;
  total_run_count: number | null;
}

export interface TaskListResponse {
  active: ActiveTask[];
  reserved: ActiveTask[];
  scheduled_periodic: ScheduledTask[];
}

export interface TaskInfo {
  task_id: string;
  name: string | null;
  status: string;
  result: string | null;
  error: string | null;
  started_at: string | null;
  completed_at: string | null;
  worker: string | null;
  progress: {
    current_symbol?: string;
    symbol_index?: number;
    total_symbols?: number;
    fold_index?: number;
    total_folds?: number;
    best_score?: number | null;
    best_model_type?: string | null;
  } | null;
}

export interface TaskActionResponse {
  task_id: string;
  action: string;
  success: boolean;
  message: string;
}

export interface DataSourceStatus {
  name: string;
  rows: number;
  latest: string | null;
  detail: string | null;
}

export interface DataStatusResponse {
  sources: DataSourceStatus[];
}

async function fetchApi<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!res.ok) {
    throw new Error(`API error: ${res.status} ${res.statusText}`);
  }
  return res.json();
}

export const api = {
  health: () => fetchApi<HealthResponse>("/health"),
  stocks: {
    list: (watchlist?: boolean) => {
      const params = watchlist !== undefined ? `?watchlist=${watchlist}` : "";
      return fetchApi<Stock[]>(`/stocks${params}`);
    },
    create: (symbol: string) =>
      fetchApi<Stock>("/stocks", {
        method: "POST",
        body: JSON.stringify({ symbol }),
      }),
    remove: (symbol: string) =>
      fetch(`${API_BASE}/stocks/${symbol}`, { method: "DELETE" }),
    prices: (symbol: string, interval = "1Day", limit = 500) =>
      fetchApi<PriceBar[]>(
        `/stocks/${symbol}/prices?interval=${interval}&limit=${limit}`
      ),
    news: (symbol: string, limit = 50) =>
      fetchApi<NewsArticle[]>(`/stocks/${symbol}/news?limit=${limit}`),
  },
  economic: {
    list: () => fetchApi<EconomicIndicator[]>("/economic-indicators"),
  },
  collection: {
    status: () => fetchApi<CollectionStatus>("/collection/status"),
    trigger: (taskName: string) =>
      fetchApi<TriggerResponse>(`/collection/trigger/${taskName}`, {
        method: "POST",
      }),
  },
  analysis: {
    forStock: (symbol: string) =>
      fetchApi<StockAnalysis>(`/analysis/stocks/${symbol}`),
    usage: (days = 30) =>
      fetchApi<UsageSummary>(`/analysis/usage?days=${days}`),
    status: () => fetchApi<AnalysisStatus>("/analysis/status"),
    trigger: (taskName: string) =>
      fetchApi<TriggerResponse>(`/analysis/trigger/${taskName}`, {
        method: "POST",
      }),
  },
  ml: {
    signals: (symbol: string, limit = 10) =>
      fetchApi<MLSignalItem[]>(`/stocks/${symbol}/signals?limit=${limit}`),
    models: () => fetchApi<ModelItem[]>("/models"),
    activateModel: (modelId: number) =>
      fetchApi<{ status: string }>(`/models/${modelId}/activate`, {
        method: "POST",
      }),
    retrain: (symbols?: string[], years = 5) =>
      fetchApi<{ task_id: string }>("/models/retrain", {
        method: "POST",
        body: JSON.stringify({ symbols, years }),
      }),
    generateSignals: () =>
      fetchApi<{ task_id: string }>("/models/generate-signals", {
        method: "POST",
      }),
    backtestResults: (limit = 20) =>
      fetchApi<BacktestResultItem[]>(`/backtest/results?limit=${limit}`),
    runBacktest: (params: {
      symbols?: string[];
      start_date?: string;
      end_date?: string;
      initial_cash?: number;
    }) =>
      fetchApi<{ task_id: string }>("/backtest/run", {
        method: "POST",
        body: JSON.stringify(params),
      }),
    status: () =>
      fetchApi<{ tasks: Record<string, unknown> }>("/ml/status"),
  },
  analyst: {
    list: (activeOnly = true) =>
      fetchApi<AnalystInputItem[]>(
        `/analyst/inputs?active_only=${activeOnly}`
      ),
    create: (input: {
      symbol: string;
      thesis: string;
      conviction: number;
      time_horizon_days?: number;
      catalysts?: string;
      override_flag?: string;
    }) =>
      fetchApi<AnalystInputItem>("/analyst/input", {
        method: "POST",
        body: JSON.stringify(input),
      }),
    update: (id: number, input: Partial<{
      thesis: string;
      conviction: number;
      time_horizon_days: number;
      catalysts: string;
      override_flag: string;
      is_active: boolean;
    }>) =>
      fetchApi<AnalystInputItem>(`/analyst/input/${id}`, {
        method: "PUT",
        body: JSON.stringify(input),
      }),
    delete: (id: number) =>
      fetchApi<{ status: string }>(`/analyst/input/${id}`, {
        method: "DELETE",
      }),
  },
  trades: {
    proposed: (status?: string, limit = 50) => {
      const params = new URLSearchParams({ limit: String(limit) });
      if (status) params.set("status", status);
      return fetchApi<ProposedTradeItem[]>(`/trades/proposed?${params}`);
    },
    approve: (id: number) =>
      fetchApi<{ status: string }>(`/trades/${id}/approve`, {
        method: "POST",
      }),
    reject: (id: number, reason?: string) =>
      fetchApi<{ status: string }>(`/trades/${id}/reject`, {
        method: "POST",
        body: JSON.stringify({ reason: reason || "Manually rejected" }),
      }),
    reevaluate: (id: number) =>
      fetchApi<{ trade_id: number; status: string; risk_check_passed: boolean; risk_check_reason: string }>(
        `/trades/${id}/reevaluate`,
        { method: "POST" }
      ),
    runDecisionCycle: () =>
      fetchApi<{ task_id: string }>("/trades/run-decision-cycle", {
        method: "POST",
      }),
    reevaluateQueued: () =>
      fetchApi<{ task_id: string }>("/trades/reevaluate-queued", {
        method: "POST",
      }),
  },
  risk: {
    status: () => fetchApi<RiskStatus>("/risk/status"),
    updateConfig: (config: Partial<{
      max_trade_dollars: number;
      max_position_pct: number;
      max_sector_pct: number;
      daily_loss_limit: number;
      max_drawdown_pct: number;
      min_confidence: number;
    }>) =>
      fetchApi<{ status: string }>("/risk/config", {
        method: "PUT",
        body: JSON.stringify(config),
      }),
    resume: () =>
      fetchApi<{ status: string }>("/risk/resume", { method: "POST" }),
  },
  portfolio: {
    get: () => fetchApi<PortfolioResponse>("/portfolio"),
    history: (days = 90) =>
      fetchApi<PortfolioSnapshot[]>(`/portfolio/history?days=${days}`),
    trades: (status?: string, limit = 100) => {
      const params = new URLSearchParams({ limit: String(limit) });
      if (status) params.set("status", status);
      return fetchApi<ExecutedTradeItem[]>(`/portfolio/trades?${params}`);
    },
  },
  system: {
    status: () => fetchApi<SystemStatus>("/system/status"),
    pause: () =>
      fetchApi<{ status: string }>("/system/pause", { method: "POST" }),
    resume: () =>
      fetchApi<{ status: string }>("/system/resume", { method: "POST" }),
    pauseSystem: () =>
      fetchApi<{ status: string }>("/system/pause-system", { method: "POST" }),
    resumeSystem: () =>
      fetchApi<{ status: string }>("/system/resume-system", { method: "POST" }),
    emergencyStop: () =>
      fetchApi<{ status: string }>("/system/emergency-stop", {
        method: "POST",
      }),
    manualTrade: (trade: {
      symbol: string;
      action: string;
      shares: number;
      order_type?: string;
      price_target?: number;
    }) =>
      fetchApi<ManualTradeResponse>("/system/trades/manual", {
        method: "POST",
        body: JSON.stringify(trade),
      }),
    backupStatus: () =>
      fetchApi<BackupStatus>("/system/backup-status"),
    backupNow: () =>
      fetchApi<{ task_id: string; status: string }>("/system/backup-now", {
        method: "POST",
      }),
  },
  analytics: {
    performance: () =>
      fetchApi<PerformanceMetrics>("/analytics/performance"),
    attribution: () =>
      fetchApi<AttributionData>("/analytics/attribution"),
  },
  alerts: {
    list: (unreadOnly = false, limit = 50) =>
      fetchApi<AlertItem[]>(
        `/alerts?unread_only=${unreadOnly}&limit=${limit}`
      ),
    acknowledge: (id: number) =>
      fetchApi<{ status: string }>(`/alerts/${id}/acknowledge`, {
        method: "POST",
      }),
    acknowledgeAll: () =>
      fetchApi<{ status: string }>("/alerts/acknowledge-all", {
        method: "POST",
      }),
    unreadCount: () =>
      fetchApi<{ count: number }>("/alerts/unread-count"),
  },
  discovery: {
    log: (limit = 50, symbol?: string) => {
      const params = new URLSearchParams({ limit: String(limit) });
      if (symbol) params.set("symbol", symbol);
      return fetchApi<DiscoveryLogItem[]>(`/discovery/log?${params}`);
    },
    createHint: (hint_text: string, symbol?: string) =>
      fetchApi<WatchlistHint>("/discovery/hints", {
        method: "POST",
        body: JSON.stringify({ hint_text, symbol: symbol || null }),
      }),
    hints: (status?: string, limit = 50) => {
      const params = new URLSearchParams({ limit: String(limit) });
      if (status) params.set("status", status);
      return fetchApi<WatchlistHint[]>(`/discovery/hints?${params}`);
    },
    trigger: () =>
      fetchApi<{ task_id: string; task_name: string }>("/discovery/trigger", {
        method: "POST",
      }),
    status: () => fetchApi<DiscoveryStatus>("/discovery/status"),
  },
  status: {
    services: () => fetchApi<ServiceStatusResponse>("/status/services"),
  },
  tasks: {
    list: () => fetchApi<TaskListResponse>("/tasks"),
    get: (taskId: string) => fetchApi<TaskInfo>(`/tasks/${taskId}`),
    cancel: (taskId: string) =>
      fetchApi<TaskActionResponse>(`/tasks/${taskId}/cancel`, { method: "POST" }),
    retry: (taskId: string) =>
      fetchApi<TaskActionResponse>(`/tasks/${taskId}/retry`, { method: "POST" }),
    dataStatus: () => fetchApi<DataStatusResponse>("/tasks/data-status"),
    updateSchedule: (taskKey: string, body: { enabled: boolean; interval_seconds?: number; crontab?: Record<string, string> }) =>
      fetchApi<{ key: string; enabled: boolean; schedule: string; message: string }>(
        `/tasks/schedules/${taskKey}`,
        { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) },
      ),
    resetSchedule: (taskKey: string) =>
      fetchApi<{ key: string; enabled: boolean; schedule: string; message: string }>(
        `/tasks/schedules/${taskKey}`,
        { method: "DELETE" },
      ),
  },
  dataCollection: {
    getMode: () =>
      fetchApi<{ mode: string }>("/system/mode"),
    setMode: (mode: string) =>
      fetchApi<{ mode: string; previous_mode: string }>("/system/mode", {
        method: "PUT",
        body: JSON.stringify({ mode }),
      }),
  },
  rlModels: {
    list: () => fetchApi<RLModelListResponse>("/rl-models"),
    get: (id: number) => fetchApi<RLModel>(`/rl-models/${id}`),
    upload: (formData: FormData) =>
      fetch(`${API_BASE}/rl-models/upload`, {
        method: "POST",
        body: formData,
      }).then(async (res) => {
        if (!res.ok) {
          const err = await res.json().catch(() => ({ detail: res.statusText }));
          throw new Error(err.detail || res.statusText);
        }
        return res.json() as Promise<RLModel>;
      }),
    activate: (id: number) =>
      fetchApi<RLModel>(`/rl-models/${id}/activate`, { method: "POST" }),
    deactivate: (id: number) =>
      fetchApi<{ status: string; message: string }>(`/rl-models/${id}/deactivate`, {
        method: "POST",
      }),
    delete: (id: number) =>
      fetchApi<{ status: string; message: string }>(`/rl-models/${id}`, {
        method: "DELETE",
      }),
  },
  training: {
    status: () => fetchApi<TrainingStatus>("/training/status"),
  },
};
