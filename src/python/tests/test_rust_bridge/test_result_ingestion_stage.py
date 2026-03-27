"""Integration tests for result processing stage integration (Task 7)."""
import json
import shutil
from pathlib import Path

import pytest

from artifacts.sqlite_manager import SQLiteManager
from rust_bridge.result_executor import ResultExecutor
from rust_bridge.result_processor import ResultProcessor


@pytest.fixture
def fixtures_dir():
    d = Path(__file__).resolve().parents[1] / "fixtures" / "backtest_output"
    if not (d / "trade-log.arrow").exists():
        pytest.skip("Backtest fixtures not generated")
    return d


@pytest.fixture
def rust_output(tmp_path, fixtures_dir):
    output_dir = tmp_path / "rust_output"
    output_dir.mkdir()
    for f in ["trade-log.arrow", "equity-curve.arrow", "metrics.arrow"]:
        shutil.copy2(str(fixtures_dir / f), str(output_dir / f))
    return output_dir


@pytest.fixture
def executor(tmp_path):
    artifacts_root = tmp_path / "artifacts"
    artifacts_root.mkdir()
    db_path = tmp_path / "pipeline.db"
    processor = ResultProcessor(artifacts_root, db_path)
    return ResultExecutor(processor)


class TestResultIngestionStage:
    def test_result_processing_triggers_after_backtest(self, executor, rust_output, tmp_path):
        """Verify result processing runs as part of backtest-complete → review-pending."""
        context = {
            "artifacts_dir": str(tmp_path / "artifacts"),
            "config_hash": "sha256:cfg1",
            "data_hash": "sha256:data1",
            "cost_model_hash": "sha256:cost1",
            "strategy_spec_hash": "sha256:spec1",
            "rust_output_dir": str(rust_output),
            "strategy_spec_version": "v001",
            "cost_model_version": "v001",
            "backtest_run_id": "run_stage_001",
        }

        result = executor.execute("ma_crossover_v001", context)
        assert result.outcome == "success"
        assert result.artifact_path is not None
        assert result.manifest_ref is not None
        assert result.metrics["trade_count"] == 50

    def test_stage_idempotent_rerun(self, executor, rust_output, tmp_path):
        """Run processing twice with same inputs, verify no duplicates or errors."""
        context = {
            "artifacts_dir": str(tmp_path / "artifacts"),
            "config_hash": "sha256:cfg1",
            "data_hash": "sha256:data1",
            "cost_model_hash": "sha256:cost1",
            "strategy_spec_hash": "sha256:spec1",
            "rust_output_dir": str(rust_output),
            "strategy_spec_version": "v001",
            "cost_model_version": "v001",
            "backtest_run_id": "run_idem_001",
        }

        result1 = executor.execute("ma_crossover_v001", context)
        assert result1.outcome == "success"

        # Second run with same run_id
        result2 = executor.execute("ma_crossover_v001", context)
        assert result2.outcome == "success"

    def test_stage_handles_missing_output(self, executor, tmp_path):
        """Missing Rust output raises controlled error."""
        context = {
            "artifacts_dir": str(tmp_path / "artifacts"),
            "config_hash": "sha256:cfg1",
            "data_hash": "sha256:data1",
            "cost_model_hash": "sha256:cost1",
            "strategy_spec_hash": "sha256:spec1",
            "rust_output_dir": str(tmp_path / "nonexistent"),
            "strategy_spec_version": "v001",
            "cost_model_version": "v001",
            "backtest_run_id": "run_fail_001",
        }

        result = executor.execute("ma_crossover_v001", context)
        assert result.outcome == "failed"
        assert result.error is not None

    def test_validate_artifact(self, executor, rust_output, tmp_path):
        """validate_artifact returns True for complete artifacts."""
        context = {
            "artifacts_dir": str(tmp_path / "artifacts"),
            "config_hash": "sha256:cfg1",
            "data_hash": "sha256:data1",
            "cost_model_hash": "sha256:cost1",
            "strategy_spec_hash": "sha256:spec1",
            "rust_output_dir": str(rust_output),
            "strategy_spec_version": "v001",
            "cost_model_version": "v001",
            "backtest_run_id": "run_validate_001",
        }

        result = executor.execute("ma_crossover_v001", context)
        assert result.outcome == "success"

        # Validate the artifact
        assert executor.validate_artifact(
            Path(result.artifact_path), Path(result.manifest_ref)
        )

    def test_validate_artifact_missing(self, executor, tmp_path):
        """validate_artifact returns False for missing directory."""
        assert not executor.validate_artifact(
            tmp_path / "nonexistent", tmp_path / "manifest.json"
        )
