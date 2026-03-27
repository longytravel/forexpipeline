"""Tests for session management module (Story 2.6)."""

from __future__ import annotations

from pathlib import Path

import pytest

from cost_model.sessions import (
    SESSION_NAMES,
    get_session_for_time,
    load_session_definitions,
    validate_config_matches_boundaries,
    validate_session_coverage,
)

_CONFIG_PATH = Path(__file__).resolve().parents[4] / "config" / "base.toml"


class TestLoadSessionDefinitions:
    def test_load_session_definitions(self):
        """Loads all 5 sessions from config/base.toml."""
        defs = load_session_definitions(_CONFIG_PATH)
        assert len(defs) == 5
        for name in SESSION_NAMES:
            assert name in defs
            assert "start_utc" in defs[name]
            assert "end_utc" in defs[name]

    def test_session_boundaries_match_architecture(self):
        """Session boundaries match architecture spec."""
        defs = load_session_definitions(_CONFIG_PATH)
        assert defs["asian"]["start_utc"] == 0
        assert defs["asian"]["end_utc"] == 8
        assert defs["london"]["start_utc"] == 8
        assert defs["london_ny_overlap"]["start_utc"] == 13
        assert defs["london_ny_overlap"]["end_utc"] == 16
        assert defs["new_york"]["start_utc"] == 13  # market presence
        assert defs["off_hours"]["start_utc"] == 21

    def test_all_required_sessions_present(self):
        """5 sessions defined in config."""
        defs = load_session_definitions(_CONFIG_PATH)
        assert set(defs.keys()) == set(SESSION_NAMES)

    def test_missing_config_raises(self, tmp_path):
        """Missing config file raises FileNotFoundError."""
        with pytest.raises(FileNotFoundError):
            load_session_definitions(tmp_path / "nonexistent.toml")


class TestValidateSessionCoverage:
    def test_session_coverage_complete(self):
        """All 24 hours covered by label boundaries."""
        defs = load_session_definitions(_CONFIG_PATH)
        errors = validate_session_coverage(defs)
        assert errors == []

    def test_session_coverage_gaps_detected(self):
        """Missing session flagged."""
        incomplete = {
            "asian": {"start_utc": 0, "end_utc": 8},
            "london": {"start_utc": 8, "end_utc": 16},
            # missing london_ny_overlap, new_york, off_hours
        }
        errors = validate_session_coverage(incomplete)
        assert any("Missing required session" in e for e in errors)


class TestGetSessionForTime:
    @pytest.mark.parametrize("hour,expected", [
        (0, "asian"),
        (3, "asian"),
        (7, "asian"),
        (8, "london"),
        (10, "london"),
        (12, "london"),
        (13, "london_ny_overlap"),
        (14, "london_ny_overlap"),
        (15, "london_ny_overlap"),
        (16, "new_york"),
        (18, "new_york"),
        (20, "new_york"),
        (21, "off_hours"),
        (22, "off_hours"),
        (23, "off_hours"),
    ])
    def test_get_session_for_time(self, hour, expected):
        """Correct session label for various UTC hours."""
        assert get_session_for_time(hour) == expected

    def test_get_session_overlap_priority(self):
        """14:00 UTC returns 'london_ny_overlap', not 'london' or 'new_york'."""
        assert get_session_for_time(14) == "london_ny_overlap"

    def test_get_session_boundary_at_13(self):
        """13:00 UTC is overlap start, not london."""
        assert get_session_for_time(13) == "london_ny_overlap"

    def test_get_session_boundary_at_16(self):
        """16:00 UTC is new_york start, not overlap."""
        assert get_session_for_time(16) == "new_york"

    def test_invalid_hour_raises(self):
        """Out-of-range hour raises ValueError."""
        with pytest.raises(ValueError, match="hour_utc must be 0-23"):
            get_session_for_time(24)
        with pytest.raises(ValueError, match="hour_utc must be 0-23"):
            get_session_for_time(-1)

    def test_all_24_hours_covered(self):
        """Every hour 0-23 maps to a valid session."""
        for h in range(24):
            result = get_session_for_time(h)
            assert result in SESSION_NAMES


class TestRegressions:
    @pytest.mark.regression
    def test_config_matches_hardcoded_boundaries(self):
        """Regression: config/base.toml boundaries must match hardcoded _LABEL_BOUNDARIES."""
        # Should not raise
        validate_config_matches_boundaries(_CONFIG_PATH)

    @pytest.mark.regression
    def test_get_session_for_time_no_unused_param(self):
        """Regression: get_session_for_time no longer accepts misleading session_defs param."""
        import inspect
        sig = inspect.signature(get_session_for_time)
        assert "session_defs" not in sig.parameters
