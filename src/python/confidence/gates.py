"""Hard gate evaluator for confidence scoring (Story 5.5, Task 3).

Evaluates binary pass/fail gates from the gauntlet manifest.
Any gate failure → immediate RED rating.
"""
from __future__ import annotations

from confidence.config import HardGateConfig
from confidence.models import GateResult


def evaluate_hard_gates(
    gauntlet_manifest: dict,
    config: HardGateConfig,
) -> list[GateResult]:
    """Evaluate all hard gates from gauntlet manifest data.

    Reads from Story 5.4's gauntlet manifest fields:
    - gate_results.dsr_passed, gate_results.dsr_value
    - gate_results.pbo_value, gate_results.pbo_passed
    - per_stage_summaries.monte_carlo.stress_survived

    Args:
        gauntlet_manifest: Per-candidate gauntlet manifest dict.
        config: Hard gate configuration thresholds.

    Returns:
        List of GateResult for each evaluated gate.
    """
    results: list[GateResult] = []
    gate_data = gauntlet_manifest.get("gate_results", {})
    stage_summaries = gauntlet_manifest.get("per_stage_summaries", {})
    total_trials = gauntlet_manifest.get("total_optimization_trials", 0)

    # Gate 1: DSR pass
    results.append(_evaluate_dsr_gate(gate_data, config, total_trials))

    # Gate 2: PBO threshold
    results.append(_evaluate_pbo_gate(gate_data, config))

    # Gate 3: Cost stress survival
    results.append(_evaluate_cost_stress_gate(stage_summaries, config))

    return results


def any_gate_failed(results: list[GateResult]) -> bool:
    """Return True if any gate in the results list failed."""
    return any(not r.passed for r in results)


def _evaluate_dsr_gate(
    gate_data: dict,
    config: HardGateConfig,
    total_trials: int,
) -> GateResult:
    """DSR pass — mandatory when >10 candidates (D11)."""
    dsr_passed = gate_data.get("dsr_passed", False)
    dsr_value = gate_data.get("dsr_value", 0.0)

    if not config.dsr_pass_required:
        return GateResult(
            gate_name="dsr_pass",
            threshold=0.0,
            actual_value=dsr_value,
            passed=True,
            description="DSR gate disabled in config",
        )

    # DSR is mandatory when total optimization trials > 10
    if total_trials <= 10:
        return GateResult(
            gate_name="dsr_pass",
            threshold=0.0,
            actual_value=dsr_value,
            passed=True,
            description=f"DSR gate skipped — only {total_trials} total trials (≤10)",
        )

    return GateResult(
        gate_name="dsr_pass",
        threshold=0.05,
        actual_value=dsr_value,
        passed=dsr_passed,
        description=(
            "DSR passed — strategy survives multiple testing correction"
            if dsr_passed
            else "DSR FAILED — strategy does not survive deflated Sharpe ratio test"
        ),
    )


def _evaluate_pbo_gate(gate_data: dict, config: HardGateConfig) -> GateResult:
    """PBO ≤ threshold — probability of backtest overfitting."""
    pbo_value = gate_data.get("pbo_value", 1.0)
    short_circuited = gate_data.get("short_circuited", False)

    # If short-circuited before PBO was computed, treat as unknown → skipped
    if short_circuited and pbo_value == 1.0:
        return GateResult(
            gate_name="pbo_threshold",
            threshold=config.pbo_max_threshold,
            actual_value=pbo_value,
            passed=False,
            description="PBO gate SKIPPED — stage skipped due to short-circuit (scored as 0.0)",
        )

    passed = pbo_value <= config.pbo_max_threshold
    return GateResult(
        gate_name="pbo_threshold",
        threshold=config.pbo_max_threshold,
        actual_value=pbo_value,
        passed=passed,
        description=(
            f"PBO {pbo_value:.3f} ≤ {config.pbo_max_threshold} — low overfitting probability"
            if passed
            else f"PBO {pbo_value:.3f} > {config.pbo_max_threshold} — HIGH overfitting probability"
        ),
    )


def _evaluate_cost_stress_gate(
    stage_summaries: dict,
    config: HardGateConfig,
) -> GateResult:
    """Cost stress survival — must survive N× cost inflation."""
    mc_data = stage_summaries.get("monte_carlo", {})
    stress_survived = mc_data.get("stress_survived", False)
    multiplier = config.cost_stress_survival_multiplier

    # If monte_carlo stage was skipped (short-circuit), treat as skipped
    if not mc_data:
        return GateResult(
            gate_name="cost_stress_survival",
            threshold=multiplier,
            actual_value=0.0,
            passed=False,
            description=(
                f"Cost stress gate SKIPPED — stage skipped due to short-circuit "
                f"(required: survive {multiplier}x cost inflation, scored as 0.0)"
            ),
        )

    return GateResult(
        gate_name="cost_stress_survival",
        threshold=multiplier,
        actual_value=multiplier if stress_survived else 0.0,
        passed=stress_survived,
        description=(
            f"Strategy survives {multiplier}x cost inflation stress test"
            if stress_survived
            else f"Strategy FAILS at {multiplier}x cost inflation — negative PnL under stress"
        ),
    )
