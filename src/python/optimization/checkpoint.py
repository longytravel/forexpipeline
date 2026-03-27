"""Optimization checkpoint manager (Story 5.3, AC #8, #9).

Crash-safe checkpoint persistence using the .partial -> fsync -> os.replace
pattern from artifacts/storage.py.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from artifacts.storage import crash_safe_write
from logging_setup.setup import get_logger

logger = get_logger("optimization.checkpoint")


@dataclass
class OptimizationCheckpoint:
    """Complete optimization state for checkpoint/resume."""
    generation: int
    branch_states: dict = field(default_factory=dict)
    portfolio_states: dict = field(default_factory=dict)
    best_candidates: list = field(default_factory=list)
    best_score: float = float("-inf")
    evaluated_count: int = 0
    elapsed_time: float = 0.0
    config_hash: str = ""
    master_seed: int = 42
    candidate_counter: int = 0
    journal_entries: list = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "generation": self.generation,
            "branch_states": self.branch_states,
            "portfolio_states": self.portfolio_states,
            "best_candidates": self.best_candidates,
            "best_score": self.best_score,
            "evaluated_count": self.evaluated_count,
            "elapsed_time": self.elapsed_time,
            "config_hash": self.config_hash,
            "master_seed": self.master_seed,
            "candidate_counter": self.candidate_counter,
            "journal_entries": self.journal_entries,
            "version": 1,
        }

    @classmethod
    def from_dict(cls, data: dict) -> OptimizationCheckpoint:
        return cls(
            generation=data["generation"],
            branch_states=data.get("branch_states", {}),
            portfolio_states=data.get("portfolio_states", {}),
            best_candidates=data.get("best_candidates", []),
            best_score=data.get("best_score", float("-inf")),
            evaluated_count=data.get("evaluated_count", 0),
            elapsed_time=data.get("elapsed_time", 0.0),
            config_hash=data.get("config_hash", ""),
            master_seed=data.get("master_seed", 42),
            candidate_counter=data.get("candidate_counter", 0),
            journal_entries=data.get("journal_entries", []),
        )


def save_checkpoint(checkpoint: OptimizationCheckpoint, path: Path) -> None:
    """Serialize checkpoint to JSON using crash-safe write."""
    content = json.dumps(checkpoint.to_dict(), indent=2, default=str)
    crash_safe_write(path, content)

    logger.info(
        f"Checkpoint saved at generation {checkpoint.generation}",
        extra={
            "component": "optimization.checkpoint",
            "ctx": {
                "generation": checkpoint.generation,
                "evaluated_count": checkpoint.evaluated_count,
                "path": str(path),
            },
        },
    )


def load_checkpoint(path: Path) -> OptimizationCheckpoint:
    """Deserialize checkpoint from JSON."""
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    checkpoint = OptimizationCheckpoint.from_dict(data)

    logger.info(
        f"Checkpoint loaded: generation {checkpoint.generation}",
        extra={
            "component": "optimization.checkpoint",
            "ctx": {
                "generation": checkpoint.generation,
                "evaluated_count": checkpoint.evaluated_count,
            },
        },
    )

    return checkpoint


def validate_checkpoint_config(
    checkpoint: OptimizationCheckpoint, current_config_hash: str
) -> bool:
    """Validate that checkpoint config_hash matches current config.

    Returns True if compatible, False if mismatched.
    """
    if not checkpoint.config_hash or not current_config_hash:
        return True  # Can't validate if either is missing
    if checkpoint.config_hash != current_config_hash:
        logger.warning(
            "Checkpoint config_hash mismatch — run config has changed since checkpoint",
            extra={
                "component": "optimization.checkpoint",
                "ctx": {
                    "checkpoint_hash": checkpoint.config_hash,
                    "current_hash": current_config_hash,
                },
            },
        )
        return False
    return True


def should_checkpoint(generation: int, interval: int) -> bool:
    """Whether to checkpoint at this generation (0-indexed, fires after every `interval` gens)."""
    return interval > 0 and (generation + 1) % interval == 0
