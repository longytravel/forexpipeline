"""Tests for Strategy Intent Capture (Story 2.4).

Covers: dialogue parsing, defaults resolution, spec generation,
versioned persistence, deterministic output, structured logging,
and end-to-end capture flow.
"""

from __future__ import annotations

import logging
import tomllib
from pathlib import Path
from unittest.mock import patch

import pytest

from strategy.defaults import apply_defaults
from strategy.dialogue_parser import (
    IntentCaptureError,
    normalize_pair,
    normalize_timeframe,
    parse_strategy_intent,
    resolve_indicator_type,
)
from strategy.hasher import compute_spec_hash
from strategy.intent_capture import CaptureResult, capture_strategy_intent
from strategy.spec_generator import generate_specification

# --- Test data paths ---
FIXTURES_DIR = Path(__file__).parent / "fixtures"
PROJECT_ROOT = Path(__file__).resolve().parents[4]
DEFAULTS_PATH = PROJECT_ROOT / "config" / "strategies" / "defaults.toml"


def _ma_crossover_input() -> dict:
    """Standard MA crossover structured input for tests."""
    return {
        "raw_description": "Try a moving average crossover on EURUSD H1, "
        "only during London session, with a chandelier exit",
        "pair": "EURUSD",
        "timeframe": "H1",
        "indicators": [
            {
                "type": "sma_crossover",
                "params": {"fast_period": 20, "slow_period": 50},
                "role": "signal",
            }
        ],
        "entry_conditions": ["SMA(20) crosses above SMA(50)"],
        "exit_rules": [
            {
                "type": "chandelier",
                "params": {"atr_period": 14, "atr_multiplier": 3.0},
            },
            {"type": "stop_loss", "params": {"sl_type": "atr_multiple", "value": 1.5}},
            {
                "type": "take_profit",
                "params": {"tp_type": "risk_reward", "value": 3.0},
            },
        ],
        "filters": [{"type": "session", "params": {"session": "london"}}],
        "position_sizing": {
            "method": "fixed_risk",
            "risk_percent": 1.0,
            "max_lots": 1.0,
        },
    }


def _minimal_input() -> dict:
    """Minimal structured input with only EMA indicator + entry logic."""
    return {
        "raw_description": "EMA crossover strategy",
        "indicators": [
            {
                "type": "ema_crossover",
                "params": {"fast_period": 12, "slow_period": 26},
                "role": "signal",
            }
        ],
        "entry_conditions": ["EMA(12) crosses above EMA(26)"],
    }


def _complex_input() -> dict:
    """Complex structured input: Bollinger + RSI + volatility filter + trailing."""
    return {
        "raw_description": "Bollinger breakout with RSI confirmation, "
        "volatility filter, trailing stop",
        "pair": "EURUSD",
        "timeframe": "H4",
        "indicators": [
            {
                "type": "bollinger_bands",
                "params": {"period": 20, "std_dev": 2.0},
                "role": "signal",
                "comparator": ">",
                "threshold": 0.0,
            },
            {
                "type": "rsi",
                "params": {"period": 14, "threshold": 70.0, "comparator": ">"},
                "role": "signal",
            },
        ],
        "entry_conditions": [
            "Price breaks above upper Bollinger Band",
            "RSI > 70 confirms momentum",
        ],
        "exit_rules": [
            {"type": "stop_loss", "params": {"sl_type": "atr_multiple", "value": 2.0}},
            {
                "type": "take_profit",
                "params": {"tp_type": "risk_reward", "value": 2.0},
            },
            {
                "type": "trailing_stop",
                "params": {"distance_pips": 50},
            },
        ],
        "filters": [
            {
                "type": "volatility",
                "params": {"indicator": "atr", "period": 14, "min_value": 0.001},
            }
        ],
    }


# ============================================================
# Task 4: Dialogue Parsing Tests
# ============================================================


class TestParseStrategyIntentMACrossover:
    """Test parsing a full MA crossover structured input."""

    def test_parse_strategy_intent_ma_crossover(self):
        intent = parse_strategy_intent(_ma_crossover_input())

        assert intent.pair == "EURUSD"
        assert intent.timeframe == "H1"
        assert len(intent.indicators) == 1
        assert intent.indicators[0].type == "sma_crossover"
        assert intent.indicators[0].params == {"fast_period": 20, "slow_period": 50}
        assert intent.indicators[0].role == "signal"
        assert len(intent.exit_rules) == 3
        assert len(intent.filters) == 1
        assert intent.filters[0].type == "session"
        assert intent.filters[0].params["include"] == ["london"]
        assert intent.position_sizing is not None
        assert intent.position_sizing.method == "fixed_risk"
        assert intent.field_provenance["pair"] == "operator"
        assert intent.field_provenance["timeframe"] == "operator"
        assert intent.field_provenance["indicators"] == "operator"


class TestParseStrategyIntentMinimal:
    """Test parsing minimal input — only indicator + entry logic."""

    def test_parse_strategy_intent_minimal_with_indicators(self):
        intent = parse_strategy_intent(_minimal_input())

        assert intent.pair is None
        assert intent.timeframe is None
        assert len(intent.indicators) == 1
        assert intent.indicators[0].type == "ema_crossover"
        assert intent.position_sizing is None
        assert len(intent.exit_rules) == 0
        assert intent.field_provenance["indicators"] == "operator"
        assert "pair" not in intent.field_provenance


class TestParseStrategyIntentComplex:
    """Test parsing complex structured input."""

    def test_parse_strategy_intent_complex(self):
        intent = parse_strategy_intent(_complex_input())

        assert intent.pair == "EURUSD"
        assert intent.timeframe == "H4"
        assert len(intent.indicators) == 2
        assert intent.indicators[0].type == "bollinger_bands"
        assert intent.indicators[1].type == "rsi"
        assert len(intent.exit_rules) == 3
        assert len(intent.filters) == 1
        assert intent.filters[0].type == "volatility"


class TestParseRejectsMissingIndicators:
    """Test that missing indicators raises IntentCaptureError."""

    def test_parse_rejects_missing_indicators(self):
        data = {
            "raw_description": "Some strategy without indicators",
            "pair": "EURUSD",
            "timeframe": "H1",
            "indicators": [],
        }
        with pytest.raises(IntentCaptureError, match="indicators"):
            parse_strategy_intent(data)


class TestParseRejectsMissingEntryLogic:
    """Test that missing entry logic raises IntentCaptureError."""

    def test_parse_rejects_missing_entry_logic(self):
        data = {
            "raw_description": "Strategy with filter-only indicators",
            "indicators": [
                {"type": "atr", "params": {"period": 14}, "role": "filter"}
            ],
            "entry_conditions": [],
        }
        with pytest.raises(IntentCaptureError, match="entry_logic"):
            parse_strategy_intent(data)


class TestParsePairNormalization:
    """Test pair format normalization."""

    def test_parse_pair_normalization(self):
        for pair_input in ["EUR_USD", "eur/usd", "EUR/USD", "eurusd", "Eur_Usd"]:
            assert normalize_pair(pair_input) == "EURUSD"


# ============================================================
# Task 5: Defaults Resolution Tests
# ============================================================


class TestApplyDefaultsFillsMissing:
    """Test that all non-identity defaults are applied."""

    def test_apply_defaults_fills_missing(self):
        intent = parse_strategy_intent(_minimal_input())
        result = apply_defaults(intent, defaults_path=DEFAULTS_PATH)

        assert result.pair == "EURUSD"
        assert result.timeframe == "H1"
        assert result.position_sizing is not None
        assert result.position_sizing.method == "fixed_risk"
        assert any(e.type == "stop_loss" for e in result.exit_rules)
        assert any(e.type == "take_profit" for e in result.exit_rules)
        assert result.field_provenance["pair"] == "default"
        assert result.field_provenance["timeframe"] == "default"
        assert result.field_provenance["position_sizing"] == "default"


class TestApplyDefaultsPreservesExplicit:
    """Test that operator-provided values are not overwritten."""

    def test_apply_defaults_preserves_explicit(self):
        intent = parse_strategy_intent(_ma_crossover_input())
        result = apply_defaults(intent, defaults_path=DEFAULTS_PATH)

        assert result.pair == "EURUSD"
        assert result.timeframe == "H1"
        assert result.position_sizing.method == "fixed_risk"
        assert result.field_provenance["pair"] == "operator"
        assert result.field_provenance["timeframe"] == "operator"
        assert result.field_provenance["position_sizing"] == "operator"


class TestProvenanceTracking:
    """Test field_provenance map correctness."""

    def test_provenance_tracking(self):
        intent = parse_strategy_intent(_minimal_input())
        result = apply_defaults(intent, defaults_path=DEFAULTS_PATH)

        # Operator-provided
        assert result.field_provenance["indicators"] == "operator"
        assert result.field_provenance["entry_conditions"] == "operator"

        # Defaulted
        assert result.field_provenance["pair"] == "default"
        assert result.field_provenance["timeframe"] == "default"
        assert result.field_provenance["position_sizing"] == "default"


class TestDefaultsLoadedFromToml:
    """Test that defaults come from config file, not hardcoded."""

    def test_defaults_loaded_from_toml(self):
        with open(DEFAULTS_PATH, "rb") as f:
            raw = tomllib.load(f)

        defaults = raw["defaults"]
        assert defaults["pair"]["value"] == "EURUSD"
        assert defaults["timeframe"]["value"] == "H1"
        assert defaults["position_sizing"]["method"] == "fixed_risk"
        assert defaults["exits"]["stop_loss"]["type"] == "atr_multiple"
        assert defaults["exits"]["take_profit"]["type"] == "risk_reward"

        # Verify apply_defaults actually uses these TOML values (not hardcoded)
        intent = parse_strategy_intent(_minimal_input())
        result = apply_defaults(intent, defaults_path=DEFAULTS_PATH)

        assert result.pair == defaults["pair"]["value"]
        assert result.timeframe == defaults["timeframe"]["value"]
        assert result.position_sizing.method == defaults["position_sizing"]["method"]
        assert result.position_sizing.params["risk_percent"] == defaults["position_sizing"]["risk_percent"]
        assert result.position_sizing.params["max_lots"] == defaults["position_sizing"]["max_lots"]


# ============================================================
# Task 6: Specification Generator Tests
# ============================================================


class TestGenerateSpecificationSchemaValid:
    """Test that generated spec passes schema validation."""

    def test_generate_specification_schema_valid(self):
        from strategy.loader import validate_strategy_spec

        intent = parse_strategy_intent(_ma_crossover_input())
        intent = apply_defaults(intent, defaults_path=DEFAULTS_PATH)
        spec = generate_specification(intent)

        # Verify metadata fields
        assert spec.metadata.name == "sma-crossover-eurusd-h1"
        assert spec.metadata.version == "v001"
        assert spec.metadata.pair == "EURUSD"
        assert spec.metadata.timeframe == "H1"
        assert spec.metadata.created_by == "intent_capture"
        assert spec.metadata.status == "draft"

        # Explicitly call Story 2.3 schema validation (AC5)
        errors = validate_strategy_spec(spec)
        assert errors == [], f"Schema validation failed: {errors}"


class TestGenerateSpecificationIndicatorMapping:
    """Test that indicators map to correct schema constructs."""

    def test_generate_specification_indicator_mapping(self):
        intent = parse_strategy_intent(_ma_crossover_input())
        intent = apply_defaults(intent, defaults_path=DEFAULTS_PATH)
        spec = generate_specification(intent)

        assert len(spec.entry_rules.conditions) == 1
        cond = spec.entry_rules.conditions[0]
        assert cond.indicator == "sma_crossover"
        assert cond.parameters == {"fast_period": 20, "slow_period": 50}
        assert cond.comparator == "crosses_above"
        assert cond.threshold == 0.0


class TestGenerateSpecificationExitMapping:
    """Test that exit types map correctly."""

    def test_generate_specification_exit_mapping(self):
        intent = parse_strategy_intent(_ma_crossover_input())
        intent = apply_defaults(intent, defaults_path=DEFAULTS_PATH)
        spec = generate_specification(intent)

        assert spec.exit_rules.stop_loss.type == "atr_multiple"
        assert spec.exit_rules.stop_loss.value == 1.5
        assert spec.exit_rules.take_profit.type == "risk_reward"
        assert spec.exit_rules.take_profit.value == 3.0
        assert spec.exit_rules.trailing is not None
        assert spec.exit_rules.trailing.type == "chandelier"


class TestGenerateSpecificationFilterMapping:
    """Test that session/volatility filters map correctly."""

    def test_generate_specification_filter_mapping(self):
        intent = parse_strategy_intent(_ma_crossover_input())
        intent = apply_defaults(intent, defaults_path=DEFAULTS_PATH)
        spec = generate_specification(intent)

        assert len(spec.entry_rules.filters) == 1
        filt = spec.entry_rules.filters[0]
        assert filt.type == "session"
        assert filt.params["include"] == ["london"]


class TestGenerateSpecificationNoOptimizationPlan:
    """Test that optimization_plan is None (not auto-populated)."""

    def test_generate_specification_no_optimization_plan(self):
        intent = parse_strategy_intent(_ma_crossover_input())
        intent = apply_defaults(intent, defaults_path=DEFAULTS_PATH)
        spec = generate_specification(intent)

        assert spec.optimization_plan is None


class TestGenerateSpecificationNoCostModel:
    """Test that cost_model_reference is None (populated later)."""

    def test_generate_specification_no_cost_model(self):
        intent = parse_strategy_intent(_ma_crossover_input())
        intent = apply_defaults(intent, defaults_path=DEFAULTS_PATH)
        spec = generate_specification(intent)

        assert spec.cost_model_reference is None


# ============================================================
# Task 7: Versioned Artifact Persistence Tests
# ============================================================


class TestSaveSpecificationVersioned:
    """Test versioned directory structure and crash-safe write."""

    def test_save_specification_versioned(self, tmp_path):
        intent = parse_strategy_intent(_ma_crossover_input())
        intent = apply_defaults(intent, defaults_path=DEFAULTS_PATH)
        spec = generate_specification(intent)

        from strategy.storage import save_strategy_spec

        strategy_dir = tmp_path / spec.metadata.name
        saved_path = save_strategy_spec(spec, strategy_dir)

        assert saved_path.exists()
        assert saved_path.name == "v001.toml"
        assert saved_path.parent == strategy_dir

        # Verify TOML is valid and loadable
        with open(saved_path, "rb") as f:
            raw = tomllib.load(f)
        assert raw["metadata"]["name"] == spec.metadata.name
        assert raw["metadata"]["version"] == "v001"


class TestSaveSpecificationSpecHashEmbedded:
    """Test that spec_hash is present in saved artifact."""

    def test_save_specification_spec_hash_embedded(self, tmp_path):
        intent = parse_strategy_intent(_ma_crossover_input())
        intent = apply_defaults(intent, defaults_path=DEFAULTS_PATH)
        spec = generate_specification(intent)
        spec_hash = compute_spec_hash(spec)

        assert isinstance(spec_hash, str)
        assert len(spec_hash) == 64  # SHA-256 hex digest

        # Save and read back to verify hash can be recomputed from saved artifact
        from strategy.storage import save_strategy_spec

        strategy_dir = tmp_path / spec.metadata.name
        saved_path = save_strategy_spec(spec, strategy_dir)
        assert saved_path.exists()

        # Load back and recompute hash — should match
        with open(saved_path, "rb") as f:
            raw = tomllib.load(f)
        from strategy.specification import StrategySpecification

        loaded_spec = StrategySpecification.model_validate(raw)
        loaded_hash = compute_spec_hash(loaded_spec)
        assert loaded_hash == spec_hash


# ============================================================
# Task 9: Deterministic Output Test
# ============================================================


class TestDeterministicOutput:
    """Test that same input + config produces identical spec."""

    def test_deterministic_output(self):
        input_data = _ma_crossover_input()

        intent1 = parse_strategy_intent(input_data)
        intent1 = apply_defaults(intent1, defaults_path=DEFAULTS_PATH)
        spec1 = generate_specification(intent1)
        hash1 = compute_spec_hash(spec1)

        intent2 = parse_strategy_intent(input_data)
        intent2 = apply_defaults(intent2, defaults_path=DEFAULTS_PATH)
        spec2 = generate_specification(intent2)
        hash2 = compute_spec_hash(spec2)

        assert hash1 == hash2
        assert spec1.model_dump() == spec2.model_dump()


# ============================================================
# Task 8: Structured Logging Tests
# ============================================================


class TestLoggingIntentCaptureEvents:
    """Test all 4 structured log events are emitted with correct ctx fields."""

    def test_logging_intent_capture_events(self, tmp_path, caplog):
        with caplog.at_level(logging.INFO):
            result = capture_strategy_intent(
                _ma_crossover_input(),
                artifacts_dir=tmp_path,
                defaults_path=DEFAULTS_PATH,
            )

        log_messages = [r.message for r in caplog.records]
        assert any("Intent capture started" in m for m in log_messages)
        assert any("Specification generated" in m for m in log_messages)
        assert any("Specification validated" in m for m in log_messages)
        assert any("Specification saved" in m for m in log_messages)

        # Verify structured ctx fields are present in log records (D6)
        ctx_records = {
            r.ctx.get("event"): r.ctx
            for r in caplog.records
            if hasattr(r, "ctx") and isinstance(r.ctx, dict) and "event" in r.ctx
        }
        assert "intent_capture_start" in ctx_records
        assert "operator_input_summary" in ctx_records["intent_capture_start"]

        assert "spec_generated" in ctx_records
        assert "spec_version" in ctx_records["spec_generated"]
        assert "strategy_name" in ctx_records["spec_generated"]
        assert "fields_defaulted" in ctx_records["spec_generated"]

        assert "spec_validated" in ctx_records
        assert "valid" in ctx_records["spec_validated"]
        assert "spec_hash" in ctx_records["spec_validated"]

        assert "spec_saved" in ctx_records
        assert "path" in ctx_records["spec_saved"]
        assert "version" in ctx_records["spec_saved"]


# ============================================================
# Task 9: End-to-End Orchestrator Tests
# ============================================================


class TestEndToEndCaptureStrategyIntent:
    """Full flow: structured dict -> saved, validated draft artifact."""

    def test_end_to_end_capture_strategy_intent(self, tmp_path):
        result = capture_strategy_intent(
            _ma_crossover_input(),
            artifacts_dir=tmp_path,
            defaults_path=DEFAULTS_PATH,
        )

        assert isinstance(result, CaptureResult)
        assert result.saved_path.exists()
        assert result.version == "v001"
        assert isinstance(result.spec_hash, str)
        assert len(result.spec_hash) == 64
        assert result.field_provenance["pair"] == "operator"
        assert result.spec.metadata.status == "draft"
        assert result.spec.optimization_plan is None
        assert result.spec.cost_model_reference is None

        # Verify saved TOML is loadable
        with open(result.saved_path, "rb") as f:
            raw = tomllib.load(f)
        assert raw["metadata"]["name"] == "sma-crossover-eurusd-h1"
        assert raw["metadata"]["status"] == "draft"


# ============================================================
# Regression Tests (Review Synthesis)
# ============================================================


class TestRegressionHardcodedDefaults:
    """Regression: defaults.py must fail-loud on missing TOML keys, not use
    hardcoded fallbacks (C1/C2 — D7 violation)."""

    @pytest.mark.regression
    def test_defaults_fail_on_missing_toml_key(self, tmp_path):
        """If a required key is missing from defaults.toml, apply_defaults
        must raise KeyError, not silently use a hardcoded value."""
        broken_toml = tmp_path / "broken_defaults.toml"
        broken_toml.write_text('[defaults.pair]\nvalue = "GBPUSD"\n')

        intent = parse_strategy_intent(_minimal_input())
        with pytest.raises(KeyError):
            apply_defaults(intent, defaults_path=broken_toml)

    @pytest.mark.regression
    def test_spec_generator_fail_on_missing_params(self):
        """spec_generator must fail-loud on missing exit/sizing params,
        not use hardcoded fallbacks."""
        from strategy.dialogue_parser import ExitIntent, PositionSizingIntent

        intent = parse_strategy_intent(_minimal_input())
        intent = apply_defaults(intent, defaults_path=DEFAULTS_PATH)

        # Corrupt the exit rule to remove 'value' key
        corrupted_exit = ExitIntent(type="stop_loss", params={"sl_type": "atr_multiple"})
        intent.exit_rules = [
            corrupted_exit if e.type == "stop_loss" else e for e in intent.exit_rules
        ]
        with pytest.raises(KeyError):
            generate_specification(intent)


class TestRegressionCliEntrypoint:
    """Regression: intent_capture.py must have a __main__ block (H1)."""

    @pytest.mark.regression
    def test_main_block_exists(self):
        """Verify __main__ block exists in intent_capture module."""
        import inspect
        import strategy.intent_capture as mod

        source = inspect.getsource(mod)
        assert 'if __name__ == "__main__"' in source


class TestRegressionStructuredLogging:
    """Regression: log records must carry structured ctx fields (H4/Codex-H3)."""

    @pytest.mark.regression
    def test_log_ctx_fields_not_lost(self, tmp_path, caplog):
        """Structured event data must appear in log record ctx, not as
        top-level extra keys that the JsonFormatter ignores."""
        with caplog.at_level(logging.INFO):
            capture_strategy_intent(
                _ma_crossover_input(),
                artifacts_dir=tmp_path,
                defaults_path=DEFAULTS_PATH,
            )

        # At least one record should have ctx with an event key
        records_with_ctx = [
            r for r in caplog.records
            if hasattr(r, "ctx") and isinstance(r.ctx, dict) and "event" in r.ctx
        ]
        assert len(records_with_ctx) >= 4, (
            "Expected 4 log records with ctx.event, got "
            f"{len(records_with_ctx)}"
        )


class TestRegressionAliasRegistry:
    """Regression: indicator aliases must resolve to actual registry keys
    (Codex-M3)."""

    @pytest.mark.regression
    def test_keltner_alias_matches_registry(self):
        assert resolve_indicator_type("keltner") == "keltner_channel"

    @pytest.mark.regression
    def test_donchian_alias_matches_registry(self):
        assert resolve_indicator_type("donchian channel") == "donchian_channel"


class TestRegressionTimeframeValidation:
    """Regression: unknown timeframes must be rejected (M1)."""

    @pytest.mark.regression
    def test_unknown_timeframe_raises_error(self):
        with pytest.raises(IntentCaptureError, match="Unknown timeframe"):
            normalize_timeframe("3h")

    @pytest.mark.regression
    def test_valid_timeframe_passes(self):
        assert normalize_timeframe("H1") == "H1"
        assert normalize_timeframe("4 hour") == "H4"


class TestRegressionSchemaValidationCalled:
    """Regression: generated spec must be validated via validate_strategy_spec
    (H2)."""

    @pytest.mark.regression
    def test_validate_called_on_generation(self):
        """generate_specification must call validate_strategy_spec internally.
        If validation fails, it raises ValueError."""
        from strategy.loader import validate_strategy_spec

        intent = parse_strategy_intent(_ma_crossover_input())
        intent = apply_defaults(intent, defaults_path=DEFAULTS_PATH)
        spec = generate_specification(intent)

        errors = validate_strategy_spec(spec)
        assert errors == []


class TestRegressionSpecHashInArtifact:
    """Regression: spec_hash must be verifiable from saved artifact (C3)."""

    @pytest.mark.regression
    def test_spec_hash_roundtrip(self, tmp_path):
        """Save spec, load it back, recompute hash — must match."""
        from strategy.specification import StrategySpecification
        from strategy.storage import save_strategy_spec

        intent = parse_strategy_intent(_ma_crossover_input())
        intent = apply_defaults(intent, defaults_path=DEFAULTS_PATH)
        spec = generate_specification(intent)
        original_hash = compute_spec_hash(spec)

        strategy_dir = tmp_path / spec.metadata.name
        saved_path = save_strategy_spec(spec, strategy_dir)

        with open(saved_path, "rb") as f:
            loaded = StrategySpecification.model_validate(tomllib.load(f))
        assert compute_spec_hash(loaded) == original_hash


class TestRegressionDefaultsVsToml:
    """Regression: apply_defaults runtime values must match TOML config (M6)."""

    @pytest.mark.regression
    def test_runtime_defaults_match_toml(self):
        """Ensure apply_defaults produces values from TOML, not from any
        residual hardcoded Python constants."""
        with open(DEFAULTS_PATH, "rb") as f:
            raw = tomllib.load(f)["defaults"]

        intent = parse_strategy_intent(_minimal_input())
        result = apply_defaults(intent, defaults_path=DEFAULTS_PATH)

        assert result.pair == raw["pair"]["value"]
        assert result.timeframe == raw["timeframe"]["value"]
        assert result.position_sizing.method == raw["position_sizing"]["method"]


# ============================================================
# Live Integration Tests
# ============================================================


@pytest.mark.live
class TestLiveFullIntentCapture:
    """Live test: full intent capture pipeline with real file I/O."""

    def test_live_full_validation(self, tmp_path):
        """Full pipeline from structured input to validated artifact on disk."""
        result = capture_strategy_intent(
            _ma_crossover_input(),
            artifacts_dir=tmp_path,
            defaults_path=DEFAULTS_PATH,
        )

        # Verify actual file exists on disk
        assert result.saved_path.exists()
        assert result.saved_path.stat().st_size > 0

        # Load and validate the saved TOML
        with open(result.saved_path, "rb") as f:
            raw = tomllib.load(f)

        # Validate content correctness
        assert raw["metadata"]["name"] == "sma-crossover-eurusd-h1"
        assert raw["metadata"]["version"] == "v001"
        assert raw["metadata"]["pair"] == "EURUSD"
        assert raw["metadata"]["timeframe"] == "H1"
        assert raw["metadata"]["created_by"] == "intent_capture"
        assert raw["metadata"]["status"] == "draft"
        assert len(raw["entry_rules"]["conditions"]) == 1
        assert raw["entry_rules"]["conditions"][0]["indicator"] == "sma_crossover"
        assert raw["exit_rules"]["stop_loss"]["type"] == "atr_multiple"
        assert "optimization_plan" not in raw
        assert "cost_model_reference" not in raw

    def test_live_minimal_input_with_defaults(self, tmp_path):
        """Minimal input produces valid spec with all defaults applied."""
        result = capture_strategy_intent(
            _minimal_input(),
            artifacts_dir=tmp_path,
            defaults_path=DEFAULTS_PATH,
        )

        assert result.saved_path.exists()

        with open(result.saved_path, "rb") as f:
            raw = tomllib.load(f)

        # Verify defaults were applied
        assert raw["metadata"]["pair"] == "EURUSD"
        assert raw["metadata"]["timeframe"] == "H1"
        assert raw["exit_rules"]["stop_loss"]["type"] == "atr_multiple"
        assert raw["exit_rules"]["take_profit"]["type"] == "risk_reward"
        assert raw["position_sizing"]["method"] == "fixed_risk"

        # Verify provenance tracking
        assert result.field_provenance["pair"] == "default"
        assert result.field_provenance["timeframe"] == "default"
        assert result.field_provenance["indicators"] == "operator"

    def test_live_deterministic_output(self, tmp_path):
        """Same input produces identical spec hashes."""
        result1 = capture_strategy_intent(
            _ma_crossover_input(),
            artifacts_dir=tmp_path / "run1",
            defaults_path=DEFAULTS_PATH,
        )
        result2 = capture_strategy_intent(
            _ma_crossover_input(),
            artifacts_dir=tmp_path / "run2",
            defaults_path=DEFAULTS_PATH,
        )

        assert result1.spec_hash == result2.spec_hash

        # Both files exist and contain valid TOML
        assert result1.saved_path.exists()
        assert result2.saved_path.exists()
