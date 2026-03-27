"""Range Proposal Engine — intelligent optimization bounds from market data (D10, FR24).

Proposes sensible parameter ranges for optimization search spaces using five
intelligence layers:
  L1: Indicator registry metadata (parameter types and typical ranges)
  L2: Timeframe scaling heuristics (period ranges bounded by timeframe)
  L3: Pair volatility from actual market data (ATR statistics)
  L4: Physical constraints (stop > spread, period < data_bars / 10)
  L5: Cross-parameter relationships (slow > fast, conditional activation)

The proposal is advisory — the operator always has final say (D9).
"""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import numpy as np

from strategy.indicator_registry import get_indicator_params, get_registry
from strategy.specification import (
    OptimizationPlan,
    ParameterCondition,
    SearchParameter,
    StrategySpecification,
)

logger = logging.getLogger(__name__)

# --- Engine metadata constants (infrastructure, not strategy-specific) ---

PIP_VALUES: dict[str, float] = {
    "EURUSD": 0.0001,
    "GBPUSD": 0.0001,
    "AUDUSD": 0.0001,
    "NZDUSD": 0.0001,
    "USDCAD": 0.0001,
    "USDCHF": 0.0001,
    "USDJPY": 0.01,
    "XAUUSD": 0.01,
}

DEFAULT_ATR_PIPS: dict[str, float] = {
    "EURUSD": 5.0,
    "GBPUSD": 7.0,
    "USDJPY": 5.0,
    "AUDUSD": 4.0,
    "USDCAD": 5.0,
    "USDCHF": 4.0,
    "NZDUSD": 4.0,
    "XAUUSD": 150.0,
}

TYPICAL_SPREADS_PIPS: dict[str, float] = {
    "EURUSD": 1.0,
    "GBPUSD": 1.5,
    "USDJPY": 1.0,
    "AUDUSD": 1.2,
    "USDCAD": 1.5,
    "USDCHF": 1.5,
    "NZDUSD": 1.8,
    "XAUUSD": 30.0,
}

TIMEFRAME_PERIOD_RANGES: dict[str, tuple[int, int]] = {
    "M1": (5, 300),
    "M5": (5, 200),
    "M15": (5, 100),
    "H1": (5, 100),
    "H4": (5, 50),
    "D1": (5, 50),
}


@dataclass(frozen=True)
class ATRStats:
    """ATR statistics for a specific pair/timeframe from market data."""

    pair: str
    timeframe: str
    atr_14_median: float  # median ATR(14) in pips
    atr_14_p90: float  # 90th percentile ATR(14) in pips
    bar_range_median: float  # median per-bar high-low range in pips
    typical_spread: float  # typical spread for pair in pips
    data_bars: int  # total bars in dataset
    source: str  # "computed" or "default"


def compute_pair_atr_stats(
    pair: str, timeframe: str, data_dir: Path | None = None
) -> ATRStats:
    """Compute ATR(14) statistics from Parquet market data.

    Falls back to hardcoded defaults if data is unavailable.

    Args:
        pair: Currency pair (e.g., "EURUSD").
        timeframe: Timeframe (e.g., "H1").
        data_dir: Root data directory (project data/).

    Returns:
        ATRStats with computed or default values.
    """
    pip_value = PIP_VALUES.get(pair, 0.0001)
    typical_spread = TYPICAL_SPREADS_PIPS.get(pair, 2.0)

    if data_dir is not None:
        parquet_files = _discover_parquet_files(pair, timeframe, data_dir)
        if parquet_files:
            try:
                return _compute_atr_from_parquet(
                    parquet_files, pair, timeframe, pip_value, typical_spread
                )
            except Exception as e:
                logger.warning(
                    "Failed to compute ATR from Parquet for %s/%s: %s. "
                    "Using defaults.",
                    pair, timeframe, e,
                )

    # Fallback to defaults
    default_atr = DEFAULT_ATR_PIPS.get(pair, 5.0)
    logger.warning(
        "Using default ATR values for %s/%s — no Parquet data available. "
        "Affected pip-based parameters will have source='default'.",
        pair, timeframe,
    )
    return ATRStats(
        pair=pair,
        timeframe=timeframe,
        atr_14_median=default_atr,
        atr_14_p90=default_atr * 1.5,
        bar_range_median=default_atr * 3.0,
        typical_spread=typical_spread,
        data_bars=0,
        source="default",
    )


def _discover_parquet_files(
    pair: str, timeframe: str, data_dir: Path
) -> list[Path]:
    """Find Parquet files for a pair/timeframe in the data directory."""
    # Try data_manifest.json first
    manifest_path = data_dir / pair / "data_manifest.json"
    if manifest_path.exists():
        try:
            with open(manifest_path) as f:
                manifest = json.load(f)
            # Look for timeframe-specific files in manifest
            file_paths = manifest.get("file_paths", {})
            timeframes = file_paths.get("timeframes", {})
            tf_files = timeframes.get(timeframe, {})
            found = []
            for _role, filename in tf_files.items():
                p = data_dir / pair / filename
                if p.exists():
                    found.append(p)
            if found:
                return found
        except (json.JSONDecodeError, KeyError):
            pass

    # Fallback: glob for parquet files
    patterns = [
        data_dir / pair / f"**/*{timeframe}*.parquet",
        data_dir / f"**/{pair}*/**/*{timeframe}*.parquet",
        data_dir / pair / "**/*.parquet",
    ]
    for pattern in patterns:
        found = sorted(data_dir.glob(str(pattern.relative_to(data_dir))))
        if found:
            return found

    return []


def _compute_atr_from_parquet(
    parquet_files: list[Path],
    pair: str,
    timeframe: str,
    pip_value: float,
    typical_spread: float,
) -> ATRStats:
    """Compute ATR statistics from Parquet files using pyarrow."""
    import pyarrow.parquet as pq

    all_high = []
    all_low = []
    all_close = []

    for pf in parquet_files:
        table = pq.read_table(pf, columns=["high", "low", "close"])
        all_high.append(table.column("high").to_numpy())
        all_low.append(table.column("low").to_numpy())
        all_close.append(table.column("close").to_numpy())

    high = np.concatenate(all_high)
    low = np.concatenate(all_low)
    close = np.concatenate(all_close)

    if len(high) < 15:
        raise ValueError(f"Insufficient data: only {len(high)} bars")

    # True Range: max(high-low, |high-prev_close|, |low-prev_close|)
    prev_close = np.roll(close, 1)
    prev_close[0] = close[0]
    tr = np.maximum(
        high - low,
        np.maximum(np.abs(high - prev_close), np.abs(low - prev_close)),
    )

    # EMA(14) of True Range
    period = 14
    alpha = 2.0 / (period + 1)
    atr = np.empty_like(tr)
    atr[0] = tr[0]
    for i in range(1, len(tr)):
        atr[i] = alpha * tr[i] + (1 - alpha) * atr[i - 1]

    # Skip initial warmup period
    atr_valid = atr[period:]
    atr_pips = atr_valid / pip_value

    # Daily range in pips
    daily_range_pips = (high - low) / pip_value

    return ATRStats(
        pair=pair,
        timeframe=timeframe,
        atr_14_median=float(np.median(atr_pips)),
        atr_14_p90=float(np.percentile(atr_pips, 90)),
        bar_range_median=float(np.median(daily_range_pips)),
        typical_spread=typical_spread,
        data_bars=len(high),
        source="computed",
    )


def propose_ranges(
    spec: StrategySpecification,
    data_dir: Path | None = None,
) -> dict[str, SearchParameter]:
    """Propose optimization bounds for all searchable parameters.

    Uses five intelligence layers (L1-L5) to compute sensible ranges.

    Args:
        spec: Validated strategy specification.
        data_dir: Root data directory for ATR computation.

    Returns:
        Flat dict of parameter_name -> SearchParameter with proposed ranges.
    """
    pair = spec.metadata.pair
    timeframe = spec.metadata.timeframe

    # L3: Compute ATR statistics
    atr_stats = compute_pair_atr_stats(pair, timeframe, data_dir)

    # L2: Timeframe scaling
    tf_min, tf_max = TIMEFRAME_PERIOD_RANGES.get(timeframe, (5, 100))

    params: dict[str, SearchParameter] = {}

    # Walk entry conditions and extract indicator parameters (L1)
    registry = get_registry()
    for cond in spec.entry_rules.conditions:
        indicator_key = cond.indicator
        if indicator_key not in registry:
            continue
        meta = registry[indicator_key]

        for param_name, param_value in cond.parameters.items():
            if param_name in meta.required_params or param_name in meta.optional_params:
                sp = _propose_indicator_param(
                    param_name, param_value, tf_min, tf_max, atr_stats
                )
                if sp is not None:
                    params[param_name] = sp

    # Walk exit rules — stop loss, take profit, trailing
    params.update(_propose_exit_params(spec, atr_stats))

    # Walk filters — session filter
    for filt in spec.entry_rules.filters:
        if filt.type == "session":
            params["session_filter"] = SearchParameter(
                type="categorical",
                choices=["asian", "london", "new_york", "london_ny_overlap"],
            )

    # L4: Physical constraints
    _apply_physical_constraints(params, atr_stats)

    # L5: Cross-parameter relationships
    params = apply_cross_parameter_constraints(params)

    return params


def _propose_indicator_param(
    param_name: str,
    current_value: int | float | str,
    tf_min: int,
    tf_max: int,
    atr_stats: ATRStats,
) -> Optional[SearchParameter]:
    """Propose range for a single indicator parameter (L1 + L2)."""
    if isinstance(current_value, str):
        return None  # Skip string params (not numeric)

    # Period parameters: integer, bounded by timeframe
    if "period" in param_name:
        current = int(current_value)
        proposed_min = max(tf_min, 5)
        proposed_max = current * 4  # generous exploration room
        proposed_max = max(proposed_max, current * 2)  # ensure at least 2x current
        proposed_max = min(proposed_max, tf_max * 2)  # soft ceiling at 2x timeframe max
        step = max(1, (proposed_max - proposed_min) // 20)  # ~20 steps
        step = max(step, 5) if proposed_max > 50 else max(step, 1)
        return SearchParameter(
            type="integer",
            min=float(proposed_min),
            max=float(proposed_max),
            step=float(step),
        )

    # Multiplier parameters: continuous
    if "multiplier" in param_name or "mult" in param_name:
        current = float(current_value)
        return SearchParameter(
            type="continuous",
            min=max(0.5, current * 0.3),
            max=current * 3.0,
        )

    # Generic numeric: continuous with 50%-200% of current
    current = float(current_value)
    return SearchParameter(
        type="continuous",
        min=max(0.1, current * 0.5),
        max=current * 2.0,
    )


def _propose_exit_params(
    spec: StrategySpecification, atr_stats: ATRStats
) -> dict[str, SearchParameter]:
    """Propose ranges for exit rule parameters (L1 + L3)."""
    params: dict[str, SearchParameter] = {}
    atr_median = atr_stats.atr_14_median

    # Stop loss — ATR-scaled
    sl = spec.exit_rules.stop_loss
    if sl.type == "atr_multiple":
        params["sl_atr_multiplier"] = SearchParameter(
            type="continuous",
            min=0.5,
            max=5.0,
        )
    elif sl.type == "fixed_pips":
        params["sl_pips"] = SearchParameter(
            type="continuous",
            min=max(atr_stats.typical_spread * 2, atr_median * 0.3),
            max=atr_median * 3.0,
        )

    # Take profit
    tp = spec.exit_rules.take_profit
    if tp.type == "risk_reward":
        params["tp_rr_ratio"] = SearchParameter(
            type="continuous",
            min=1.0,
            max=5.0,
        )
    elif tp.type == "atr_multiple":
        params["tp_atr_multiplier"] = SearchParameter(
            type="continuous",
            min=1.0,
            max=8.0,
        )
    elif tp.type == "fixed_pips":
        params["tp_pips"] = SearchParameter(
            type="continuous",
            min=atr_median * 0.5,
            max=atr_median * 5.0,
        )

    # Trailing stop
    if spec.exit_rules.trailing:
        trail = spec.exit_rules.trailing
        if trail.type == "chandelier":
            atr_period = trail.params.get("atr_period", 14)
            params["trailing_atr_period"] = SearchParameter(
                type="integer",
                min=5.0,
                max=50.0,
                step=5.0,
            )
            params["trailing_atr_multiplier"] = SearchParameter(
                type="continuous",
                min=1.0,
                max=5.0,
            )
        elif trail.type == "trailing_stop":
            params["trailing_distance_pips"] = SearchParameter(
                type="continuous",
                min=max(atr_stats.typical_spread * 2, atr_median * 0.5),
                max=atr_median * 3.0,
            )

    return params


def _apply_physical_constraints(
    params: dict[str, SearchParameter], atr_stats: ATRStats
) -> None:
    """Apply physical constraints to proposed ranges (L4)."""
    # Stop loss min > typical spread
    for key in ("sl_pips", "trailing_distance_pips"):
        if key in params and params[key].min is not None:
            if params[key].min < atr_stats.typical_spread * 1.5:
                params[key] = SearchParameter(
                    type=params[key].type,
                    min=round(atr_stats.typical_spread * 1.5, 2),
                    max=params[key].max,
                    step=params[key].step,
                    condition=params[key].condition,
                )

    # Period max < data_bars / 10 (if we have actual data)
    if atr_stats.data_bars > 0:
        max_period = atr_stats.data_bars // 10
        for key, param in list(params.items()):
            if param.type == "integer" and "period" in key and param.max is not None:
                if param.max > max_period:
                    params[key] = SearchParameter(
                        type="integer",
                        min=param.min,
                        max=float(max(int(param.min) + 1, max_period)),
                        step=param.step,
                        condition=param.condition,
                    )


def apply_cross_parameter_constraints(
    params: dict[str, SearchParameter],
) -> dict[str, SearchParameter]:
    """Apply cross-parameter relationship constraints (L5).

    Args:
        params: Dict of parameter_name -> SearchParameter.

    Returns:
        Updated dict with cross-parameter constraints applied.
    """
    # slow_period.min >= fast_period.min + step
    if "fast_period" in params and "slow_period" in params:
        fp = params["fast_period"]
        sp = params["slow_period"]
        if fp.min is not None and sp.min is not None:
            fp_step = fp.step if fp.step else 1.0
            min_slow = fp.min + fp_step
            if sp.min < min_slow:
                params["slow_period"] = SearchParameter(
                    type="integer",
                    min=min_slow,
                    max=sp.max,
                    step=sp.step,
                    condition=sp.condition,
                )

    # take_profit.min >= stop_loss.min for pip-based
    if "sl_pips" in params and "tp_pips" in params:
        sl = params["sl_pips"]
        tp = params["tp_pips"]
        if sl.min is not None and tp.min is not None and tp.min < sl.min:
            params["tp_pips"] = SearchParameter(
                type="continuous",
                min=sl.min,
                max=tp.max,
                condition=tp.condition,
            )

    return params


def persist_proposal(
    proposal: dict[str, SearchParameter],
    atr_stats: ATRStats,
    strategy_name: str,
    output_dir: Path,
) -> Path:
    """Write proposal artifact with provenance metadata.

    Args:
        proposal: Proposed parameter ranges.
        atr_stats: ATR statistics used for proposal.
        strategy_name: Strategy name for path construction.
        output_dir: Base directory (e.g., artifacts/strategies/).

    Returns:
        Path to written JSON artifact.
    """
    # Compute indicator registry hash for provenance
    registry = get_registry()
    registry_str = json.dumps(
        {k: v.model_dump() for k, v in sorted(registry.items())},
        sort_keys=True,
    )
    registry_hash = hashlib.sha256(registry_str.encode()).hexdigest()[:16]

    artifact = {
        "proposal_timestamp": datetime.now(timezone.utc).isoformat(),
        "pair": atr_stats.pair,
        "timeframe": atr_stats.timeframe,
        "atr_stats": {
            "atr_14_median": atr_stats.atr_14_median,
            "atr_14_p90": atr_stats.atr_14_p90,
            "bar_range_median": atr_stats.bar_range_median,
            "typical_spread": atr_stats.typical_spread,
            "data_bars": atr_stats.data_bars,
            "source": atr_stats.source,
        },
        "indicator_registry_hash": registry_hash,
        "proposal_engine_version": "1.0.0",
        "parameters": {},
    }

    for param_name, param in proposal.items():
        source_layer = _determine_source_layer(param_name, param, atr_stats)
        param_data = param.model_dump(exclude_none=True)
        param_data["source_layer"] = source_layer
        if atr_stats.source == "default" and source_layer == "L3":
            param_data["atr_source"] = "default"
        artifact["parameters"][param_name] = param_data

    strategy_dir = output_dir / strategy_name
    strategy_dir.mkdir(parents=True, exist_ok=True)
    artifact_path = strategy_dir / "optimization_proposal.json"

    with open(artifact_path, "w") as f:
        json.dump(artifact, f, indent=2)

    logger.info("Proposal artifact written to %s", artifact_path)
    return artifact_path


def _determine_source_layer(
    param_name: str, param: SearchParameter, atr_stats: ATRStats
) -> str:
    """Determine which intelligence layer primarily drove this parameter's range."""
    if param.type == "categorical":
        return "L1"  # From indicator registry/strategy structure
    if "period" in param_name:
        return "L2"  # Timeframe scaling
    if "pips" in param_name or "distance" in param_name:
        return "L3"  # ATR/volatility scaling (pip-denominated params)
    if any(k in param_name for k in ("multiplier", "mult", "ratio")):
        return "L1"  # Dimensionless multipliers — registry metadata, not ATR-scaled
    if "spread" in param_name:
        return "L4"  # Physical constraints
    return "L1"  # Default: registry metadata
