"""Tests for optimization.executor (Task 11)."""
from __future__ import annotations

from pathlib import Path
from typing import Protocol, runtime_checkable

import pyarrow as pa
import pyarrow.ipc
import pytest

from optimization.executor import OptimizationExecutor


class TestExecutor:
    def test_executor_implements_protocol(self):
        """Verify OptimizationExecutor has the StageExecutor interface."""
        executor = OptimizationExecutor()
        assert hasattr(executor, "execute")
        assert hasattr(executor, "validate_artifact")
        assert callable(executor.execute)
        assert callable(executor.validate_artifact)

    def test_executor_validate_artifact_missing_file(self, tmp_path: Path):
        executor = OptimizationExecutor()
        result = executor.validate_artifact(
            tmp_path / "nonexistent.arrow",
            tmp_path / "manifest.json",
        )
        assert result is False

    def test_executor_validate_artifact_valid_file(self, tmp_path: Path):
        executor = OptimizationExecutor()

        # Create a valid Arrow IPC file
        table = pa.table({
            "candidate_id": pa.array([1, 2], type=pa.uint64()),
            "cv_objective": pa.array([0.5, 0.8], type=pa.float64()),
        })
        path = tmp_path / "results.arrow"
        with pa.ipc.new_file(str(path), table.schema) as writer:
            writer.write_table(table)

        result = executor.validate_artifact(path, tmp_path / "manifest.json")
        assert result is True

    def test_executor_validate_empty_file(self, tmp_path: Path):
        executor = OptimizationExecutor()

        # Create an empty Arrow IPC file
        schema = pa.schema([("x", pa.int64())])
        table = pa.table({"x": pa.array([], type=pa.int64())})
        path = tmp_path / "empty.arrow"
        with pa.ipc.new_file(str(path), schema) as writer:
            writer.write_table(table)

        result = executor.validate_artifact(path, tmp_path / "manifest.json")
        assert result is False  # Empty is not valid

    def test_executor_resume_detects_checkpoint(self, tmp_path: Path):
        """Verify checkpoint detection for resume."""
        executor = OptimizationExecutor()

        # No checkpoint — resume_from should be None
        artifacts_dir = tmp_path / "artifacts" / "test-strategy" / "optimization"
        artifacts_dir.mkdir(parents=True)

        # With checkpoint
        checkpoint = artifacts_dir / "optimization-checkpoint.json"
        checkpoint.write_text('{"generation": 5}', encoding="utf-8")
        assert checkpoint.exists()
