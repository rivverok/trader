"""Gymnasium trading environment for offline RL training.

Replays historical state snapshots exported from the trading platform.
No server dependencies — runs standalone on a training machine.

Usage:
    from rl_environment import TradingEnvironment

    env = TradingEnvironment(data_path="./data/exported/", config={})
    obs, info = env.reset()
    for _ in range(1000):
        action = env.action_space.sample()
        obs, reward, terminated, truncated, info = env.step(action)
        if terminated or truncated:
            obs, info = env.reset()
"""

import json
import logging
from pathlib import Path

import gymnasium as gym
import numpy as np
import pandas as pd
from gymnasium import spaces

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────
#  Action definitions
# ─────────────────────────────────────────────────────────────────────

# Per-stock actions: 0=hold, 1=buy_small, 2=buy_large, 3=sell_small, 4=sell_all
NUM_ACTIONS_PER_STOCK = 5

ACTION_LABELS = {
    0: "hold",
    1: "buy_small",   # ~2% of portfolio
    2: "buy_large",   # ~5% of portfolio
    3: "sell_small",  # sell half position
    4: "sell_all",    # exit position
}

# Position sizing
BUY_SMALL_PCT = 0.02
BUY_LARGE_PCT = 0.05
SELL_SMALL_FRACTION = 0.5


class TradingEnvironment(gym.Env):
    """Offline RL environment that replays historical state snapshots.

    Observation: Concatenated feature vector of
        [portfolio_features, market_features, stock_1_features, ..., stock_N_features]

    Action: MultiDiscrete — one action per stock (5 choices each)

    Episode: One pass through historical data (start_date to end_date).
    Step: One trading day.

    Reward: Daily portfolio return (with optional Sharpe-like shaping).
    """

    metadata = {"render_modes": ["human"]}

    def __init__(
        self,
        data_path: str,
        config: dict | None = None,
    ):
        super().__init__()
        self.config = config or {}
        self.data_path = Path(data_path)

        # ── Load data ────────────────────────────────────────────────
        self.states_df = pd.read_parquet(self.data_path / "states.parquet")
        self.portfolio_df = pd.read_parquet(self.data_path / "portfolio.parquet")
        self.market_df = pd.read_parquet(self.data_path / "market.parquet")

        with open(self.data_path / "metadata.json") as f:
            self.metadata_info = json.load(f)

        # ── Identify stock universe and dates ────────────────────────
        self.symbols = sorted(self.metadata_info["stock_universe"])
        self.dates = sorted(self.portfolio_df["date"].unique())
        self.num_stocks = len(self.symbols)
        self.num_dates = len(self.dates)

        # ── Feature dimensions ───────────────────────────────────────
        self.portfolio_cols = [
            c for c in self.portfolio_df.columns if c != "date"
        ]
        self.market_cols = [
            c for c in self.market_df.columns if c != "date"
        ]

        # Get stock feature columns (everything except date, symbol)
        stock_cols_set = set(self.states_df.columns) - {"date", "symbol"}
        self.stock_cols = sorted(stock_cols_set)

        self.portfolio_dim = len(self.portfolio_cols)
        self.market_dim = len(self.market_cols)
        self.per_stock_dim = len(self.stock_cols)

        obs_dim = self.portfolio_dim + self.market_dim + (self.num_stocks * self.per_stock_dim)

        logger.info(
            "Environment: %d stocks, %d dates, obs_dim=%d "
            "(portfolio=%d, market=%d, per_stock=%d×%d)",
            self.num_stocks, self.num_dates, obs_dim,
            self.portfolio_dim, self.market_dim,
            self.num_stocks, self.per_stock_dim,
        )

        # ── Gymnasium spaces ─────────────────────────────────────────
        self.observation_space = spaces.Box(
            low=-np.inf, high=np.inf, shape=(obs_dim,), dtype=np.float32
        )
        self.action_space = spaces.MultiDiscrete(
            [NUM_ACTIONS_PER_STOCK] * self.num_stocks
        )

        # ── Index data for fast lookup ───────────────────────────────
        self._index_data()

        # ── Episode state ────────────────────────────────────────────
        self.current_step = 0
        self.portfolio_value = self.config.get("initial_capital", 100_000.0)
        self.cash = self.portfolio_value
        self.positions: dict[str, float] = {}  # symbol -> shares
        self.cost_basis: dict[str, float] = {}  # symbol -> avg cost per share
        self.episode_returns: list[float] = []

        # ── Risk limits (mirrors server-side) ────────────────────────
        self.max_position_pct = self.config.get("max_position_pct", 0.20)
        self.max_portfolio_risk = self.config.get("max_portfolio_risk", 0.95)
        self.transaction_cost_bps = self.config.get("transaction_cost_bps", 5)

    def _index_data(self):
        """Pre-index data by date for fast lookups during step()."""
        # Portfolio features indexed by date
        self._portfolio_by_date = {}
        for _, row in self.portfolio_df.iterrows():
            vals = row[self.portfolio_cols].values.astype(np.float32)
            self._portfolio_by_date[row["date"]] = np.nan_to_num(vals, nan=0.0)

        # Market features indexed by date
        self._market_by_date = {}
        for _, row in self.market_df.iterrows():
            vals = row[self.market_cols].values.astype(np.float32)
            self._market_by_date[row["date"]] = np.nan_to_num(vals, nan=0.0)

        # Stock features indexed by (date, symbol)
        self._stock_by_date_sym: dict[str, dict[str, np.ndarray]] = {}
        for _, row in self.states_df.iterrows():
            d, sym = row["date"], row["symbol"]
            if d not in self._stock_by_date_sym:
                self._stock_by_date_sym[d] = {}
            vals = row[self.stock_cols].values.astype(np.float32)
            self._stock_by_date_sym[d][sym] = np.nan_to_num(vals, nan=0.0)

        # Stock close prices by (date, symbol) — for trade execution
        self._close_prices: dict[str, dict[str, float]] = {}
        for _, row in self.states_df.iterrows():
            d, sym = row["date"], row["symbol"]
            if d not in self._close_prices:
                self._close_prices[d] = {}
            # price_close should be in the states columns (normalized)
            # We also need raw prices for portfolio tracking
            # Store the normalized value — we'll use relative changes
            self._close_prices[d][sym] = float(row.get("price_close", 0.0))

    def reset(self, *, seed=None, options=None):
        """Reset to start of episode."""
        super().reset(seed=seed)

        self.current_step = 0
        self.portfolio_value = self.config.get("initial_capital", 100_000.0)
        self.cash = self.portfolio_value
        self.positions = {}
        self.cost_basis = {}
        self.episode_returns = []

        obs = self._get_observation()
        info = {
            "date": self.dates[self.current_step],
            "portfolio_value": self.portfolio_value,
        }
        return obs, info

    def step(self, action: np.ndarray):
        """Execute one trading day.

        Args:
            action: Array of length num_stocks, each value in [0, 4].

        Returns:
            (observation, reward, terminated, truncated, info)
        """
        current_date = self.dates[self.current_step]
        prev_value = self.portfolio_value

        # ── Execute trades ───────────────────────────────────────────
        trades_executed = self._execute_actions(action, current_date)

        # ── Advance to next day and update portfolio ─────────────────
        self.current_step += 1
        terminated = self.current_step >= self.num_dates
        truncated = False

        if not terminated:
            next_date = self.dates[self.current_step]
            self._update_portfolio_value(next_date)

        # ── Compute reward ───────────────────────────────────────────
        daily_return = (self.portfolio_value - prev_value) / prev_value if prev_value > 0 else 0.0
        self.episode_returns.append(daily_return)

        reward = self._compute_reward(daily_return)

        obs = self._get_observation() if not terminated else np.zeros(
            self.observation_space.shape, dtype=np.float32
        )
        info = {
            "date": self.dates[min(self.current_step, self.num_dates - 1)],
            "portfolio_value": self.portfolio_value,
            "daily_return": daily_return,
            "trades": trades_executed,
            "cash": self.cash,
            "num_positions": len(self.positions),
        }

        return obs, reward, terminated, truncated, info

    def _get_observation(self) -> np.ndarray:
        """Build the observation vector for the current step."""
        date = self.dates[self.current_step]

        # Portfolio features
        pf = self._portfolio_by_date.get(date, np.zeros(self.portfolio_dim, dtype=np.float32))

        # Market features
        mkt = self._market_by_date.get(date, np.zeros(self.market_dim, dtype=np.float32))

        # Per-stock features
        stock_data = self._stock_by_date_sym.get(date, {})
        stock_vectors = []
        zero_stock = np.zeros(self.per_stock_dim, dtype=np.float32)
        for sym in self.symbols:
            stock_vectors.append(stock_data.get(sym, zero_stock))

        obs = np.concatenate([pf, mkt] + stock_vectors).astype(np.float32)
        return obs

    def _execute_actions(self, action: np.ndarray, date: str) -> list[dict]:
        """Execute trade actions and update cash/positions."""
        trades = []
        prices = self._close_prices.get(date, {})

        for i, sym in enumerate(self.symbols):
            act = int(action[i])
            if act == 0:  # hold
                continue

            price = prices.get(sym)
            if price is None or price == 0:
                continue

            current_shares = self.positions.get(sym, 0.0)
            current_value = current_shares * price

            if act == 1:  # buy_small
                target_value = self.portfolio_value * BUY_SMALL_PCT
                buy_value = min(target_value, self.cash)
                buy_value = self._apply_position_limit(sym, price, buy_value)
                if buy_value > 0:
                    shares = buy_value / price
                    cost = buy_value * (1 + self.transaction_cost_bps / 10_000)
                    if cost <= self.cash:
                        self.cash -= cost
                        self._add_position(sym, shares, price)
                        trades.append({"symbol": sym, "action": "buy_small", "value": buy_value})

            elif act == 2:  # buy_large
                target_value = self.portfolio_value * BUY_LARGE_PCT
                buy_value = min(target_value, self.cash)
                buy_value = self._apply_position_limit(sym, price, buy_value)
                if buy_value > 0:
                    shares = buy_value / price
                    cost = buy_value * (1 + self.transaction_cost_bps / 10_000)
                    if cost <= self.cash:
                        self.cash -= cost
                        self._add_position(sym, shares, price)
                        trades.append({"symbol": sym, "action": "buy_large", "value": buy_value})

            elif act == 3:  # sell_small (half position)
                if current_shares > 0:
                    sell_shares = current_shares * SELL_SMALL_FRACTION
                    sell_value = sell_shares * price
                    proceeds = sell_value * (1 - self.transaction_cost_bps / 10_000)
                    self.cash += proceeds
                    self.positions[sym] -= sell_shares
                    if self.positions[sym] <= 0:
                        del self.positions[sym]
                        self.cost_basis.pop(sym, None)
                    trades.append({"symbol": sym, "action": "sell_small", "value": sell_value})

            elif act == 4:  # sell_all
                if current_shares > 0:
                    sell_value = current_value
                    proceeds = sell_value * (1 - self.transaction_cost_bps / 10_000)
                    self.cash += proceeds
                    del self.positions[sym]
                    self.cost_basis.pop(sym, None)
                    trades.append({"symbol": sym, "action": "sell_all", "value": sell_value})

        return trades

    def _add_position(self, sym: str, shares: float, price: float):
        """Add shares to position, updating average cost basis."""
        old_shares = self.positions.get(sym, 0.0)
        old_cost = self.cost_basis.get(sym, 0.0)

        new_shares = old_shares + shares
        if new_shares > 0:
            new_cost = (old_cost * old_shares + price * shares) / new_shares
        else:
            new_cost = price

        self.positions[sym] = new_shares
        self.cost_basis[sym] = new_cost

    def _apply_position_limit(self, sym: str, price: float, buy_value: float) -> float:
        """Ensure a buy doesn't exceed max position size."""
        current_value = self.positions.get(sym, 0.0) * price
        max_value = self.portfolio_value * self.max_position_pct
        remaining = max_value - current_value
        return max(0, min(buy_value, remaining))

    def _update_portfolio_value(self, date: str):
        """Recalculate portfolio value using new day's prices."""
        prices = self._close_prices.get(date, {})
        positions_value = 0.0
        for sym, shares in list(self.positions.items()):
            price = prices.get(sym)
            if price and price > 0:
                positions_value += shares * price
            # If price is missing, keep last known value (positions unchanged)

        self.portfolio_value = self.cash + positions_value

    def _compute_reward(self, daily_return: float) -> float:
        """Compute reward with optional risk adjustment.

        Default: daily portfolio return.
        With risk shaping: penalize large drawdowns, reward consistency.
        """
        reward_type = self.config.get("reward_type", "simple_return")

        if reward_type == "simple_return":
            return daily_return

        elif reward_type == "risk_adjusted":
            # Sharpe-like: return minus volatility penalty
            if len(self.episode_returns) >= 5:
                recent = self.episode_returns[-5:]
                vol = np.std(recent)
                return daily_return - 0.5 * vol
            return daily_return

        elif reward_type == "log_return":
            return np.log1p(daily_return)

        elif reward_type == "asymmetric":
            # Penalize losses more than rewarding gains
            if daily_return < 0:
                return daily_return * 2.0
            return daily_return

        return daily_return

    def render(self):
        """Print current state."""
        date = self.dates[min(self.current_step, self.num_dates - 1)]
        print(
            f"Day {self.current_step}/{self.num_dates} ({date}) | "
            f"Value: ${self.portfolio_value:,.2f} | "
            f"Cash: ${self.cash:,.2f} | "
            f"Positions: {len(self.positions)}"
        )
