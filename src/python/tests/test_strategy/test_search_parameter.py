"""Tests for SearchParameter and OptimizationPlan v2 models (Story 5.2b).

Covers: AC #1 (flat registry), AC #2 (nested conditionals), AC #3 (validators),
AC #7 (cross-parameter constraints), AC #12 (schema versioning).
"""

from pathlib import Path

import pytest
import tomllib
from pydantic import ValidationError

from strategy.indicator_registry import reset_registry
from strategy.loader import load_strategy_spec, validate_strategy_spec
from strategy.specification import (
    OptimizationPlan,
    SchemaVersionError,
    SearchParameter,
)

PROJECT_ROOT = Path(__file__).resolve().parents[4]
V002_SPEC = PROJECT_ROOT / "artifacts" / "strategies" / "ma-crossover" / "v002.toml"
V001_SPEC = PROJECT_ROOT / "artifacts" / "strategies" / "ma-crossover" / "v001.toml"


@pytest.fixture(autouse=True)
def _clear_registry():
    reset_registry()
    yield
    reset_registry()


# --- SearchParameter type validation ---


def test_search_parameter_continuous_valid():
    """Continuous parameter with min/max validates."""
    sp = SearchParameter(type="continuous", min=0.5, max=5.0)
    assert sp.type == "continuous"
    assert sp.min == 0.5
    assert sp.max == 5.0


def test_search_parameter_integer_valid():
    """Integer parameter with min/max/step validates, min/max are whole numbers."""
    sp = SearchParameter(type="integer", min=5.0, max=50.0, step=5.0)
    assert sp.type == "integer"
    assert sp.min == 5.0
    assert sp.max == 50.0
    assert sp.step == 5.0


def test_search_parameter_integer_non_whole_fails():
    """Integer with min=5.5 fails."""
    with pytest.raises(ValidationError, match="whole number"):
        SearchParameter(type="integer", min=5.5, max=50.0)


def test_search_parameter_categorical_valid():
    """Categorical with choices validates."""
    sp = SearchParameter(type="categorical", choices=["a", "b", "c"])
    assert sp.type == "categorical"
    assert sp.choices == ["a", "b", "c"]


def test_search_parameter_categorical_needs_two_choices():
    """Single choice fails."""
    with pytest.raises(ValidationError, match="at least 2"):
        SearchParameter(type="categorical", choices=["only_one"])


def test_search_parameter_continuous_missing_bounds_fails():
    """Continuous without min/max fails."""
    with pytest.raises(ValidationError, match="requires both min and max"):
        SearchParameter(type="continuous")


def test_search_parameter_categorical_rejects_bounds():
    """Categorical with min/max fails."""
    with pytest.raises(ValidationError, match="must not have min/max/step"):
        SearchParameter(type="categorical", choices=["a", "b"], min=1.0, max=10.0)


def test_search_parameter_min_gte_max_fails():
    """min >= max fails."""
    with pytest.raises(ValidationError, match="must be less than max"):
        SearchParameter(type="continuous", min=10.0, max=5.0)
    with pytest.raises(ValidationError, match="must be less than max"):
        SearchParameter(type="continuous", min=5.0, max=5.0)


def test_search_parameter_conditional_valid():
    """Condition with valid parent ref structure validates."""
    sp = SearchParameter(
        type="continuous",
        min=1.0,
        max=10.0,
        condition={"parent": "exit_type", "value": "trailing"},
    )
    assert sp.condition is not None
    assert sp.condition.parent == "exit_type"
    assert sp.condition.value == "trailing"


# --- OptimizationPlan flat format ---


def test_optimization_plan_flat_valid():
    """Full flat plan with mixed types validates."""
    plan = OptimizationPlan(
        schema_version=2,
        parameters={
            "fast_period": SearchParameter(type="integer", min=5.0, max=50.0, step=5.0),
            "slow_period": SearchParameter(type="integer", min=20.0, max=200.0, step=10.0),
            "sl_mult": SearchParameter(type="continuous", min=0.5, max=5.0),
            "session": SearchParameter(type="categorical", choices=["london", "new_york"]),
        },
        objective_function="sharpe",
    )
    assert len(plan.parameters) == 4
    assert plan.schema_version == 2


def test_optimization_plan_condition_invalid_parent():
    """Condition references nonexistent parent fails."""
    with pytest.raises(ValidationError, match="unknown parent.*nonexistent"):
        OptimizationPlan(
            schema_version=2,
            parameters={
                "child": SearchParameter(
                    type="continuous",
                    min=1.0,
                    max=10.0,
                    condition={"parent": "nonexistent", "value": "x"},
                ),
            },
            objective_function="sharpe",
        )


def test_optimization_plan_condition_invalid_choice():
    """Condition references choice not in parent's choices fails."""
    with pytest.raises(ValidationError, match="not in parent.*exit_type"):
        OptimizationPlan(
            schema_version=2,
            parameters={
                "exit_type": SearchParameter(
                    type="categorical", choices=["fixed", "trailing"]
                ),
                "trail_dist": SearchParameter(
                    type="continuous",
                    min=1.0,
                    max=10.0,
                    condition={"parent": "exit_type", "value": "bogus_choice"},
                ),
            },
            objective_function="sharpe",
        )


def test_optimization_plan_circular_dependency():
    """A conditioned on B conditioned on A fails."""
    with pytest.raises(ValidationError, match="[Cc]ircular"):
        OptimizationPlan(
            schema_version=2,
            parameters={
                "a": SearchParameter(
                    type="categorical",
                    choices=["x", "y"],
                    condition={"parent": "b", "value": "p"},
                ),
                "b": SearchParameter(
                    type="categorical",
                    choices=["p", "q"],
                    condition={"parent": "a", "value": "x"},
                ),
            },
            objective_function="sharpe",
        )


def test_optimization_plan_nested_three_deep():
    """A -> B -> C conditional chain validates."""
    plan = OptimizationPlan(
        schema_version=2,
        parameters={
            "exit_type": SearchParameter(
                type="categorical", choices=["trailing", "fixed"]
            ),
            "trailing_method": SearchParameter(
                type="categorical",
                choices=["chandelier", "simple"],
                condition={"parent": "exit_type", "value": "trailing"},
            ),
            "chandelier_atr_period": SearchParameter(
                type="integer",
                min=5.0,
                max=50.0,
                condition={"parent": "trailing_method", "value": "chandelier"},
            ),
        },
        objective_function="sharpe",
    )
    assert len(plan.parameters) == 3
    assert plan.parameters["chandelier_atr_period"].condition.parent == "trailing_method"


# --- v002 loading ---


def test_v002_loads_and_validates():
    """Load v002.toml through full pipeline, no errors."""
    spec = load_strategy_spec(V002_SPEC)
    assert spec.metadata.name == "ma-crossover"
    assert spec.metadata.version == "v002"
    assert spec.optimization_plan is not None
    assert spec.optimization_plan.schema_version == 2
    assert "fast_period" in spec.optimization_plan.parameters
    assert "session_filter" in spec.optimization_plan.parameters


def test_v002_semantic_validation_passes():
    """v002 passes validate_strategy_spec()."""
    spec = load_strategy_spec(V002_SPEC)
    errors = validate_strategy_spec(spec)
    assert errors == [], f"Semantic validation failed: {errors}"


# --- Schema versioning ---


def test_schema_version_required():
    """OptimizationPlan without schema_version fails validation."""
    with pytest.raises(ValidationError):
        OptimizationPlan(
            parameters={
                "p": SearchParameter(type="integer", min=1.0, max=10.0),
            },
            objective_function="sharpe",
        )


def test_schema_version_1_rejected():
    """schema_version=1 raises validation error."""
    with pytest.raises(ValidationError):
        OptimizationPlan(
            schema_version=1,
            parameters={
                "p": SearchParameter(type="integer", min=1.0, max=10.0),
            },
            objective_function="sharpe",
        )


def test_v001_legacy_format_clear_error(tmp_path):
    """Loading a legacy parameter_groups optimization_plan raises clear error."""
    legacy_toml = tmp_path / "legacy.toml"
    legacy_toml.write_text(
        '[metadata]\nname = "test"\nversion = "001"\n'
        'schema_version = "1"\npair = "EUR_USD"\ntimeframe = "M1"\n\n'
        "[optimization_plan]\n"
        'parameter_groups = [{name = "fast", params = ["fast_period"]}]\n'
    )
    with pytest.raises(SchemaVersionError, match="legacy parameter_groups"):
        load_strategy_spec(legacy_toml)
