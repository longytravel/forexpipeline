"""Tests for optimization.fold_manager (Task 6)."""
from __future__ import annotations

import numpy as np
import pytest

from optimization.fold_manager import FoldManager, compute_cv_objective


class TestFoldBoundaries:
    def test_fold_boundaries_no_overlap(self):
        fm = FoldManager(data_length=10000, n_folds=5, embargo_bars=0)
        folds = fm.get_fold_boundaries()
        assert len(folds) == 5

        for i in range(len(folds) - 1):
            # Test regions should not overlap
            assert folds[i].test_end <= folds[i + 1].test_start

    def test_fold_embargo_gap(self):
        embargo = 100
        fm = FoldManager(data_length=10000, n_folds=3, embargo_bars=embargo)
        folds = fm.get_fold_boundaries()

        for fold in folds:
            # Train end should be at least embargo bars before test start
            assert fold.test_start - fold.train_end >= embargo

    def test_fold_boundaries_cover_data(self):
        fm = FoldManager(data_length=10000, n_folds=5, embargo_bars=0)
        folds = fm.get_fold_boundaries()

        # All folds should start from 0 for training
        for fold in folds:
            assert fold.train_start == 0
            assert fold.test_end > fold.test_start

    def test_fold_to_rust_format(self):
        fm = FoldManager(data_length=10000, n_folds=3, embargo_bars=50)
        rust_args = fm.to_rust_fold_args()

        assert len(rust_args) == 3
        for arg in rust_args:
            assert "fold_id" in arg
            assert "train_start" in arg
            assert "train_end" in arg
            assert "test_start" in arg
            assert "test_end" in arg
            assert "embargo_bars" in arg
            assert arg["embargo_bars"] == 50

    def test_too_small_data_raises(self):
        with pytest.raises(ValueError, match="too small"):
            FoldManager(data_length=3, n_folds=5)

    def test_too_few_folds_raises(self):
        with pytest.raises(ValueError, match="at least 2"):
            FoldManager(data_length=10000, n_folds=1)


class TestCVObjective:
    def test_cv_objective_penalizes_variance(self):
        # Low variance → higher score
        low_var = np.array([1.0, 1.0, 1.0, 1.0, 1.0])
        high_var = np.array([0.5, 1.5, 0.5, 1.5, 0.5])

        score_low = compute_cv_objective(low_var, lambda_=1.5)
        score_high = compute_cv_objective(high_var, lambda_=1.5)

        # Same mean but higher variance → lower score
        assert score_low > score_high

    def test_cv_objective_mean_minus_lambda_std(self):
        scores = np.array([2.0, 4.0])
        result = compute_cv_objective(scores, lambda_=1.0)
        sample_std = float(np.std(scores, ddof=1))  # sqrt(2) ≈ 1.4142
        expected = 3.0 - 1.0 * sample_std
        assert abs(result - expected) < 1e-6

    def test_cv_objective_empty_returns_neginf(self):
        result = compute_cv_objective(np.array([]), lambda_=1.0)
        assert result == float("-inf")

    def test_cv_objective_zero_lambda_equals_mean(self):
        scores = np.array([1.0, 3.0, 5.0])
        result = compute_cv_objective(scores, lambda_=0.0)
        assert abs(result - 3.0) < 1e-6
