"""Specification Generator — converts parsed intent to Pydantic model (D10).

Maps StrategyIntent fields to StrategySpecification schema constructs.
Delegates validation to Story 2.3's validate_strategy_spec().
"""

from __future__ import annotations

import re
from typing import Any

from strategy.dialogue_parser import StrategyIntent
from strategy.loader import validate_strategy_spec
from strategy.specification import (
    EntryCondition,
    EntryFilter,
    EntryRules,
    ExitRules,
    ExitStopLoss,
    ExitTakeProfit,
    ExitTrailing,
    PositionSizing,
    StrategyMetadata,
    StrategySpecification,
)

# Crossover indicators use crosses_above comparator with threshold 0.0
CROSSOVER_INDICATORS = {"sma_crossover", "ema_crossover"}

# Default comparators/thresholds for common indicator types
DEFAULT_COMPARATORS: dict[str, tuple[str, float]] = {
    "rsi": (">", 50.0),
    "cci": (">", 0.0),
    "stochastic": (">", 50.0),
    "adx": (">", 25.0),
}


def _generate_strategy_name(intent: StrategyIntent) -> str:
    """Auto-generate a strategy slug from intent."""
    parts: list[str] = []
    if intent.indicators:
        primary = intent.indicators[0].type
        parts.append(primary.replace("_", "-"))
    if intent.pair:
        parts.append(intent.pair.lower())
    if intent.timeframe:
        parts.append(intent.timeframe.lower())

    name = "-".join(parts) if parts else "unnamed-strategy"
    name = re.sub(r"[^a-z0-9-]", "", name)
    return name


def _build_entry_conditions(intent: StrategyIntent) -> list[EntryCondition]:
    """Map IndicatorIntents with role=signal to EntryConditions."""
    conditions: list[EntryCondition] = []

    for ind in intent.indicators:
        if ind.role != "signal":
            continue

        # Determine comparator and threshold based on indicator type
        if ind.type in CROSSOVER_INDICATORS:
            comparator = "crosses_above"
            threshold = 0.0
        elif ind.type in DEFAULT_COMPARATORS:
            comparator, threshold = DEFAULT_COMPARATORS[ind.type]
        else:
            comparator = ">"
            threshold = 0.0

        # Allow overrides from params
        clean_params = dict(ind.params)
        comparator = str(clean_params.pop("comparator", comparator))
        threshold = float(clean_params.pop("threshold", threshold))

        conditions.append(
            EntryCondition(
                indicator=ind.type,
                parameters=clean_params,
                threshold=threshold,
                comparator=comparator,
            )
        )

    return conditions


def _build_filters(intent: StrategyIntent) -> list[EntryFilter]:
    """Map FilterIntents to EntryFilters."""
    filters: list[EntryFilter] = []
    for flt in intent.filters:
        params: dict[str, Any] = dict(flt.params)
        filters.append(EntryFilter(type=flt.type, params=params))
    return filters


def _build_exit_rules(intent: StrategyIntent) -> ExitRules:
    """Map ExitIntents to ExitRules."""
    stop_loss = None
    take_profit = None
    trailing = None

    for ex in intent.exit_rules:
        if ex.type == "stop_loss":
            sl_type = ex.params.get("sl_type", ex.params.get("type"))
            sl_value = ex.params["value"]
            if sl_type is None:
                raise ValueError("stop_loss exit must have 'sl_type' or 'type' in params")
            stop_loss = ExitStopLoss(type=sl_type, value=float(sl_value))

        elif ex.type == "take_profit":
            tp_type = ex.params.get("tp_type", ex.params.get("type"))
            tp_value = ex.params["value"]
            if tp_type is None:
                raise ValueError("take_profit exit must have 'tp_type' or 'type' in params")
            take_profit = ExitTakeProfit(type=tp_type, value=float(tp_value))

        elif ex.type == "trailing_stop":
            trailing = ExitTrailing(
                type="trailing_stop",
                params={k: v for k, v in ex.params.items() if k != "type"},
            )

        elif ex.type == "chandelier":
            trailing = ExitTrailing(
                type="chandelier",
                params={k: v for k, v in ex.params.items() if k != "type"},
            )

    if stop_loss is None:
        raise ValueError("Exit rules must include a stop_loss (apply_defaults first)")
    if take_profit is None:
        raise ValueError("Exit rules must include a take_profit (apply_defaults first)")

    return ExitRules(
        stop_loss=stop_loss,
        take_profit=take_profit,
        trailing=trailing,
    )


def _build_position_sizing(intent: StrategyIntent) -> PositionSizing:
    """Map PositionSizingIntent to PositionSizing."""
    if intent.position_sizing is None:
        raise ValueError(
            "Position sizing must be resolved before spec generation "
            "(apply_defaults first)"
        )

    ps = intent.position_sizing
    return PositionSizing(
        method=ps.method,
        risk_percent=float(ps.params["risk_percent"]),
        max_lots=float(ps.params["max_lots"]),
    )


def generate_specification(intent: StrategyIntent) -> StrategySpecification:
    """Convert parsed intent to validated StrategySpecification.

    Args:
        intent: Fully resolved StrategyIntent (defaults applied).

    Returns:
        Validated StrategySpecification ready for persistence.

    Raises:
        ValueError: If intent cannot be mapped to valid specification.
        pydantic.ValidationError: If generated spec fails schema validation.
    """
    name = _generate_strategy_name(intent)

    metadata = StrategyMetadata(
        name=name,
        version="v001",
        pair=intent.pair,
        timeframe=intent.timeframe,
        created_by="intent_capture",
        status="draft",
    )

    conditions = _build_entry_conditions(intent)
    filters = _build_filters(intent)

    entry_rules = EntryRules(
        conditions=conditions,
        filters=filters,
    )

    exit_rules = _build_exit_rules(intent)
    position_sizing = _build_position_sizing(intent)

    spec = StrategySpecification(
        metadata=metadata,
        entry_rules=entry_rules,
        exit_rules=exit_rules,
        position_sizing=position_sizing,
        optimization_plan=None,
        cost_model_reference=None,
    )

    # Validate using Story 2.3's semantic validation
    errors = validate_strategy_spec(spec)
    if errors:
        raise ValueError(
            "Generated specification failed validation:\n"
            + "\n".join(f"  - {e}" for e in errors)
        )

    return spec
