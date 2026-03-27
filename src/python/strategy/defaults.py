"""Defaults resolution with provenance tracking (D7).

Loads defaults from config/strategies/defaults.toml (NOT hardcoded).
Fills missing non-identity fields and records provenance.
"""

from __future__ import annotations

import logging
import tomllib
from pathlib import Path

from strategy.dialogue_parser import (
    ExitIntent,
    PositionSizingIntent,
    StrategyIntent,
)

logger = logging.getLogger(__name__)


def _find_defaults_path() -> Path:
    """Locate config/strategies/defaults.toml by walking up from CWD."""
    current = Path.cwd()
    for parent in [current, *current.parents]:
        candidate = parent / "config" / "strategies" / "defaults.toml"
        if candidate.exists():
            return candidate
    raise FileNotFoundError("Cannot locate config/strategies/defaults.toml")


def _load_defaults(defaults_path: Path | None = None) -> dict:
    """Load strategy defaults from TOML config."""
    if defaults_path is None:
        defaults_path = _find_defaults_path()

    with open(defaults_path, "rb") as f:
        return tomllib.load(f)


def apply_defaults(
    intent: StrategyIntent,
    defaults_path: Path | None = None,
) -> StrategyIntent:
    """Fill missing non-identity fields from defaults, return new StrategyIntent.

    Follows immutable pattern: returns a new StrategyIntent, does not mutate input.

    Args:
        intent: Parsed strategy intent (may have None/empty fields).
        defaults_path: Path to defaults TOML. Auto-discovered if None.

    Returns:
        New StrategyIntent with defaults applied and provenance updated.
    """
    defaults = _load_defaults(defaults_path)
    defaults_section = defaults["defaults"]

    provenance = dict(intent.field_provenance)

    # --- Pair default (should-have: warn + default) ---
    pair = intent.pair
    if not pair:
        pair_cfg = defaults_section["pair"]
        pair = pair_cfg["value"]
        provenance["pair"] = "default"
        logger.warning(
            "Pair not specified, defaulting to %s (rationale: %s)",
            pair,
            pair_cfg.get("rationale", ""),
        )

    # --- Timeframe default (should-have: warn + default) ---
    timeframe = intent.timeframe
    if not timeframe:
        tf_cfg = defaults_section["timeframe"]
        timeframe = tf_cfg["value"]
        provenance["timeframe"] = "default"
        logger.warning(
            "Timeframe not specified, defaulting to %s (rationale: %s)",
            timeframe,
            tf_cfg.get("rationale", ""),
        )

    # --- Position sizing default (may default silently) ---
    position_sizing = intent.position_sizing
    if not position_sizing:
        ps_cfg = defaults_section["position_sizing"]
        position_sizing = PositionSizingIntent(
            method=ps_cfg["method"],
            params={
                "risk_percent": ps_cfg["risk_percent"],
                "max_lots": ps_cfg["max_lots"],
            },
        )
        provenance["position_sizing"] = "default"

    # --- Exit rules defaults (may default silently) ---
    exit_rules = list(intent.exit_rules)
    has_stop_loss = any(e.type == "stop_loss" for e in exit_rules)
    has_take_profit = any(e.type == "take_profit" for e in exit_rules)

    if not has_stop_loss:
        sl_cfg = defaults_section["exits"]["stop_loss"]
        exit_rules.append(
            ExitIntent(
                type="stop_loss",
                params={
                    "sl_type": sl_cfg["type"],
                    "value": sl_cfg["value"],
                },
            )
        )
        provenance["exit_rules.stop_loss"] = "default"

    if not has_take_profit:
        tp_cfg = defaults_section["exits"]["take_profit"]
        exit_rules.append(
            ExitIntent(
                type="take_profit",
                params={
                    "tp_type": tp_cfg["type"],
                    "value": tp_cfg["value"],
                },
            )
        )
        provenance["exit_rules.take_profit"] = "default"

    if "exit_rules" not in provenance:
        provenance["exit_rules"] = "default"

    return StrategyIntent(
        pair=pair,
        timeframe=timeframe,
        indicators=list(intent.indicators),
        entry_conditions=list(intent.entry_conditions),
        exit_rules=exit_rules,
        filters=list(intent.filters),
        position_sizing=position_sizing,
        raw_description=intent.raw_description,
        field_provenance=provenance,
    )
