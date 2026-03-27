"""Validation gauntlet orchestrator with checkpointing (Story 5.4, Task 9).

Runs candidates through validation stages in configured order:
perturbation -> walk_forward -> cpcv -> monte_carlo -> regime.

Short-circuits on validity gates ONLY (PBO, DSR) — performance metrics
are recorded but do NOT trigger short-circuit per FR41.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

from artifacts.storage import crash_safe_write_json
from logging_setup.setup import get_logger
from validation.config import ValidationConfig
from validation.cpcv import CPCVResult, run_cpcv
from validation.dsr import DSRResult, compute_dsr
from validation.monte_carlo import MonteCarloResult, run_monte_carlo
from validation.perturbation import PerturbationResult, run_perturbation
from validation.regime_analysis import RegimeResult, run_regime_analysis
from validation.walk_forward import WalkForwardResult, run_walk_forward

logger = get_logger("validation.gauntlet")


@dataclass
class StageOutput:
    stage_name: str
    result: Any
    passed: bool  # For gated stages (PBO, DSR); True for non-gated
    metrics: dict = field(default_factory=dict)


@dataclass
class CandidateValidation:
    candidate_id: int
    stages: dict[str, StageOutput] = field(default_factory=dict)
    short_circuited: bool = False
    hard_gate_failures: list[str] = field(default_factory=list)
    is_oos_divergence: float = 0.0


@dataclass
class GauntletState:
    """Serializable gauntlet checkpoint state."""
    candidates_progress: dict[int, dict[str, str]]  # cid -> {stage: status}
    completed_results: dict[int, dict]  # cid -> serialized CandidateValidation
    run_id: str = ""
    rng_state: dict = field(default_factory=dict)


@dataclass
class GauntletResults:
    candidates: list[CandidateValidation]
    dsr: DSRResult | None = None
    run_manifest: dict = field(default_factory=dict)


class ValidationGauntlet:
    """Orchestrates candidates through the validation gauntlet."""

    def __init__(self, config: ValidationConfig, dispatcher=None):
        self._config = config
        self._dispatcher = dispatcher
        self._stage_runners = {
            "perturbation": self._run_perturbation,
            "walk_forward": self._run_walk_forward,
            "cpcv": self._run_cpcv,
            "monte_carlo": self._run_monte_carlo,
            "regime": self._run_regime,
        }

    def run(
        self,
        candidates: list[dict],
        market_data_path: Path,
        strategy_spec: dict,
        cost_model: dict,
        optimization_manifest: dict,
        output_dir: Path | None = None,
        param_ranges: dict | None = None,
        trade_results=None,
        market_data_table=None,
        data_length: int | None = None,
    ) -> GauntletResults:
        """Run all candidates through validation stages in configured order."""
        # Deterministic run_id from seed + candidate count for reproducibility (FR18)
        run_id_input = f"{self._config.deterministic_seed_base}-{len(candidates)}"
        run_id = hashlib.sha256(run_id_input.encode()).hexdigest()[:8]
        checkpoint_path = output_dir / "gauntlet_checkpoint.json" if output_dir else None

        # Resume from checkpoint if available (NFR5)
        resumed_state = None
        if checkpoint_path and checkpoint_path.exists():
            resumed_state = self.resume(checkpoint_path)
            if resumed_state:
                run_id = resumed_state.run_id or run_id
                logger.info(
                    "Resuming gauntlet from checkpoint",
                    extra={
                        "component": "validation.gauntlet",
                        "ctx": {"run_id": run_id},
                    },
                )

        logger.info(
            f"Gauntlet starting: {len(candidates)} candidates, "
            f"stages={self._config.stage_order}",
            extra={
                "component": "validation.gauntlet",
                "ctx": {
                    "run_id": run_id,
                    "n_candidates": len(candidates),
                    "stages": self._config.stage_order,
                },
            },
        )

        candidate_results: list[CandidateValidation] = []
        walk_forward_results: dict[int, WalkForwardResult] = {}

        for cid, candidate_params in enumerate(candidates):
            cv = CandidateValidation(candidate_id=cid)

            for stage_idx, stage_name in enumerate(self._config.stage_order):
                # Skip stages already completed in resumed checkpoint
                if (
                    resumed_state
                    and str(cid) in resumed_state.candidates_progress
                    and stage_name in resumed_state.candidates_progress[str(cid)]
                ):
                    logger.info(
                        f"Skipping {stage_name} for candidate {cid} (resumed)",
                        extra={"component": "validation.gauntlet"},
                    )
                    continue

                if stage_name not in self._stage_runners:
                    logger.warning(
                        f"Unknown stage '{stage_name}', skipping",
                        extra={"component": "validation.gauntlet"},
                    )
                    continue

                # Check short-circuit before running stage
                if self._should_short_circuit(cv):
                    cv.short_circuited = True
                    logger.info(
                        f"Candidate {cid} short-circuited after hard gate failure: "
                        f"{cv.hard_gate_failures}",
                        extra={
                            "component": "validation.gauntlet",
                            "ctx": {
                                "candidate_id": cid,
                                "failures": cv.hard_gate_failures,
                            },
                        },
                    )
                    break

                # Deterministic seeding: base + cid*1000 + stage_index
                seed = self._config.deterministic_seed_base + cid * 1000 + stage_idx

                logger.info(
                    f"Running {stage_name} for candidate {cid}",
                    extra={
                        "component": "validation.gauntlet",
                        "ctx": {
                            "candidate_id": cid,
                            "stage": stage_name,
                            "seed": seed,
                        },
                    },
                )

                context = {
                    "candidate": candidate_params,
                    "market_data_path": market_data_path,
                    "strategy_spec": strategy_spec,
                    "cost_model": cost_model,
                    "seed": seed,
                    "param_ranges": param_ranges,
                    "data_length": data_length,
                    "trade_results": trade_results,
                    "market_data_table": market_data_table,
                    "walk_forward_result": walk_forward_results.get(cid),
                }

                stage_output = self._run_stage(stage_name, context)
                cv.stages[stage_name] = stage_output

                # Track walk-forward results for Monte Carlo consumption
                if stage_name == "walk_forward" and isinstance(stage_output.result, WalkForwardResult):
                    walk_forward_results[cid] = stage_output.result
                    cv.is_oos_divergence = stage_output.result.is_oos_divergence

                # Check hard gates
                if not stage_output.passed:
                    cv.hard_gate_failures.append(stage_name)

                # Checkpoint after each (candidate, stage) — save ALL progress
                if checkpoint_path:
                    all_progress = {}
                    for prev_cv in candidate_results:
                        all_progress[prev_cv.candidate_id] = {
                            s: "complete" for s in prev_cv.stages
                        }
                    # Include current candidate's progress
                    all_progress[cid] = {s: "complete" for s in cv.stages}
                    self._checkpoint(
                        GauntletState(
                            candidates_progress=all_progress,
                            completed_results={},
                            run_id=run_id,
                        ),
                        checkpoint_path,
                    )

            candidate_results.append(cv)

        # DSR: computed once after all candidates complete walk-forward
        dsr_result = self._compute_dsr_if_needed(
            candidate_results, optimization_manifest, walk_forward_results
        )

        # Wire DSR hard gate back to candidates (D11)
        if dsr_result and not dsr_result.passed:
            for cv in candidate_results:
                if not cv.short_circuited:
                    cv.hard_gate_failures.append("dsr")

        results = GauntletResults(
            candidates=candidate_results,
            dsr=dsr_result,
            run_manifest={
                "run_id": run_id,
                "n_candidates": len(candidates),
                "stages": self._config.stage_order,
                "optimization_run_id": optimization_manifest.get("run_id", ""),
                "total_optimization_trials": optimization_manifest.get(
                    "total_trials", 0
                ),
            },
        )

        logger.info(
            f"Gauntlet complete: {len(candidate_results)} candidates processed",
            extra={
                "component": "validation.gauntlet",
                "ctx": {
                    "run_id": run_id,
                    "n_short_circuited": sum(
                        1 for c in candidate_results if c.short_circuited
                    ),
                    "dsr_passed": dsr_result.passed if dsr_result else None,
                },
            },
        )

        return results

    def resume(self, checkpoint_path: Path) -> GauntletState | None:
        """Load gauntlet state from checkpoint file."""
        if not checkpoint_path.exists():
            return None
        data = json.loads(checkpoint_path.read_text(encoding="utf-8"))
        return GauntletState(
            candidates_progress=data.get("candidates_progress", {}),
            completed_results=data.get("completed_results", {}),
            run_id=data.get("run_id", ""),
            rng_state=data.get("rng_state", {}),
        )

    def _run_stage(self, stage_name: str, context: dict) -> StageOutput:
        """Dispatch to appropriate validator based on stage name."""
        runner = self._stage_runners[stage_name]
        return runner(context)

    def _run_walk_forward(self, context: dict) -> StageOutput:
        result = run_walk_forward(
            candidate=context["candidate"],
            market_data_path=context["market_data_path"],
            strategy_spec=context["strategy_spec"],
            cost_model=context["cost_model"],
            config=self._config.walk_forward,
            dispatcher=self._dispatcher,
            seed=context["seed"],
            data_length=context.get("data_length"),
        )
        return StageOutput(
            stage_name="walk_forward",
            result=result,
            passed=True,  # Walk-forward has no hard gate
            metrics={
                "aggregate_sharpe": result.aggregate_sharpe,
                "aggregate_pf": result.aggregate_pf,
                "is_oos_divergence": result.is_oos_divergence,
                "n_windows": len(result.windows),
            },
        )

    def _run_cpcv(self, context: dict) -> StageOutput:
        result = run_cpcv(
            candidate=context["candidate"],
            market_data_path=context["market_data_path"],
            strategy_spec=context["strategy_spec"],
            cost_model=context["cost_model"],
            config=self._config.cpcv,
            dispatcher=self._dispatcher,
            seed=context["seed"],
            data_length=context.get("data_length"),
        )
        return StageOutput(
            stage_name="cpcv",
            result=result,
            passed=result.pbo_gate_passed,  # PBO > 0.40 = hard RED gate
            metrics={
                "pbo": result.pbo,
                "pbo_gate_passed": result.pbo_gate_passed,
                "mean_oos_sharpe": result.mean_oos_sharpe,
            },
        )

    def _run_perturbation(self, context: dict) -> StageOutput:
        result = run_perturbation(
            candidate=context["candidate"],
            market_data_path=context["market_data_path"],
            strategy_spec=context["strategy_spec"],
            cost_model=context["cost_model"],
            config=self._config.perturbation,
            dispatcher=self._dispatcher,
            seed=context["seed"],
            param_ranges=context.get("param_ranges"),
        )
        return StageOutput(
            stage_name="perturbation",
            result=result,
            passed=True,  # Perturbation has no hard gate
            metrics={
                "max_sensitivity": result.max_sensitivity,
                "fragile_params": result.fragile_params,
            },
        )

    def _run_monte_carlo(self, context: dict) -> StageOutput:
        # Monte Carlo operates on trade results, not raw market data
        trade_results = context.get("trade_results")
        if trade_results is None:
            logger.warning(
                "Monte Carlo skipped: no trade_results provided",
                extra={"component": "validation.gauntlet"},
            )
            return StageOutput(
                stage_name="monte_carlo",
                result=None,
                passed=True,  # Not a hard gate — just missing data
                metrics={"skipped": True, "reason": "no_trade_results"},
            )

        result = run_monte_carlo(
            trade_results=trade_results,
            equity_curve=None,
            cost_model=context["cost_model"],
            config=self._config.monte_carlo,
            seed=context["seed"],
        )
        return StageOutput(
            stage_name="monte_carlo",
            result=result,
            passed=True,  # Monte Carlo has no hard gate
            metrics={
                "bootstrap_sharpe_ci_lower": result.bootstrap.sharpe_ci_lower
                if result.bootstrap else 0.0,
                "permutation_p_value": result.permutation.p_value
                if result.permutation else 1.0,
            },
        )

    def _run_regime(self, context: dict) -> StageOutput:
        trade_results = context.get("trade_results")
        market_data_table = context.get("market_data_table")

        if trade_results is None:
            logger.warning(
                "Regime analysis skipped: no trade_results provided",
                extra={"component": "validation.gauntlet"},
            )
            return StageOutput(
                stage_name="regime",
                result=None,
                passed=True,  # Not a hard gate — just missing data
                metrics={"skipped": True, "reason": "no_trade_results"},
            )
        if market_data_table is None:
            logger.warning(
                "Regime analysis skipped: no market_data_table provided",
                extra={"component": "validation.gauntlet"},
            )
            return StageOutput(
                stage_name="regime",
                result=None,
                passed=True,  # Not a hard gate — just missing data
                metrics={"skipped": True, "reason": "no_market_data_table"},
            )

        result = run_regime_analysis(
            trade_results=trade_results,
            market_data=market_data_table,
            config=self._config.regime,
        )
        return StageOutput(
            stage_name="regime",
            result=result,
            passed=True,  # Regime has no hard gate
            metrics={
                "sufficient_buckets": result.sufficient_buckets,
                "total_buckets": result.total_buckets,
                "weakest_regime": result.weakest_regime,
            },
        )

    def _should_short_circuit(self, cv: CandidateValidation) -> bool:
        """Check if candidate has failed validity gates (PBO, DSR).

        Performance-based metrics do NOT trigger short-circuit per FR41.
        Only hard validity gates cause short-circuit.
        """
        if not self._config.short_circuit_on_validity_failure:
            return False
        return len(cv.hard_gate_failures) > 0

    def _checkpoint(self, state: GauntletState, checkpoint_path: Path) -> None:
        """Persist gauntlet state via crash_safe_write_json."""
        crash_safe_write_json(
            {
                "candidates_progress": state.candidates_progress,
                "completed_results": state.completed_results,
                "run_id": state.run_id,
                "rng_state": state.rng_state,
            },
            checkpoint_path,
        )

    def _compute_dsr_if_needed(
        self,
        candidate_results: list[CandidateValidation],
        optimization_manifest: dict,
        walk_forward_results: dict[int, WalkForwardResult],
    ) -> DSRResult | None:
        """Compute DSR if >10 candidates were evaluated during optimization."""
        total_trials = optimization_manifest.get("total_trials", 0)
        if total_trials <= 10:
            return None

        # Collect walk-forward sharpes across candidates
        sharpes = []
        for cid, wf_result in walk_forward_results.items():
            if wf_result and wf_result.aggregate_sharpe != 0.0:
                sharpes.append(wf_result.aggregate_sharpe)

        if not sharpes:
            return None

        observed = max(sharpes)
        variance = float(np.var(sharpes, ddof=1)) if len(sharpes) > 1 else 1.0
        skew = float(_compute_skewness(sharpes)) if len(sharpes) > 2 else 0.0
        kurt = float(_compute_kurtosis(sharpes)) if len(sharpes) > 3 else 3.0

        dsr_result = compute_dsr(
            observed_sharpe=observed,
            num_trials=total_trials,
            sharpe_variance=variance,
            skewness=skew,
            kurtosis=kurt,
            significance_level=self._config.dsr.significance_level,
        )

        logger.info(
            f"DSR computed: dsr={dsr_result.dsr:.4f}, "
            f"passed={dsr_result.passed}, trials={total_trials}",
            extra={
                "component": "validation.gauntlet",
                "ctx": {
                    "dsr": dsr_result.dsr,
                    "p_value": dsr_result.p_value,
                    "num_trials": total_trials,
                    "expected_max_sharpe": dsr_result.expected_max_sharpe,
                },
            },
        )

        return dsr_result


def _compute_skewness(values: list[float]) -> float:
    """Compute sample skewness."""
    arr = np.array(values)
    n = len(arr)
    if n < 3:
        return 0.0
    mean = np.mean(arr)
    std = np.std(arr, ddof=1)
    if std == 0:
        return 0.0
    return float(n / ((n - 1) * (n - 2)) * np.sum(((arr - mean) / std) ** 3))


def _compute_kurtosis(values: list[float]) -> float:
    """Compute sample excess kurtosis + 3 (to get regular kurtosis)."""
    arr = np.array(values)
    n = len(arr)
    if n < 4:
        return 3.0
    mean = np.mean(arr)
    std = np.std(arr, ddof=1)
    if std == 0:
        return 3.0
    m4 = float(np.mean((arr - mean) ** 4))
    return m4 / (std ** 4)
