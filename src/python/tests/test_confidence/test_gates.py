"""Tests for hard gate evaluator (Task 3)."""
import pytest

from confidence.config import HardGateConfig
from confidence.gates import any_gate_failed, evaluate_hard_gates


def _default_config() -> HardGateConfig:
    return HardGateConfig(
        dsr_pass_required=True,
        pbo_max_threshold=0.40,
        cost_stress_survival_multiplier=1.5,
    )


def _green_manifest() -> dict:
    return {
        "total_optimization_trials": 5000,
        "gate_results": {
            "dsr_passed": True,
            "dsr_value": 2.31,
            "pbo_value": 0.18,
            "pbo_passed": True,
            "short_circuited": False,
        },
        "per_stage_summaries": {
            "monte_carlo": {
                "stress_survived": True,
                "bootstrap_ci_lower": 0.15,
            },
        },
    }


class TestDSRGate:
    def test_dsr_gate_pass(self):
        results = evaluate_hard_gates(_green_manifest(), _default_config())
        dsr = next(r for r in results if r.gate_name == "dsr_pass")
        assert dsr.passed is True

    def test_dsr_gate_fail(self):
        manifest = _green_manifest()
        manifest["gate_results"]["dsr_passed"] = False
        manifest["gate_results"]["dsr_value"] = 0.02
        results = evaluate_hard_gates(manifest, _default_config())
        dsr = next(r for r in results if r.gate_name == "dsr_pass")
        assert dsr.passed is False

    def test_dsr_gate_skipped_low_trials(self):
        manifest = _green_manifest()
        manifest["total_optimization_trials"] = 5
        manifest["gate_results"]["dsr_passed"] = False
        results = evaluate_hard_gates(manifest, _default_config())
        dsr = next(r for r in results if r.gate_name == "dsr_pass")
        assert dsr.passed is True  # Skipped — not enough trials

    def test_dsr_gate_disabled_in_config(self):
        config = HardGateConfig(
            dsr_pass_required=False,
            pbo_max_threshold=0.40,
            cost_stress_survival_multiplier=1.5,
        )
        manifest = _green_manifest()
        manifest["gate_results"]["dsr_passed"] = False
        results = evaluate_hard_gates(manifest, config)
        dsr = next(r for r in results if r.gate_name == "dsr_pass")
        assert dsr.passed is True


class TestPBOGate:
    def test_pbo_gate_pass(self):
        results = evaluate_hard_gates(_green_manifest(), _default_config())
        pbo = next(r for r in results if r.gate_name == "pbo_threshold")
        assert pbo.passed is True
        assert pbo.actual_value == 0.18

    def test_pbo_gate_fail(self):
        manifest = _green_manifest()
        manifest["gate_results"]["pbo_value"] = 0.55
        results = evaluate_hard_gates(manifest, _default_config())
        pbo = next(r for r in results if r.gate_name == "pbo_threshold")
        assert pbo.passed is False

    def test_pbo_gate_exact_threshold(self):
        manifest = _green_manifest()
        manifest["gate_results"]["pbo_value"] = 0.40
        results = evaluate_hard_gates(manifest, _default_config())
        pbo = next(r for r in results if r.gate_name == "pbo_threshold")
        assert pbo.passed is True  # ≤ threshold

    def test_pbo_gate_short_circuited(self):
        manifest = _green_manifest()
        manifest["gate_results"]["short_circuited"] = True
        manifest["gate_results"]["pbo_value"] = 1.0
        results = evaluate_hard_gates(manifest, _default_config())
        pbo = next(r for r in results if r.gate_name == "pbo_threshold")
        assert pbo.passed is False


class TestCostStressGate:
    def test_cost_stress_gate_pass(self):
        results = evaluate_hard_gates(_green_manifest(), _default_config())
        stress = next(r for r in results if r.gate_name == "cost_stress_survival")
        assert stress.passed is True

    def test_cost_stress_gate_fail(self):
        manifest = _green_manifest()
        manifest["per_stage_summaries"]["monte_carlo"]["stress_survived"] = False
        results = evaluate_hard_gates(manifest, _default_config())
        stress = next(r for r in results if r.gate_name == "cost_stress_survival")
        assert stress.passed is False

    def test_cost_stress_gate_missing_monte_carlo(self):
        manifest = _green_manifest()
        manifest["per_stage_summaries"].pop("monte_carlo")
        results = evaluate_hard_gates(manifest, _default_config())
        stress = next(r for r in results if r.gate_name == "cost_stress_survival")
        assert stress.passed is False


class TestMultipleGateFailures:
    def test_multiple_gate_failures(self):
        manifest = _green_manifest()
        manifest["gate_results"]["dsr_passed"] = False
        manifest["gate_results"]["pbo_value"] = 0.60
        manifest["per_stage_summaries"]["monte_carlo"]["stress_survived"] = False
        results = evaluate_hard_gates(manifest, _default_config())
        failed = [r for r in results if not r.passed]
        assert len(failed) == 3
        assert any_gate_failed(results) is True

    def test_all_gates_pass(self):
        results = evaluate_hard_gates(_green_manifest(), _default_config())
        assert any_gate_failed(results) is False
        assert all(r.passed for r in results)


class TestShortCircuitGateDescriptions:
    """Regression: short-circuited gates must say SKIPPED, not FAILED."""

    @pytest.mark.regression
    def test_pbo_gate_short_circuit_description_says_skipped(self):
        """Short-circuited PBO gate description should say SKIPPED, not FAILED."""
        manifest = _green_manifest()
        manifest["gate_results"]["short_circuited"] = True
        manifest["gate_results"]["pbo_value"] = 1.0
        results = evaluate_hard_gates(manifest, _default_config())
        pbo = next(r for r in results if r.gate_name == "pbo_threshold")
        assert pbo.passed is False
        assert "SKIPPED" in pbo.description
        assert "FAILED" not in pbo.description

    @pytest.mark.regression
    def test_cost_stress_gate_skipped_description_says_skipped(self):
        """Missing Monte Carlo stage gate description should say SKIPPED, not FAILED."""
        manifest = _green_manifest()
        manifest["per_stage_summaries"].pop("monte_carlo")
        results = evaluate_hard_gates(manifest, _default_config())
        stress = next(r for r in results if r.gate_name == "cost_stress_survival")
        assert stress.passed is False
        assert "SKIPPED" in stress.description
        assert "FAILED" not in stress.description

    @pytest.mark.regression
    def test_actual_pbo_failure_not_marked_skipped(self):
        """A real PBO failure (not short-circuited) must NOT say SKIPPED."""
        manifest = _green_manifest()
        manifest["gate_results"]["pbo_value"] = 0.55
        results = evaluate_hard_gates(manifest, _default_config())
        pbo = next(r for r in results if r.gate_name == "pbo_threshold")
        assert pbo.passed is False
        assert "SKIPPED" not in pbo.description
        assert "HIGH overfitting probability" in pbo.description
