"""Tests for cost model schema definitions and validation (Story 2.6)."""

from __future__ import annotations

from pathlib import Path

import pytest

from cost_model.schema import (
    REQUIRED_SESSIONS,
    VALID_SOURCES,
    CostModelArtifact,
    SessionProfile,
    load_schema,
    validate_cost_model,
)

# Path to contract schema relative to project root
_SCHEMA_PATH = Path(__file__).resolve().parents[4] / "contracts" / "cost_model_schema.toml"


def _make_valid_sessions() -> dict[str, SessionProfile]:
    return {
        "asian": SessionProfile(1.2, 0.4, 0.1, 0.05),
        "london": SessionProfile(0.8, 0.3, 0.05, 0.03),
        "london_ny_overlap": SessionProfile(0.6, 0.2, 0.03, 0.02),
        "new_york": SessionProfile(0.9, 0.3, 0.06, 0.03),
        "off_hours": SessionProfile(1.5, 0.6, 0.15, 0.08),
    }


def _make_valid_artifact() -> CostModelArtifact:
    return CostModelArtifact(
        pair="EURUSD",
        version="v001",
        source="research",
        calibrated_at="2026-03-15T00:00:00Z",
        sessions=_make_valid_sessions(),
        metadata={"description": "test", "data_points": None, "confidence_level": "research_estimate"},
    )


class TestSessionProfile:
    def test_session_profile_creation(self):
        """Valid SessionProfile creation with all required fields."""
        sp = SessionProfile(
            mean_spread_pips=1.2,
            std_spread=0.4,
            mean_slippage_pips=0.1,
            std_slippage=0.05,
        )
        assert sp.mean_spread_pips == 1.2
        assert sp.std_spread == 0.4
        assert sp.mean_slippage_pips == 0.1
        assert sp.std_slippage == 0.05

    def test_session_profile_to_dict(self):
        sp = SessionProfile(1.2, 0.4, 0.1, 0.05)
        d = sp.to_dict()
        assert d == {
            "mean_spread_pips": 1.2,
            "std_spread": 0.4,
            "mean_slippage_pips": 0.1,
            "std_slippage": 0.05,
        }

    def test_session_profile_negative_values_rejected(self):
        """Validation catches negative spread/slippage values."""
        artifact = _make_valid_artifact()
        artifact.sessions["asian"] = SessionProfile(-0.5, 0.4, 0.1, 0.05)
        errors = validate_cost_model(artifact, _SCHEMA_PATH)
        assert any("must be >= 0" in e for e in errors)


class TestCostModelArtifact:
    def test_cost_model_artifact_creation(self):
        """Valid CostModelArtifact with all required fields."""
        artifact = _make_valid_artifact()
        assert artifact.pair == "EURUSD"
        assert artifact.version == "v001"
        assert artifact.source == "research"
        assert len(artifact.sessions) == 5

    def test_cost_model_to_dict_roundtrip(self):
        artifact = _make_valid_artifact()
        d = artifact.to_dict()
        restored = CostModelArtifact.from_dict(d)
        assert restored.pair == artifact.pair
        assert restored.version == artifact.version
        assert restored.sessions["asian"].mean_spread_pips == 1.2

    def test_cost_model_missing_session_rejected(self):
        """Validation catches missing required sessions."""
        sessions = _make_valid_sessions()
        del sessions["off_hours"]
        artifact = CostModelArtifact(
            pair="EURUSD", version="v001", source="research",
            calibrated_at="2026-03-15T00:00:00Z", sessions=sessions,
        )
        errors = validate_cost_model(artifact, _SCHEMA_PATH)
        assert any("Missing required session: off_hours" in e for e in errors)

    def test_cost_model_invalid_source_rejected(self):
        """Validation catches invalid source enum."""
        artifact = _make_valid_artifact()
        artifact.source = "invalid_source"
        errors = validate_cost_model(artifact, _SCHEMA_PATH)
        assert any("Invalid source" in e for e in errors)

    def test_cost_model_invalid_version_rejected(self):
        """Validation catches invalid version format."""
        artifact = _make_valid_artifact()
        artifact.version = "1.0"
        errors = validate_cost_model(artifact, _SCHEMA_PATH)
        assert any("Invalid version format" in e for e in errors)

    def test_cost_model_version_supports_4plus_digits(self):
        """Version v1000+ should be valid (lesson from Story 2.5)."""
        artifact = _make_valid_artifact()
        artifact.version = "v1000"
        errors = validate_cost_model(artifact, _SCHEMA_PATH)
        assert not any("Invalid version" in e for e in errors)


class TestSchemaLoading:
    def test_schema_loading(self):
        """contracts/cost_model_schema.toml loads correctly."""
        schema = load_schema(_SCHEMA_PATH)
        assert "artifact" in schema
        assert "session_profile" in schema
        assert "required" in schema["artifact"]

    def test_validate_cost_model_valid(self):
        """Valid artifact passes validation."""
        artifact = _make_valid_artifact()
        errors = validate_cost_model(artifact, _SCHEMA_PATH)
        assert errors == []

    def test_validate_cost_model_invalid(self):
        """Invalid artifact returns errors list."""
        artifact = CostModelArtifact(
            pair="EURUSD", version="bad", source="invalid",
            calibrated_at="2026-01-01", sessions={},
        )
        errors = validate_cost_model(artifact, _SCHEMA_PATH)
        assert len(errors) >= 3  # version, source, missing sessions


class TestConstants:
    def test_valid_sources(self):
        assert VALID_SOURCES == ("research", "tick_analysis", "live_calibration")

    def test_required_sessions(self):
        assert len(REQUIRED_SESSIONS) == 5
        assert "london_ny_overlap" in REQUIRED_SESSIONS


class TestRegressions:
    @pytest.mark.regression
    def test_calibrated_at_invalid_rejected(self):
        """Regression: malformed calibrated_at must be rejected (review synthesis fix)."""
        artifact = _make_valid_artifact()
        artifact.calibrated_at = "not-a-date"
        errors = validate_cost_model(artifact, _SCHEMA_PATH)
        assert any("calibrated_at" in e.lower() or "Invalid calibrated_at" in e for e in errors)

    @pytest.mark.regression
    def test_calibrated_at_valid_iso8601_passes(self):
        """Regression: valid ISO 8601 UTC calibrated_at passes validation."""
        artifact = _make_valid_artifact()
        artifact.calibrated_at = "2026-03-15T12:00:00Z"
        errors = validate_cost_model(artifact, _SCHEMA_PATH)
        assert not any("calibrated_at" in e for e in errors)

    @pytest.mark.regression
    def test_calibrated_at_non_utc_rejected(self):
        """Regression: non-UTC calibrated_at must be rejected."""
        artifact = _make_valid_artifact()
        artifact.calibrated_at = "2026-03-15T12:00:00+05:00"
        errors = validate_cost_model(artifact, _SCHEMA_PATH)
        assert any("UTC" in e for e in errors)

    @pytest.mark.regression
    def test_from_dict_with_optional_fields(self):
        """Regression: from_dict must tolerate optional fields in session data."""
        data = _make_valid_artifact().to_dict()
        # Add optional fields that the schema contract allows
        data["sessions"]["asian"]["description"] = "Asian session"
        data["sessions"]["asian"]["data_points"] = 1000
        data["sessions"]["asian"]["confidence_level"] = "high"
        # Should not raise — optional fields are filtered out
        artifact = CostModelArtifact.from_dict(data)
        assert artifact.sessions["asian"].mean_spread_pips == 1.2
