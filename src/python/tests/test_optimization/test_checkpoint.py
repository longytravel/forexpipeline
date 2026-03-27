"""Tests for optimization.checkpoint (Task 8)."""
from __future__ import annotations

from pathlib import Path

import pytest

from optimization.checkpoint import (
    OptimizationCheckpoint,
    load_checkpoint,
    save_checkpoint,
    should_checkpoint,
)


class TestCheckpoint:
    def test_checkpoint_roundtrip(self, tmp_path: Path):
        cp = OptimizationCheckpoint(
            generation=42,
            branch_states={"__default__": {"instances": []}},
            best_candidates=[{"p1": 1.0, "p2": 2.0}],
            evaluated_count=1000,
            elapsed_time=123.4,
            config_hash="sha256:test",
            master_seed=42,
            candidate_counter=500,
        )

        path = tmp_path / "checkpoint.json"
        save_checkpoint(cp, path)
        assert path.exists()

        loaded = load_checkpoint(path)
        assert loaded.generation == 42
        assert loaded.evaluated_count == 1000
        assert loaded.elapsed_time == 123.4
        assert loaded.config_hash == "sha256:test"
        assert loaded.master_seed == 42
        assert loaded.candidate_counter == 500
        assert len(loaded.best_candidates) == 1

    def test_checkpoint_crash_safe(self, tmp_path: Path):
        """Verify .partial file is cleaned up after write."""
        cp = OptimizationCheckpoint(generation=1)
        path = tmp_path / "checkpoint.json"

        save_checkpoint(cp, path)

        # Final file exists
        assert path.exists()
        # .partial should not exist
        partial = path.with_name(path.name + ".partial")
        assert not partial.exists()

    def test_checkpoint_resume_generation(self, tmp_path: Path):
        """Verify optimization can resume at correct generation."""
        cp = OptimizationCheckpoint(
            generation=15,
            candidate_counter=750,
            evaluated_count=750,
        )

        path = tmp_path / "checkpoint.json"
        save_checkpoint(cp, path)
        loaded = load_checkpoint(path)

        assert loaded.generation == 15
        assert loaded.candidate_counter == 750


class TestShouldCheckpoint:
    def test_checkpoints_at_interval(self):
        # 0-indexed: gen 9 is the 10th gen, gen 19 is the 20th
        assert should_checkpoint(9, 10)
        assert should_checkpoint(19, 10)
        assert not should_checkpoint(10, 10)
        assert not should_checkpoint(15, 10)

    def test_checkpoint_gen_zero_with_interval_one(self):
        # interval=1 should fire every gen including gen 0
        assert should_checkpoint(0, 1)

    def test_no_checkpoint_with_zero_interval(self):
        assert not should_checkpoint(10, 0)
