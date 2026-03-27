"""Tests for strategy specification schema validation (AC #1-#8)."""

from pathlib import Path

import pytest
import tomllib
from pydantic import ValidationError

from strategy.indicator_registry import reset_registry
from strategy.loader import load_strategy_spec, validate_strategy_spec
from strategy.specification import (
    CostModelReference,
    EntryCondition,
    EntryFilter,
    EntryRules,
    ExitRules,
    ExitStopLoss,
    ExitTakeProfit,
    ExitTrailing,
    OptimizationPlan,
    PositionSizing,
    SearchParameter,
    StrategyMetadata,
    StrategySpecification,
)

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture(autouse=True)
def _clear_registry():
    """Clear indicator registry cache between tests."""
    reset_registry()
    yield
    reset_registry()


# --- AC #1, #2: Valid spec loads with all fields ---


def test_valid_ma_crossover_spec_loads():
    """Load reference spec, assert all fields parsed correctly."""
    spec = load_strategy_spec(FIXTURES / "valid_ma_crossover.toml")

    assert spec.metadata.name == "ma-crossover"
    assert spec.metadata.version == "v001"
    assert spec.metadata.pair == "EURUSD"
    assert spec.metadata.timeframe == "H1"
    assert spec.metadata.schema_version == "1"
    assert spec.metadata.created_by == "test-fixture"
    assert spec.metadata.config_hash is None

    # Entry rules — single sma_crossover condition (review synthesis fix C1)
    assert len(spec.entry_rules.conditions) == 1
    assert spec.entry_rules.conditions[0].indicator == "sma_crossover"
    assert spec.entry_rules.conditions[0].comparator == "crosses_above"
    assert spec.entry_rules.conditions[0].parameters["fast_period"] == 20
    assert spec.entry_rules.conditions[0].parameters["slow_period"] == 50
    assert len(spec.entry_rules.filters) == 1
    assert spec.entry_rules.filters[0].type == "session"

    # Exit rules
    assert spec.exit_rules.stop_loss.type == "atr_multiple"
    assert spec.exit_rules.stop_loss.value == 1.5
    assert spec.exit_rules.take_profit.type == "risk_reward"
    assert spec.exit_rules.take_profit.value == 3.0
    assert spec.exit_rules.trailing is not None
    assert spec.exit_rules.trailing.type == "chandelier"
    assert spec.exit_rules.trailing.params["atr_period"] == 14
    assert spec.exit_rules.trailing.params["atr_multiplier"] == 3.0

    # Position sizing
    assert spec.position_sizing.method == "fixed_risk"
    assert spec.position_sizing.risk_percent == 1.0
    assert spec.position_sizing.max_lots == 1.0

    # Optimization plan (v2 flat format)
    assert spec.optimization_plan.schema_version == 2
    assert spec.optimization_plan.objective_function == "sharpe"
    assert "fast_period" in spec.optimization_plan.parameters
    assert "slow_period" in spec.optimization_plan.parameters
    assert "atr_multiplier" in spec.optimization_plan.parameters
    assert spec.optimization_plan.parameters["fast_period"].type == "integer"

    # Cost model reference
    assert spec.cost_model_reference.version == "v001"


# --- AC #4: Fail loud on invalid specs ---


def test_invalid_spec_missing_metadata_fails():
    """Missing metadata -> ValidationError."""
    with pytest.raises(ValidationError, match="metadata"):
        load_strategy_spec(FIXTURES / "invalid_missing_metadata.toml")


def test_invalid_spec_missing_entry_rules_fails():
    """Missing entry_rules -> ValidationError."""
    with pytest.raises(ValidationError, match="entry_rules"):
        # Build a spec dict without entry_rules
        StrategySpecification.model_validate(
            {
                "metadata": {
                    "schema_version": "1",
                    "name": "test",
                    "version": "v001",
                    "pair": "EURUSD",
                    "timeframe": "H1",
                    "created_by": "test",
                },
                "exit_rules": {
                    "stop_loss": {"type": "fixed_pips", "value": 30.0},
                    "take_profit": {"type": "fixed_pips", "value": 60.0},
                },
                "position_sizing": {
                    "method": "fixed_lots",
                    "risk_percent": 1.0,
                    "max_lots": 0.1,
                },
                "optimization_plan": {
                    "schema_version": 2,
                    "parameters": {
                        "p": {"type": "integer", "min": 1.0, "max": 10.0, "step": 1.0}
                    },
                    "objective_function": "sharpe",
                },
                "cost_model_reference": {"version": "v001"},
            }
        )


# --- AC #5: Param range validation ---


def test_invalid_param_range_min_gt_max_fails():
    """min > max -> ValidationError."""
    with pytest.raises(ValidationError, match="min.*must be less than max"):
        load_strategy_spec(FIXTURES / "invalid_bad_param_range.toml")


def test_invalid_param_range_step_zero_fails():
    """step=0 -> ValidationError (step must be > 0)."""
    with pytest.raises(ValidationError, match="step must be > 0"):
        SearchParameter(type="integer", min=1.0, max=10.0, step=0.0)


# --- AC #5: Unknown indicator ---


def test_unknown_indicator_type_fails():
    """Indicator not in registry -> semantic validation error."""
    spec = load_strategy_spec(FIXTURES / "invalid_unknown_indicator.toml")
    errors = validate_strategy_spec(spec)
    assert len(errors) > 0
    assert "magic_oscillator_9000" in errors[0]


# --- AC #5: Cost model reference validation ---


def test_invalid_cost_model_ref_fails():
    """Bad version format -> ValidationError."""
    with pytest.raises(ValidationError, match="cost_model_reference"):
        load_strategy_spec(FIXTURES / "invalid_bad_cost_ref.toml")


# --- Roundtrip ---


def test_spec_roundtrip_toml_to_model_to_toml():
    """Load -> serialize -> reload -> assert equal."""
    import tomli_w

    spec1 = load_strategy_spec(FIXTURES / "valid_ma_crossover.toml")
    dumped = spec1.model_dump(mode="python")

    # Remove None values (TOML has no null)
    def clean_none(d):
        if isinstance(d, dict):
            return {k: clean_none(v) for k, v in d.items() if v is not None}
        if isinstance(d, list):
            return [clean_none(i) for i in d]
        return d

    cleaned = clean_none(dumped)
    toml_str = tomli_w.dumps(cleaned)
    raw2 = tomllib.loads(toml_str)
    spec2 = StrategySpecification.model_validate(raw2)

    assert spec1.metadata.name == spec2.metadata.name
    assert spec1.metadata.version == spec2.metadata.version
    assert spec1.exit_rules.stop_loss.value == spec2.exit_rules.stop_loss.value
    assert len(spec1.entry_rules.conditions) == len(spec2.entry_rules.conditions)
    assert (
        spec1.optimization_plan.objective_function
        == spec2.optimization_plan.objective_function
    )


# --- Model-level unit tests ---


def test_metadata_version_pattern_rejects_invalid():
    """Version must match vNNN pattern."""
    with pytest.raises(ValidationError, match="vNNN"):
        StrategyMetadata(
            name="test",
            version="1.0.0",
            pair="EURUSD",
            timeframe="H1",
            created_by="test",
        )


def test_entry_filter_session_validates_session_names():
    """Session filter rejects invalid session names."""
    with pytest.raises(ValidationError, match="Invalid session"):
        EntryFilter(type="session", params={"include": ["invalid_session"]})


def test_entry_filter_volatility_requires_indicator():
    """Volatility filter requires indicator param."""
    with pytest.raises(ValidationError, match="volatility filter requires 'indicator'"):
        EntryFilter(type="volatility", params={"period": 14})


def test_exit_trailing_chandelier_requires_params():
    """Chandelier trailing requires atr_period and atr_multiplier."""
    with pytest.raises(ValidationError, match="atr_period"):
        ExitTrailing(type="chandelier", params={"distance_pips": 20.0})


def test_position_sizing_risk_percent_bounds():
    """risk_percent must be 0.1-10.0."""
    with pytest.raises(ValidationError):
        PositionSizing(method="fixed_risk", risk_percent=0.01, max_lots=1.0)
    with pytest.raises(ValidationError):
        PositionSizing(method="fixed_risk", risk_percent=15.0, max_lots=1.0)


def test_search_parameter_categorical_needs_two_choices():
    """Categorical parameter must have at least 2 choices."""
    with pytest.raises(ValidationError, match="at least 2"):
        SearchParameter(type="categorical", choices=["only_one"])
