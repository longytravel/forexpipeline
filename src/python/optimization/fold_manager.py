"""CV-inside-objective fold manager (Story 5.3, AC #4, #5).

Time-series aware cross-validation with embargo gaps.
Fold boundaries are passed to the Rust evaluator as bar index ranges.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from logging_setup.setup import get_logger

logger = get_logger("optimization.fold_manager")


@dataclass(frozen=True)
class FoldSpec:
    """Single fold definition with train/test bar index ranges."""
    fold_id: int
    train_start: int
    train_end: int  # exclusive
    test_start: int
    test_end: int    # exclusive
    embargo_bars: int


class FoldManager:
    """Manages time-series cross-validation fold boundaries.

    Uses expanding-window or sliding-window splits with embargo gaps
    to prevent lookback contamination.
    """

    def __init__(self, data_length: int, n_folds: int, embargo_bars: int = 0):
        if data_length < n_folds * 2:
            raise ValueError(
                f"Data length {data_length} too small for {n_folds} folds"
            )
        if n_folds < 2:
            raise ValueError(f"Need at least 2 folds, got {n_folds}")

        self._data_length = data_length
        self._n_folds = n_folds
        self._embargo_bars = embargo_bars
        self._folds = self._compute_folds()

        logger.info(
            f"FoldManager initialized: {n_folds} folds, {embargo_bars} embargo bars",
            extra={
                "component": "optimization.fold_manager",
                "ctx": {
                    "data_length": data_length,
                    "n_folds": n_folds,
                    "embargo_bars": embargo_bars,
                },
            },
        )

    def _compute_folds(self) -> list[FoldSpec]:
        """Compute time-series fold boundaries (no shuffle, temporal order)."""
        total = self._data_length
        n = self._n_folds
        embargo = self._embargo_bars

        # Divide data into n+1 blocks: first block always train, rest rotate as test
        block_size = total // (n + 1)
        folds: list[FoldSpec] = []

        for i in range(n):
            # Test block is block i+1
            test_start = (i + 1) * block_size
            test_end = min((i + 2) * block_size, total) if i < n - 1 else total

            # Train is everything before test, minus embargo
            train_end = max(0, test_start - embargo)
            train_start = 0

            if train_end <= train_start:
                train_end = test_start  # Fallback: no embargo if insufficient data

            folds.append(FoldSpec(
                fold_id=i,
                train_start=train_start,
                train_end=train_end,
                test_start=test_start,
                test_end=test_end,
                embargo_bars=embargo,
            ))

        return folds

    def get_fold_boundaries(self) -> list[FoldSpec]:
        """Return all fold definitions."""
        return list(self._folds)

    def to_rust_fold_args(self) -> list[dict]:
        """Format fold boundaries for Rust evaluator batch dispatch.

        Returns list of dicts with bar index ranges.
        """
        return [
            {
                "fold_id": f.fold_id,
                "train_start": f.train_start,
                "train_end": f.train_end,
                "test_start": f.test_start,
                "test_end": f.test_end,
                "embargo_bars": f.embargo_bars,
            }
            for f in self._folds
        ]


def compute_cv_objective(fold_scores: np.ndarray, lambda_: float) -> float:
    """Compute CV objective: mean - lambda * std.

    Args:
        fold_scores: Array of per-fold scores for a single candidate.
        lambda_: Penalty weight for variance (default ~1.0-2.0).

    Returns:
        Penalized mean score. Higher is better.
    """
    if len(fold_scores) == 0:
        return float("-inf")
    mean = float(np.mean(fold_scores))
    std = float(np.std(fold_scores, ddof=1)) if len(fold_scores) > 1 else 0.0
    return mean - lambda_ * std
