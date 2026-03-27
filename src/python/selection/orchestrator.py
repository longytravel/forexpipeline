"""SelectionOrchestrator — coordinates the full selection pipeline (Story 5.6, Task 7).

Orchestrates: clustering → quality metrics → ranking funnel → diversity selection → manifest.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pyarrow as pa
import pyarrow.ipc as ipc

from logging_setup.setup import get_logger
from selection.clustering import (
    cluster_candidates,
    compute_cluster_summaries,
    compute_gower_distance,
    pre_filter_candidates,
)
from selection.config import SelectionConfig
from selection.diversity import (
    BehaviorDimension,
    build_diversity_archive,
    define_behavior_dimensions,
    select_diverse_candidates,
)
from selection.equity_curve_quality import compute_all_quality_metrics
from selection.models import (
    EquityCurveQuality,
    FunnelStats,
    SelectionManifest,
    UpstreamRefs,
)
from selection.ranking import four_stage_funnel
from selection.visualization import (
    prepare_cluster_membership,
    prepare_parallel_coordinates,
    prepare_parameter_heatmap,
)

logger = get_logger("selection.orchestrator")


class SelectionOrchestrator:
    """Coordinates the full advanced candidate selection pipeline."""

    def run_selection(
        self,
        candidates_path: Path,
        equity_curves_dir: Path | None,
        scoring_manifest_path: Path | None,
        config: SelectionConfig,
        hard_gate_config: dict[str, Any],
        output_dir: Path,
        optimization_run_id: str,
        strategy_id: str,
    ) -> SelectionManifest:
        """Run the full selection pipeline.

        Args:
            candidates_path: Path to candidates.arrow file.
            equity_curves_dir: Directory with per-candidate equity curve files.
            scoring_manifest_path: Optional path to scoring manifest.json.
            config: Selection configuration.
            hard_gate_config: Hard gate thresholds from [confidence.hard_gates].
            output_dir: Output directory for manifest and viz data.
            optimization_run_id: Run ID for seed derivation and provenance.
            strategy_id: Strategy identifier.

        Returns:
            Completed SelectionManifest.
        """
        seed = config.resolve_seed(optimization_run_id)

        # ── Load candidates ──
        candidates = self._load_candidates(candidates_path)
        candidates_hash = self._compute_file_hash(candidates_path)

        # Track original count before filtering (for DSR n_trials)
        total_candidates_tested = len(candidates)

        # Pre-filter if too many candidates
        candidates = pre_filter_candidates(candidates, config.max_clustering_candidates)

        # Deduplicate by params_json (keep best cv_objective)
        candidates = self._deduplicate_candidates(candidates)

        n_candidates = len(candidates)
        logger.info(
            "Selection pipeline starting",
            extra={
                "component": "selection.orchestrator",
                "ctx": {
                    "n_candidates": n_candidates,
                    "strategy_id": strategy_id,
                    "seed": seed,
                },
            },
        )

        # ── Extract param columns and expand params_json into table ──
        candidates, param_columns = self._expand_param_columns(candidates)

        # ── Clustering ──
        # Extract actual candidate IDs for correct cluster assignment
        candidate_ids = (
            [int(x) for x in candidates.column("candidate_id").to_pylist()]
            if "candidate_id" in candidates.column_names
            else list(range(n_candidates))
        )
        distance_matrix = compute_gower_distance(candidates, param_columns)
        cluster_assignments = cluster_candidates(distance_matrix, config, candidate_ids=candidate_ids)
        cluster_summaries = compute_cluster_summaries(
            candidates, cluster_assignments, param_columns
        )

        # ── Equity curve quality ──
        quality_metrics = self._compute_quality_metrics(
            candidates, equity_curves_dir, n_candidates, total_candidates_tested
        )

        # ── Load scoring manifests (optional) ──
        scoring_manifests = self._load_scoring_manifests(scoring_manifest_path)
        scoring_hash = self._compute_file_hash(scoring_manifest_path) if scoring_manifest_path else None

        # ── 4-stage funnel ──
        funnel_survivors, funnel_stats, critic_weights, gate_failure_summary = four_stage_funnel(
            candidates,
            quality_metrics,
            cluster_assignments,
            config,
            hard_gate_config,
            scoring_manifests,
        )

        # ── Diversity archive + selection ──
        dimensions = define_behavior_dimensions(config)
        behavior_data = self._extract_behavior_data(candidates, quality_metrics)
        archive = build_diversity_archive(funnel_survivors, behavior_data, dimensions)

        selected = select_diverse_candidates(
            archive,
            funnel_survivors,
            config.target_candidates,
            config.deterministic_ratio,
            seed,
        )

        funnel_stats = FunnelStats(
            total_input=funnel_stats.total_input,
            after_hard_gates=funnel_stats.after_hard_gates,
            after_topsis=funnel_stats.after_topsis,
            after_stability=funnel_stats.after_stability,
            after_pareto=funnel_stats.after_pareto,
            final_selected=len(selected),
        )

        # ── Visualization data ──
        viz_data = self._prepare_viz_data(
            selected, funnel_survivors, cluster_assignments, cluster_summaries,
            candidates, param_columns, quality_metrics,
        )

        # ── Build manifest ──
        manifest = SelectionManifest(
            strategy_id=strategy_id,
            optimization_run_id=optimization_run_id,
            selected_candidates=selected,
            clusters=cluster_summaries,
            diversity_archive=archive,
            funnel_stats=funnel_stats,
            config_hash=config.config_hash(),
            selected_at=datetime.now(timezone.utc).isoformat(),
            upstream_refs=UpstreamRefs(
                candidates_path=str(candidates_path),
                candidates_hash=candidates_hash,
                scoring_manifest_path=str(scoring_manifest_path) if scoring_manifest_path else None,
                scoring_manifest_hash=scoring_hash,
            ),
            critic_weights=critic_weights,
            gate_failure_summary=gate_failure_summary,
            random_seed_used=seed,
        )

        logger.info(
            "Selection pipeline complete",
            extra={
                "component": "selection.orchestrator",
                "ctx": {
                    "selected": len(selected),
                    "clusters": len(cluster_summaries),
                    "archive_cells": len(archive),
                },
            },
        )

        return manifest, viz_data

    def _load_candidates(self, path: Path) -> pa.Table:
        """Load candidates from Arrow IPC file."""
        with pa.ipc.open_file(path) as reader:
            return reader.read_all()

    def _compute_file_hash(self, path: Path | None) -> str:
        """Compute SHA-256 hash of a file for provenance."""
        if path is None or not path.exists():
            return ""
        h = hashlib.sha256()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                h.update(chunk)
        return f"sha256:{h.hexdigest()}"

    def _deduplicate_candidates(self, candidates: pa.Table) -> pa.Table:
        """Deduplicate candidates with identical params_json, keeping best cv_objective."""
        if "params_json" not in candidates.column_names:
            return candidates

        df = candidates.to_pandas()
        if "cv_objective" in df.columns:
            df = df.sort_values("cv_objective", ascending=False)
        df = df.drop_duplicates(subset=["params_json"], keep="first")

        if len(df) < len(candidates):
            logger.info(
                "Deduplicated candidates",
                extra={
                    "component": "selection.orchestrator",
                    "ctx": {"before": len(candidates), "after": len(df)},
                },
            )

        return pa.Table.from_pandas(df, preserve_index=False)

    def _expand_param_columns(self, candidates: pa.Table) -> tuple[pa.Table, list[str]]:
        """Expand params_json into individual columns in the table.

        If params_json column exists, parse it and add individual parameter
        columns to the table. Returns the expanded table and param column names.
        """
        df = candidates.to_pandas()

        if "params_json" in df.columns:
            # Parse first non-null params_json to get parameter names
            for val in df["params_json"]:
                if val is not None:
                    try:
                        params = json.loads(val) if isinstance(val, str) else val
                        param_names = list(params.keys())
                        # Expand params_json into columns
                        for name in param_names:
                            if name not in df.columns:
                                df[name] = df["params_json"].apply(
                                    lambda x: json.loads(x).get(name) if isinstance(x, str) else (x or {}).get(name)
                                )
                        expanded = pa.Table.from_pandas(df, preserve_index=False)
                        return expanded, param_names
                    except (json.JSONDecodeError, AttributeError):
                        break

        # Fallback: use numeric columns that aren't metadata
        metadata_cols = {
            "candidate_id", "rank", "cv_objective", "branch",
            "instance_type", "fold_scores", "params_json",
        }
        param_cols = [
            col for col in df.columns
            if col not in metadata_cols and df[col].dtype in [np.float64, np.float32, np.int64, np.int32]
        ]
        return candidates, param_cols

    def _compute_quality_metrics(
        self,
        candidates: pa.Table,
        equity_curves_dir: Path | None,
        n_candidates: int,
        total_candidates_tested: int | None = None,
    ) -> list[EquityCurveQuality]:
        """Compute equity curve quality metrics per candidate.

        Streams equity curves from disk — does NOT accumulate in memory.
        """
        df = candidates.to_pandas()
        metrics: list[EquityCurveQuality] = []
        n_synthetic = 0
        # Use total optimization trial count for DSR, not filtered count
        n_trials = total_candidates_tested if total_candidates_tested else n_candidates

        for idx in range(n_candidates):
            cid = int(df.iloc[idx].get("candidate_id", idx))
            using_synthetic = True

            equity_curve = np.array([100.0, 110.0, 105.0, 115.0, 120.0])
            returns = np.diff(equity_curve) / equity_curve[:-1]

            if equity_curves_dir and equity_curves_dir.exists():
                ec_path = equity_curves_dir / f"candidate_{cid}_equity.npy"
                if ec_path.exists():
                    equity_curve = np.load(ec_path)
                    returns = np.diff(equity_curve) / np.where(
                        equity_curve[:-1] != 0, equity_curve[:-1], 1.0
                    )
                    using_synthetic = False

            if using_synthetic:
                n_synthetic += 1

            # Get Sharpe info from fold_scores if available
            fold_scores = df.iloc[idx].get("fold_scores")
            if fold_scores is not None and hasattr(fold_scores, '__len__') and len(fold_scores) > 1:
                sharpe = float(np.mean(fold_scores))
                sharpe_std = float(np.std(fold_scores))
            else:
                sharpe = float(df.iloc[idx].get("cv_objective", 0.0))
                sharpe_std = 0.1

            m = compute_all_quality_metrics(
                candidate_id=cid,
                equity_curve=equity_curve,
                returns=returns,
                sharpe=sharpe,
                n_trials=n_trials,
                sharpe_std=max(sharpe_std, 0.01),
            )
            metrics.append(m)

        if n_synthetic > 0:
            logger.warning(
                "Equity curve quality uses synthetic fallback curves — "
                "metrics will be identical for affected candidates",
                extra={
                    "component": "selection.orchestrator",
                    "ctx": {
                        "n_synthetic": n_synthetic,
                        "n_total": n_candidates,
                        "limitation": "AC #2 quality metrics are placeholders until "
                            "equity curve artifacts are materialized by upstream stages",
                    },
                },
            )

        return metrics

    def _load_scoring_manifests(
        self, scoring_manifest_path: Path | None
    ) -> dict[int, dict] | None:
        """Load per-candidate scoring manifests if available."""
        if scoring_manifest_path is None or not scoring_manifest_path.exists():
            return None

        try:
            with open(scoring_manifest_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            # Handle both single manifest and list of manifests
            if isinstance(data, list):
                return {m["candidate_id"]: m for m in data if "candidate_id" in m}
            elif isinstance(data, dict) and "candidates" in data:
                return {m["candidate_id"]: m for m in data["candidates"] if "candidate_id" in m}
            return None
        except (json.JSONDecodeError, OSError) as e:
            logger.warning(
                "Failed to load scoring manifests — proceeding without",
                extra={"component": "selection.orchestrator", "ctx": {"error": str(e)}},
            )
            return None

    def _extract_behavior_data(
        self,
        candidates: pa.Table,
        quality_metrics: list[EquityCurveQuality],
    ) -> dict[int, dict[str, float]]:
        """Extract behavior dimensions data for diversity archive.

        Uses available metrics; missing dimensions get defaults.
        """
        df = candidates.to_pandas()
        quality_map = {q.candidate_id: q for q in quality_metrics}
        behavior: dict[int, dict[str, float]] = {}
        n_defaults = 0
        available_cols = set(df.columns)
        behavior_cols = {"trade_count", "avg_holding_time", "win_rate"}

        for idx in range(len(df)):
            cid = int(df.iloc[idx].get("candidate_id", idx))
            q = quality_map.get(cid)
            uses_default = not behavior_cols.intersection(available_cols)

            if uses_default:
                n_defaults += 1

            behavior[cid] = {
                "trade_frequency": float(df.iloc[idx].get("trade_count", 100)),
                "avg_holding_time": float(df.iloc[idx].get("avg_holding_time", 120)),
                "win_rate": float(df.iloc[idx].get("win_rate", 0.5)),
                "max_drawdown": float(q.ulcer_index / 100.0 if q else 0.1),
            }

        if n_defaults > 0:
            logger.warning(
                "Behavior dimensions using default values — diversity archive "
                "may not reflect actual candidate trading behavior",
                extra={
                    "component": "selection.orchestrator",
                    "ctx": {
                        "n_defaults": n_defaults,
                        "n_total": len(df),
                        "limitation": "AC #5 behavior dimensions are estimated proxies "
                            "until trade-level stats are piped into behavior extraction",
                    },
                },
            )

        return behavior

    def _prepare_viz_data(
        self,
        selected: list,
        funnel_survivors: list,
        cluster_assignments: list,
        cluster_summaries: list,
        candidates: pa.Table,
        param_columns: list[str] | None = None,
        quality_metrics: list[EquityCurveQuality] | None = None,
    ) -> dict[str, Any]:
        """Prepare all visualization data."""
        df = candidates.to_pandas()
        selected_ids = {rc.candidate_id for rc in selected}

        # Build quality metrics lookup
        q_map = {q.candidate_id: q for q in (quality_metrics or [])}

        # Params for parallel coordinates — populate with actual values
        params: dict[int, dict[str, float]] = {}
        quality: dict[int, dict[str, float]] = {}
        for rc in funnel_survivors:
            cid = rc.candidate_id
            # Extract actual parameter values for this candidate
            p: dict[str, float] = {}
            if param_columns:
                row = df[df["candidate_id"] == cid] if "candidate_id" in df.columns else df.iloc[[0]]
                if not row.empty:
                    for col in param_columns:
                        if col in row.columns:
                            val = row.iloc[0][col]
                            try:
                                p[col] = float(val)
                            except (ValueError, TypeError):
                                pass
            params[cid] = p

            # Populate quality metrics
            q_data: dict[str, float] = {"topsis_score": rc.topsis_score}
            q = q_map.get(cid)
            if q:
                q_data["k_ratio"] = q.k_ratio
                q_data["ulcer_index"] = q.ulcer_index
                q_data["gain_to_pain"] = q.gain_to_pain
                q_data["serenity_ratio"] = q.serenity_ratio
            quality[cid] = q_data

        return {
            "parallel_coordinates": prepare_parallel_coordinates(
                selected, params, quality
            ),
            "parameter_heatmap": prepare_parameter_heatmap(cluster_summaries),
            "cluster_membership": prepare_cluster_membership(
                cluster_assignments, selected_ids
            ),
        }
