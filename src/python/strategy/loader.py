"""Strategy Specification Loader (D10, D7).

Load TOML strategy specifications into validated Pydantic models.
Follows validate_or_die() pattern: collect ALL errors, print ALL, then exit.
Uses tomllib (stdlib 3.11+) for TOML parsing.
"""

from __future__ import annotations

import logging
import sys
import tomllib
from pathlib import Path

from pydantic import ValidationError

from strategy.indicator_registry import get_indicator_params, is_indicator_known
from strategy.specification import SchemaVersionError, StrategySpecification

logger = logging.getLogger(__name__)


def load_strategy_spec(spec_path: Path) -> StrategySpecification:
    """Load a TOML strategy specification into a validated Pydantic model.

    Args:
        spec_path: Path to the .toml specification file.

    Returns:
        Validated StrategySpecification instance.

    Raises:
        FileNotFoundError: If spec_path does not exist.
        ValueError: If TOML parsing fails.
        pydantic.ValidationError: If schema validation fails.
    """
    spec_path = Path(spec_path)
    if not spec_path.exists():
        raise FileNotFoundError(f"Strategy specification not found: {spec_path}")

    with open(spec_path, "rb") as f:
        try:
            raw = tomllib.load(f)
        except tomllib.TOMLDecodeError as e:
            raise ValueError(f"Invalid TOML in {spec_path}: {e}") from e

    # Detect legacy v1 optimization_plan format
    opt_plan = raw.get("optimization_plan")
    if opt_plan is not None and "parameter_groups" in opt_plan:
        raise SchemaVersionError(
            f"optimization_plan in {spec_path} uses legacy parameter_groups format "
            f"(schema v1). Migrate to flat parameters registry (schema_version = 2). "
            f"See contracts/strategy_specification.toml for the new format."
        )

    return StrategySpecification.model_validate(raw)


def validate_strategy_spec(spec: StrategySpecification) -> list[str]:
    """Semantic validation beyond schema: indicator types, parameter ranges, references.

    Collects ALL errors (does not stop at first).

    Args:
        spec: A structurally valid StrategySpecification.

    Returns:
        List of error strings. Empty means valid.
    """
    errors: list[str] = []

    # Validate all indicator references are known and params match registry
    for i, cond in enumerate(spec.entry_rules.conditions):
        if not is_indicator_known(cond.indicator):
            errors.append(
                f"entry_rules.conditions[{i}]: unknown indicator '{cond.indicator}'"
            )
        else:
            meta = get_indicator_params(cond.indicator)
            for req_param in meta.required_params:
                if req_param not in cond.parameters:
                    errors.append(
                        f"entry_rules.conditions[{i}]: indicator '{cond.indicator}' "
                        f"requires parameter '{req_param}'"
                    )
            known_params = set(meta.required_params) | set(meta.optional_params)
            for param_name in cond.parameters:
                if param_name not in known_params:
                    errors.append(
                        f"entry_rules.conditions[{i}]: indicator '{cond.indicator}' "
                        f"has no parameter '{param_name}'"
                    )

    for i, conf in enumerate(spec.entry_rules.confirmation):
        if not is_indicator_known(conf.indicator):
            errors.append(
                f"entry_rules.confirmation[{i}]: unknown indicator '{conf.indicator}'"
            )
        else:
            meta = get_indicator_params(conf.indicator)
            for req_param in meta.required_params:
                if req_param not in conf.parameters:
                    errors.append(
                        f"entry_rules.confirmation[{i}]: indicator '{conf.indicator}' "
                        f"requires parameter '{req_param}'"
                    )
            known_params = set(meta.required_params) | set(meta.optional_params)
            for param_name in conf.parameters:
                if param_name not in known_params:
                    errors.append(
                        f"entry_rules.confirmation[{i}]: indicator '{conf.indicator}' "
                        f"has no parameter '{param_name}'"
                    )

    # Validate volatility filter indicators
    for i, filt in enumerate(spec.entry_rules.filters):
        if filt.type == "volatility":
            ind = filt.params.get("indicator")
            if ind and isinstance(ind, str) and not is_indicator_known(ind):
                errors.append(
                    f"entry_rules.filters[{i}]: unknown volatility indicator '{ind}'"
                )

    # Validate optimization parameter names reference actual spec parameters
    if spec.optimization_plan is not None:
        # Build set of known optimizable parameter names from strategy components
        optimizable_params: set[str] = set()
        for cond in spec.entry_rules.conditions:
            optimizable_params.update(cond.parameters.keys())
        for conf in spec.entry_rules.confirmation:
            optimizable_params.update(conf.parameters.keys())
        if spec.exit_rules.trailing:
            optimizable_params.update(spec.exit_rules.trailing.params.keys())
        # Component-prefixed names for exit rule values
        optimizable_params.update([
            "sl_atr_multiplier", "tp_rr_ratio", "trailing_atr_period",
            "trailing_atr_multiplier", "session_filter",
        ])

        for param_name, param in spec.optimization_plan.parameters.items():
            # Skip categorical params — they represent strategy choices, not
            # direct indicator params (e.g., session_filter, exit_type)
            if param.type == "categorical":
                continue
            if param_name not in optimizable_params:
                errors.append(
                    f"optimization_plan.parameters['{param_name}']: parameter "
                    f"not found in entry conditions, confirmations, "
                    f"or exit params"
                )

            # Validate condition chains resolve to valid categorical parents
            if param.condition is not None:
                parent_name = param.condition.parent
                if parent_name in spec.optimization_plan.parameters:
                    parent = spec.optimization_plan.parameters[parent_name]
                    if parent.type != "categorical":
                        errors.append(
                            f"optimization_plan.parameters['{param_name}']: "
                            f"condition parent '{parent_name}' is not categorical"
                        )

        # Cross-parameter range warnings
        params = spec.optimization_plan.parameters
        if "fast_period" in params and "slow_period" in params:
            fp = params["fast_period"]
            sp = params["slow_period"]
            if (fp.max is not None and sp.min is not None
                    and sp.min <= fp.max):
                logger.warning(
                    "optimization_plan: slow_period.min (%s) <= fast_period.max (%s) — "
                    "overlap could produce invalid fast >= slow combinations",
                    sp.min, fp.max,
                )

    # Validate cost_model_reference format (already done by Pydantic, but defense-in-depth)
    if spec.cost_model_reference is not None:
        import re

        if not re.match(r"^v\d{3}$", spec.cost_model_reference.version):
            errors.append(
                f"cost_model_reference.version: invalid format '{spec.cost_model_reference.version}'"
            )

    return errors


def validate_or_die_strategy(spec_path: Path) -> StrategySpecification:
    """Load + validate + sys.exit(1) on failure.

    Follows validate_or_die() pattern from config_loader/validator.py:
    collect all errors, print all, then exit.

    Args:
        spec_path: Path to the .toml specification file.

    Returns:
        Validated StrategySpecification if all checks pass.
    """
    errors: list[str] = []

    # Phase 1: Load and structural validation
    try:
        spec = load_strategy_spec(spec_path)
    except FileNotFoundError as e:
        errors.append(str(e))
    except ValueError as e:
        errors.append(str(e))
    except ValidationError as e:
        for err in e.errors():
            loc = " -> ".join(str(x) for x in err["loc"])
            errors.append(f"{loc}: {err['msg']}")

    if errors:
        print(f"Strategy specification validation failed ({spec_path}):", file=sys.stderr)
        for err in errors:
            print(f"  - {err}", file=sys.stderr)
        sys.exit(1)

    # Phase 2: Semantic validation
    semantic_errors = validate_strategy_spec(spec)
    if semantic_errors:
        print(f"Strategy specification semantic validation failed ({spec_path}):", file=sys.stderr)
        for err in semantic_errors:
            print(f"  - {err}", file=sys.stderr)
        sys.exit(1)

    logger.info("Strategy specification validated: %s", spec_path)
    return spec
