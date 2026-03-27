"""Timeframe conversion module (Story 1.7).

Converts M1 (or tick) data to higher timeframes (M5, H1, D1, W)
using PyArrow compute operations. Outputs both Arrow IPC and Parquet.

Architecture references:
- D2: Arrow IPC for compute, Parquet for archival
- D6: Structured JSON logging
- D7: TOML configuration
- D8: Error handling with structured error codes
- Crash-safe write pattern for all artifact writes
- Session-awareness: session column preserved or recomputed
"""
import logging
import os
from datetime import time
from pathlib import Path
from typing import Optional

import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.ipc
import pyarrow.parquet as pq


# Valid timeframes and their ordering
VALID_TIMEFRAMES = ("M1", "M5", "H1", "D1", "W")

# Microseconds per unit
_US_PER_SECOND = 1_000_000
_US_PER_MINUTE = 60 * _US_PER_SECOND
_US_PER_HOUR = 60 * _US_PER_MINUTE
_US_PER_DAY = 24 * _US_PER_HOUR

# Period durations in microseconds for grouping
TIMEFRAME_PERIOD_US = {
    "M5": 5 * _US_PER_MINUTE,
    "H1": _US_PER_HOUR,
    "D1": _US_PER_DAY,
    # W is special — handled by forex week alignment
}

# Forex week: Sunday 22:00 UTC to Friday 22:00 UTC
# Epoch 0 = Thursday 1970-01-01 00:00 UTC
# First Sunday 22:00 after epoch = 1970-01-04 22:00 UTC
# That's 3 days + 22 hours = 3*86400 + 22*3600 = 259200 + 79200 = 338400 seconds
_FOREX_WEEK_EPOCH_OFFSET_US = 338_400 * _US_PER_SECOND
_US_PER_WEEK = 7 * _US_PER_DAY


def _parse_time(time_str: str) -> time:
    """Parse HH:MM string to time object."""
    parts = time_str.split(":")
    return time(int(parts[0]), int(parts[1]))


def _compute_period_start(
    timestamps: pa.ChunkedArray, timeframe: str, daily_open_utc_hour: int = 0
) -> pa.ChunkedArray:
    """Compute period start timestamp for each row based on target timeframe.

    Args:
        timestamps: int64 epoch microseconds UTC.
        timeframe: Target timeframe (M5, H1, D1, W).
        daily_open_utc_hour: UTC hour when broker daily candle opens.
            E.g. 22 for GMT+2 brokers (IC Markets). Only affects D1.

    Returns:
        ChunkedArray of int64 period start timestamps.
    """
    if timeframe == "W":
        # Forex week alignment: Sunday 22:00 UTC
        # Subtract the offset, divide by week, multiply back, add offset
        offset = pa.scalar(_FOREX_WEEK_EPOCH_OFFSET_US, type=pa.int64())
        week_us = pa.scalar(_US_PER_WEEK, type=pa.int64())
        shifted = pc.subtract(timestamps, offset)
        week_num = pc.divide(shifted, week_us)
        period_start = pc.add(pc.multiply(week_num, week_us), offset)
        return period_start
    elif timeframe == "D1" and daily_open_utc_hour != 0:
        # Broker-aligned daily bars: shift timestamps so floor aligns to broker open
        # E.g. daily_open_utc_hour=22 means D1 bars start at 22:00 UTC
        offset_us = pa.scalar(daily_open_utc_hour * _US_PER_HOUR, type=pa.int64())
        day_us = pa.scalar(_US_PER_DAY, type=pa.int64())
        shifted = pc.subtract(timestamps, offset_us)
        quotient = pc.divide(shifted, day_us)
        return pc.add(pc.multiply(quotient, day_us), offset_us)
    else:
        period_us = pa.scalar(TIMEFRAME_PERIOD_US[timeframe], type=pa.int64())
        # floor division: (timestamp // period_us) * period_us
        quotient = pc.divide(timestamps, period_us)
        return pc.multiply(quotient, period_us)


def convert_timeframe(
    source_table: pa.Table,
    source_tf: str,
    target_tf: str,
    session_schedule: dict | None = None,
    daily_open_utc_hour: int = 0,
) -> pa.Table:
    """Convert source timeframe data to target timeframe via OHLC aggregation.

    Args:
        source_table: Arrow Table with market_data schema columns.
        source_tf: Source timeframe identifier (e.g., "M1").
        target_tf: Target timeframe identifier (e.g., "M5", "H1", "D1", "W").
        daily_open_utc_hour: UTC hour when broker daily candle opens (D1 only).

    Returns:
        Arrow Table aggregated to the target timeframe.

    Raises:
        ValueError: If timeframes are invalid or target <= source.
    """
    if source_tf not in VALID_TIMEFRAMES:
        raise ValueError(f"Invalid source timeframe: {source_tf}")
    if target_tf not in VALID_TIMEFRAMES:
        raise ValueError(f"Invalid target timeframe: {target_tf}")
    if VALID_TIMEFRAMES.index(target_tf) <= VALID_TIMEFRAMES.index(source_tf):
        raise ValueError(
            f"Target timeframe {target_tf} must be higher than source {source_tf}"
        )

    # Step 1: Filter out quarantined bars BEFORE aggregation
    quarantined_col = source_table.column("quarantined")
    not_quarantined = pc.invert(quarantined_col)
    filtered = source_table.filter(not_quarantined)

    if filtered.num_rows == 0:
        # Return empty table with correct schema (minus quarantined, plus period_start)
        return _empty_aggregated_table(source_table.schema)

    # Step 2: Sort by timestamp for deterministic ordering
    sort_indices = pc.sort_indices(filtered, sort_keys=[("timestamp", "ascending")])
    filtered = filtered.take(sort_indices)

    # Step 3: Compute period start for each bar
    timestamps = filtered.column("timestamp")
    period_starts = _compute_period_start(timestamps, target_tf, daily_open_utc_hour)

    # Add period_start as a column for grouping
    filtered = filtered.append_column("period_start", period_starts)

    # Step 4: Group by period_start and aggregate
    return _aggregate_by_period(filtered, target_tf, session_schedule)


def _empty_aggregated_table(source_schema: pa.Schema) -> pa.Table:
    """Create an empty table with the aggregated output schema."""
    # Use the canonical 9-column output schema, not source schema,
    # to match the non-empty aggregation path.
    schema = pa.schema([
        pa.field("timestamp", pa.int64()),
        pa.field("open", pa.float64()),
        pa.field("high", pa.float64()),
        pa.field("low", pa.float64()),
        pa.field("close", pa.float64()),
        pa.field("bid", pa.float64()),
        pa.field("ask", pa.float64()),
        pa.field("session", pa.utf8()),
        pa.field("quarantined", pa.bool_()),
    ])
    return pa.table({f.name: pa.array([], type=f.type) for f in schema}, schema=schema)


def _aggregate_by_period(table: pa.Table, target_tf: str, session_schedule: dict | None = None) -> pa.Table:
    """Aggregate table rows by period_start column.

    OHLC rules:
    - open = first bar's open
    - high = max of highs
    - low = min of lows
    - close = last bar's close
    - bid = last bar's bid
    - ask = last bar's ask
    - session = determined by timeframe rules
    """
    # Get unique period starts (already sorted due to sorted input)
    period_starts_col = table.column("period_start")
    unique_periods = pc.unique(period_starts_col).sort()

    # Pre-extract columns as chunked arrays for efficient access
    ts_col = table.column("timestamp")
    open_col = table.column("open")
    high_col = table.column("high")
    low_col = table.column("low")
    close_col = table.column("close")
    bid_col = table.column("bid")
    ask_col = table.column("ask")
    session_col = table.column("session")

    # Build result arrays
    result_timestamps = []
    result_opens = []
    result_highs = []
    result_lows = []
    result_closes = []
    result_bids = []
    result_asks = []
    result_sessions = []

    for period_val in unique_periods:
        # Create mask for this period
        mask = pc.equal(period_starts_col, period_val)

        # Filter columns for this period
        period_open = pc.filter(open_col, mask)
        period_high = pc.filter(high_col, mask)
        period_low = pc.filter(low_col, mask)
        period_close = pc.filter(close_col, mask)
        period_bid = pc.filter(bid_col, mask)
        period_ask = pc.filter(ask_col, mask)
        period_session = pc.filter(session_col, mask)

        # Aggregate OHLC
        # First and last require index-based access (data is already sorted by timestamp)
        n = period_open.length()
        result_timestamps.append(period_val.as_py())
        result_opens.append(period_open[0].as_py())
        result_highs.append(pc.max(period_high).as_py())
        result_lows.append(pc.min(period_low).as_py())
        result_closes.append(period_close[n - 1].as_py())
        result_bids.append(period_bid[n - 1].as_py())
        result_asks.append(period_ask[n - 1].as_py())

        # Session handling
        session_value = _compute_session_for_period(
            target_tf, period_session, period_val.as_py(), session_schedule
        )
        result_sessions.append(session_value)

    # Build output table
    output = pa.table({
        "timestamp": pa.array(result_timestamps, type=pa.int64()),
        "open": pa.array(result_opens, type=pa.float64()),
        "high": pa.array(result_highs, type=pa.float64()),
        "low": pa.array(result_lows, type=pa.float64()),
        "close": pa.array(result_closes, type=pa.float64()),
        "bid": pa.array(result_bids, type=pa.float64()),
        "ask": pa.array(result_asks, type=pa.float64()),
        "session": pa.array(result_sessions, type=pa.utf8()),
        "quarantined": pa.array([False] * len(result_timestamps), type=pa.bool_()),
    })

    return output


def _compute_session_for_period(
    target_tf: str,
    period_sessions: pa.ChunkedArray,
    period_start_us: int,
    session_schedule: dict | None = None,
) -> str:
    """Determine session label for an aggregated period.

    Rules:
    - M5: session of first bar (session doesn't change within 5 minutes)
    - H1: recompute from session schedule (AC #4); fallback to majority vote
    - D1: "mixed"
    - W: "mixed"
    """
    if target_tf in ("D1", "W"):
        return "mixed"

    if target_tf == "M5":
        return period_sessions[0].as_py()

    if target_tf == "H1":
        if session_schedule is not None:
            return _recompute_h1_session(period_start_us, session_schedule)
        # Fallback when no schedule provided
        return _majority_session(period_sessions, period_start_us)

    return period_sessions[0].as_py()


def _majority_session(
    sessions: pa.ChunkedArray,
    period_start_us: int,
) -> str:
    """Find the majority session in a period.

    If tied, pick the session that starts during the hour (has more representation
    going forward). Fallback: first session alphabetically for determinism.
    """
    counts: dict[str, int] = {}
    for i in range(sessions.length()):
        s = sessions[i].as_py()
        counts[s] = counts.get(s, 0) + 1

    max_count = max(counts.values())
    candidates = [s for s, c in counts.items() if c == max_count]

    if len(candidates) == 1:
        return candidates[0]

    # Tie-breaking: prefer the session that starts during this hour
    # The session starting later in the hour is likely the "new" session
    # For determinism, sort and pick first if still tied
    candidates.sort()
    return candidates[0]


def _recompute_h1_session(period_start_us: int, session_schedule: dict) -> str:
    """Recompute H1 session from timestamp using session schedule (AC #4).

    Checks each minute in the hour, assigns session via schedule,
    then returns the session covering the majority of the hour.
    If tied, prefers the session whose start time falls within the hour.
    """
    counts: dict[str, int] = {}
    for m in range(60):
        ts = period_start_us + m * _US_PER_MINUTE
        s = compute_session_for_timestamp(ts, session_schedule)
        counts[s] = counts.get(s, 0) + 1

    max_count = max(counts.values())
    candidates = [s for s, c in counts.items() if c == max_count]
    if len(candidates) == 1:
        return candidates[0]

    # Tie-break: prefer the session that starts during this hour
    hour_start_minutes = (period_start_us // _US_PER_SECOND % 86400) // 60
    hour_end_minutes = hour_start_minutes + 60
    for cand in candidates:
        if cand in session_schedule and isinstance(session_schedule[cand], dict):
            start_str = session_schedule[cand].get("start")
            if start_str:
                s = _parse_time(start_str)
                s_min = s.hour * 60 + s.minute
                if hour_start_minutes <= s_min < hour_end_minutes:
                    return cand

    # Still tied — alphabetical for determinism
    candidates.sort()
    return candidates[0]


def compute_session_for_timestamp(
    timestamp_us: int, session_schedule: dict
) -> str:
    """Compute session label for a single timestamp using session schedule.

    Args:
        timestamp_us: Epoch microseconds UTC.
        session_schedule: Session config dict from config/base.toml [sessions].

    Returns:
        Session label string.
    """
    # Convert to hour:minute
    total_seconds = timestamp_us // _US_PER_SECOND
    time_of_day_seconds = total_seconds % 86400
    hour = time_of_day_seconds // 3600
    minute = (time_of_day_seconds % 3600) // 60
    total_minutes = hour * 60 + minute

    # Check overlap first (most specific)
    if "london_ny_overlap" in session_schedule:
        ovl = session_schedule["london_ny_overlap"]
        s = _parse_time(ovl["start"])
        e = _parse_time(ovl["end"])
        s_min = s.hour * 60 + s.minute
        e_min = e.hour * 60 + e.minute
        if s_min <= total_minutes < e_min:
            return "london_ny_overlap"

    for key in ("asian", "london", "new_york", "off_hours"):
        if key not in session_schedule:
            continue
        sess = session_schedule[key]
        s = _parse_time(sess["start"])
        e = _parse_time(sess["end"])
        s_min = s.hour * 60 + s.minute
        e_min = e.hour * 60 + e.minute

        if s_min < e_min:
            if s_min <= total_minutes < e_min:
                return key
        else:
            if total_minutes >= s_min or total_minutes < e_min:
                return key

    return "off_hours"


# --- Tick-to-M1 aggregation (Task 3) ---

def aggregate_ticks_to_m1(tick_table: pa.Table) -> pa.Table:
    """Aggregate tick data to M1 bars.

    Tick-to-M1 rules:
    - mid = (bid + ask) / 2
    - open = first tick's mid in the minute
    - high = max mid in the minute
    - low = min mid in the minute
    - close = last tick's mid in the minute
    - bid = last tick's bid in the minute
    - ask = last tick's ask in the minute

    Args:
        tick_table: Arrow Table with tick_data schema (timestamp, bid, ask, ...).

    Returns:
        Arrow Table with market_data schema columns.
    """
    if tick_table.num_rows == 0:
        return pa.table({
            "timestamp": pa.array([], type=pa.int64()),
            "open": pa.array([], type=pa.float64()),
            "high": pa.array([], type=pa.float64()),
            "low": pa.array([], type=pa.float64()),
            "close": pa.array([], type=pa.float64()),
            "bid": pa.array([], type=pa.float64()),
            "ask": pa.array([], type=pa.float64()),
            "session": pa.array([], type=pa.utf8()),
            "quarantined": pa.array([], type=pa.bool_()),
        })

    # Sort by timestamp
    sort_indices = pc.sort_indices(tick_table, sort_keys=[("timestamp", "ascending")])
    tick_table = tick_table.take(sort_indices)

    # Cast timestamps to int64 epoch microseconds
    timestamps = tick_table.column("timestamp")
    if pa.types.is_timestamp(timestamps.type):
        timestamps = timestamps.cast(pa.timestamp("us", tz="UTC")).cast(pa.int64())

    # Compute mid, minute_start in Arrow, then aggregate via pandas groupby
    bid_col = tick_table.column("bid")
    ask_col = tick_table.column("ask")
    mid = pc.divide(pc.add(bid_col, ask_col), pa.scalar(2.0, type=pa.float64()))
    minute_us = pa.scalar(_US_PER_MINUTE, type=pa.int64())
    minute_starts = pc.multiply(pc.divide(timestamps, minute_us), minute_us)

    has_session = "session" in tick_table.schema.names
    has_quarantined = "quarantined" in tick_table.schema.names

    # Build a lean DataFrame for groupby (only needed columns)
    import pandas as pd
    agg_df = pd.DataFrame({
        "minute_start": minute_starts.to_pandas(),
        "mid": mid.to_pandas(),
        "bid": bid_col.to_pandas(),
        "ask": ask_col.to_pandas(),
    })
    if has_session:
        agg_df["session"] = tick_table.column("session").to_pandas()
    if has_quarantined:
        agg_df["quarantined"] = tick_table.column("quarantined").to_pandas()

    # Vectorized groupby aggregation — O(n) instead of O(n*m)
    grouped = agg_df.groupby("minute_start", sort=True)
    result = pd.DataFrame({
        "timestamp": grouped["mid"].first().index,  # minute_start values
        "open": grouped["mid"].first().values,
        "high": grouped["mid"].max().values,
        "low": grouped["mid"].min().values,
        "close": grouped["mid"].last().values,
        "bid": grouped["bid"].last().values,
        "ask": grouped["ask"].last().values,
        "session": grouped["session"].first().values if has_session
                   else ["off_hours"] * len(grouped),
        "quarantined": grouped["quarantined"].any().values if has_quarantined
                       else [False] * len(grouped),
    })

    return pa.table({
        "timestamp": pa.array(result["timestamp"].values, type=pa.int64()),
        "open": pa.array(result["open"].values, type=pa.float64()),
        "high": pa.array(result["high"].values, type=pa.float64()),
        "low": pa.array(result["low"].values, type=pa.float64()),
        "close": pa.array(result["close"].values, type=pa.float64()),
        "bid": pa.array(result["bid"].values, type=pa.float64()),
        "ask": pa.array(result["ask"].values, type=pa.float64()),
        "session": pa.array(result["session"].values, type=pa.utf8()),
        "quarantined": pa.array(result["quarantined"].values, type=pa.bool_()),
    })


def is_tick_data(table: pa.Table) -> bool:
    """Detect if a table contains tick data vs bar data.

    Tick data has bid/ask but no open/high/low/close columns.
    """
    col_names = set(table.schema.names)
    has_ohlc = {"open", "high", "low", "close"}.issubset(col_names)
    has_bid_ask = {"bid", "ask"}.issubset(col_names)
    return has_bid_ask and not has_ohlc


# --- Output storage (Task 5) ---

def write_arrow_ipc(table: pa.Table, output_path: Path, logger: logging.Logger) -> Path:
    """Write Arrow IPC file using shared crash-safe utility.

    No compression — must be mmap-friendly.
    """
    from data_pipeline.utils.safe_write import safe_write_arrow_ipc

    output_path = Path(output_path)
    safe_write_arrow_ipc(table, output_path)

    size_mb = output_path.stat().st_size / (1024 * 1024)
    logger.info(
        "Timeframe Arrow IPC written: %s (%.2f MB, %d rows)",
        output_path, size_mb, table.num_rows,
        extra={"ctx": {"component": "data_pipeline", "stage": "timeframe_conversion"}},
    )
    return output_path


def write_parquet(
    table: pa.Table,
    output_path: Path,
    logger: logging.Logger,
    compression: str = "snappy",
) -> Path:
    """Write Parquet file using shared crash-safe utility."""
    from data_pipeline.utils.safe_write import safe_write_parquet

    output_path = Path(output_path)
    safe_write_parquet(table, output_path, compression)

    size_mb = output_path.stat().st_size / (1024 * 1024)
    logger.info(
        "Timeframe Parquet written: %s (%.2f MB, %d rows, compression=%s)",
        output_path, size_mb, table.num_rows, compression,
        extra={"ctx": {"component": "data_pipeline", "stage": "timeframe_conversion"}},
    )
    return output_path


def validate_output_schema(table: pa.Table, contracts_path: Path) -> None:
    """Validate output table schema against contracts/arrow_schemas.toml.

    Raises SchemaValidationError on mismatch.
    """
    from data_pipeline.schema_loader import load_arrow_schema, SchemaValidationError

    expected = load_arrow_schema(contracts_path, "market_data")
    actual = table.schema

    # Check column names and types match
    expected_names = [f.name for f in expected]
    actual_names = table.schema.names

    if expected_names != actual_names:
        raise SchemaValidationError(
            f"Schema column mismatch.\n"
            f"  Expected: {expected_names}\n"
            f"  Got: {actual_names}"
        )

    for exp_field, act_field in zip(expected, actual):
        if exp_field.type != act_field.type:
            raise SchemaValidationError(
                f"Type mismatch for column '{exp_field.name}': "
                f"expected {exp_field.type}, got {act_field.type}"
            )


# --- Orchestration entry point (Task 6) ---

def _resolve_contracts_path(config: dict) -> Path:
    """Resolve the contracts/ directory from config (AC #11).

    Requires explicit config path — no directory walking.
    """
    override = config.get("data_pipeline", {}).get("contracts_path", "")
    if override and Path(override).is_dir():
        return Path(override)
    raise FileNotFoundError(
        "data_pipeline.contracts_path not set or not a valid directory. "
        "Set it explicitly in config to point to the contracts/ folder."
    )


def _build_output_filename(
    pair: str, start_date: str, end_date: str, timeframe: str, extension: str
) -> str:
    """Build output filename following convention: {pair}_{start}_{end}_{tf}.{ext}"""
    return f"{pair}_{start_date}_{end_date}_{timeframe}.{extension}"


def _extract_date_range(table: pa.Table) -> tuple[str, str]:
    """Extract start and end dates from timestamp column."""
    ts_col = table.column("timestamp")
    min_ts = pc.min(ts_col).as_py()
    max_ts = pc.max(ts_col).as_py()

    # Convert epoch microseconds to date strings
    from datetime import datetime, timezone
    start_dt = datetime.fromtimestamp(min_ts / _US_PER_SECOND, tz=timezone.utc)
    end_dt = datetime.fromtimestamp(max_ts / _US_PER_SECOND, tz=timezone.utc)

    return start_dt.strftime("%Y-%m-%d"), end_dt.strftime("%Y-%m-%d")


def run_timeframe_conversion(
    pair: str,
    source_path: Path,
    config: dict,
    logger: Optional[logging.Logger] = None,
) -> dict:
    """Orchestrate timeframe conversion for a currency pair.

    Steps:
    1. Load M1 Arrow IPC from source_path
    2. If tick data, run tick-to-M1 first
    3. For each target timeframe, convert and write output
    4. Return dict of {timeframe: output_path}

    Args:
        pair: Currency pair (e.g., "EURUSD").
        source_path: Path to source Arrow IPC file.
        config: Full config dict.
        logger: Logger instance.

    Returns:
        Dict mapping timeframe -> {"arrow": path, "parquet": path}.
    """
    if logger is None:
        logger = logging.getLogger(__name__)

    # Load config
    dp_cfg = config.get("data_pipeline", {})
    tf_cfg = dp_cfg.get("timeframe_conversion", {})
    target_timeframes = tf_cfg.get("target_timeframes", ["M5", "H1", "D1", "W"])
    source_tf = tf_cfg.get("source_timeframe", "M1")
    daily_open_utc_hour = tf_cfg.get("daily_open_utc_hour", 0)

    # Storage config
    storage_path = Path(dp_cfg.get("storage_path", config.get("data", {}).get("storage_path", "")))
    output_dir = storage_path / "data-pipeline"

    # Parquet compression
    parquet_compression = dp_cfg.get("parquet", {}).get("compression", "snappy")

    # Contracts path — resolved from config (AC #11)
    contracts_path = _resolve_contracts_path(config)

    logger.info(
        "Starting timeframe conversion: pair=%s, source=%s, targets=%s",
        pair, source_path, target_timeframes,
        extra={"ctx": {
            "component": "data_pipeline",
            "stage": "timeframe_conversion",
            "pair": pair,
        }},
    )

    # Step 1: Load source data
    source_path = Path(source_path)
    if not source_path.exists():
        raise FileNotFoundError(f"Source file not found: {source_path}")

    mmap_file = pa.memory_map(str(source_path), "r")
    reader = pa.ipc.open_file(mmap_file)
    source_table = reader.read_all()
    mmap_file.close()

    input_rows = source_table.num_rows
    logger.info(
        "Source data loaded: %d rows from %s",
        input_rows, source_path,
        extra={"ctx": {"component": "data_pipeline", "stage": "timeframe_conversion"}},
    )

    # Step 2: Detect tick data and convert to M1 if needed
    if is_tick_data(source_table):
        logger.info(
            "Tick data detected — aggregating to M1 first",
            extra={"ctx": {"component": "data_pipeline", "stage": "timeframe_conversion"}},
        )
        source_table = aggregate_ticks_to_m1(source_table)
        source_tf = "M1"
        logger.info(
            "Tick-to-M1 complete: %d M1 bars from %d ticks",
            source_table.num_rows, input_rows,
            extra={"ctx": {"component": "data_pipeline", "stage": "timeframe_conversion"}},
        )

    # Guard: empty source data after loading/conversion
    if source_table.num_rows == 0:
        logger.warning(
            "Source data is empty after loading: %s",
            source_path,
            extra={"ctx": {"component": "data_pipeline", "stage": "timeframe_conversion"}},
        )
        return {}

    # Validate target timeframes early
    for tf in target_timeframes:
        if tf not in VALID_TIMEFRAMES:
            raise ValueError(
                f"Invalid target timeframe '{tf}' in config. "
                f"Allowed values: {VALID_TIMEFRAMES}"
            )

    # Extract date range for filenames
    start_date, end_date = _extract_date_range(source_table)

    # Step 3: Convert each target timeframe
    results = {}
    for target_tf in target_timeframes:
        if target_tf == source_tf:
            continue
        if VALID_TIMEFRAMES.index(target_tf) <= VALID_TIMEFRAMES.index(source_tf):
            logger.warning(
                "Skipping %s — not higher than source %s",
                target_tf, source_tf,
                extra={"ctx": {"component": "data_pipeline", "stage": "timeframe_conversion"}},
            )
            continue

        logger.info(
            "Converting %s → %s for %s",
            source_tf, target_tf, pair,
            extra={"ctx": {"component": "data_pipeline", "stage": "timeframe_conversion"}},
        )

        converted = convert_timeframe(
            source_table, source_tf, target_tf,
            session_schedule=config.get("sessions"),
            daily_open_utc_hour=daily_open_utc_hour,
        )

        # Count quarantined bars excluded
        quarantined_col = source_table.column("quarantined")
        quarantined_count = pc.sum(quarantined_col.cast(pa.int64())).as_py()

        # Validate output schema
        validate_output_schema(converted, contracts_path)

        # Build filenames
        arrow_name = _build_output_filename(pair, start_date, end_date, target_tf, "arrow")
        parquet_name = _build_output_filename(pair, start_date, end_date, target_tf, "parquet")

        arrow_path = output_dir / arrow_name
        parquet_path = output_dir / parquet_name

        # Check if files already exist — skip for idempotency
        # Anti-pattern #6: do NOT overwrite existing converted files
        if arrow_path.exists() and parquet_path.exists():
            logger.info(
                "Output already exists, skipping: %s",
                arrow_name,
                extra={"ctx": {"component": "data_pipeline", "stage": "timeframe_conversion"}},
            )
            results[target_tf] = {"arrow": arrow_path, "parquet": parquet_path}
            continue

        # Write outputs — only write files that don't already exist
        if not arrow_path.exists():
            write_arrow_ipc(converted, arrow_path, logger)
        if not parquet_path.exists():
            write_parquet(converted, parquet_path, logger, parquet_compression)

        logger.info(
            "Conversion complete: %s → %s, input=%d bars, output=%d bars, quarantined_excluded=%d",
            source_tf, target_tf, input_rows, converted.num_rows, quarantined_count,
            extra={"ctx": {
                "component": "data_pipeline",
                "stage": "timeframe_conversion",
                "pair": pair,
                "source_tf": source_tf,
                "target_tf": target_tf,
                "input_bar_count": input_rows,
                "output_bar_count": converted.num_rows,
                "quarantined_bars_excluded": quarantined_count,
            }},
        )

        results[target_tf] = {"arrow": arrow_path, "parquet": parquet_path}

    logger.info(
        "Timeframe conversion complete for %s: %d timeframes produced",
        pair, len(results),
        extra={"ctx": {"component": "data_pipeline", "stage": "timeframe_conversion"}},
    )

    return results
