"""Results writer, run manifest, and candidate promotion (Story 5.3, AC #13, #15, #16).

Streams optimization results to Arrow IPC incrementally.
Writes provenance-rich run manifest for downstream traceability.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pyarrow as pa
import pyarrow.ipc

from artifacts.storage import crash_safe_write
from data_pipeline.utils.safe_write import safe_write_arrow_ipc
from logging_setup.setup import get_logger

logger = get_logger("optimization.results")

# Arrow IPC schema for optimization candidates
CANDIDATES_SCHEMA = pa.schema([
    ("candidate_id", pa.uint64()),
    ("generation", pa.uint32()),
    ("branch", pa.utf8()),
    ("instance_type", pa.utf8()),
    ("params_json", pa.utf8()),
    ("cv_objective", pa.float64()),
    ("fold_scores", pa.list_(pa.float64())),
])

PROMOTED_SCHEMA = pa.schema([
    ("candidate_id", pa.uint64()),
    ("rank", pa.uint32()),
    ("params_json", pa.utf8()),
    ("cv_objective", pa.float64()),
    ("fold_scores", pa.list_(pa.float64())),
    ("branch", pa.utf8()),
    ("instance_type", pa.utf8()),
])


class StreamingResultsWriter:
    """Append-mode Arrow IPC writer that streams results per generation.

    Never accumulates all candidates in memory — writes incrementally.
    Supports context manager protocol for safe resource cleanup.
    """

    def __init__(self, output_path: Path):
        self._output_path = Path(output_path)
        self._output_path.parent.mkdir(parents=True, exist_ok=True)
        self._partial_path = self._output_path.with_name(
            self._output_path.name + ".partial"
        )
        self._file = open(self._partial_path, "wb")
        self._writer = pa.ipc.new_file(self._file, CANDIDATES_SCHEMA)
        self._count = 0
        self._closed = False

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if not self._closed:
            try:
                self._writer.close()
            except Exception:
                pass
            try:
                self._file.close()
            except Exception:
                pass
            self._closed = True
        return False

    def append_generation(
        self,
        generation: int,
        candidate_ids: list[int],
        params_list: list[str],
        fold_scores: np.ndarray,
        cv_objectives: np.ndarray,
        branch: str,
        instance_types: list[str],
    ) -> None:
        """Append one generation's results to the Arrow IPC file."""
        n = len(candidate_ids)
        if n == 0:
            return

        # Build per-candidate fold score lists
        fold_score_lists = [fold_scores[i].tolist() for i in range(n)]

        table = pa.table({
            "candidate_id": pa.array(candidate_ids, type=pa.uint64()),
            "generation": pa.array([generation] * n, type=pa.uint32()),
            "branch": pa.array([branch] * n, type=pa.utf8()),
            "instance_type": pa.array(
                instance_types[:n] if len(instance_types) >= n
                else instance_types + ["unknown"] * (n - len(instance_types)),
                type=pa.utf8(),
            ),
            "params_json": pa.array(params_list, type=pa.utf8()),
            "cv_objective": pa.array(cv_objectives.tolist(), type=pa.float64()),
            "fold_scores": pa.array(fold_score_lists, type=pa.list_(pa.float64())),
        })

        self._writer.write_table(table)
        self._count += n

    def finalize(self) -> Path:
        """Flush, close, and atomically rename to final path."""
        import os

        self._writer.close()
        self._file.flush()
        os.fsync(self._file.fileno())
        self._file.close()
        self._closed = True

        os.replace(str(self._partial_path), str(self._output_path))

        logger.info(
            f"Results finalized: {self._count} candidates",
            extra={
                "component": "optimization.results",
                "ctx": {"count": self._count, "path": str(self._output_path)},
            },
        )

        return self._output_path


def write_run_manifest(
    artifacts_dir: Path,
    dataset_hash: str,
    strategy_spec_hash: str,
    config_hash: str,
    fold_definitions: list[dict],
    rng_seeds: dict,
    stop_reason: str,
    generation_count: int,
    branch_metadata: dict,
    total_evaluations: int = 0,
) -> Path:
    """Write crash-safe JSON run manifest with full provenance."""
    manifest = {
        "dataset_hash": dataset_hash,
        "strategy_spec_hash": strategy_spec_hash,
        "config_hash": config_hash,
        "fold_definitions": fold_definitions,
        "rng_seeds": rng_seeds,
        "stop_reason": stop_reason,
        "generation_count": generation_count,
        "branch_metadata": branch_metadata,
        "total_evaluations": total_evaluations,
        "version": 1,
    }

    manifest_path = artifacts_dir / "run-manifest.json"
    crash_safe_write(manifest_path, json.dumps(manifest, indent=2, default=str))

    logger.info(
        "Run manifest written",
        extra={
            "component": "optimization.results",
            "ctx": {
                "path": str(manifest_path),
                "generations": generation_count,
                "stop_reason": stop_reason,
            },
        },
    )

    return manifest_path


def promote_top_candidates(
    results_path: Path,
    top_n: int = 20,
) -> Path:
    """Read Arrow IPC results, sort by cv_objective, write top-N promoted candidates."""
    reader = pa.ipc.open_file(str(results_path))
    table = reader.read_all()

    # Sort descending by cv_objective
    indices = pa.compute.sort_indices(
        table, sort_keys=[("cv_objective", "descending")]
    )
    sorted_table = table.take(indices)

    # Take top N
    top = sorted_table.slice(0, min(top_n, len(sorted_table)))

    # Add rank column
    ranks = pa.array(list(range(1, len(top) + 1)), type=pa.uint32())
    promoted = pa.table({
        "candidate_id": top.column("candidate_id"),
        "rank": ranks,
        "params_json": top.column("params_json"),
        "cv_objective": top.column("cv_objective"),
        "fold_scores": top.column("fold_scores"),
        "branch": top.column("branch"),
        "instance_type": top.column("instance_type"),
    })

    output_path = results_path.parent / "promoted-candidates.arrow"
    safe_write_arrow_ipc(promoted, output_path)

    logger.info(
        f"Promoted top {len(promoted)} candidates",
        extra={
            "component": "optimization.results",
            "ctx": {
                "top_n": top_n,
                "actual": len(promoted),
                "path": str(output_path),
            },
        },
    )

    return output_path
