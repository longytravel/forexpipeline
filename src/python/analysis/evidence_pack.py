"""Evidence pack assembler — single-pass full evidence pack (D11).

Assembles narrative, anomaly detection, metrics, equity curve summary,
and trade distribution into a versioned JSON artifact.

Epic 3 assembles the full evidence pack in a single pass. The two-pass
distinction (Phase 1 triage, Phase 2 deep review) becomes operationally
relevant in Epic 5 for processing optimization candidate batches.
"""
from __future__ import annotations

import json
import sqlite3
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pyarrow.ipc

from analysis.anomaly_detector import detect_anomalies
from analysis.models import AnalysisError, EvidencePack
from analysis.narrative import generate_narrative
from artifacts.storage import crash_safe_write
from logging_setup.setup import get_logger

logger = get_logger("pipeline.analysis.evidence_pack")

# Session values from contracts/session_schema.toml
_SESSIONS = ["asian", "london", "new_york", "london_ny_overlap", "off_hours"]


def assemble_evidence_pack(
    backtest_id: str,
    db_path: Path | None = None,
    artifacts_root: Path | None = None,
) -> EvidencePack:
    """Assemble a complete evidence pack for a backtest run.

    Calls generate_narrative() and detect_anomalies() internally,
    then enriches with equity curve summary and trade distribution.

    Args:
        backtest_id: The backtest run ID.
        db_path: Path to SQLite database.
        artifacts_root: Root directory for artifacts.

    Returns:
        Populated EvidencePack dataclass.

    Raises:
        AnalysisError: If required data is missing or invalid.
    """
    db_path = _resolve_db_path(db_path)
    artifacts_root = _resolve_artifacts_root(artifacts_root)

    logger.info(
        "Assembling evidence pack",
        extra={
            "component": "pipeline.analysis.evidence_pack",
            "ctx": {"backtest_id": backtest_id},
        },
    )

    # Step 1: Generate narrative and detect anomalies
    narrative = generate_narrative(backtest_id, db_path)
    anomalies = detect_anomalies(backtest_id, db_path)

    # Step 2: Load run metadata and trades for path resolution & distribution
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        run_meta = _load_run_metadata(conn, backtest_id)
        trades = _load_trades(conn, backtest_id)
    finally:
        conn.close()

    strategy_id = run_meta["strategy_id"]

    # Step 3: Resolve version directory
    version_dir = _find_version_dir(strategy_id, backtest_id, artifacts_root)
    version_str = version_dir.parent.name  # "v001"

    # Step 4: Reuse metrics from narrative (same shared compute_metrics call)
    metrics = narrative.metrics

    # Step 5: Load and downsample equity curve from Arrow IPC
    equity_curve_path = version_dir / "equity-curve.arrow"
    equity_curve_summary = _downsample_equity_curve(equity_curve_path)

    # Step 6: Compute trade distribution
    trade_distribution = _compute_trade_distribution(trades)

    # Step 7: Build relative paths
    rel_prefix = f"artifacts/{strategy_id}/{version_str}/backtest"
    trade_log_path = f"{rel_prefix}/trade-log.arrow"
    equity_full_path = f"{rel_prefix}/equity-curve.arrow"
    manifest_path = f"{rel_prefix}/manifest.json"

    # Step 8: Populate metadata
    metadata = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "backtest_run_id": backtest_id,
        "strategy_id": strategy_id,
        "version": version_str,
        "pipeline_stage": "backtest",
        "manifest_path": manifest_path,
        "schema_version": "1.0",
    }

    pack = EvidencePack(
        backtest_id=backtest_id,
        strategy_id=strategy_id,
        version=version_str,
        narrative=narrative,
        anomalies=anomalies,
        metrics=metrics,
        equity_curve_summary=equity_curve_summary,
        equity_curve_full_path=equity_full_path,
        trade_distribution=trade_distribution,
        trade_log_path=trade_log_path,
        metadata=metadata,
    )

    # Step 9: Persist evidence pack JSON using crash-safe write
    output_path = version_dir / "evidence_pack.json"
    pack_json = json.dumps(pack.to_json(), indent=2, default=str)
    crash_safe_write(output_path, pack_json)

    logger.info(
        "Evidence pack assembled and persisted",
        extra={
            "component": "pipeline.analysis.evidence_pack",
            "ctx": {
                "backtest_id": backtest_id,
                "output_path": str(output_path),
                "anomaly_count": len(anomalies.anomalies),
                "equity_points": len(equity_curve_summary),
            },
        },
    )

    return pack


def _resolve_db_path(db_path: Path | None) -> Path:
    """Resolve SQLite database path."""
    if db_path is not None:
        return Path(db_path)
    return Path("artifacts") / "backtest.db"


def _resolve_artifacts_root(artifacts_root: Path | None) -> Path:
    """Resolve artifacts root directory."""
    if artifacts_root is not None:
        return Path(artifacts_root)
    return Path("artifacts")


def _load_run_metadata(conn: sqlite3.Connection, backtest_id: str) -> dict[str, Any]:
    """Load backtest run metadata."""
    row = conn.execute(
        "SELECT run_id, strategy_id, total_trades, started_at, completed_at "
        "FROM backtest_runs WHERE run_id = ?",
        (backtest_id,),
    ).fetchone()

    if row is None:
        raise AnalysisError("evidence_pack", f"Backtest run not found: {backtest_id}")

    return dict(row)


def _load_trades(conn: sqlite3.Connection, backtest_id: str) -> list[dict[str, Any]]:
    """Load trade data for metrics and distribution."""
    rows = conn.execute(
        "SELECT trade_id, direction, entry_time, exit_time, "
        "pnl_pips, session, lot_size "
        "FROM trades WHERE backtest_run_id = ? ORDER BY entry_time",
        (backtest_id,),
    ).fetchall()
    return [dict(r) for r in rows]


def _find_version_dir(
    strategy_id: str, backtest_id: str, artifacts_root: Path,
) -> Path:
    """Find the backtest version directory for a given run.

    Scans version directories to find one containing a manifest that
    references the given backtest_id, or falls back to the latest version.
    """
    strategy_dir = artifacts_root / strategy_id
    if not strategy_dir.exists():
        raise AnalysisError(
            "evidence_pack",
            f"Strategy directory not found: {strategy_dir}",
        )

    # Scan version directories in reverse order (latest first)
    version_dirs = sorted(
        [d for d in strategy_dir.iterdir() if d.is_dir() and d.name.startswith("v")],
        reverse=True,
    )

    for vdir in version_dirs:
        backtest_dir = vdir / "backtest"
        if not backtest_dir.exists():
            continue

        manifest_path = backtest_dir / "manifest.json"
        if manifest_path.exists():
            try:
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                if manifest.get("backtest_run_id") == backtest_id:
                    return backtest_dir
            except (json.JSONDecodeError, OSError):
                continue

    # Fallback: only safe when exactly one version exists
    if len(version_dirs) == 1:
        backtest_dir = version_dirs[0] / "backtest"
        if backtest_dir.exists():
            return backtest_dir

    if len(version_dirs) > 1:
        raise AnalysisError(
            "evidence_pack",
            f"Multiple version directories exist for {strategy_id} but none "
            f"has a manifest matching backtest_id={backtest_id}. "
            f"Cannot determine which version to use.",
        )

    raise AnalysisError(
        "evidence_pack",
        f"No version directory found for {strategy_id}",
    )


def _downsample_equity_curve(
    arrow_path: Path, max_points: int = 500,
) -> list[dict[str, Any]]:
    """Load equity curve from Arrow IPC and downsample to max_points.

    Uses streaming two-pass approach to avoid loading entire equity curves
    into memory (anti-pattern #2 — curves can be ~125 MB Arrow IPC).

    Pass 1: Count total rows across all record batches.
    Pass 2: Extract only the rows at stride indices.
    """
    if not arrow_path.exists():
        logger.warning(
            "Equity curve file not found, returning empty summary",
            extra={
                "component": "pipeline.analysis.evidence_pack",
                "ctx": {"path": str(arrow_path)},
            },
        )
        return []

    reader = pyarrow.ipc.open_file(str(arrow_path))
    num_batches = reader.num_record_batches

    # Pass 1: Count total rows across all batches
    total_rows = sum(
        reader.get_batch(i).num_rows for i in range(num_batches)
    )

    if total_rows == 0:
        return []

    if total_rows <= max_points:
        # Small enough to return all points — stream batch-by-batch
        points: list[dict[str, Any]] = []
        for i in range(num_batches):
            batch = reader.get_batch(i)
            ts_col = batch.column("timestamp").to_pylist()
            eq_col = batch.column("equity_pips").to_pylist()
            dd_col = batch.column("drawdown_pct").to_pylist()
            for row_idx in range(batch.num_rows):
                points.append({
                    "timestamp": ts_col[row_idx],
                    "equity": eq_col[row_idx],
                    "drawdown_pct": dd_col[row_idx],
                })
        return points

    # Pass 2: Compute stride and extract only needed rows
    stride = total_rows / (max_points - 1)
    # Build set of global row indices to sample (always include last)
    target_indices: set[int] = {int(i * stride) for i in range(max_points - 1)}
    target_indices.add(total_rows - 1)

    sampled: list[dict[str, Any]] = []
    global_offset = 0
    for i in range(num_batches):
        batch = reader.get_batch(i)
        batch_end = global_offset + batch.num_rows

        # Find which target indices fall in this batch
        local_targets = sorted(
            idx - global_offset
            for idx in target_indices
            if global_offset <= idx < batch_end
        )

        if local_targets:
            # Convert columns to Python lists once per batch (not per-row)
            ts_col = batch.column("timestamp").to_pylist()
            eq_col = batch.column("equity_pips").to_pylist()
            dd_col = batch.column("drawdown_pct").to_pylist()
            for local_idx in local_targets:
                sampled.append({
                    "timestamp": ts_col[local_idx],
                    "equity": eq_col[local_idx],
                    "drawdown_pct": dd_col[local_idx],
                })

        global_offset = batch_end

    return sampled


def _compute_trade_distribution(trades: list[dict[str, Any]]) -> dict[str, Any]:
    """Compute trade distribution by session and by month."""
    by_session: dict[str, int] = {}
    for session in _SESSIONS:
        count = sum(1 for t in trades if t.get("session") == session)
        if count > 0:
            by_session[session] = count

    by_month: Counter[str] = Counter()
    for t in trades:
        entry = t.get("entry_time")
        if entry and isinstance(entry, str):
            month_key = entry[:7]
            by_month[month_key] += 1

    return {
        "by_session": by_session,
        "by_month": dict(sorted(by_month.items())),
    }
