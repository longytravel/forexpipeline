"""Confidence scoring orchestrator (Story 5.5, Task 9).

Processes candidates sequentially — scoring is lightweight CPU work.
Scores and persists one candidate at a time (anti-pattern #6).
"""
from __future__ import annotations

import json
from pathlib import Path

from artifacts.storage import crash_safe_write_json
from confidence.anomaly_layer import run_layer_a, run_layer_b
from confidence.config import ConfidenceConfig
from confidence.evidence_builder import (
    build_decision_trace,
    build_evidence_pack,
    build_triage_summary,
    persist_evidence_pack,
)
from confidence.models import ValidationEvidencePack
from confidence.narrative_engine import generate_confidence_narrative
from confidence.scorer import score_candidate
from confidence.visualization import prepare_all_visualizations
from logging_setup.setup import get_logger

logger = get_logger("confidence.orchestrator")


class ConfidenceOrchestrator:
    """Orchestrate confidence scoring for all candidates."""

    def __init__(self, config: ConfidenceConfig):
        self._config = config

    def score_all_candidates(
        self,
        gauntlet_results_dir: Path,
        optimization_manifest: dict,
        output_dir: Path,
    ) -> Path:
        """Score all candidates, persist each evidence pack immediately.

        Returns path to aggregate scoring manifest.
        """
        manifests = self._load_gauntlet_manifests(gauntlet_results_dir)

        if not manifests:
            logger.warning(
                "No gauntlet manifests found",
                extra={"component": "confidence.orchestrator", "ctx": {
                    "gauntlet_results_dir": str(gauntlet_results_dir),
                }},
            )
            # Write empty manifest
            return self._write_aggregate_manifest([], output_dir, optimization_manifest)

        logger.info(
            f"Scoring {len(manifests)} candidates",
            extra={"component": "confidence.orchestrator", "ctx": {
                "n_candidates": len(manifests),
                "output_dir": str(output_dir),
            }},
        )

        # Run anomaly detection across all candidates first (Layer A needs all)
        layer_a_scores = run_layer_a(
            manifests,
            min_population_size=self._config.anomaly.min_population_size,
        )
        anomaly_reports = run_layer_b(manifests, layer_a_scores)

        # Score and persist each candidate
        evidence_packs: list[ValidationEvidencePack] = []
        for manifest in manifests:
            pack = self.score_single_candidate(manifest, anomaly_reports)
            evidence_packs.append(pack)
            # Persist immediately — don't hold all in memory (anti-pattern #6)
            persist_evidence_pack(pack, output_dir)
            logger.info(
                f"Scored candidate {pack.candidate_id}: {pack.confidence_score.rating.value}",
                extra={"component": "confidence.orchestrator", "ctx": {
                    "candidate_id": pack.candidate_id,
                    "rating": pack.confidence_score.rating.value,
                    "composite_score": pack.confidence_score.composite_score,
                }},
            )

        return self._write_aggregate_manifest(
            evidence_packs, output_dir, optimization_manifest
        )

    def score_single_candidate(
        self,
        candidate_manifest: dict,
        anomaly_reports: dict,
    ) -> ValidationEvidencePack:
        """Full pipeline: gates → score → anomaly → narrative → viz → evidence pack."""
        cid = candidate_manifest.get("candidate_id", 0)

        # Score
        confidence_score = score_candidate(candidate_manifest, self._config)

        # Get anomaly report for this candidate
        from analysis.models import AnomalyReport
        anomaly_report = anomaly_reports.get(
            cid,
            AnomalyReport(backtest_id=f"cand_{cid}", anomalies=[], run_timestamp=""),
        )

        # Narrative
        narrative = generate_confidence_narrative(
            confidence_score, candidate_manifest, anomaly_report,
        )

        # Visualization refs
        viz_refs = prepare_all_visualizations(candidate_manifest)

        # Build triage summary
        triage = build_triage_summary(confidence_score, candidate_manifest)

        # Build decision trace
        decision_trace = build_decision_trace(
            confidence_score, self._config, candidate_manifest,
        )

        # Assemble evidence pack
        return build_evidence_pack(
            candidate_id=cid,
            confidence_score=confidence_score,
            triage_summary=triage,
            decision_trace=decision_trace,
            gauntlet_manifest=candidate_manifest,
            anomaly_report=anomaly_report,
            narrative=narrative,
            visualization_refs=viz_refs,
        )

    def _load_gauntlet_manifests(
        self, gauntlet_results_dir: Path,
    ) -> list[dict]:
        """Load per-candidate gauntlet manifests from results directory."""
        manifests = []
        if not gauntlet_results_dir.exists():
            return manifests

        # Look for per-candidate manifest files
        for manifest_file in sorted(gauntlet_results_dir.glob("gauntlet-manifest-candidate-*.json")):
            try:
                with open(manifest_file, "r", encoding="utf-8") as f:
                    manifests.append(json.load(f))
            except (json.JSONDecodeError, OSError) as e:
                logger.error(
                    f"Failed to load manifest: {manifest_file}: {e}",
                    extra={"component": "confidence.orchestrator"},
                )

        # Also try single gauntlet manifest with candidates array
        single_manifest = gauntlet_results_dir / "gauntlet-manifest.json"
        if single_manifest.exists() and not manifests:
            try:
                with open(single_manifest, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if "candidates" in data:
                    manifests.extend(data["candidates"])
                else:
                    manifests.append(data)
            except (json.JSONDecodeError, OSError) as e:
                logger.error(
                    f"Failed to load single manifest: {e}",
                    extra={"component": "confidence.orchestrator"},
                )

        return manifests

    def _write_aggregate_manifest(
        self,
        evidence_packs: list[ValidationEvidencePack],
        output_dir: Path,
        optimization_manifest: dict,
    ) -> Path:
        """Write aggregate scoring manifest sorted by composite score descending."""
        # Sort by composite score descending
        sorted_packs = sorted(
            evidence_packs,
            key=lambda p: p.confidence_score.composite_score,
            reverse=True,
        )

        scored_at = ""
        config_hash = ""
        if sorted_packs:
            scored_at = sorted_packs[0].confidence_score.scored_at
            config_hash = sorted_packs[0].decision_trace.confidence_config_hash

        manifest = {
            "optimization_run_id": optimization_manifest.get("optimization_run_id", ""),
            "confidence_config_hash": config_hash,
            "scored_at": scored_at,
            "candidates": [
                {
                    "candidate_id": p.candidate_id,
                    "rating": p.confidence_score.rating.value,
                    "composite_score": p.confidence_score.composite_score,
                    "hard_gates_passed": p.confidence_score.breakdown.hard_gate_passed,
                    "triage_summary_path": str(
                        output_dir / f"evidence-triage-candidate-{p.candidate_id}.json"
                    ),
                    "evidence_pack_path": str(
                        output_dir / f"evidence-pack-candidate-{p.candidate_id}.json"
                    ),
                }
                for p in sorted_packs
            ],
        }

        manifest_path = output_dir / "scoring-manifest.json"
        crash_safe_write_json(manifest, manifest_path)

        logger.info(
            f"Aggregate scoring manifest written with {len(sorted_packs)} candidates",
            extra={"component": "confidence.orchestrator", "ctx": {
                "manifest_path": str(manifest_path),
                "n_green": sum(1 for p in sorted_packs if p.confidence_score.rating.value == "GREEN"),
                "n_yellow": sum(1 for p in sorted_packs if p.confidence_score.rating.value == "YELLOW"),
                "n_red": sum(1 for p in sorted_packs if p.confidence_score.rating.value == "RED"),
            }},
        )

        return manifest_path
