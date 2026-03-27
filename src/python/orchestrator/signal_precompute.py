"""Signal pre-computation stage (D14: precompute-once, filter-many).

Sits between data-ready and the Rust backtester. Reads M1 Arrow IPC data,
rolls up to the strategy's timeframe, computes all indicators referenced in the
strategy spec, and writes an enriched Arrow IPC file with original M1 bars
PLUS indicator signal columns.

CRITICAL: No lookahead bias. Each M1 bar sees indicator values ONLY from the
most recently COMPLETED strategy-timeframe bar (forward-fill / point-in-time).
"""
from __future__ import annotations

import tomllib
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.ipc as ipc

from logging_setup.setup import get_logger

logger = get_logger("pipeline.signal_precompute")

# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def precompute_signals(
    strategy_spec_path: str | Path,
    market_data_path: str | Path,
    output_path: str | Path | None = None,
    session_schedule: dict | None = None,
) -> Path:
    """Pre-compute indicator signals and write enriched Arrow IPC.

    Args:
        strategy_spec_path: Path to strategy TOML spec.
        market_data_path: Path to M1 Arrow IPC market data.
        output_path: Where to write enriched file. If None, writes next to
            market_data_path with ``-enriched`` suffix.
        session_schedule: Optional session schedule dict from config [sessions].
            If provided and the data has only "off_hours" sessions, sessions
            are relabeled using this schedule.

    Returns:
        Path to the enriched Arrow IPC file.
    """
    strategy_spec_path = Path(strategy_spec_path)
    market_data_path = Path(market_data_path)

    if output_path is None:
        output_path = market_data_path.with_name(
            market_data_path.stem + "-enriched" + market_data_path.suffix
        )
    output_path = Path(output_path)

    spec = _load_strategy_spec(strategy_spec_path)

    # Extract year_range from optimization_plan if present
    opt_plan = spec.get("optimization_plan", {})
    year_range = opt_plan.get("year_range")
    if year_range is not None:
        year_range = (int(year_range[0]), int(year_range[1]))

    return _precompute_core(
        spec, market_data_path, output_path, session_schedule,
        year_range=year_range,
    )


def precompute_signals_from_spec(
    strategy_spec: dict,
    market_data_path: str | Path,
    output_path: str | Path,
    session_schedule: dict | None = None,
    year_range: tuple[int, int] | None = None,
    output_resolution: str = "M1",
) -> Path:
    """Pre-compute indicator signals from an in-memory strategy spec dict.

    Same pipeline as precompute_signals() but accepts a dict instead of a
    file path. Used by the signal cache for per-entry-param precompute
    during joint optimization.

    Args:
        strategy_spec: Parsed strategy spec dict (with entry params overridden).
        market_data_path: Path to M1 Arrow IPC market data.
        output_path: Where to write enriched file.
        session_schedule: Optional session schedule dict.
        year_range: Optional (start_year, end_year) inclusive filter.
            If None, uses full dataset.
        output_resolution: Output bar resolution. "M1" (default) forward-fills
            indicators to M1 bars. "H1" writes H1 bars directly (used for
            pre-screening).

    Returns:
        Path to the enriched Arrow IPC file.
    """
    market_data_path = Path(market_data_path)
    output_path = Path(output_path)
    return _precompute_core(
        strategy_spec, market_data_path, output_path, session_schedule,
        year_range=year_range, output_resolution=output_resolution,
    )


def _precompute_core(
    spec: dict,
    market_data_path: Path,
    output_path: Path,
    session_schedule: dict | None = None,
    year_range: tuple[int, int] | None = None,
    output_resolution: str = "M1",
) -> Path:
    """Core signal precompute pipeline.

    Loads M1 data, rolls up to strategy timeframe, computes all indicators
    referenced in the strategy spec, forward-fills to M1 bars, and writes
    the enriched Arrow IPC file.

    Args:
        year_range: Optional (start_year, end_year) inclusive filter applied
            after loading M1 data. Reduces dataset before any computation.
        output_resolution: "M1" (default) forward-fills to M1, "H1" writes
            H1 bars directly (for pre-screening).
    """
    timeframe = spec["metadata"]["timeframe"]
    conditions = spec["entry_rules"]["conditions"]

    logger.info(
        "Signal precompute starting",
        extra={
            "component": "pipeline.signal_precompute",
            "ctx": {
                "strategy": spec["metadata"]["name"],
                "timeframe": timeframe,
                "conditions": len(conditions),
                "data_path": str(market_data_path),
            },
        },
    )

    # 1. Load M1 data
    m1_df = _load_arrow_ipc(market_data_path)

    # 1a. Year-range filtering (optional)
    if year_range is not None:
        yr_start, yr_end = year_range
        pre_filter_len = len(m1_df)
        m1_df = m1_df[
            (m1_df["_datetime"].dt.year >= yr_start)
            & (m1_df["_datetime"].dt.year <= yr_end)
        ].copy()
        m1_df.reset_index(drop=True, inplace=True)
        logger.info(
            f"Year-range filter [{yr_start}, {yr_end}]: {pre_filter_len} -> {len(m1_df)} bars",
            extra={
                "component": "pipeline.signal_precompute",
                "ctx": {"year_range": list(year_range), "pre": pre_filter_len, "post": len(m1_df)},
            },
        )

    # Strip any pre-existing indicator columns (e.g., from previously enriched
    # data) to prevent pandas merge _x/_y collisions during forward-fill.
    base_columns = {
        "timestamp", "open", "high", "low", "close", "bid", "ask",
        "session", "quarantined", "volume", "_datetime",
    }
    extra_cols = [c for c in m1_df.columns if c not in base_columns]
    if extra_cols:
        m1_df = m1_df.drop(columns=extra_cols)
        logger.info(
            f"Stripped {len(extra_cols)} pre-existing indicator columns from input",
            extra={
                "component": "pipeline.signal_precompute",
                "ctx": {"dropped": extra_cols},
            },
        )

    logger.info(
        f"Loaded {len(m1_df)} M1 bars",
        extra={"component": "pipeline.signal_precompute"},
    )

    # 1b. Relabel sessions if data has only "off_hours" and schedule provided
    if session_schedule is not None and "session" in m1_df.columns:
        unique_sessions = m1_df["session"].unique()
        if len(unique_sessions) == 1 and unique_sessions[0] == "off_hours":
            m1_df = _relabel_sessions(m1_df, session_schedule)
            logger.info(
                "Sessions relabeled from off_hours using schedule",
                extra={
                    "component": "pipeline.signal_precompute",
                    "ctx": {"sessions": m1_df["session"].value_counts().to_dict()},
                },
            )

    # 2. Roll up to strategy timeframe
    tf_df = _rollup_timeframe(m1_df, timeframe)
    logger.info(
        f"Rolled up to {len(tf_df)} {timeframe} bars",
        extra={"component": "pipeline.signal_precompute"},
    )

    # 3. Compute indicators on rolled-up bars
    indicator_columns: dict[str, pd.Series] = {}
    for condition in conditions:
        indicator = condition["indicator"]
        params = condition.get("parameters", {})
        col_name = build_signal_column_name(indicator, params)

        if col_name in indicator_columns:
            continue  # Already computed

        series = _compute_indicator(indicator, params, tf_df, m1_df=m1_df)
        if series is not None:
            indicator_columns[col_name] = series
            logger.info(
                f"Computed indicator column: {col_name}",
                extra={"component": "pipeline.signal_precompute"},
            )
        else:
            logger.warning(
                f"Unsupported indicator: {indicator}, skipping",
                extra={"component": "pipeline.signal_precompute"},
            )

    # 3b. Auto-compute ATR if exit rules reference atr_multiple or chandelier
    exit_rules = spec.get("exit_rules", {})
    needs_atr = False
    atr_period = 14  # default

    sl_cfg = exit_rules.get("stop_loss", {})
    tp_cfg = exit_rules.get("take_profit", {})
    tr_cfg = exit_rules.get("trailing", {})

    if sl_cfg.get("type") == "atr_multiple" or tp_cfg.get("type") == "atr_multiple":
        needs_atr = True
    if tr_cfg.get("type") == "chandelier":
        needs_atr = True
        tr_params = tr_cfg.get("params", {})
        atr_period = int(tr_params.get("atr_period", 14))

    if needs_atr:
        atr_col_name = f"atr_{atr_period}"
        if atr_col_name not in indicator_columns:
            atr_series = _compute_indicator(
                "atr", {"period": atr_period}, tf_df, m1_df=m1_df,
            )
            if atr_series is not None:
                indicator_columns[atr_col_name] = atr_series
                logger.info(
                    f"Auto-computed ATR for exit rules: {atr_col_name}",
                    extra={"component": "pipeline.signal_precompute"},
                )

    # 4. Forward-fill to M1 bars (point-in-time, NO lookahead)
    #    If output_resolution != "M1", write timeframe bars directly
    #    (used for H1 pre-screening: skip the expensive M1 forward-fill).
    if output_resolution != "M1":
        enriched_df = tf_df.copy()
        for col_name, series in indicator_columns.items():
            enriched_df[col_name] = series.shift(1).values
        # Ensure _datetime column exists for _write_arrow_ipc
        if "_datetime" not in enriched_df.columns:
            enriched_df["_datetime"] = enriched_df.index
        enriched_df = enriched_df.reset_index(drop=True)
    else:
        enriched_df = _forward_fill_to_m1(m1_df, tf_df, indicator_columns, timeframe)

    # 5. Write enriched Arrow IPC
    _write_arrow_ipc(enriched_df, output_path)

    n_signal_cols = len(indicator_columns)
    logger.info(
        f"Signal precompute complete: {n_signal_cols} indicator columns written",
        extra={
            "component": "pipeline.signal_precompute",
            "ctx": {
                "output_path": str(output_path),
                "m1_bars": len(m1_df),
                "tf_bars": len(tf_df),
                "signal_columns": list(indicator_columns.keys()),
            },
        },
    )

    return output_path


# ---------------------------------------------------------------------------
# Column naming — must match Rust build_signal_column_name() in engine.rs
# ---------------------------------------------------------------------------


def build_signal_column_name(indicator: str, params: dict) -> str:
    """Build column name matching Rust convention.

    Convention from engine.rs: indicator + "_" + value for each param
    whose key is ``period``, ``length``, or ``window``.
    Other param keys (fast_period, slow_period, etc.) are NOT appended.
    """
    name = indicator
    for key in ("period", "length", "window"):
        if key in params:
            val = params[key]
            if isinstance(val, float):
                val = int(val)
            name = f"{name}_{val}"
    return name


# ---------------------------------------------------------------------------
# Strategy spec loader
# ---------------------------------------------------------------------------


def _load_strategy_spec(path: Path) -> dict:
    with open(path, "rb") as f:
        return tomllib.load(f)


# ---------------------------------------------------------------------------
# Session relabeling
# ---------------------------------------------------------------------------


def _relabel_sessions(df: pd.DataFrame, session_schedule: dict) -> pd.DataFrame:
    """Relabel sessions from off_hours using the session schedule.

    Uses the _datetime column (already in UTC) to assign session labels
    based on UTC hour boundaries from the config.
    """
    from datetime import time as dt_time

    def _parse_time(t: str) -> dt_time:
        parts = t.split(":")
        return dt_time(int(parts[0]), int(parts[1]))

    result = df.copy()
    hours = result["_datetime"].dt.hour
    minutes = result["_datetime"].dt.minute
    total_minutes = hours * 60 + minutes

    # Parse boundaries
    boundaries = {}
    for key in ("asian", "london", "new_york", "london_ny_overlap", "off_hours"):
        if key not in session_schedule:
            continue
        sess = session_schedule[key]
        if "start" not in sess or "end" not in sess:
            continue
        s = _parse_time(sess["start"])
        e = _parse_time(sess["end"])
        boundaries[key] = (s.hour * 60 + s.minute, e.hour * 60 + e.minute)

    # Default to off_hours
    labels = pd.Series("off_hours", index=result.index)

    # Assign broader sessions first
    for key in ("asian", "london", "new_york", "off_hours"):
        if key not in boundaries:
            continue
        s_min, e_min = boundaries[key]
        if s_min < e_min:
            mask = (total_minutes >= s_min) & (total_minutes < e_min)
        else:
            mask = (total_minutes >= s_min) | (total_minutes < e_min)
        labels[mask] = key

    # Overlap overrides
    if "london_ny_overlap" in boundaries:
        s_min, e_min = boundaries["london_ny_overlap"]
        mask = (total_minutes >= s_min) & (total_minutes < e_min)
        labels[mask] = "london_ny_overlap"

    result["session"] = labels
    return result


# ---------------------------------------------------------------------------
# Arrow IPC I/O
# ---------------------------------------------------------------------------


def _load_arrow_ipc(path: Path) -> pd.DataFrame:
    """Load Arrow IPC file into a pandas DataFrame."""
    reader = ipc.open_file(str(path))
    table = reader.read_all()
    df = table.to_pandas()

    # Ensure timestamp is datetime for resampling.
    # Auto-detect unit: if max value > 1e15 it's microseconds, > 1e12 ms, else seconds.
    if "timestamp" in df.columns:
        ts_max = df["timestamp"].max()
        if ts_max > 1e15:
            unit = "us"
        elif ts_max > 1e12:
            unit = "ms"
        else:
            unit = "s"
        df["_datetime"] = pd.to_datetime(df["timestamp"], unit=unit, utc=True)
    return df


def _write_arrow_ipc(df: pd.DataFrame, path: Path) -> None:
    """Write DataFrame to Arrow IPC file.

    Preserves the original Arrow schema types (e.g., string not large_string)
    so the Rust backtester can downcast correctly.
    """
    path.parent.mkdir(parents=True, exist_ok=True)

    # Drop helper columns before writing
    write_df = df.drop(columns=["_datetime"], errors="ignore")

    table = pa.Table.from_pandas(write_df, preserve_index=False)

    # Fix schema: pandas->arrow defaults to large_string for object columns,
    # but the Rust backtester expects Utf8 (string). Cast any large_string
    # columns to string, and ensure bool columns stay bool (not int8).
    new_fields = []
    needs_cast = False
    for field in table.schema:
        if field.type == pa.large_string():
            new_fields.append(pa.field(field.name, pa.string(), field.nullable))
            needs_cast = True
        elif field.type == pa.large_binary():
            new_fields.append(pa.field(field.name, pa.binary(), field.nullable))
            needs_cast = True
        else:
            new_fields.append(field)

    if needs_cast:
        target_schema = pa.schema(new_fields)
        table = table.cast(target_schema)

    with ipc.new_file(str(path), table.schema) as writer:
        writer.write_table(table)


# ---------------------------------------------------------------------------
# Timeframe rollup (M1 -> H1, H4, etc.)
# ---------------------------------------------------------------------------

_TF_RESAMPLE_MAP = {
    "M1": "1min",
    "M5": "5min",
    "M15": "15min",
    "H1": "1h",
    "H4": "4h",
    "D1": "1D",
}


def _rollup_timeframe(m1_df: pd.DataFrame, timeframe: str) -> pd.DataFrame:
    """Aggregate M1 bars to the strategy's timeframe using OHLCV rules.

    If the strategy is already M1, returns a copy with the period-start index.
    """
    if timeframe == "M1":
        result = m1_df.copy()
        result.index = result["_datetime"]
        return result

    freq = _TF_RESAMPLE_MAP.get(timeframe)
    if freq is None:
        raise ValueError(f"Unsupported timeframe: {timeframe}")

    # Set datetime index for resampling
    indexed = m1_df.set_index("_datetime")

    # OHLCV aggregation rules
    agg_rules = {
        "open": "first",
        "high": "max",
        "low": "min",
        "close": "last",
    }
    # Add volume if present
    if "volume" in indexed.columns:
        agg_rules["volume"] = "sum"

    # Session: take the first session label (majority would be expensive)
    if "session" in indexed.columns:
        agg_rules["session"] = "first"

    # Timestamp: take the first (period start)
    if "timestamp" in indexed.columns:
        agg_rules["timestamp"] = "first"

    # Use label='left', closed='left' so the index is the period START
    resampled = indexed.resample(freq, label="left", closed="left").agg(agg_rules)

    # Drop periods with no data (weekends, gaps)
    resampled = resampled.dropna(subset=["close"])

    return resampled


# ---------------------------------------------------------------------------
# Indicator computation
# ---------------------------------------------------------------------------


def _compute_indicator(
    indicator: str, params: dict, tf_df: pd.DataFrame,
    m1_df: pd.DataFrame | None = None,
) -> pd.Series | None:
    """Compute a single indicator on timeframe-level bars.

    Returns a Series indexed like tf_df, or None if unsupported.
    """
    close = tf_df["close"]
    high = tf_df["high"]
    low = tf_df["low"]

    match indicator:
        case "sma":
            period = int(params["period"])
            return close.rolling(window=period, min_periods=period).mean()

        case "ema":
            period = int(params["period"])
            return close.ewm(span=period, adjust=False, min_periods=period).mean()

        case "sma_crossover":
            fast = int(params["fast_period"])
            slow = int(params["slow_period"])
            sma_fast = close.rolling(window=fast, min_periods=fast).mean()
            sma_slow = close.rolling(window=slow, min_periods=slow).mean()
            # Positive = fast above slow, negative = fast below slow
            return sma_fast - sma_slow

        case "ema_crossover":
            fast = int(params["fast_period"])
            slow = int(params["slow_period"])
            ema_fast = close.ewm(span=fast, adjust=False, min_periods=fast).mean()
            ema_slow = close.ewm(span=slow, adjust=False, min_periods=slow).mean()
            return ema_fast - ema_slow

        case "atr":
            period = int(params["period"])
            return _compute_atr(high, low, close, period)

        case "true_range":
            return _compute_true_range(high, low, close)

        case "rsi":
            period = int(params["period"])
            return _compute_rsi(close, period)

        case "bollinger_bands":
            # Returns middle band; upper/lower could be separate columns
            period = int(params["period"])
            num_std = float(params.get("num_std", 2.0))
            sma = close.rolling(window=period, min_periods=period).mean()
            std = close.rolling(window=period, min_periods=period).std()
            # Return middle band (same as SMA); for upper/lower, extend later
            return sma  # Could return dict for upper/lower

        case "rolling_max":
            period = int(params["period"])
            return high.rolling(window=period, min_periods=period).max()

        case "rolling_min":
            period = int(params["period"])
            return low.rolling(window=period, min_periods=period).min()

        case "donchian_channel":
            period = int(params["period"])
            upper = high.rolling(window=period, min_periods=period).max()
            lower = low.rolling(window=period, min_periods=period).min()
            return (upper + lower) / 2  # Middle channel

        case "macd":
            fast = int(params["fast_period"])
            slow = int(params["slow_period"])
            signal_period = int(params["signal_period"])
            ema_fast = close.ewm(span=fast, adjust=False, min_periods=fast).mean()
            ema_slow = close.ewm(span=slow, adjust=False, min_periods=slow).mean()
            macd_line = ema_fast - ema_slow
            # Return MACD histogram (line - signal)
            signal_line = macd_line.ewm(
                span=signal_period, adjust=False, min_periods=signal_period,
            ).mean()
            return macd_line - signal_line

        case "adx":
            period = int(params["period"])
            return _compute_adx(high, low, close, period)

        case "williams_r":
            period = int(params["period"])
            highest = high.rolling(window=period, min_periods=period).max()
            lowest = low.rolling(window=period, min_periods=period).min()
            return -100 * (highest - close) / (highest - lowest).replace(0, np.nan)

        case "cci":
            period = int(params["period"])
            tp = (high + low + close) / 3
            sma_tp = tp.rolling(window=period, min_periods=period).mean()
            mad = tp.rolling(window=period, min_periods=period).apply(
                lambda x: np.mean(np.abs(x - x.mean())), raw=True,
            )
            return (tp - sma_tp) / (0.015 * mad).replace(0, np.nan)

        case "stochastic":
            k_period = int(params["k_period"])
            d_period = int(params["d_period"])
            lowest = low.rolling(window=k_period, min_periods=k_period).min()
            highest = high.rolling(window=k_period, min_periods=k_period).max()
            k = 100 * (close - lowest) / (highest - lowest).replace(0, np.nan)
            # Return %K (could add %D as separate column)
            return k

        case "swing_highs":
            n = int(params.get("left_bars", params.get("right_bars", 3)))
            swing_h, _ = _detect_swings(high, low, n)
            return swing_h.astype(float)

        case "swing_lows":
            n = int(params.get("left_bars", params.get("right_bars", 3)))
            _, swing_l = _detect_swings(high, low, n)
            return swing_l.astype(float)

        case "market_structure":
            n = int(params.get("swing_bars", 3))
            return _compute_market_structure_series(high, low, n)

        case "swing_pullback":
            if m1_df is None:
                logger.warning(
                    "swing_pullback requires M1 data for multi-TF computation",
                    extra={"component": "pipeline.signal_precompute"},
                )
                return None
            return _compute_swing_pullback(m1_df, tf_df, params)

        case "channel_breakout":
            return _compute_channel_breakout(tf_df, params)

        case _:
            return None


def _compute_true_range(
    high: pd.Series, low: pd.Series, close: pd.Series,
) -> pd.Series:
    """True Range: max(H-L, |H-Cprev|, |L-Cprev|)."""
    prev_close = close.shift(1)
    tr1 = high - low
    tr2 = (high - prev_close).abs()
    tr3 = (low - prev_close).abs()
    return pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)


def _compute_atr(
    high: pd.Series, low: pd.Series, close: pd.Series, period: int,
) -> pd.Series:
    """ATR using Wilder's smoothing (equivalent to EMA with alpha=1/period)."""
    tr = _compute_true_range(high, low, close)
    return tr.ewm(alpha=1.0 / period, adjust=False, min_periods=period).mean()


def _compute_rsi(close: pd.Series, period: int) -> pd.Series:
    """RSI using standard RS calculation with Wilder's smoothing."""
    delta = close.diff()
    gain = delta.where(delta > 0, 0.0)
    loss = (-delta).where(delta < 0, 0.0)

    avg_gain = gain.ewm(alpha=1.0 / period, adjust=False, min_periods=period).mean()
    avg_loss = loss.ewm(alpha=1.0 / period, adjust=False, min_periods=period).mean()

    rs = avg_gain / avg_loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


def _compute_adx(
    high: pd.Series, low: pd.Series, close: pd.Series, period: int,
) -> pd.Series:
    """ADX: Average Directional Index."""
    plus_dm = high.diff()
    minus_dm = -low.diff()

    plus_dm = plus_dm.where((plus_dm > minus_dm) & (plus_dm > 0), 0.0)
    minus_dm = minus_dm.where((minus_dm > plus_dm) & (minus_dm > 0), 0.0)

    atr = _compute_atr(high, low, close, period)

    plus_di = 100 * (
        plus_dm.ewm(alpha=1.0 / period, adjust=False, min_periods=period).mean()
        / atr.replace(0, np.nan)
    )
    minus_di = 100 * (
        minus_dm.ewm(alpha=1.0 / period, adjust=False, min_periods=period).mean()
        / atr.replace(0, np.nan)
    )

    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan)
    return dx.ewm(alpha=1.0 / period, adjust=False, min_periods=period).mean()


# ---------------------------------------------------------------------------
# Swing detection helpers
# ---------------------------------------------------------------------------


def _detect_swings(
    high: pd.Series, low: pd.Series, n: int,
) -> tuple[pd.Series, pd.Series]:
    """Detect swing highs/lows using fractal-style n-bar comparison.

    A swing high at bar i: high[i] > all highs in [i-n..i+n] (strict).
    A swing low at bar i: low[i] < all lows in [i-n..i+n] (strict).

    Returns (swing_high_bool, swing_low_bool).
    Note: Detection uses future bars; apply lag before using levels.

    Uses numpy arrays internally to avoid pandas SingleBlockManager bugs
    that corrupt boolean Series operations in some pandas versions.
    """
    h = high.values.astype(np.float64)
    l = low.values.astype(np.float64)
    length = len(h)

    sh = np.ones(length, dtype=bool)
    sl = np.ones(length, dtype=bool)

    for j in range(1, n + 1):
        # Forward shift: compare with bar j positions earlier
        sh[:length - j] &= h[:length - j] > h[j:]
        sh[length - j:] = False
        # Backward shift: compare with bar j positions later
        sh[j:] &= h[j:] > h[:length - j]
        sh[:j] = False

        sl[:length - j] &= l[:length - j] < l[j:]
        sl[length - j:] = False
        sl[j:] &= l[j:] < l[:length - j]
        sl[:j] = False

    # Edges can't be confirmed
    sh[:n] = False
    sh[-n:] = False
    sl[:n] = False
    sl[-n:] = False

    return pd.Series(sh, index=high.index), pd.Series(sl, index=low.index)


def _track_swing_levels(
    swing_bool: pd.Series, price: pd.Series, lag: int,
) -> tuple[pd.Series, pd.Series]:
    """Track last and previous swing levels with confirmation lag.

    The lag shifts swing knowledge forward by ``lag`` bars to prevent
    lookahead — in real-time, a swing at bar i is only confirmed at
    bar i + lag (when all right_bars have formed).

    Returns (last_level, prev_level) — both forward-filled.
    """
    # Swing prices at actual swing bars, delayed by lag
    lagged_prices = price.where(swing_bool, np.nan).shift(lag)

    # Forward-fill to get "last known" level at each bar
    last_level = lagged_prices.ffill()

    # Previous level: at each new swing detection, the prior last_level was the prev swing
    prev_at_swing = last_level.shift(1).where(lagged_prices.notna())
    prev_level = prev_at_swing.ffill()

    return last_level, prev_level


def _compute_market_structure_series(
    high: pd.Series, low: pd.Series, swing_bars: int,
) -> pd.Series:
    """Compute market structure bias from swing sequences.

    Returns 1.0 (bullish: HH + HL), -1.0 (bearish: LL + LH), 0.0 (neutral).
    Includes confirmation lag so no lookahead bias.
    """
    swing_h, swing_l = _detect_swings(high, low, swing_bars)
    last_high, prev_high = _track_swing_levels(swing_h, high, swing_bars)
    last_low, prev_low = _track_swing_levels(swing_l, low, swing_bars)

    hh = last_high > prev_high  # Higher High
    hl = last_low > prev_low    # Higher Low
    ll = last_low < prev_low    # Lower Low
    lh = last_high < prev_high  # Lower High

    structure = pd.Series(0.0, index=high.index)
    structure[hh & hl] = 1.0
    structure[ll & lh] = -1.0
    return structure


def _compute_swing_pullback(
    m1_df: pd.DataFrame, tf_df: pd.DataFrame, params: dict,
) -> pd.Series:
    """Compute multi-TF swing pullback composite signal.

    Combines HTF structural bias with LTF swing overextension:
    - Buy (1.0): HTF bullish + price < LTF swing low - ATR*mult + new swing
    - Sell (-1.0): HTF bearish + price > LTF swing high + ATR*mult + new swing
    Each swing extreme is traded only once (no repeat signals).
    """
    swing_bars = int(params.get("swing_bars", 3))
    atr_period = int(params.get("atr_period", 14))
    atr_mult = float(params.get("atr_multiplier", 1.0))
    htf = str(params.get("htf_timeframe", "H1"))

    # --- HTF bias ---
    htf_df = _rollup_timeframe(m1_df, htf)
    htf_structure = _compute_market_structure_series(
        htf_df["high"], htf_df["low"], swing_bars,
    )
    # Point-in-time: only see COMPLETED HTF bar's structure
    htf_structure_pit = htf_structure.shift(1)

    # Forward-fill HTF bias to LTF bars via merge_asof
    htf_lookup = pd.DataFrame({
        "_htf_dt": pd.to_datetime(htf_df.index.values, utc=True),
        "htf_bias": htf_structure_pit.values,
    }).sort_values("_htf_dt")

    ltf_dt = pd.to_datetime(tf_df.index.values, utc=True)
    ltf_lookup = pd.DataFrame({"_ltf_dt": ltf_dt}).sort_values("_ltf_dt")

    merged = pd.merge_asof(
        ltf_lookup, htf_lookup,
        left_on="_ltf_dt", right_on="_htf_dt",
        direction="backward",
    )
    bias = merged["htf_bias"].values

    # --- LTF swings + ATR ---
    swing_h, swing_l = _detect_swings(tf_df["high"], tf_df["low"], swing_bars)
    last_sh, _ = _track_swing_levels(swing_h, tf_df["high"], swing_bars)
    last_sl, _ = _track_swing_levels(swing_l, tf_df["low"], swing_bars)
    atr_series = _compute_atr(
        tf_df["high"], tf_df["low"], tf_df["close"], atr_period,
    )

    # --- Entry signal evaluation ---
    close = tf_df["close"].values
    lh = last_sh.values
    ll = last_sl.values
    atr_v = atr_series.values

    signal = np.zeros(len(close))
    # NaN sentinels: np.nan != np.nan is True, so the first valid swing
    # always fires (desired — we want to trade the first swing we see).
    prev_buy_swing = np.nan
    prev_sell_swing = np.nan

    for i in range(len(close)):
        a = atr_v[i]
        if np.isnan(a) or a <= 0:
            continue
        if np.isnan(ll[i]) or np.isnan(lh[i]) or np.isnan(bias[i]):
            continue

        # Buy: HTF bullish + overextended below LTF swing low + new swing
        if bias[i] > 0:
            if close[i] < ll[i] - a * atr_mult and ll[i] != prev_buy_swing:
                signal[i] = 1.0
                prev_buy_swing = ll[i]

        # Sell: HTF bearish + overextended above LTF swing high + above low + new swing
        if bias[i] < 0:
            if (
                close[i] > lh[i] + a * atr_mult
                and close[i] > ll[i]
                and lh[i] != prev_sell_swing
            ):
                signal[i] = -1.0
                prev_sell_swing = lh[i]

    return pd.Series(signal, index=tf_df.index)


def _compute_channel_breakout(
    tf_df: pd.DataFrame, params: dict,
) -> pd.Series:
    """Compute adaptive parallel channel breakout signal.

    Algorithm (MQL5 Part 62 — faithful reproduction):
    1. Detect swing highs/lows with ATR-based minimum-size filter.
    2. Build upper channel boundary from last 2 confirmed swing highs.
    3. Project lower boundary in parallel using swing-low offset (equidistant).
    4. Detect breakouts: N consecutive confirmation bars closing beyond boundary.
    5. Filter by same-timeframe market structure alignment.
    6. Each breakout signaled only once (minimum gap between signals).

    Returns 1.0 (bullish breakout), -1.0 (bearish breakout), 0.0 (no signal).

    Point-in-time: swings are lagged by swing_bars (confirmation delay).
    No lookahead bias — each bar only sees previously confirmed swings.
    """
    swing_bars = int(params.get("swing_bars", 3))
    atr_period = int(params.get("atr_period", 14))
    atr_mult = float(params.get("atr_multiplier", 1.0))
    confirm_bars = int(params.get("confirmation_bars", 2))
    use_close = params.get("use_close", True)
    if isinstance(use_close, str):
        use_close = use_close.lower() == "true"

    n = len(tf_df)
    close = tf_df["close"].values
    high_arr = tf_df["high"].values
    low_arr = tf_df["low"].values

    # ATR for swing-size filtering and channel-width sanity checks
    atr_series = _compute_atr(
        tf_df["high"], tf_df["low"], tf_df["close"], atr_period,
    )
    atr_v = atr_series.values

    # Swing detection (fractal n-bar) — convert to numpy to avoid pandas
    # .iloc SystemError under certain parameter combos in tight loops.
    swing_h_s, swing_l_s = _detect_swings(tf_df["high"], tf_df["low"], swing_bars)
    swing_h = swing_h_s.values
    swing_l = swing_l_s.values

    # Market structure on the same timeframe (for breakout-direction filter)
    structure = _compute_market_structure_series(
        tf_df["high"], tf_df["low"], swing_bars,
    )
    struct_v = structure.values

    lag = swing_bars  # confirmation delay for point-in-time

    # Accumulate confirmed, ATR-filtered swings as (bar_index, price)
    confirmed_highs: list[tuple[int, float]] = []
    confirmed_lows: list[tuple[int, float]] = []

    signal = np.zeros(n)
    last_signal_bar = -999
    min_gap = max(confirm_bars * 3, swing_bars * 2)

    for i in range(n):
        # --- Register newly confirmed swings (lag bars after detection) ---
        cb = i - lag
        if 0 <= cb < n:
            a_cb = atr_v[cb]
            if not np.isnan(a_cb) and a_cb > 0:
                min_size = a_cb * atr_mult

                if swing_h[cb]:
                    # Swing size: high minus max(min-left-lows, min-right-lows)
                    # Matches MQL5: swingSize = currentHigh - max(leftLow, rightLow)
                    left_start = max(0, cb - swing_bars)
                    right_end = min(cb + swing_bars + 1, n)
                    left_low = (
                        low_arr[left_start:cb].min()
                        if cb > left_start else low_arr[cb]
                    )
                    right_low = (
                        low_arr[cb + 1:right_end].min()
                        if right_end > cb + 1 else low_arr[cb]
                    )
                    swing_size = high_arr[cb] - max(left_low, right_low)
                    if swing_size >= min_size:
                        confirmed_highs.append((cb, float(high_arr[cb])))

                if swing_l[cb]:
                    left_start = max(0, cb - swing_bars)
                    right_end = min(cb + swing_bars + 1, n)
                    left_high = (
                        high_arr[left_start:cb].max()
                        if cb > left_start else high_arr[cb]
                    )
                    right_high = (
                        high_arr[cb + 1:right_end].max()
                        if right_end > cb + 1 else high_arr[cb]
                    )
                    swing_size = min(left_high, right_high) - low_arr[cb]
                    if swing_size >= min_size:
                        confirmed_lows.append((cb, float(low_arr[cb])))

        # --- Need >= 2 swing highs + >= 1 swing low to build a channel ---
        if len(confirmed_highs) < 2 or len(confirmed_lows) < 1:
            continue

        # --- Build channel (MQL5 parallel projection method) ---
        # Upper boundary: line through last 2 confirmed swing highs
        sh1_b, sh1_p = confirmed_highs[-2]
        sh2_b, sh2_p = confirmed_highs[-1]

        bar_diff = sh2_b - sh1_b
        if bar_diff < 2:
            continue  # swings too close, slope unreliable

        slope = (sh2_p - sh1_p) / bar_diff

        # Upper boundary price at current bar
        upper = sh2_p + slope * (i - sh2_b)

        # Channel width: distance from upper line to the most recent swing low
        # (equidistant offset — faithful to article's parallel projection)
        sl_b, sl_p = confirmed_lows[-1]
        upper_at_sl = sh2_p + slope * (sl_b - sh2_b)
        width = upper_at_sl - sl_p

        # If width <= 0 (swing low above upper line), try previous swing low
        if width <= 0 and len(confirmed_lows) >= 2:
            sl_b, sl_p = confirmed_lows[-2]
            upper_at_sl = sh2_p + slope * (sl_b - sh2_b)
            width = upper_at_sl - sl_p
        if width <= 0:
            continue  # no valid channel

        lower = upper - width

        # Sanity: channel width should be reasonable relative to ATR
        a_i = atr_v[i]
        if np.isnan(a_i) or a_i <= 0:
            continue
        if width < a_i * 0.3 or width > a_i * 15:
            continue  # too narrow or absurdly wide

        # --- Minimum gap between signals ---
        if i - last_signal_bar < min_gap:
            continue

        # --- Bullish breakout: price above upper channel ---
        bp = close[i] if use_close else high_arr[i]
        if bp > upper:
            ok = True
            for j in range(1, confirm_bars + 1):
                ci = i - j
                if ci < 0:
                    ok = False
                    break
                upper_at_ci = sh2_p + slope * (ci - sh2_b)
                cp = close[ci] if use_close else high_arr[ci]
                if cp <= upper_at_ci:
                    ok = False
                    break

            # Structure filter: bullish or neutral structure for bullish breakout
            if ok and not np.isnan(struct_v[i]) and struct_v[i] >= 0:
                signal[i] = 1.0
                last_signal_bar = i
                continue

        # --- Bearish breakout: price below lower channel ---
        bp = close[i] if use_close else low_arr[i]
        if bp < lower:
            ok = True
            for j in range(1, confirm_bars + 1):
                ci = i - j
                if ci < 0:
                    ok = False
                    break
                lower_at_ci = (sh2_p + slope * (ci - sh2_b)) - width
                cp = close[ci] if use_close else low_arr[ci]
                if cp >= lower_at_ci:
                    ok = False
                    break

            # Structure filter: bearish or neutral structure for bearish breakout
            if ok and not np.isnan(struct_v[i]) and struct_v[i] <= 0:
                signal[i] = -1.0
                last_signal_bar = i

    return pd.Series(signal, index=tf_df.index)


# ---------------------------------------------------------------------------
# Forward-fill indicators to M1 (point-in-time, NO lookahead)
# ---------------------------------------------------------------------------


def _forward_fill_to_m1(
    m1_df: pd.DataFrame,
    tf_df: pd.DataFrame,
    indicator_columns: dict[str, pd.Series],
    timeframe: str,
) -> pd.DataFrame:
    """Assign each M1 bar the indicator value from the most recently COMPLETED
    strategy-timeframe bar.

    Point-in-time semantics:
    - If current M1 bar is at 10:15 and timeframe is H1, it gets indicator
      values from the 09:00-09:59 bar (completed), NOT the 10:00-10:59 bar.
    - This is achieved by shifting the timeframe indicator values forward by one
      period before merging via asof.

    For M1 timeframe, indicators are shifted by 1 bar (previous bar's value).
    """
    result = m1_df.copy()

    if not indicator_columns:
        return result

    if timeframe == "M1":
        # For M1, just shift by 1 bar (previous bar's completed value)
        for col_name, series in indicator_columns.items():
            shifted = series.shift(1)
            result[col_name] = shifted.values
        return result

    # Build a lookup table from timeframe bars with shifted indicators.
    # The shift ensures we only see the COMPLETED bar's value:
    # - tf_df index is the period START (e.g., 10:00 for the 10:00-10:59 bar)
    # - An M1 bar at 10:15 should see the 09:00 bar's indicators, NOT 10:00's
    # - By shifting indicators forward by 1, the 10:00 index row now holds
    #   the 09:00 bar's indicator values
    # - pd.merge_asof with direction='backward' then correctly assigns 09:00's
    #   values to all M1 bars from 10:00 to 10:59

    tf_lookup = pd.DataFrame(index=tf_df.index)
    for col_name, series in indicator_columns.items():
        # Shift forward by 1 timeframe period: the value at index T
        # becomes the value computed from the bar that ENDED before T
        tf_lookup[col_name] = series.shift(1).values

    tf_lookup = tf_lookup.reset_index()
    tf_lookup.rename(columns={tf_lookup.columns[0]: "_tf_datetime"}, inplace=True)
    # Use .values to extract numpy array — avoids pandas SystemError when
    # calling to_datetime on an already tz-aware DatetimeTZDtype Series.
    tf_lookup["_tf_datetime"] = pd.to_datetime(tf_lookup["_tf_datetime"].values, utc=True)
    tf_lookup = tf_lookup.sort_values("_tf_datetime")

    # Merge via asof: for each M1 bar, find the latest tf bar <= M1 timestamp
    m1_sorted = result.sort_values("_datetime").copy()

    merged = pd.merge_asof(
        m1_sorted,
        tf_lookup,
        left_on="_datetime",
        right_on="_tf_datetime",
        direction="backward",
    )

    # Drop the tf merge key
    merged.drop(columns=["_tf_datetime"], errors="ignore", inplace=True)

    # Restore original M1 order
    merged = merged.sort_index()

    return merged
