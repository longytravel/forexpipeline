"""Three-tier parameter classification for joint optimization (D10 taxonomy).

Classifies each optimization_plan parameter into one of three tiers:
- signal: affects indicator computation, requires signal precompute per unique set
- batch: handled by Rust apply_candidate_params at runtime (exit params)
- spec_override: needs per-group strategy spec TOML (e.g., session_filter)

Generic across all strategy specs — classification is derived from the spec
structure, not hardcoded per strategy.
"""
from __future__ import annotations

import copy
import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from logging_setup.setup import get_logger
from optimization.parameter_space import ParameterSpace, ParamType

logger = get_logger("optimization.param_classifier")

# Params handled by Rust's apply_candidate_params() at runtime.
# When a new exit param type is added to Rust, add it here too.
RUST_BATCH_PARAMS: set[str] = {
    "sl_atr_multiplier",
    "tp_rr_ratio",
    "trailing_atr_multiplier",
    "trailing_atr_period",
}


@dataclass
class ParamClassification:
    """Three-tier classification of optimization parameters.

    - signal_params: affect signal computation. Changing these requires
      a different enriched Arrow file. dict maps param name to list of
      spec paths where the param appears in entry_rules.conditions.
    - batch_params: applied by Rust at runtime via param_batch.json.
    - spec_override_params: need per-group strategy spec TOML override.
      dict maps param name to the spec path it targets.
    """

    signal_params: dict[str, list[str]] = field(default_factory=dict)
    batch_params: set[str] = field(default_factory=set)
    spec_override_params: dict[str, str] = field(default_factory=dict)

    # Positional indices into ParameterSpace.parameters
    signal_indices: list[int] = field(default_factory=list)
    batch_indices: list[int] = field(default_factory=list)
    spec_override_indices: list[int] = field(default_factory=list)

    @property
    def group_key_indices(self) -> list[int]:
        """Indices of params that define the candidate grouping key.

        Candidates are grouped by signal + spec_override params combined.
        Only batch params vary freely within a group.
        """
        return sorted(self.signal_indices + self.spec_override_indices)

    @property
    def has_signal_params(self) -> bool:
        return len(self.signal_params) > 0


def classify_params(
    strategy_spec: dict, space: ParameterSpace
) -> ParamClassification:
    """Classify each optimization parameter into signal/batch/spec_override.

    Algorithm:
    1. Collect all param names from entry_rules.conditions[].parameters
    2. For each optimization param:
       - If name appears in entry conditions params -> signal
       - If name is in RUST_BATCH_PARAMS -> batch
       - Otherwise -> spec_override (with logged warning)

    Args:
        strategy_spec: Parsed strategy TOML dict.
        space: Parsed ParameterSpace from optimization_plan.

    Returns:
        ParamClassification with all three tiers populated.
    """
    # 1. Collect entry condition param names and their spec paths
    entry_param_paths: dict[str, list[str]] = {}
    conditions = strategy_spec.get("entry_rules", {}).get("conditions", [])
    for i, cond in enumerate(conditions):
        cond_params = cond.get("parameters", {})
        for pname in cond_params:
            path = f"entry_rules.conditions[{i}].parameters.{pname}"
            entry_param_paths.setdefault(pname, []).append(path)

    # 2. Classify each optimization parameter
    classification = ParamClassification()
    opt_param_names = {p.name for p in space.parameters}

    for i, p in enumerate(space.parameters):
        if p.name in entry_param_paths and p.name in opt_param_names:
            # Signal: appears in entry_rules.conditions[].parameters
            classification.signal_params[p.name] = entry_param_paths[p.name]
            classification.signal_indices.append(i)
        elif p.name in RUST_BATCH_PARAMS:
            # Batch: handled by Rust apply_candidate_params
            classification.batch_params.add(p.name)
            classification.batch_indices.append(i)
        else:
            # Spec override: needs per-group TOML spec
            # Derive target path heuristically
            target = _derive_spec_override_target(p.name, strategy_spec)
            classification.spec_override_params[p.name] = target
            classification.spec_override_indices.append(i)

    logger.info(
        f"Parameter classification: {len(classification.signal_params)} signal, "
        f"{len(classification.batch_params)} batch, "
        f"{len(classification.spec_override_params)} spec_override",
        extra={
            "component": "optimization.param_classifier",
            "ctx": {
                "signal": list(classification.signal_params.keys()),
                "batch": list(classification.batch_params),
                "spec_override": list(classification.spec_override_params.keys()),
            },
        },
    )

    return classification


def _derive_spec_override_target(param_name: str, spec: dict) -> str:
    """Derive the spec path for a spec_override parameter.

    Searches entry_rules.filters, position_sizing, and other spec sections
    to find where this parameter should be applied.
    """
    # Check entry_rules.filters
    filters = spec.get("entry_rules", {}).get("filters", [])
    for i, f in enumerate(filters):
        ftype = f.get("type", "")
        if param_name == f"{ftype}_filter" or param_name == ftype:
            return f"entry_rules.filters[{i}]"
        fparams = f.get("params", {})
        if param_name in fparams:
            return f"entry_rules.filters[{i}].params.{param_name}"

    # Check position_sizing
    ps = spec.get("position_sizing", {})
    if param_name in ps:
        return f"position_sizing.{param_name}"

    # Fallback: log warning, no known target
    logger.warning(
        f"Parameter '{param_name}' not found in entry_rules, exit_rules, "
        f"or position_sizing — will be passed as spec override but target "
        f"path is unknown. Verify strategy spec.",
        extra={"component": "optimization.param_classifier"},
    )
    return f"unknown.{param_name}"


def build_override_spec(
    base_spec: dict,
    signal_params: dict[str, Any],
    spec_override_params: dict[str, Any],
    classification: ParamClassification,
) -> dict:
    """Build a modified strategy spec with overridden parameter values.

    Deep-copies the base spec and applies:
    - signal_params to all entry_rules.conditions[].parameters
    - spec_override_params to their derived target paths

    Args:
        base_spec: Original strategy spec dict.
        signal_params: Signal-affecting param values (e.g., {"swing_bars": 5}).
        spec_override_params: Spec override param values.
        classification: Classification with target path info.

    Returns:
        Modified spec dict (deep copy, original untouched).
    """
    spec = copy.deepcopy(base_spec)

    # Apply signal params to all conditions
    conditions = spec.get("entry_rules", {}).get("conditions", [])
    for cond in conditions:
        cond_params = cond.get("parameters", {})
        for pname, pval in signal_params.items():
            if pname in cond_params:
                cond_params[pname] = pval

    # Apply spec override params
    for pname, pval in spec_override_params.items():
        target = classification.spec_override_params.get(pname, "")
        _apply_spec_override(spec, target, pname, pval)

    return spec


def _apply_spec_override(
    spec: dict, target_path: str, param_name: str, value: Any
) -> None:
    """Apply a single parameter override to a spec dict by target path."""
    if target_path.startswith("unknown."):
        # Unknown target — skip with warning (already logged at classification)
        return

    # Handle filter overrides (e.g., session_filter → entry_rules.filters[i])
    if target_path.startswith("entry_rules.filters["):
        filters = spec.get("entry_rules", {}).get("filters", [])
        # Extract index
        idx_str = target_path.split("[")[1].split("]")[0]
        idx = int(idx_str)
        if idx < len(filters):
            filt = filters[idx]
            if ".params." in target_path:
                # Target is a specific param within the filter
                filt.setdefault("params", {})[param_name] = value
            else:
                # Target is the filter itself (e.g., session_filter → include list)
                if isinstance(value, str):
                    # Categorical choice → update include list
                    filt.setdefault("params", {})["include"] = [value]
                else:
                    filt.setdefault("params", {})[param_name] = value
        return

    # Handle position_sizing overrides
    if target_path.startswith("position_sizing."):
        spec.setdefault("position_sizing", {})[param_name] = value
        return


def compute_group_hash(
    signal_params: dict[str, Any],
    spec_override_params: dict[str, Any],
) -> str:
    """Deterministic hash for a candidate group (signal + spec_override params)."""
    combined = {
        "signal": signal_params,
        "spec_override": spec_override_params,
    }
    canonical = json.dumps(combined, sort_keys=True, default=str)
    return hashlib.sha256(canonical.encode()).hexdigest()[:16]


def compute_signal_hash(signal_params: dict[str, Any]) -> str:
    """Deterministic hash for signal params only (enriched data cache key)."""
    canonical = json.dumps(signal_params, sort_keys=True, default=str)
    return hashlib.sha256(canonical.encode()).hexdigest()[:16]


def write_toml_spec(spec: dict, output_dir: Path, group_hash: str) -> Path:
    """Write a strategy spec dict as TOML for Rust consumption.

    Args:
        spec: Strategy spec dict to serialize.
        output_dir: Directory to write into.
        group_hash: Hash for unique filename.

    Returns:
        Path to the written TOML file.
    """
    try:
        import tomli_w
        serialize = tomli_w.dumps
    except ImportError:
        serialize = _fallback_toml_serialize

    # Keep optimization_plan — Rust strategy_engine requires it for
    # spec parsing (the field is non-optional in StrategySpec struct).
    spec_for_rust = dict(spec)

    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / f"spec_{group_hash[:12]}.toml"
    path.write_text(serialize(spec_for_rust), encoding="utf-8")
    return path


def _fallback_toml_serialize(data: dict) -> str:
    """Minimal TOML serializer for strategy specs without tomli_w."""
    import io

    buf = io.StringIO()
    _write_toml_section(buf, data, [])
    return buf.getvalue()


def _write_toml_section(
    buf, data: dict, path: list[str], *, inline: bool = False
) -> None:
    """Recursively write a dict as TOML."""
    # Separate simple values from nested dicts/lists
    simple: list[tuple[str, Any]] = []
    nested: list[tuple[str, Any]] = []

    for k, v in data.items():
        if isinstance(v, dict):
            nested.append((k, v))
        elif isinstance(v, list) and v and isinstance(v[0], dict):
            nested.append((k, v))
        else:
            simple.append((k, v))

    # Write simple key-value pairs
    for k, v in simple:
        buf.write(f"{k} = {_toml_value(v)}\n")

    # Write nested sections
    for k, v in nested:
        section_path = path + [k]
        if isinstance(v, list):
            # Array of tables
            for item in v:
                buf.write(f"\n[[{'.'.join(section_path)}]]\n")
                _write_toml_section(buf, item, section_path)
        else:
            buf.write(f"\n[{'.'.join(section_path)}]\n")
            _write_toml_section(buf, v, section_path)


def _toml_value(v: Any) -> str:
    """Format a Python value as a TOML literal."""
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, int):
        return str(v)
    if isinstance(v, float):
        return str(v)
    if isinstance(v, str):
        return f'"{v}"'
    if isinstance(v, list):
        items = ", ".join(_toml_value(i) for i in v)
        return f"[{items}]"
    return f'"{v}"'
