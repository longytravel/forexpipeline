"""Dialogue Parser — keyword/pattern extraction from structured input (D10).

Receives structured data from Claude Code skill (NOT raw natural language).
Maps aliases, normalizes formats, validates against indicator registry.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from strategy.indicator_registry import is_indicator_known


class IntentCaptureError(Exception):
    """Raised when strategy-defining fields are missing or invalid."""


@dataclass
class IndicatorIntent:
    """Parsed indicator from structured input."""

    type: str
    params: dict[str, Any]
    role: str  # signal/filter/exit


@dataclass
class ExitIntent:
    """Parsed exit rule from structured input."""

    type: str  # stop_loss/take_profit/trailing_stop/chandelier
    params: dict[str, Any]


@dataclass
class FilterIntent:
    """Parsed filter from structured input."""

    type: str  # session/volatility/day_of_week
    params: dict[str, Any]


@dataclass
class PositionSizingIntent:
    """Parsed position sizing from structured input."""

    method: str  # fixed_risk/fixed_lots
    params: dict[str, Any]


@dataclass
class StrategyIntent:
    """Complete parsed strategy intent with provenance tracking."""

    pair: str | None
    timeframe: str | None
    indicators: list[IndicatorIntent]
    entry_conditions: list[str]
    exit_rules: list[ExitIntent]
    filters: list[FilterIntent]
    position_sizing: PositionSizingIntent | None
    raw_description: str
    field_provenance: dict[str, str]


# --- Alias mappings ---

INDICATOR_ALIASES: dict[str, str] = {
    "ma": "sma",
    "moving average": "sma",
    "simple moving average": "sma",
    "exponential moving average": "ema",
    "moving average crossover": "sma_crossover",
    "ma crossover": "sma_crossover",
    "ema crossover": "ema_crossover",
    "sma crossover": "sma_crossover",
    "average true range": "atr",
    "bollinger": "bollinger_bands",
    "bollinger bands": "bollinger_bands",
    "keltner": "keltner_channel",
    "keltner channels": "keltner_channel",
    "keltner channel": "keltner_channel",
    "relative strength index": "rsi",
    "stoch": "stochastic",
    "super trend": "supertrend",
    "donchian channel": "donchian_channel",
    "donchian": "donchian_channel",
    "williams %r": "williams_r",
    "williams r": "williams_r",
    "average directional index": "adx",
}

TIMEFRAME_ALIASES: dict[str, str] = {
    "1 minute": "M1",
    "1m": "M1",
    "5 minute": "M5",
    "5m": "M5",
    "15 minute": "M15",
    "15m": "M15",
    "1 hour": "H1",
    "1h": "H1",
    "4 hour": "H4",
    "4h": "H4",
    "daily": "D1",
    "1 day": "D1",
    "1d": "D1",
}

EXIT_TYPE_ALIASES: dict[str, str] = {
    "chandelier exit": "chandelier",
    "chandelier": "chandelier",
    "trailing stop": "trailing_stop",
    "trailing": "trailing_stop",
    "stop loss": "stop_loss",
    "stoploss": "stop_loss",
    "take profit": "take_profit",
    "takeprofit": "take_profit",
    "tp": "take_profit",
    "sl": "stop_loss",
}

FILTER_TYPE_ALIASES: dict[str, str] = {
    "london session": "session",
    "asian session": "session",
    "new york session": "session",
    "ny session": "session",
    "session": "session",
    "high volatility": "volatility",
    "low volatility": "volatility",
    "volatility": "volatility",
    "volatility filter": "volatility",
}

SESSION_NAME_ALIASES: dict[str, str] = {
    "london": "london",
    "asian": "asian",
    "asia": "asian",
    "new york": "new_york",
    "ny": "new_york",
    "new_york": "new_york",
    "overlap": "london_ny_overlap",
    "london ny overlap": "london_ny_overlap",
    "off hours": "off_hours",
    "off_hours": "off_hours",
}

SIZING_METHOD_ALIASES: dict[str, str] = {
    "fixed_fractional": "fixed_risk",
    "fixed fractional": "fixed_risk",
    "fixed_risk": "fixed_risk",
    "fixed risk": "fixed_risk",
    "percent risk": "fixed_risk",
    "fixed_lot": "fixed_lots",
    "fixed lot": "fixed_lots",
    "fixed_lots": "fixed_lots",
    "fixed lots": "fixed_lots",
}

# Pair normalization pattern
PAIR_SEPARATORS = re.compile(r"[_/]")


def normalize_pair(pair: str) -> str:
    """Normalize pair format to EURUSD convention."""
    return PAIR_SEPARATORS.sub("", pair).upper()


VALID_TIMEFRAMES = {"M1", "M5", "M15", "H1", "H4", "D1"}


def normalize_timeframe(tf: str) -> str:
    """Normalize timeframe aliases to canonical format.

    Raises:
        IntentCaptureError: If timeframe is not a recognized alias or valid format.
    """
    canonical = TIMEFRAME_ALIASES.get(tf.lower().strip())
    if canonical:
        return canonical
    upper = tf.upper().strip()
    if upper in VALID_TIMEFRAMES:
        return upper
    raise IntentCaptureError(
        f"Unknown timeframe '{tf}'. "
        f"Valid options: {', '.join(sorted(VALID_TIMEFRAMES))}"
    )


def resolve_indicator_type(name: str) -> str:
    """Resolve indicator name alias to registry type."""
    lower = name.lower().strip()
    return INDICATOR_ALIASES.get(lower, lower)


def resolve_exit_type(name: str) -> str:
    """Resolve exit type alias."""
    lower = name.lower().strip()
    return EXIT_TYPE_ALIASES.get(lower, lower)


def resolve_filter_type(name: str) -> str:
    """Resolve filter type alias."""
    lower = name.lower().strip()
    return FILTER_TYPE_ALIASES.get(lower, lower)


def resolve_session_name(name: str) -> str:
    """Resolve session name alias."""
    lower = name.lower().strip()
    return SESSION_NAME_ALIASES.get(lower, lower)


def resolve_sizing_method(name: str) -> str:
    """Resolve position sizing method alias."""
    lower = name.lower().strip()
    return SIZING_METHOD_ALIASES.get(lower, lower)


def parse_strategy_intent(structured_input: dict) -> StrategyIntent:
    """Extract structured intent from skill-provided data.

    The Claude Code skill pre-processes operator dialogue into a structured
    dict before calling this function. This module does NOT parse raw
    natural language — it normalizes, validates, and structures.

    Args:
        structured_input: Dict with keys: raw_description, pair, timeframe,
            indicators, entry_conditions, exit_rules, filters, position_sizing.

    Returns:
        StrategyIntent with normalized and validated fields.

    Raises:
        IntentCaptureError: If strategy-defining fields are missing.
    """
    provenance: dict[str, str] = {}
    raw_description = structured_input.get("raw_description", "")

    # --- Pair normalization ---
    pair = structured_input.get("pair")
    if pair:
        pair = normalize_pair(pair)
        provenance["pair"] = "operator"

    # --- Timeframe normalization ---
    timeframe = structured_input.get("timeframe")
    if timeframe:
        timeframe = normalize_timeframe(timeframe)
        provenance["timeframe"] = "operator"

    # --- Indicator parsing ---
    raw_indicators = structured_input.get("indicators", [])
    indicators: list[IndicatorIntent] = []

    for ind in raw_indicators:
        ind_type = resolve_indicator_type(ind.get("type", ""))
        if not is_indicator_known(ind_type):
            raise IntentCaptureError(
                f"Unknown indicator type '{ind.get('type', '')}' "
                f"(resolved to '{ind_type}'). Check indicator registry for valid types."
            )
        params = dict(ind.get("params", {}))
        role = ind.get("role", "signal")
        indicators.append(IndicatorIntent(type=ind_type, params=params, role=role))

    # --- Entry conditions ---
    entry_conditions = list(structured_input.get("entry_conditions", []))

    # --- Clarification policy enforcement (must-have fields) ---
    if not indicators:
        raise IntentCaptureError(
            "Strategy-defining fields missing: [indicators]. "
            "These cannot be defaulted — please specify at least one indicator."
        )

    signal_indicators = [i for i in indicators if i.role == "signal"]
    if not signal_indicators and not entry_conditions:
        raise IntentCaptureError(
            "Strategy-defining fields missing: [entry_logic]. "
            "These cannot be defaulted — please specify entry conditions "
            "or signal indicators."
        )

    # --- Exit rules ---
    raw_exits = structured_input.get("exit_rules", [])
    exit_rules: list[ExitIntent] = []
    for ex in raw_exits:
        ex_type = resolve_exit_type(ex.get("type", ""))
        params = dict(ex.get("params", {}))
        exit_rules.append(ExitIntent(type=ex_type, params=params))
    if exit_rules:
        provenance["exit_rules"] = "operator"

    # --- Filters ---
    raw_filters = structured_input.get("filters", [])
    filters: list[FilterIntent] = []
    for flt in raw_filters:
        flt_type = resolve_filter_type(flt.get("type", ""))
        params = dict(flt.get("params", {}))
        # Normalize session names within filter params
        if flt_type == "session" and "session" in params:
            session = params.pop("session")
            params["include"] = [resolve_session_name(session)]
        elif flt_type == "session" and "include" in params:
            params["include"] = [resolve_session_name(s) for s in params["include"]]
        filters.append(FilterIntent(type=flt_type, params=params))
    if filters:
        provenance["filters"] = "operator"

    # --- Position sizing ---
    raw_sizing = structured_input.get("position_sizing")
    position_sizing = None
    if raw_sizing:
        method = resolve_sizing_method(raw_sizing.get("method", "fixed_risk"))
        params = {k: v for k, v in raw_sizing.items() if k != "method"}
        position_sizing = PositionSizingIntent(method=method, params=params)
        provenance["position_sizing"] = "operator"

    provenance["indicators"] = "operator"
    if entry_conditions:
        provenance["entry_conditions"] = "operator"

    return StrategyIntent(
        pair=pair,
        timeframe=timeframe,
        indicators=indicators,
        entry_conditions=entry_conditions,
        exit_rules=exit_rules,
        filters=filters,
        position_sizing=position_sizing,
        raw_description=raw_description,
        field_provenance=provenance,
    )
