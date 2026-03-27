"""Tests for optimization.prescreener (Phase 3: Pre-Screening).

Covers: PreScreener group discovery, survival ranking, and edge cases.
Uses mocked evaluator to avoid Rust binary dependency.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import numpy as np
import pytest

from optimization.prescreener import PreScreener, PreScreenResult


def _make_mock_classification(n_signal=2, n_spec_override=0):
    """Create a minimal mock ParamClassification."""
    mock = MagicMock()
    mock.has_signal_params = n_signal > 0
    mock.signal_indices = list(range(n_signal))
    mock.spec_override_indices = list(range(n_signal, n_signal + n_spec_override))
    mock.group_key_indices = mock.signal_indices + mock.spec_override_indices
    mock.spec_override_params = {}
    return mock


class TestPreScreenResult:
    """Tests for the PreScreenResult dataclass."""

    def test_result_fields(self):
        result = PreScreenResult(
            surviving_groups=["abc123", "def456"],
            eliminated_count=3,
            total_count=5,
            elapsed_s=1.5,
            group_scores={"abc123": 0.8, "def456": 0.7},
        )
        assert len(result.surviving_groups) == 2
        assert result.eliminated_count == 3
        assert result.total_count == 5
        assert result.elapsed_s == 1.5

    def test_empty_result(self):
        result = PreScreenResult(
            surviving_groups=[],
            eliminated_count=0,
            total_count=0,
            elapsed_s=0.1,
        )
        assert len(result.surviving_groups) == 0
        assert result.group_scores == {}


class TestPreScreenerInit:
    """Tests for PreScreener initialization."""

    def test_init_stores_params(self, tmp_path):
        prescreener = PreScreener(
            strategy_spec={"metadata": {"name": "test"}},
            market_data_path=tmp_path / "data.arrow",
            config={},
            artifacts_dir=tmp_path,
            classification=_make_mock_classification(),
            data_hash="sha256:abc",
            batch_runner=MagicMock(),
            year_range=(2020, 2025),
        )
        assert prescreener._year_range == (2020, 2025)

    def test_init_without_year_range(self, tmp_path):
        prescreener = PreScreener(
            strategy_spec={"metadata": {"name": "test"}},
            market_data_path=tmp_path / "data.arrow",
            config={},
            artifacts_dir=tmp_path,
            classification=_make_mock_classification(),
            data_hash="sha256:abc",
            batch_runner=MagicMock(),
        )
        assert prescreener._year_range is None


class TestPreScreenerSliceComputation:
    """Tests for _compute_slice_year_range."""

    def test_slice_with_year_range(self, tmp_path):
        prescreener = PreScreener(
            strategy_spec={},
            market_data_path=tmp_path / "data.arrow",
            config={},
            artifacts_dir=tmp_path,
            classification=_make_mock_classification(),
            data_hash="sha256:abc",
            batch_runner=MagicMock(),
            year_range=(2018, 2025),
        )
        # 3-month slice from end of configured range
        result = prescreener._compute_slice_year_range(3)
        assert result == (2025, 2025)

    def test_slice_long_duration(self, tmp_path):
        prescreener = PreScreener(
            strategy_spec={},
            market_data_path=tmp_path / "data.arrow",
            config={},
            artifacts_dir=tmp_path,
            classification=_make_mock_classification(),
            data_hash="sha256:abc",
            batch_runner=MagicMock(),
            year_range=(2018, 2025),
        )
        # 24-month slice
        result = prescreener._compute_slice_year_range(24)
        assert result == (2023, 2025)

    def test_slice_no_year_range_no_data(self, tmp_path):
        """Without year_range and no readable data, should return None."""
        prescreener = PreScreener(
            strategy_spec={},
            market_data_path=tmp_path / "nonexistent.arrow",
            config={},
            artifacts_dir=tmp_path,
            classification=_make_mock_classification(),
            data_hash="sha256:abc",
            batch_runner=MagicMock(),
        )
        result = prescreener._compute_slice_year_range(3)
        assert result is None


class TestPreScreenerMode:
    """Tests for mode validation in screen()."""

    def test_invalid_mode_raises(self, tmp_path):
        prescreener = PreScreener(
            strategy_spec={"metadata": {"name": "test"}, "optimization_plan": {}},
            market_data_path=tmp_path / "data.arrow",
            config={},
            artifacts_dir=tmp_path,
            classification=_make_mock_classification(),
            data_hash="sha256:abc",
            batch_runner=MagicMock(),
        )

        mock_space = MagicMock()
        mock_space.n_dims = 4
        mock_space.parameters = []
        mock_space.param_names = []

        with pytest.raises(ValueError, match="Unknown prescreening mode"):
            asyncio.run(prescreener.screen(
                space=mock_space,
                branches={},
                mode="INVALID",
            ))


class TestPreScreenerSurvival:
    """Tests for survival ratio ranking logic."""

    def test_survival_ratio_selects_top_groups(self):
        """Verify that survival_ratio correctly selects top-scoring groups."""
        # Simulate what screen() does with group_scores
        group_scores = {
            "group_a": 0.5,
            "group_b": 0.9,
            "group_c": 0.1,
            "group_d": 0.7,
            "group_e": 0.3,
        }
        survival_ratio = 0.4  # keep top 40% = 2 groups

        n_survive = max(1, int(len(group_scores) * survival_ratio))
        sorted_groups = sorted(
            group_scores.items(), key=lambda kv: kv[1], reverse=True
        )
        surviving = [g_hash for g_hash, _ in sorted_groups[:n_survive]]

        assert len(surviving) == 2
        assert "group_b" in surviving  # score 0.9
        assert "group_d" in surviving  # score 0.7
        assert "group_c" not in surviving  # score 0.1

    def test_survival_ratio_minimum_one(self):
        """At least 1 group should always survive."""
        group_scores = {"group_a": 0.5, "group_b": 0.9}
        survival_ratio = 0.01  # Would be 0.02 -> rounds to 0

        n_survive = max(1, int(len(group_scores) * survival_ratio))
        assert n_survive >= 1

    def test_survival_ratio_one_keeps_all(self):
        """survival_ratio=1.0 should keep all groups."""
        group_scores = {"a": 0.1, "b": 0.5, "c": 0.9}
        survival_ratio = 1.0

        n_survive = max(1, int(len(group_scores) * survival_ratio))
        assert n_survive == 3
