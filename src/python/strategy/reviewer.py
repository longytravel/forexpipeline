"""Strategy Review — human-readable summary generation (D10, FR11).

Translates a StrategySpecification into plain English for operator review.
Pure text transformation — no LLM calls. Deterministic output for identical specs.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from artifacts.storage import crash_safe_write
from logging_setup.setup import get_logger
from strategy.indicator_registry import get_registry
from strategy.specification import StrategySpecification

logger = get_logger("strategy.reviewer")

# Indicator type → human-readable name
_INDICATOR_DISPLAY_NAMES: dict[str, str] = {
    "sma": "Simple Moving Average",
    "ema": "Exponential Moving Average",
    "sma_crossover": "SMA Crossover",
    "ema_crossover": "EMA Crossover",
    "atr": "Average True Range",
    "rsi": "Relative Strength Index",
    "macd": "MACD",
    "bollinger": "Bollinger Bands",
    "supertrend": "SuperTrend",
    "keltner": "Keltner Channel",
    "donchian": "Donchian Channel",
    "williams_r": "Williams %R",
    "cci": "Commodity Channel Index",
    "stochastic": "Stochastic Oscillator",
    "adx": "Average Directional Index",
    "ichimoku": "Ichimoku Cloud",
    "vwap": "Volume Weighted Average Price",
    "rolling_max": "Rolling Maximum",
    "rolling_min": "Rolling Minimum",
    "swing_highs": "Swing Highs",
    "swing_lows": "Swing Lows",
}

# Comparator → human-readable text
_COMPARATOR_TEXT: dict[str, str] = {
    ">": "is above",
    "<": "is below",
    "==": "equals",
    ">=": "is at or above",
    "<=": "is at or below",
    "crosses_above": "crosses above",
    "crosses_below": "crosses below",
}

# Stop loss type → description template
_STOP_LOSS_TEXT: dict[str, str] = {
    "fixed_pips": "{value} pips fixed stop loss",
    "atr_multiple": "{value}x ATR stop loss",
    "percentage": "{value}% stop loss",
}

# Take profit type → description template
_TAKE_PROFIT_TEXT: dict[str, str] = {
    "fixed_pips": "{value} pips fixed take profit",
    "atr_multiple": "{value}x ATR take profit",
    "percentage": "{value}% take profit",
    "risk_reward": "{value}:1 reward-to-risk ratio",
}

# Session name → human-readable
_SESSION_NAMES: dict[str, str] = {
    "asian": "Asian session",
    "london": "London session",
    "new_york": "New York session",
    "london_ny_overlap": "London/New York overlap",
    "off_hours": "Off hours",
}

# Sizing method → description template
_SIZING_TEXT: dict[str, str] = {
    "fixed_risk": "Fixed fractional: risk {risk}% of account per trade (max {max_lots} lots)",
    "fixed_lots": "Fixed lots: {max_lots} lots per trade (risk cap {risk}%)",
}


@dataclass
class StrategySummary:
    """Human-readable strategy summary."""

    strategy_name: str
    pair: str
    timeframe: str
    indicators: list[str]
    entry_logic: str
    exit_logic: str
    filters: list[str]
    position_sizing: str
    version: str
    status: str


def _indicator_display_name(indicator_type: str) -> str:
    """Get human-readable indicator name, falling back to registry then raw type."""
    if indicator_type in _INDICATOR_DISPLAY_NAMES:
        return _INDICATOR_DISPLAY_NAMES[indicator_type]
    # Try registry description
    try:
        registry = get_registry()
        if indicator_type in registry:
            return registry[indicator_type].description
    except (FileNotFoundError, Exception):
        pass
    return indicator_type.replace("_", " ").title()


def _format_params(params: dict) -> str:
    """Format indicator parameters as readable string."""
    if not params:
        return ""
    parts = []
    for k, v in params.items():
        parts.append(f"{k}: {v}")
    return ", ".join(parts)


def _describe_condition(indicator: str, params: dict, comparator: str, threshold: float) -> str:
    """Describe a single entry condition in plain English."""
    display_name = _indicator_display_name(indicator)
    param_text = _format_params(params)
    comp_text = _COMPARATOR_TEXT.get(comparator, comparator)

    if comparator in ("crosses_above", "crosses_below") and threshold == 0.0:
        # Crossover indicators — threshold 0.0 means signal line cross
        return f"{display_name} ({param_text}) {comp_text} signal line"
    elif threshold == 0.0:
        return f"{display_name} ({param_text}) {comp_text} zero"
    else:
        return f"{display_name} ({param_text}) {comp_text} {threshold}"


def generate_summary(spec: StrategySpecification) -> StrategySummary:
    """Generate a human-readable summary from a strategy specification.

    Args:
        spec: Validated StrategySpecification.

    Returns:
        StrategySummary with all fields populated in plain English.
    """
    meta = spec.metadata

    # Collect indicator descriptions
    indicators: list[str] = []
    entry_parts: list[str] = []

    for cond in spec.entry_rules.conditions:
        display = _indicator_display_name(cond.indicator)
        param_text = _format_params(cond.parameters)
        indicators.append(f"{display} ({param_text})")

        desc = _describe_condition(
            cond.indicator, cond.parameters, cond.comparator, cond.threshold
        )
        entry_parts.append(desc)

    # Confirmations
    for conf in spec.entry_rules.confirmation:
        display = _indicator_display_name(conf.indicator)
        param_text = _format_params(conf.parameters)
        indicators.append(f"{display} ({param_text}) [confirmation]")

        desc = _describe_condition(
            conf.indicator, conf.parameters, conf.comparator, conf.threshold
        )
        entry_parts.append(f"Confirmed by: {desc}")

    # Entry logic
    if len(entry_parts) == 1:
        entry_logic = f"Enter when {entry_parts[0]}"
    else:
        entry_logic = "Enter when ALL of:\n" + "\n".join(
            f"  - {part}" for part in entry_parts
        )

    # Exit logic
    exit_parts: list[str] = []
    sl = spec.exit_rules.stop_loss
    sl_template = _STOP_LOSS_TEXT.get(sl.type, f"{sl.type}: {sl.value}")
    exit_parts.append(sl_template.format(value=sl.value))

    tp = spec.exit_rules.take_profit
    tp_template = _TAKE_PROFIT_TEXT.get(tp.type, f"{tp.type}: {tp.value}")
    exit_parts.append(tp_template.format(value=tp.value))

    if spec.exit_rules.trailing:
        trailing = spec.exit_rules.trailing
        if trailing.type == "trailing_stop":
            dist = trailing.params.get("distance_pips", "?")
            exit_parts.append(f"Trailing stop at {dist} pips")
        elif trailing.type == "chandelier":
            period = trailing.params.get("atr_period", "?")
            mult = trailing.params.get("atr_multiplier", "?")
            exit_parts.append(f"Chandelier exit: ATR({period}) x {mult}")

    exit_logic = "\n".join(f"  - {part}" for part in exit_parts)

    # Filters
    filters: list[str] = []
    for filt in spec.entry_rules.filters:
        if filt.type == "session":
            sessions = filt.params.get("include", [])
            session_names = [_SESSION_NAMES.get(s, s) for s in sessions]
            filters.append(f"Only trade during: {', '.join(session_names)}")
        elif filt.type == "volatility":
            ind = filt.params.get("indicator", "?")
            period = filt.params.get("period", "?")
            min_val = filt.params.get("min_value", None)
            max_val = filt.params.get("max_value", None)
            desc = f"Volatility filter: {_indicator_display_name(str(ind))} (period: {period})"
            if min_val is not None:
                desc += f", min: {min_val}"
            if max_val is not None:
                desc += f", max: {max_val}"
            filters.append(desc)
        elif filt.type == "day_of_week":
            days = filt.params.get("include", [])
            day_names = {0: "Mon", 1: "Tue", 2: "Wed", 3: "Thu", 4: "Fri", 5: "Sat", 6: "Sun"}
            day_strs = [day_names.get(d, str(d)) for d in days]
            filters.append(f"Only trade on: {', '.join(day_strs)}")

    # Position sizing
    ps = spec.position_sizing
    sizing_template = _SIZING_TEXT.get(
        ps.method, f"{ps.method}: risk {ps.risk_percent}%, max {ps.max_lots} lots"
    )
    position_sizing = sizing_template.format(risk=ps.risk_percent, max_lots=ps.max_lots)

    return StrategySummary(
        strategy_name=meta.name,
        pair=meta.pair,
        timeframe=meta.timeframe,
        indicators=indicators,
        entry_logic=entry_logic,
        exit_logic=exit_logic,
        filters=filters,
        position_sizing=position_sizing,
        version=meta.version,
        status=meta.status or "draft",
    )


def format_summary_text(summary: StrategySummary) -> str:
    """Format a StrategySummary as multi-line human-readable text.

    Deterministic: identical summaries produce identical output.
    Does NOT expose raw specification format (no TOML, JSON, or dict repr).

    Args:
        summary: StrategySummary instance.

    Returns:
        Formatted multi-line string.
    """
    lines: list[str] = []
    lines.append(f"Strategy Review: {summary.strategy_name}")
    lines.append("=" * len(lines[0]))
    lines.append("")
    lines.append(f"Version: {summary.version}")
    lines.append(f"Status: {summary.status}")
    lines.append(f"Pair: {summary.pair}")
    lines.append(f"Timeframe: {summary.timeframe}")
    lines.append("")

    lines.append("Indicators:")
    for ind in summary.indicators:
        lines.append(f"  - {ind}")
    lines.append("")

    lines.append("Entry Logic:")
    lines.append(f"  {summary.entry_logic}")
    lines.append("")

    lines.append("Exit Rules:")
    lines.append(summary.exit_logic)
    lines.append("")

    if summary.filters:
        lines.append("Filters:")
        for f in summary.filters:
            lines.append(f"  - {f}")
        lines.append("")

    lines.append("Position Sizing:")
    lines.append(f"  {summary.position_sizing}")
    lines.append("")

    return "\n".join(lines)


def save_summary_artifact(
    summary_text: str, strategy_slug: str, version: str, artifacts_dir: Path
) -> Path:
    """Save formatted review summary as a persistent artifact.

    Layout: artifacts_dir/strategies/{slug}/reviews/{version}_summary.txt

    Uses crash-safe write pattern (NFR15).

    Args:
        summary_text: Formatted summary text.
        strategy_slug: Strategy identifier slug.
        version: Version string (e.g., "v001").
        artifacts_dir: Root artifacts directory.

    Returns:
        Path to the saved summary file.
    """
    artifacts_dir = Path(artifacts_dir).resolve()
    reviews_dir = artifacts_dir / "strategies" / strategy_slug / "reviews"
    reviews_dir.mkdir(parents=True, exist_ok=True)

    output_path = reviews_dir / f"{version}_summary.txt"
    crash_safe_write(str(output_path), summary_text)

    logger.info(
        "strategy_review_artifact_saved",
        extra={"strategy_slug": strategy_slug, "version": version, "path": str(output_path)},
    )
    return output_path
