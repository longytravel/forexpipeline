"""Tests for cost model builder (Story 2.6)."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from unittest.mock import patch

import pytest

from cost_model.builder import CostModelBuilder, _EURUSD_DEFAULTS
from cost_model.schema import REQUIRED_SESSIONS, CostModelArtifact, validate_cost_model

_PROJECT_ROOT = Path(__file__).resolve().parents[4]
_CONFIG_PATH = _PROJECT_ROOT / "config" / "base.toml"
_CONTRACTS_PATH = _PROJECT_ROOT / "contracts"
_SCHEMA_PATH = _CONTRACTS_PATH / "cost_model_schema.toml"


@pytest.fixture
def builder(tmp_path):
    """CostModelBuilder with temporary artifacts directory."""
    return CostModelBuilder(
        config_path=_CONFIG_PATH,
        contracts_path=_CONTRACTS_PATH,
        artifacts_dir=tmp_path,
    )


class TestFromResearchData:
    def test_from_research_data_valid(self, builder):
        """Creates valid artifact from research data dict."""
        artifact = builder.from_research_data("EURUSD", _EURUSD_DEFAULTS)
        assert artifact.pair == "EURUSD"
        assert artifact.source == "research"
        assert artifact.version == "v001"
        assert len(artifact.sessions) == 5

    def test_from_research_data_missing_session(self, builder):
        """Fails with clear error when required session is missing."""
        incomplete = dict(_EURUSD_DEFAULTS)
        del incomplete["off_hours"]
        with pytest.raises(ValueError, match="missing required sessions"):
            builder.from_research_data("EURUSD", incomplete)

    def test_from_research_data_validates_output(self, builder):
        """Schema validation runs before return."""
        artifact = builder.from_research_data("EURUSD", _EURUSD_DEFAULTS)
        errors = validate_cost_model(artifact, _SCHEMA_PATH)
        assert errors == []


class TestFromTickData:
    def test_from_tick_data_valid(self, builder, tmp_path):
        """Creates artifact from tick data Parquet file."""
        try:
            import pyarrow as pa
            import pyarrow.parquet as pq
        except ImportError:
            pytest.skip("pyarrow not available")

        # Create test tick data
        tick_dir = tmp_path / "tick_data"
        tick_dir.mkdir()

        import random
        random.seed(42)
        n_rows = 100
        timestamps = [
            f"2026-01-15T{h:02d}:00:00Z"
            for h in range(24)
            for _ in range(n_rows // 24 + 1)
        ][:n_rows]

        bid_opens = [1.08000 + random.uniform(-0.001, 0.001) for _ in range(n_rows)]
        ask_opens = [b + random.uniform(0.00005, 0.0002) for b in bid_opens]

        table = pa.table({
            "timestamp": pa.array([
                __import__("datetime").datetime.fromisoformat(t.replace("Z", "+00:00"))
                for t in timestamps
            ], type=pa.timestamp("us", tz="UTC")),
            "bid_open": pa.array(bid_opens, type=pa.float64()),
            "bid_close": pa.array(bid_opens, type=pa.float64()),
            "ask_open": pa.array(ask_opens, type=pa.float64()),
            "ask_close": pa.array(ask_opens, type=pa.float64()),
        })
        pq.write_table(table, str(tick_dir / "test.parquet"))

        artifact = builder.from_tick_data("EURUSD", tick_dir)
        assert artifact.pair == "EURUSD"
        assert artifact.source == "tick_analysis"
        assert len(artifact.sessions) == 5
        assert artifact.metadata.get("slippage_source") == "research_estimate"
        assert artifact.metadata.get("data_points") == n_rows

    def test_from_tick_data_missing_path(self, builder, tmp_path):
        """Raises FileNotFoundError for missing tick data path."""
        with pytest.raises(FileNotFoundError, match="Tick data path not found"):
            builder.from_tick_data("EURUSD", tmp_path / "nonexistent")

    def test_from_tick_data_no_parquet(self, builder, tmp_path):
        """Raises FileNotFoundError when no .parquet files found."""
        empty_dir = tmp_path / "empty_ticks"
        empty_dir.mkdir()
        with pytest.raises(FileNotFoundError, match="No .parquet files"):
            builder.from_tick_data("EURUSD", empty_dir)


class TestFromLiveCalibration:
    def test_from_live_calibration_raises(self, builder):
        """NotImplementedError with Epic 7 message."""
        with pytest.raises(NotImplementedError, match="Epic 7"):
            builder.from_live_calibration("EURUSD", {})


class TestBuildDefaultEurusd:
    def test_build_default_eurusd(self, builder):
        """Creates valid EURUSD with all 5 sessions."""
        artifact = builder.build_default_eurusd()
        assert artifact.pair == "EURUSD"
        assert artifact.source == "research"
        assert len(artifact.sessions) == 5
        for name in REQUIRED_SESSIONS:
            assert name in artifact.sessions

    def test_default_eurusd_spread_ordering(self, builder):
        """Overlap has tightest spread, off-hours has widest."""
        artifact = builder.build_default_eurusd()
        overlap = artifact.sessions["london_ny_overlap"].mean_spread_pips
        off_hours = artifact.sessions["off_hours"].mean_spread_pips
        assert overlap < off_hours

    def test_default_values_match_spec(self, builder):
        """Default values match the story specification."""
        artifact = builder.build_default_eurusd()
        assert artifact.sessions["asian"].mean_spread_pips == 1.2
        assert artifact.sessions["london"].mean_spread_pips == 0.8
        assert artifact.sessions["london_ny_overlap"].mean_spread_pips == 0.6
        assert artifact.sessions["new_york"].mean_spread_pips == 0.9
        assert artifact.sessions["off_hours"].mean_spread_pips == 1.5


class TestBuilderLogging:
    def test_builder_logs_events(self, builder, caplog):
        """Structured log events emitted during build."""
        with caplog.at_level(logging.INFO):
            builder.build_default_eurusd()
        # Check that build events were logged
        messages = [r.message for r in caplog.records]
        assert "cost_model_build_start" in messages
        assert "cost_model_build_complete" in messages
        assert "cost_model_validated" in messages


class TestRegressions:
    @pytest.mark.regression
    def test_pip_multiplier_jpy_pair(self):
        """Regression: JPY pairs must use 100 multiplier, not 10000."""
        from cost_model.builder import _pip_multiplier
        assert _pip_multiplier("USDJPY") == 100
        assert _pip_multiplier("EURJPY") == 100
        assert _pip_multiplier("EURUSD") == 10000
        assert _pip_multiplier("GBPUSD") == 10000

    @pytest.mark.regression
    def test_eurusd_fallback_warns_for_non_eurusd(self, builder, tmp_path, caplog):
        """Regression: falling back to EURUSD defaults for non-EURUSD tick data warns."""
        try:
            import pyarrow as pa
            import pyarrow.parquet as pq
        except ImportError:
            pytest.skip("pyarrow not available")

        tick_dir = tmp_path / "tick_data"
        tick_dir.mkdir()

        # Create minimal tick data with only hours 8-12 (london only)
        # Other sessions will have no data and trigger the fallback warning
        import datetime as dt
        n_rows = 20
        timestamps = [dt.datetime(2026, 1, 15, 10, 0, tzinfo=dt.timezone.utc)] * n_rows
        bid_opens = [1.08] * n_rows
        ask_opens = [1.0802] * n_rows
        table = pa.table({
            "timestamp": pa.array(timestamps, type=pa.timestamp("us", tz="UTC")),
            "bid_open": pa.array(bid_opens, type=pa.float64()),
            "bid_close": pa.array(bid_opens, type=pa.float64()),
            "ask_open": pa.array(ask_opens, type=pa.float64()),
            "ask_close": pa.array(ask_opens, type=pa.float64()),
        })
        pq.write_table(table, str(tick_dir / "test.parquet"))

        with caplog.at_level(logging.WARNING):
            artifact = builder.from_tick_data("GBPUSD", tick_dir)
        # Should have warned about using EURUSD defaults for non-EURUSD pair
        assert any("EURUSD research defaults" in r.message for r in caplog.records)

    @pytest.mark.regression
    def test_builder_validates_config_boundaries_at_init(self):
        """Regression: builder init validates config matches hardcoded boundaries."""
        # Normal init should succeed
        builder = CostModelBuilder(
            config_path=_CONFIG_PATH,
            contracts_path=_CONTRACTS_PATH,
            artifacts_dir=Path("/tmp/test_artifacts"),
        )
        assert builder.session_defs is not None
