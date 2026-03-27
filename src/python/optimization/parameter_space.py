"""Parameter space parser for optimization (D10 taxonomy).

Parses strategy specification TOML into a structured parameter space
supporting continuous, integer, categorical, and conditional parameters.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

import numpy as np

from logging_setup.setup import get_logger

logger = get_logger("optimization.parameter_space")


class ParamType(str, Enum):
    CONTINUOUS = "continuous"
    INTEGER = "integer"
    CATEGORICAL = "categorical"


@dataclass
class ParameterSpec:
    """Single parameter definition from strategy specification."""
    name: str
    param_type: ParamType
    min_val: float | None = None
    max_val: float | None = None
    step: float | None = None
    choices: list[str] | None = None
    condition: dict | None = None  # {"parent": str, "value": str}

    @property
    def is_conditional(self) -> bool:
        return self.condition is not None

    @property
    def n_choices(self) -> int:
        if self.choices is not None:
            return len(self.choices)
        return 0


@dataclass
class ParameterSpace:
    """Container for all optimizable parameters with dimensionality tracking."""
    parameters: list[ParameterSpec] = field(default_factory=list)

    @property
    def n_dims(self) -> int:
        """Total number of searchable dimensions (categoricals count as 1)."""
        return len(self.parameters)

    @property
    def continuous_params(self) -> list[ParameterSpec]:
        return [p for p in self.parameters if p.param_type == ParamType.CONTINUOUS]

    @property
    def integer_params(self) -> list[ParameterSpec]:
        return [p for p in self.parameters if p.param_type == ParamType.INTEGER]

    @property
    def categorical_params(self) -> list[ParameterSpec]:
        return [p for p in self.parameters if p.param_type == ParamType.CATEGORICAL]

    @property
    def param_names(self) -> list[str]:
        return [p.name for p in self.parameters]

    def subset(self, names: set[str]) -> ParameterSpace:
        """Return a new ParameterSpace with only the named parameters."""
        return ParameterSpace(
            parameters=[p for p in self.parameters if p.name in names]
        )


def parse_strategy_params(strategy_spec: dict) -> ParameterSpace:
    """Parse optimization parameters from strategy specification TOML.

    Expects the flat parameter registry format from
    ``contracts/strategy_specification.toml`` (schema_version=2).
    """
    opt_plan = strategy_spec.get("optimization_plan", {})
    schema_version = opt_plan.get("schema_version", 1)

    if schema_version < 2:
        raise ValueError(
            f"Unsupported optimization_plan schema_version={schema_version}. "
            "Expected version 2 (flat parameter registry)."
        )

    raw_params = opt_plan.get("parameters", {})
    parameters: list[ParameterSpec] = []

    for name, spec in raw_params.items():
        param_type = ParamType(spec["type"])
        param = ParameterSpec(
            name=name,
            param_type=param_type,
            min_val=spec.get("min"),
            max_val=spec.get("max"),
            step=spec.get("step"),
            choices=spec.get("choices"),
            condition=spec.get("condition"),
        )
        parameters.append(param)

    space = ParameterSpace(parameters=parameters)

    logger.info(
        f"Parsed parameter space: {space.n_dims} dimensions",
        extra={
            "component": "optimization.parameter_space",
            "ctx": {
                "n_continuous": len(space.continuous_params),
                "n_integer": len(space.integer_params),
                "n_categorical": len(space.categorical_params),
            },
        },
    )

    return space


def detect_branches(space: ParameterSpace) -> dict[str, ParameterSpace]:
    """Identify conditional parameter branches.

    Top-level categoricals (no condition themselves) that have child parameters
    conditioned on them define branches. Each branch gets the unconditional
    params plus the branch-specific conditional params.

    Returns:
        dict mapping branch_key (e.g. "exit_type=trailing_stop") to its
        ParameterSpace. If no branching, returns {"__default__": full_space}.
    """
    # Find top-level categoricals that have children conditioned on them
    branch_parents: dict[str, ParameterSpec] = {}
    for p in space.parameters:
        if p.param_type == ParamType.CATEGORICAL and not p.is_conditional:
            # Check if any parameter is conditioned on this one
            has_children = any(
                other.condition and other.condition.get("parent") == p.name
                for other in space.parameters
            )
            if has_children:
                branch_parents[p.name] = p

    if not branch_parents:
        return {"__default__": space}

    # For simplicity, branch on the first branching categorical found
    # (multi-level branching can be extended later)
    branch_param_name = next(iter(branch_parents))
    branch_param = branch_parents[branch_param_name]

    # Unconditional params (not conditioned on this branch parent)
    unconditional = [
        p for p in space.parameters
        if p.name != branch_param_name
        and (not p.is_conditional or p.condition.get("parent") != branch_param_name)
    ]

    branches: dict[str, ParameterSpace] = {}
    for choice in (branch_param.choices or []):
        branch_key = f"{branch_param_name}={choice}"
        # Params conditioned on this choice
        branch_specific = [
            p for p in space.parameters
            if p.is_conditional
            and p.condition.get("parent") == branch_param_name
            and p.condition.get("value") == choice
        ]
        branches[branch_key] = ParameterSpace(
            parameters=unconditional + branch_specific
        )

    logger.info(
        f"Detected {len(branches)} branches on '{branch_param_name}'",
        extra={
            "component": "optimization.parameter_space",
            "ctx": {"branches": list(branches.keys())},
        },
    )

    return branches


def to_cmaes_bounds(space: ParameterSpace) -> tuple[np.ndarray, np.ndarray]:
    """Convert parameter space to CMA-ES bounds arrays.

    Returns (lower_bounds, upper_bounds) as float64 arrays.
    Categoricals are encoded as [0, n_choices-1] continuous range.
    """
    lower = []
    upper = []
    for p in space.parameters:
        if p.param_type == ParamType.CATEGORICAL:
            lower.append(0.0)
            upper.append(float(p.n_choices - 1))
        else:
            lower.append(float(p.min_val if p.min_val is not None else 0.0))
            upper.append(float(p.max_val if p.max_val is not None else 1.0))

    return np.array(lower, dtype=np.float64), np.array(upper, dtype=np.float64)


def to_nevergrad_params(space: ParameterSpace) -> dict[str, Any]:
    """Convert parameter space to Nevergrad parametrization dict.

    Returns a dict suitable for constructing ng.p.Instrumentation.
    """
    import nevergrad as ng

    params: dict[str, Any] = {}
    for p in space.parameters:
        if p.param_type == ParamType.CONTINUOUS:
            params[p.name] = ng.p.Scalar(
                lower=p.min_val, upper=p.max_val
            )
        elif p.param_type == ParamType.INTEGER:
            params[p.name] = ng.p.Scalar(
                lower=p.min_val, upper=p.max_val
            ).set_integer_casting()
        elif p.param_type == ParamType.CATEGORICAL:
            params[p.name] = ng.p.Choice(p.choices or [])

    return params


def decode_candidate(candidate: np.ndarray, space: ParameterSpace) -> dict[str, Any]:
    """Decode a numpy candidate vector back to named parameter dict."""
    result: dict[str, Any] = {}
    for i, p in enumerate(space.parameters):
        val = candidate[i]
        if p.param_type == ParamType.INTEGER:
            rounded = int(round(val))
            if p.step is not None and p.step > 0:
                base = int(p.min_val) if p.min_val is not None else 0
                step = int(p.step)
                rounded = base + round((rounded - base) / step) * step
            result[p.name] = rounded
        elif p.param_type == ParamType.CATEGORICAL:
            idx = int(round(np.clip(val, 0, p.n_choices - 1)))
            result[p.name] = p.choices[idx]
        else:
            result[p.name] = float(val)
    return result


def encode_params(params: dict[str, Any], space: ParameterSpace) -> np.ndarray:
    """Encode a named parameter dict to a numpy vector."""
    vec = np.zeros(space.n_dims, dtype=np.float64)
    for i, p in enumerate(space.parameters):
        val = params.get(p.name)
        if p.param_type == ParamType.CATEGORICAL:
            if val in (p.choices or []):
                vec[i] = float((p.choices or []).index(val))
            else:
                vec[i] = 0.0
        else:
            vec[i] = float(val) if val is not None else 0.0
    return vec


def snap_to_grid(value: float, spec: "ParameterSpec") -> Any:
    """Snap a raw optimizer value to the parameter's step grid.

    Critical for cache hit rate: CMA-ES produces continuous values like
    4.7 and 4.3 which both round to integer 5. Snapping before hashing
    ensures they produce identical cache keys.

    Uses the same rounding logic as decode_candidate().
    """
    if spec.param_type == ParamType.INTEGER:
        rounded = int(round(value))
        if spec.step is not None and spec.step > 0:
            base = int(spec.min_val) if spec.min_val is not None else 0
            step = int(spec.step)
            rounded = base + round((rounded - base) / step) * step
        # Clamp to bounds
        if spec.min_val is not None:
            rounded = max(rounded, int(spec.min_val))
        if spec.max_val is not None:
            rounded = min(rounded, int(spec.max_val))
        return rounded
    elif spec.param_type == ParamType.CONTINUOUS:
        if spec.step is not None and spec.step > 0:
            value = round(value / spec.step) * spec.step
        # Clamp to bounds
        if spec.min_val is not None:
            value = max(value, spec.min_val)
        if spec.max_val is not None:
            value = min(value, spec.max_val)
        return float(value)
    elif spec.param_type == ParamType.CATEGORICAL:
        idx = int(round(np.clip(value, 0, spec.n_choices - 1)))
        return spec.choices[idx] if spec.choices else str(idx)
    return float(value)


def extract_params_by_indices(
    candidate: np.ndarray,
    space: "ParameterSpace",
    indices: list[int],
) -> dict[str, Any]:
    """Extract a subset of params from a candidate vector, snapped to grid.

    Args:
        candidate: Raw optimizer output vector.
        space: Full ParameterSpace with param specs.
        indices: Positional indices of params to extract.

    Returns:
        dict of param_name → snapped value.
    """
    result: dict[str, Any] = {}
    for idx in indices:
        p = space.parameters[idx]
        result[p.name] = snap_to_grid(candidate[idx], p)
    return result
