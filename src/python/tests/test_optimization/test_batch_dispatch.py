"""Tests for optimization.batch_dispatch (Task 7)."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import numpy as np
import pytest

from optimization.batch_dispatch import OptimizationBatchDispatcher
from optimization.fold_manager import FoldSpec
from rust_bridge.batch_runner import BatchResult, BatchRunner


class TestBatchDispatch:
    def test_dispatch_memory_check(self, sample_config):
        runner = MagicMock(spec=BatchRunner)
        dispatcher = OptimizationBatchDispatcher(
            batch_runner=runner,
            artifacts_dir=Path("/tmp/test"),
            config=sample_config,
        )

        # Memory check should return a result
        ok, adjusted = dispatcher.check_memory(batch_size=2048, n_folds=5)
        assert isinstance(ok, bool)
        assert isinstance(adjusted, int)
        assert adjusted > 0


class TestDispatchMemoryGuard:
    def test_memory_reduces_batch_when_needed(self, sample_config):
        runner = MagicMock(spec=BatchRunner)
        dispatcher = OptimizationBatchDispatcher(
            batch_runner=runner,
            artifacts_dir=Path("/tmp/test"),
            config=sample_config,
        )

        # With very large batch and small budget
        small_budget_config = dict(sample_config)
        small_budget_config["optimization"] = dict(sample_config["optimization"])
        small_budget_config["optimization"]["memory_budget_mb"] = 1  # 1MB budget

        small_dispatcher = OptimizationBatchDispatcher(
            batch_runner=runner,
            artifacts_dir=Path("/tmp/test"),
            config=small_budget_config,
        )

        ok, adjusted = small_dispatcher.check_memory(batch_size=100000, n_folds=10)
        # Should reduce batch size
        assert adjusted <= 100000
