"""Unit tests for artifacts.manifest — ManifestBuilder (Task 4)."""
import hashlib
import json
from pathlib import Path

import pytest

from artifacts.manifest import ManifestBuilder, _file_sha256


@pytest.fixture
def builder(tmp_path):
    """ManifestBuilder for test_strategy v001."""
    version_dir = tmp_path / "test_strategy" / "v001"
    version_dir.mkdir(parents=True)
    return ManifestBuilder("test_strategy", 1, tmp_path)


@pytest.fixture
def sample_manifest(builder):
    """Build a complete sample manifest."""
    return builder.build(
        backtest_run_id="run_001",
        strategy_spec_version="v001",
        strategy_spec_hash="sha256:aaa",
        cost_model_version="v001",
        cost_model_hash="sha256:bbb",
        dataset_hash="sha256:ccc",
        config_hash="sha256:ddd",
        run_timestamp="2025-01-01T00:00:00Z",
        started_at="2025-01-01T00:00:00Z",
        completed_at="2025-01-01T01:00:00Z",
        result_files={
            "trade_log": "backtest/trade-log.arrow",
            "equity_curve": "backtest/equity-curve.arrow",
            "metrics": "backtest/metrics.arrow",
        },
        metrics_summary={"total_trades": 50, "win_rate": 0.56},
        input_paths={"strategy_spec_path": "/tmp/spec.toml"},
    )


class TestManifestBuilder:
    def test_build_manifest_complete(self, sample_manifest):
        """Verify all required fields present."""
        required = {
            "schema_version", "backtest_run_id", "strategy_id", "version",
            "provenance", "execution", "result_files", "metrics_summary",
        }
        assert required.issubset(set(sample_manifest.keys()))

        # Provenance fields
        prov = sample_manifest["provenance"]
        assert prov["strategy_spec_hash"] == "sha256:aaa"
        assert prov["config_hash"] == "sha256:ddd"

        # Execution fields
        assert sample_manifest["execution"]["started_at"] == "2025-01-01T00:00:00Z"

    def test_write_manifest_crash_safe(self, builder, sample_manifest):
        """Verify crash-safe write: no .partial files, file exists."""
        manifest_path = builder.write(sample_manifest)
        assert manifest_path.exists()
        assert not manifest_path.with_name("manifest.json.partial").exists()

        # Verify content is valid JSON
        loaded = json.loads(manifest_path.read_text(encoding="utf-8"))
        assert loaded["backtest_run_id"] == "run_001"

    def test_load_manifest_roundtrip(self, builder, sample_manifest):
        """Write then load produces identical dict."""
        manifest_path = builder.write(sample_manifest)
        loaded = ManifestBuilder.load(manifest_path)
        assert loaded["backtest_run_id"] == sample_manifest["backtest_run_id"]
        assert loaded["provenance"] == sample_manifest["provenance"]
        assert loaded["metrics_summary"] == sample_manifest["metrics_summary"]

    def test_load_manifest_missing_file(self, tmp_path):
        """Missing manifest raises FileNotFoundError."""
        with pytest.raises(FileNotFoundError):
            ManifestBuilder.load(tmp_path / "nonexistent.json")

    def test_load_manifest_missing_keys(self, tmp_path):
        """Manifest with missing required keys raises ValueError."""
        bad_manifest = tmp_path / "bad.json"
        bad_manifest.write_text('{"schema_version": "1.0"}', encoding="utf-8")
        with pytest.raises(ValueError, match="missing required keys"):
            ManifestBuilder.load(bad_manifest)

    def test_verify_inputs_retrievable_success(self, tmp_path):
        """All inputs exist — returns True."""
        spec_path = tmp_path / "spec.toml"
        spec_path.write_text("spec content", encoding="utf-8")
        spec_hash = _file_sha256(spec_path)

        manifest = {
            "provenance": {"strategy_spec_hash": spec_hash},
            "inputs": {"strategy_spec_path": str(spec_path)},
        }
        assert ManifestBuilder.verify_inputs_retrievable(manifest) is True

    def test_verify_inputs_retrievable_missing(self, tmp_path):
        """Missing input raises FileNotFoundError."""
        manifest = {
            "provenance": {"strategy_spec_hash": "sha256:xxx"},
            "inputs": {"strategy_spec_path": str(tmp_path / "missing.toml")},
        }
        with pytest.raises(FileNotFoundError, match="Input not found"):
            ManifestBuilder.verify_inputs_retrievable(manifest)

    def test_verify_inputs_hash_mismatch(self, tmp_path):
        """Input exists but hash changed returns False."""
        spec_path = tmp_path / "spec.toml"
        spec_path.write_text("original content", encoding="utf-8")

        manifest = {
            "provenance": {"strategy_spec_hash": "sha256:wrong_hash"},
            "inputs": {"strategy_spec_path": str(spec_path)},
        }
        assert ManifestBuilder.verify_inputs_retrievable(manifest) is False
