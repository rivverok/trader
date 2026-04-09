"""Feature engineering — compute 100+ technical indicators from OHLCV data.

This module runs on both the training PC (for training data prep) and
the trading server (for live inference feature generation).

All indicators are computed with pure pandas/numpy — no third-party TA
libraries required.
"""

import logging
from typing import Literal

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

# ── Default thresholds for label generation ──────────────────────────
DEFAULT_FORWARD_DAYS = 5
DEFAULT_BUY_THRESHOLD = 0.02   # +2%
DEFAULT_SELL_THRESHOLD = -0.02  # -2%


# ═════════════════════════════════════════════════════════════════════
#  Pure pandas/numpy indicator helpers
# ═════════════════════════════════════════════════════════════════════

def _sma(series: pd.Series, period: int) -> pd.Series:
    return series.rolling(window=period, min_periods=period).mean()


def _ema(series: pd.Series, period: int) -> pd.Series:
    return series.ewm(span=period, adjust=False).mean()


def _rsi(close: pd.Series, period: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


def _macd(close: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9):
    ema_fast = _ema(close, fast)
    ema_slow = _ema(close, slow)
    macd_line = ema_fast - ema_slow
    signal_line = _ema(macd_line, signal)
    histogram = macd_line - signal_line
    return macd_line, signal_line, histogram


def _true_range(high: pd.Series, low: pd.Series, close: pd.Series) -> pd.Series:
    prev_close = close.shift(1)
    tr1 = high - low
    tr2 = (high - prev_close).abs()
    tr3 = (low - prev_close).abs()
    return pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)


def _atr(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14) -> pd.Series:
    tr = _true_range(high, low, close)
    return tr.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()


def _adx(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14):
    up_move = high.diff()
    down_move = -low.diff()
    plus_dm = np.where((up_move > down_move) & (up_move > 0), up_move, 0.0)
    minus_dm = np.where((down_move > up_move) & (down_move > 0), down_move, 0.0)
    atr = _atr(high, low, close, period)
    plus_di = 100 * pd.Series(plus_dm, index=high.index).ewm(
        alpha=1 / period, min_periods=period, adjust=False
    ).mean() / atr.replace(0, np.nan)
    minus_di = 100 * pd.Series(minus_dm, index=high.index).ewm(
        alpha=1 / period, min_periods=period, adjust=False
    ).mean() / atr.replace(0, np.nan)
    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan)
    adx_val = dx.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    return adx_val, plus_di, minus_di


def _stochastic(high: pd.Series, low: pd.Series, close: pd.Series,
                k_period: int = 14, d_period: int = 3):
    lowest_low = low.rolling(window=k_period, min_periods=k_period).min()
    highest_high = high.rolling(window=k_period, min_periods=k_period).max()
    denom = (highest_high - lowest_low).replace(0, np.nan)
    stoch_k = 100 * (close - lowest_low) / denom
    stoch_d = stoch_k.rolling(window=d_period, min_periods=d_period).mean()
    return stoch_k, stoch_d


def _williams_r(high: pd.Series, low: pd.Series, close: pd.Series,
                period: int = 14) -> pd.Series:
    highest_high = high.rolling(window=period, min_periods=period).max()
    lowest_low = low.rolling(window=period, min_periods=period).min()
    denom = (highest_high - lowest_low).replace(0, np.nan)
    return -100 * (highest_high - close) / denom


def _cci(high: pd.Series, low: pd.Series, close: pd.Series,
         period: int = 14) -> pd.Series:
    tp = (high + low + close) / 3
    sma_tp = _sma(tp, period)
    mad = tp.rolling(window=period, min_periods=period).apply(
        lambda x: np.abs(x - x.mean()).mean(), raw=True
    )
    return (tp - sma_tp) / (0.015 * mad.replace(0, np.nan))


def _roc(close: pd.Series, period: int = 10) -> pd.Series:
    return close.pct_change(periods=period) * 100


def _bbands(close: pd.Series, period: int = 20, std_dev: float = 2.0):
    mid = _sma(close, period)
    std = close.rolling(window=period, min_periods=period).std()
    upper = mid + std_dev * std
    lower = mid - std_dev * std
    return upper, mid, lower


def _keltner_channel(high: pd.Series, low: pd.Series, close: pd.Series,
                     ema_period: int = 20, atr_period: int = 10, mult: float = 2.0):
    mid = _ema(close, ema_period)
    atr = _atr(high, low, close, atr_period)
    upper = mid + mult * atr
    lower = mid - mult * atr
    return upper, mid, lower


def _obv(close: pd.Series, volume: pd.Series) -> pd.Series:
    direction = np.sign(close.diff()).fillna(0)
    return (volume * direction).cumsum()


def _cmf(high: pd.Series, low: pd.Series, close: pd.Series,
         volume: pd.Series, period: int = 20) -> pd.Series:
    denom = (high - low).replace(0, np.nan)
    mfm = ((close - low) - (high - close)) / denom
    mfv = mfm * volume
    return mfv.rolling(window=period, min_periods=period).sum() / \
        volume.rolling(window=period, min_periods=period).sum().replace(0, np.nan)


def _aroon(high: pd.Series, low: pd.Series, period: int = 25):
    aroon_up = high.rolling(window=period + 1, min_periods=period + 1).apply(
        lambda x: x.argmax() / period * 100, raw=True
    )
    aroon_down = low.rolling(window=period + 1, min_periods=period + 1).apply(
        lambda x: x.argmin() / period * 100, raw=True
    )
    return aroon_up, aroon_down


def _ichimoku(high: pd.Series, low: pd.Series,
              tenkan: int = 9, kijun: int = 26, senkou_b: int = 52):
    tenkan_sen = (high.rolling(tenkan).max() + low.rolling(tenkan).min()) / 2
    kijun_sen = (high.rolling(kijun).max() + low.rolling(kijun).min()) / 2
    senkou_a = ((tenkan_sen + kijun_sen) / 2).shift(kijun)
    senkou_b_val = ((high.rolling(senkou_b).max() + low.rolling(senkou_b).min()) / 2).shift(kijun)
    return tenkan_sen, kijun_sen, senkou_a, senkou_b_val


# ═════════════════════════════════════════════════════════════════════
#  Main feature computation
# ═════════════════════════════════════════════════════════════════════

def compute_features(df: pd.DataFrame) -> pd.DataFrame:
    """Compute all technical indicator features from OHLCV data.

    Args:
        df: DataFrame with columns [open, high, low, close, volume] indexed by timestamp,
            sorted ascending (oldest first).

    Returns:
        DataFrame with original columns + all computed feature columns.
        Rows with NaN values in indicator columns are dropped.
    """
    df = df.copy().sort_index()

    if len(df) < 200:
        logger.warning("Only %d rows — some long-period indicators may be NaN", len(df))

    c, h, l, v = df["close"], df["high"], df["low"], df["volume"]

    # ── Trend indicators ─────────────────────────────────────────────
    for period in [10, 20, 50, 200]:
        df[f"sma_{period}"] = _sma(c, period)
    for period in [10, 20, 50]:
        df[f"ema_{period}"] = _ema(c, period)

    # MACD
    macd_line, macd_signal, macd_hist = _macd(c)
    df["MACD_12_26_9"] = macd_line
    df["MACDs_12_26_9"] = macd_signal
    df["MACDh_12_26_9"] = macd_hist

    # ADX
    adx_val, plus_di, minus_di = _adx(h, l, c)
    df["ADX_14"] = adx_val
    df["DMP_14"] = plus_di
    df["DMN_14"] = minus_di

    # Aroon
    aroon_up, aroon_down = _aroon(h, l)
    df["AROONU_25"] = aroon_up
    df["AROOND_25"] = aroon_down

    # Ichimoku
    tenkan, kijun, senkou_a, senkou_b = _ichimoku(h, l)
    df["ISA_9"] = tenkan
    df["ISB_26"] = kijun
    df["ITS_9"] = senkou_a
    df["IKS_26"] = senkou_b

    # ── Momentum indicators ──────────────────────────────────────────
    df["rsi_14"] = _rsi(c, 14)

    # Stochastic
    stoch_k, stoch_d = _stochastic(h, l, c)
    df["STOCHk_14_3_3"] = stoch_k
    df["STOCHd_14_3_3"] = stoch_d

    df["willr_14"] = _williams_r(h, l, c, 14)
    df["cci_14"] = _cci(h, l, c, 14)
    df["roc_10"] = _roc(c, 10)
    df["roc_20"] = _roc(c, 20)

    # ── Volatility indicators ────────────────────────────────────────
    bbu, bbm, bbl = _bbands(c)
    df["BBU_20_2.0"] = bbu
    df["BBM_20_2.0"] = bbm
    df["BBL_20_2.0"] = bbl

    df["atr_14"] = _atr(h, l, c, 14)

    kcu, kcm, kcl = _keltner_channel(h, l, c)
    df["KCU_20_2.0"] = kcu
    df["KCM_20_2.0"] = kcm
    df["KCL_20_2.0"] = kcl

    df["hist_vol_20"] = c.pct_change().rolling(20).std() * np.sqrt(252)
    df["hist_vol_60"] = c.pct_change().rolling(60).std() * np.sqrt(252)

    # ── Volume indicators ────────────────────────────────────────────
    df["obv"] = _obv(c, v)
    df["cmf"] = _cmf(h, l, c, v)
    df["vol_sma_20"] = _sma(v, 20)
    df["vol_ratio"] = v / df["vol_sma_20"].replace(0, np.nan)

    # ── Price-derived features ───────────────────────────────────────
    df["return_1d"] = c.pct_change(1)
    df["return_5d"] = c.pct_change(5)
    df["return_10d"] = c.pct_change(10)
    df["return_20d"] = c.pct_change(20)

    df["hl_range"] = (h - l) / c
    df["gap"] = (df["open"] - c.shift(1)) / c.shift(1)

    # Price relative to moving averages
    for period in [10, 20, 50, 200]:
        sma_col = f"sma_{period}"
        if sma_col in df.columns:
            df[f"price_vs_sma_{period}"] = (c - df[sma_col]) / df[sma_col]

    # Distance between MAs (trend strength)
    if "sma_50" in df.columns and "sma_200" in df.columns:
        df["ma_50_200_spread"] = (df["sma_50"] - df["sma_200"]) / df["sma_200"]

    if "ema_10" in df.columns and "ema_20" in df.columns:
        df["ema_10_20_spread"] = (df["ema_10"] - df["ema_20"]) / df["ema_20"]

    # Bollinger bandwidth
    df["bb_width"] = (df["BBU_20_2.0"] - df["BBL_20_2.0"]) / df["BBM_20_2.0"]
    bb_range = (df["BBU_20_2.0"] - df["BBL_20_2.0"]).replace(0, np.nan)
    df["bb_pct"] = (c - df["BBL_20_2.0"]) / bb_range

    return df


def generate_labels(
    df: pd.DataFrame,
    forward_days: int = DEFAULT_FORWARD_DAYS,
    buy_threshold: float = DEFAULT_BUY_THRESHOLD,
    sell_threshold: float = DEFAULT_SELL_THRESHOLD,
) -> pd.DataFrame:
    """Generate target labels based on forward returns.

    Args:
        df: DataFrame with a 'close' column.
        forward_days: Number of days ahead for return calculation.
        buy_threshold: Minimum return to be labelled 'buy' (e.g. 0.02 for 2%).
        sell_threshold: Maximum return to be labelled 'sell' (e.g. -0.02 for -2%).

    Returns:
        DataFrame with added 'forward_return' and 'label' columns.
        The last `forward_days` rows will have NaN labels and should be dropped for training.
    """
    df = df.copy()
    df["forward_return"] = df["close"].shift(-forward_days) / df["close"] - 1.0

    conditions = [
        df["forward_return"] > buy_threshold,
        df["forward_return"] < sell_threshold,
    ]
    choices = [0, 2]  # 0=buy, 2=sell
    df["label"] = np.select(conditions, choices, default=1)  # 1=hold

    # Mark rows where we can't compute forward return as NaN
    df.loc[df["forward_return"].isna(), "label"] = np.nan

    return df


LABEL_MAP = {0: "buy", 1: "hold", 2: "sell"}
LABEL_MAP_INV = {v: k for k, v in LABEL_MAP.items()}


def get_feature_columns(df: pd.DataFrame) -> list[str]:
    """Return the list of feature column names (excludes OHLCV, labels, metadata)."""
    exclude = {
        "open", "high", "low", "close", "volume",
        "forward_return", "label",
        "stock_id", "timestamp", "interval", "id",
    }
    return [c for c in df.columns if c not in exclude and not df[c].isna().all()]


def prepare_training_data(
    df: pd.DataFrame,
    forward_days: int = DEFAULT_FORWARD_DAYS,
    buy_threshold: float = DEFAULT_BUY_THRESHOLD,
    sell_threshold: float = DEFAULT_SELL_THRESHOLD,
) -> tuple[pd.DataFrame, pd.Series, list[str]]:
    """Full pipeline: features → labels → clean data ready for training.

    Returns:
        (X, y, feature_names) — feature matrix, label series, and column names.
    """
    df = compute_features(df)
    df = generate_labels(df, forward_days, buy_threshold, sell_threshold)

    feature_cols = get_feature_columns(df)

    # Drop rows with NaN labels or features
    clean = df.dropna(subset=["label"] + feature_cols)
    X = clean[feature_cols]
    y = clean["label"].astype(int)

    logger.info(
        "Training data: %d rows, %d features. Label distribution: %s",
        len(X),
        len(feature_cols),
        y.value_counts().to_dict(),
    )

    return X, y, feature_cols
