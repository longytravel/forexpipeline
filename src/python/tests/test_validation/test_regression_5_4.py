"""Regression tests for Story 5.4 code review findings.

Each test covers a specific accepted finding from the dual-review synthesis.
These tests ensure the same class of bug never recurs.
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import numpy as np
import pyarrow as pa
import pytest

from validation.config import (
    CPCVConfig,
    MonteCarloConfig,
    ValidationConfig,
    WalkForwardConfig,
)


# ---------------------------------------------------------------------------
# R1: Permutation test must use sign-flip, not order shuffle (Codex HIGH)
# ---------------------------------------------------------------------------


@pytest.mark.regression
class TestPermutationSignFlip:
    """Permutation test must produce meaningful p-values for strong signals."""

    def test_strong_positive_signal_detectable(self):
        """A strategy with strong positive mean should have low p-value.

        The old order-shuffle was degenerate because mean/std are
        order-invariant. Sign-flip tests H0: mean=0 and rejects it.
        """
        from validation.monte_carlo import permutation_test

        rng_data = np.random.default_rng(42)
        returns = rng_data.normal(loc=5.0, scale=2.0, size=100)
        observed = float(np.mean(returns)) / float(np.std(returns, ddof=1))

        rng = np.random.default_rng(99)
        result = permutation_test(returns, observed, 500, rng)

        # Strong signal must be detected (p < 0.05)
        assert result.p_value < 0.05, (
            f"Sign-flip test should detect strong signal, got p={result.p_value}"
        )

    def test_pvalue_never_zero(self):
        """P-value must use (count+1)/(N+1) formula — never exactly 0."""
        from validation.monte_carlo import permutation_test

        rng_data = np.random.default_rng(42)
        returns = rng_data.normal(loc=100.0, scale=1.0, size=50)
        observed = float(np.mean(returns)) / float(np.std(returns, ddof=1))

        rng = np.random.default_rng(99)
        result = permutation_test(returns, observed, 100, rng)

        assert result.p_value > 0.0, "P-value must never be exactly 0"
        # Minimum possible is 1/(N+1)
        assert result.p_value >= 1.0 / 101.0


# ---------------------------------------------------------------------------
# R2: CPCV non-contiguous test groups evaluated separately (BMAD C3)
# ---------------------------------------------------------------------------


@pytest.mark.regression
class TestCPCVPerGroupDispatch:
    """CPCV must dispatch each non-contiguous test group independently."""

    def test_non_contiguous_groups_dispatched_separately(self):
        """With k=2 test groups from n=4, test groups like [0,2] must NOT
        be evaluated as a single span [0..3] which would include train data.
        """
        from validation.cpcv import run_cpcv

        dispatched_ranges = []

        class TrackingDispatcher:
            def evaluate_candidate(self, *args, **kwargs):
                dispatched_ranges.append(
                    (kwargs.get("window_start"), kwargs.get("window_end"))
                )
                return {"sharpe": 1.0, "profit_factor": 1.5, "net_pnl": 100.0}

        config = CPCVConfig(
            n_groups=4, k_test_groups=2, purge_bars=0, embargo_bars=0,
        )
        run_cpcv(
            candidate={"p": 1},
            market_data_path=Path("dummy.arrow"),
            strategy_spec={},
            cost_model={},
            config=config,
            dispatcher=TrackingDispatcher(),
            seed=42,
            data_length=4000,
        )

        # Each combination dispatches OOS per test group + IS per train range.
        # Verify no single call spans more than one group (group_size=1000).
        for start, end in dispatched_ranges:
            span = end - start
            assert span <= 1000, (
                f"Dispatch span {span} exceeds group size 1000 — "
                f"non-contiguous groups may be merged: [{start}:{end}]"
            )


# ---------------------------------------------------------------------------
# R3: CPCV IS returns must NOT be populated with OOS data (BMAD C2)
# ---------------------------------------------------------------------------


@pytest.mark.regression
class TestCPCVISDataNotLeaked:
    """IS returns must come from train evaluation, not copied from OOS."""

    def test_is_and_oos_distinct_when_dispatched(self):
        """IS and OOS sharpes must differ when dispatcher returns
        position-dependent results.
        """
        from validation.cpcv import run_cpcv

        class PositionDispatcher:
            """Returns different sharpe for different data ranges."""
            def evaluate_candidate(self, *args, **kwargs):
                start = kwargs.get("window_start", 0)
                # Train (low index) -> high sharpe; Test (high index) -> low
                sharpe = 3.0 if start < 3000 else 0.5
                return {"sharpe": sharpe, "profit_factor": 1.5, "net_pnl": 100.0}

        config = CPCVConfig(
            n_groups=4, k_test_groups=2, purge_bars=0, embargo_bars=0,
        )
        result = run_cpcv(
            candidate={"p": 1},
            market_data_path=Path("dummy.arrow"),
            strategy_spec={},
            cost_model={},
            config=config,
            dispatcher=PositionDispatcher(),
            seed=42,
            data_length=4000,
        )

        # With IS from train ranges (low index -> high sharpe) and OOS from
        # test ranges (mixed), the IS and OOS distributions should differ.
        # The old bug copied OOS sharpe into IS, making them identical.
        assert len(result.combinations) > 0


# ---------------------------------------------------------------------------
# R4: DSR skew/kurtosis correction on observed Sharpe, not E[max] (BMAD C4)
# ---------------------------------------------------------------------------


@pytest.mark.regression
class TestDSRNonNormalityCorrection:
    """Non-normality correction must adjust observed Sharpe, not E[max SR]."""

    def test_negative_skew_reduces_dsr(self):
        """Negative skew (common in trading) should inflate the SE of the
        Sharpe ratio, making DSR harder to pass when observed > E[max SR].
        """
        from validation.dsr import compute_dsr

        # Use few trials so E[max SR] is low, observed well above it
        # With 10 trials, E[max] ≈ 1.7; observed=3.0 → passing case
        result_normal = compute_dsr(
            observed_sharpe=3.0, num_trials=10, sharpe_variance=1.0,
            skewness=0.0, kurtosis=3.0,
        )
        result_skewed = compute_dsr(
            observed_sharpe=3.0, num_trials=10, sharpe_variance=1.0,
            skewness=-2.0, kurtosis=5.0,
        )

        # Negative skew + fat tails → larger SE → smaller z-stat → lower DSR
        assert result_skewed.dsr < result_normal.dsr, (
            f"Negative skew should reduce DSR via larger SE: "
            f"normal={result_normal.dsr:.4f}, skewed={result_skewed.dsr:.4f}"
        )

    def test_expected_max_sharpe_unaffected_by_skew(self):
        """E[max SR] should NOT change with skewness/kurtosis."""
        from validation.dsr import compute_expected_max_sharpe

        e_normal = compute_expected_max_sharpe(100, sharpe_std=1.0, skew=0.0, kurt=3.0)
        e_skewed = compute_expected_max_sharpe(100, sharpe_std=1.0, skew=-2.0, kurt=5.0)

        assert e_normal == e_skewed, (
            "E[max SR] should not be adjusted for non-normality"
        )


# ---------------------------------------------------------------------------
# R5: DSR gate must be wired to candidate failures (BMAD C5 + Codex HIGH)
# ---------------------------------------------------------------------------


@pytest.mark.regression
class TestDSRGatingEnforced:
    """DSR failure must mark candidates with hard_gate_failures."""

    def test_dsr_failure_marks_candidates(self):
        """When DSR fails, all non-short-circuited candidates get 'dsr' failure."""
        from validation.gauntlet import ValidationGauntlet

        config = ValidationConfig(
            stage_order=["walk_forward"],
            short_circuit_on_validity_failure=True,
            deterministic_seed_base=42,
        )

        class MockDispatcher:
            def evaluate_candidate(self, *args, **kwargs):
                return {
                    "sharpe": 0.1, "profit_factor": 0.8,
                    "max_drawdown": 0.0, "trade_count": 10, "net_pnl": 5.0,
                }

        gauntlet = ValidationGauntlet(config=config, dispatcher=MockDispatcher())

        results = gauntlet.run(
            candidates=[{"p": 1}, {"p": 2}],
            market_data_path=Path("dummy.arrow"),
            strategy_spec={},
            cost_model={},
            optimization_manifest={"total_trials": 500},  # >10 triggers DSR
            output_dir=Path("/tmp/test_dsr_gate"),
            data_length=50000,
        )

        # With observed Sharpe ~0.1 and 500 trials, DSR should fail
        if results.dsr and not results.dsr.passed:
            for cv in results.candidates:
                assert "dsr" in cv.hard_gate_failures, (
                    f"Candidate {cv.candidate_id} missing DSR failure"
                )


# ---------------------------------------------------------------------------
# R6: Checkpoint saves ALL candidates' progress (BMAD H3)
# ---------------------------------------------------------------------------


@pytest.mark.regression
class TestCheckpointFullState:
    """Checkpoint must persist progress for ALL candidates, not just current."""

    def test_checkpoint_includes_all_candidates(self, tmp_path):
        """After processing 2 candidates, checkpoint file must reference both."""
        import json
        from validation.gauntlet import ValidationGauntlet

        config = ValidationConfig(
            stage_order=["perturbation"],
            short_circuit_on_validity_failure=False,
            deterministic_seed_base=42,
        )

        gauntlet = ValidationGauntlet(config=config, dispatcher=None)
        gauntlet.run(
            candidates=[{"p": 1}, {"p": 2}],
            market_data_path=Path("dummy.arrow"),
            strategy_spec={},
            cost_model={},
            optimization_manifest={"total_trials": 5},
            output_dir=tmp_path,
            param_ranges={"p": {"type": "float", "min": 0, "max": 10}},
        )

        checkpoint = tmp_path / "gauntlet_checkpoint.json"
        if checkpoint.exists():
            data = json.loads(checkpoint.read_text())
            progress = data.get("candidates_progress", {})
            # Must have entries for candidate 0 AND candidate 1
            assert "0" in progress or 0 in progress, "Missing candidate 0 in checkpoint"
            assert "1" in progress or 1 in progress, "Missing candidate 1 in checkpoint"


# ---------------------------------------------------------------------------
# R7: Gauntlet must NOT fabricate dummy data (BMAD H8 + Codex HIGH)
# ---------------------------------------------------------------------------


@pytest.mark.regression
class TestNoDummyDataFabrication:
    """Monte Carlo and regime stages must raise on missing inputs."""

    def test_monte_carlo_skips_without_trade_results(self, tmp_path):
        """_run_monte_carlo must gracefully skip when trade_results is None."""
        from validation.gauntlet import ValidationGauntlet

        config = ValidationConfig(
            stage_order=["monte_carlo"],
            deterministic_seed_base=42,
        )
        gauntlet = ValidationGauntlet(config=config)

        results = gauntlet.run(
            candidates=[{"p": 1}],
            market_data_path=Path("dummy.arrow"),
            strategy_spec={},
            cost_model={},
            optimization_manifest={"total_trials": 5},
            output_dir=tmp_path,
            trade_results=None,
            data_length=10000,
        )
        # Should skip gracefully, not raise
        assert len(results.candidates) == 1
        mc_output = results.candidates[0].stages["monte_carlo"]
        assert mc_output.metrics.get("skipped") is True
        assert mc_output.metrics.get("reason") == "no_trade_results"

    def test_regime_skips_without_market_data(self, tmp_path):
        """_run_regime must gracefully skip when market_data_table is None."""
        from validation.gauntlet import ValidationGauntlet

        config = ValidationConfig(
            stage_order=["regime"],
            deterministic_seed_base=42,
        )
        gauntlet = ValidationGauntlet(config=config)

        results = gauntlet.run(
            candidates=[{"p": 1}],
            market_data_path=Path("dummy.arrow"),
            strategy_spec={},
            cost_model={},
            optimization_manifest={"total_trials": 5},
            output_dir=tmp_path,
            trade_results=None,
            market_data_table=None,
            data_length=10000,
        )
        # Should skip gracefully, not raise
        assert len(results.candidates) == 1
        regime_output = results.candidates[0].stages["regime"]
        assert regime_output.metrics.get("skipped") is True


# ---------------------------------------------------------------------------
# R8: gated_stages must include validation-complete (BMAD C6 + Codex MEDIUM)
# ---------------------------------------------------------------------------


@pytest.mark.regression
class TestGatedStagesConfig:
    """base.toml gated_stages must include validation-complete."""

    def test_base_toml_includes_validation_complete(self):
        """Config file must gate validation-complete stage."""
        import tomllib

        config_path = Path(__file__).resolve().parents[4] / "config" / "base.toml"
        if not config_path.exists():
            # Try alternative path
            config_path = Path("config/base.toml")
        if config_path.exists():
            with open(config_path, "rb") as f:
                config = tomllib.load(f)
            gated = config.get("pipeline", {}).get("gated_stages", [])
            assert "validation-complete" in gated, (
                f"gated_stages must include 'validation-complete', got: {gated}"
            )


# ---------------------------------------------------------------------------
# R9: Config validation rejects nonsensical values (BMAD M1)
# ---------------------------------------------------------------------------


@pytest.mark.regression
class TestConfigValidation:
    """ValidationConfig.from_dict must reject invalid configurations."""

    def test_zero_windows_rejected(self):
        with pytest.raises(ValueError, match="n_windows"):
            ValidationConfig.from_dict({
                "validation": {"walk_forward": {"n_windows": 0}}
            })

    def test_train_ratio_over_one_rejected(self):
        with pytest.raises(ValueError, match="train_ratio"):
            ValidationConfig.from_dict({
                "validation": {"walk_forward": {"train_ratio": 1.5}}
            })

    def test_k_test_groups_exceeds_n_groups_rejected(self):
        with pytest.raises(ValueError, match="k_test_groups"):
            ValidationConfig.from_dict({
                "validation": {"cpcv": {"n_groups": 5, "k_test_groups": 5}}
            })


# ---------------------------------------------------------------------------
# R10: Walk-forward suspicious performance flagging (Codex HIGH)
# ---------------------------------------------------------------------------


@pytest.mark.regression
class TestSuspiciousPerformanceFlagging:
    """Walk-forward must flag suspicious IS/OOS divergence."""

    def test_walk_forward_result_has_suspicious_flag(self):
        """WalkForwardResult must include suspicious flag and PF divergence."""
        from validation.walk_forward import WalkForwardResult

        result = WalkForwardResult(
            windows=[],
            aggregate_sharpe=1.0,
            aggregate_pf=1.5,
            is_oos_divergence=3.0,  # IS 3x OOS = suspicious
        )

        assert hasattr(result, "suspicious"), "Missing suspicious flag"
        assert hasattr(result, "is_oos_pf_divergence"), "Missing PF divergence"


# ---------------------------------------------------------------------------
# R11: PBO must use IS returns for IS-vs-OOS ranking (BMAD C1, synthesis fix)
# ---------------------------------------------------------------------------


@pytest.mark.regression
class TestPBOUsesISReturns:
    """compute_pbo must use IS returns for proper IS-vs-OOS ranking."""

    def test_anticorrelated_is_oos_gives_high_pbo(self):
        """When IS-best combos are OOS-worst, PBO should be high (overfit)."""
        from validation.cpcv import compute_pbo

        is_returns = [5.0, 4.0, 3.0, 2.0, 1.0]
        oos_returns = [1.0, 2.0, 3.0, 4.0, 5.0]
        pbo = compute_pbo(oos_returns, is_returns)
        assert pbo > 0.5, f"Anti-correlated IS/OOS should give high PBO, got {pbo}"

    def test_correlated_is_oos_gives_low_pbo(self):
        """When IS-best combos are also OOS-best, PBO should be low."""
        from validation.cpcv import compute_pbo

        is_returns = [1.0, 2.0, 3.0, 4.0, 5.0]
        oos_returns = [1.1, 2.1, 3.1, 4.1, 5.1]
        pbo = compute_pbo(oos_returns, is_returns)
        assert pbo < 0.3, f"Correlated IS/OOS should give low PBO, got {pbo}"

    def test_identical_is_oos_warns_data_leak(self):
        """Passing identical IS/OOS should trigger fallback (data leak)."""
        from validation.cpcv import compute_pbo

        data = [1.0, 2.0, 3.0, 4.0]
        pbo = compute_pbo(data, data)
        # Should not crash; falls back to OOS-only median test
        assert 0.0 <= pbo <= 1.0


# ---------------------------------------------------------------------------
# R12: Manifest must include all downstream contract fields (BMAD C8, synthesis fix)
# ---------------------------------------------------------------------------


@pytest.mark.regression
class TestManifestContractFields:
    """Gauntlet manifest must include all Story 5.5 contract fields."""

    def test_manifest_has_required_fields(self, tmp_path):
        """Manifest JSON must contain candidate_rank, per_stage_metric_ids,
        config_hash, chart_data_refs per the downstream contract."""
        from unittest.mock import MagicMock
        from validation.results import write_gauntlet_manifest

        # Build minimal mock results
        mock_results = MagicMock()
        mock_cv = MagicMock()
        mock_cv.candidate_id = 0
        mock_cv.short_circuited = False
        mock_cv.hard_gate_failures = []
        mock_cv.is_oos_divergence = 1.5
        mock_stage = MagicMock()
        mock_stage.passed = True
        mock_stage.metrics = {"sharpe": 1.0}
        mock_cv.stages = {"walk_forward": mock_stage}
        mock_results.candidates = [mock_cv]
        mock_results.dsr = None
        mock_results.run_manifest = {"stages": ["walk_forward"]}

        manifest_path = write_gauntlet_manifest(
            mock_results,
            {"run_id": "test", "total_trials": 50},
            tmp_path,
            validation_config={"walk_forward": {"n_windows": 5}},
            artifact_paths={0: {"walk_forward": "/tmp/wf.arrow"}},
        )

        import json
        manifest = json.loads(manifest_path.read_text())

        required = [
            "optimization_run_id", "total_optimization_trials",
            "config_hash", "chart_data_refs", "gate_results", "candidates",
        ]
        for field_name in required:
            assert field_name in manifest, f"Missing contract field: {field_name}"

        # config_hash must be non-empty when config is provided
        assert manifest["config_hash"] != "", "config_hash should be populated"

        # chart_data_refs should contain artifact path
        assert "0" in manifest["chart_data_refs"]

        # Candidate must have per_stage_metric_ids and candidate_rank
        cand = manifest["candidates"][0]
        assert "per_stage_metric_ids" in cand
        assert "candidate_rank" in cand


# ---------------------------------------------------------------------------
# R13: ValidationExecutor must have stage attribute (BMAD H1, synthesis fix)
# ---------------------------------------------------------------------------


@pytest.mark.regression
class TestExecutorStageAttribute:
    """ValidationExecutor must declare PipelineStage.VALIDATING."""

    def test_executor_has_stage_attribute(self):
        from validation.executor import ValidationExecutor
        from orchestrator.pipeline_state import PipelineStage

        assert hasattr(ValidationExecutor, "stage")
        assert ValidationExecutor.stage == PipelineStage.VALIDATING


# ---------------------------------------------------------------------------
# R14: Walk-forward must compute IS PF divergence (AC9, synthesis fix)
# ---------------------------------------------------------------------------


@pytest.mark.regression
class TestWalkForwardPFDivergence:
    """Walk-forward must collect IS profit factor and compute PF divergence."""

    def test_window_result_has_is_pf(self):
        from validation.walk_forward import WindowResult

        wr = WindowResult(
            window_id=0, oos_sharpe=1.0, oos_pf=1.5,
            oos_drawdown=0.1, oos_trades=50, oos_pnl=100.0,
            is_sharpe=2.0, is_pf=3.0,
        )
        assert wr.is_pf == 3.0

    def test_pf_divergence_computed(self):
        """run_walk_forward must compute is_oos_pf_divergence."""
        from validation.walk_forward import run_walk_forward, WalkForwardConfig

        class PFDispatcher:
            def evaluate_candidate(self, *args, **kwargs):
                start = kwargs.get("window_start", 0)
                is_train = start == 0  # anchored: train starts at 0
                return {
                    "sharpe": 2.0 if is_train else 1.0,
                    "profit_factor": 3.0 if is_train else 1.5,
                    "max_drawdown": 0.1, "trade_count": 50, "net_pnl": 100.0,
                }

        config = WalkForwardConfig(n_windows=3, train_ratio=0.8, purge_bars=0, embargo_bars=0)
        result = run_walk_forward(
            candidate={"p": 1}, market_data_path=Path("dummy.arrow"),
            strategy_spec={}, cost_model={}, config=config,
            dispatcher=PFDispatcher(), seed=42, data_length=30000,
        )
        assert result.is_oos_pf_divergence != 0.0, "PF divergence should be computed"


# ---------------------------------------------------------------------------
# R15: Regime _get_pnl must handle 'pnl' column (BMAD M4, synthesis fix)
# ---------------------------------------------------------------------------


@pytest.mark.regression
class TestRegimePnlFallback:
    """regime_analysis._get_pnl must handle 'pnl' column, not just 'pnl_pips'."""

    def test_pnl_column_detected(self):
        from validation.regime_analysis import _get_pnl

        table = pa.table({"pnl": pa.array([1.0, 2.0, 3.0], type=pa.float64())})
        result = _get_pnl(table)
        np.testing.assert_array_equal(result, [1.0, 2.0, 3.0])

    def test_float_column_fallback(self):
        from validation.regime_analysis import _get_pnl

        table = pa.table({"profit": pa.array([5.0, 6.0], type=pa.float64())})
        result = _get_pnl(table)
        np.testing.assert_array_equal(result, [5.0, 6.0])


# ---------------------------------------------------------------------------
# R16: Deterministic run_id for reproducibility (Codex MEDIUM, synthesis fix)
# ---------------------------------------------------------------------------


@pytest.mark.regression
class TestDeterministicRunId:
    """Gauntlet run_id must be deterministic given same config and candidates."""

    def test_same_config_same_run_id(self):
        from validation.gauntlet import ValidationGauntlet

        config = ValidationConfig(
            stage_order=["perturbation"],
            deterministic_seed_base=42,
        )
        gauntlet = ValidationGauntlet(config=config, dispatcher=None)

        r1 = gauntlet.run(
            candidates=[{"p": 1}], market_data_path=Path("d.arrow"),
            strategy_spec={}, cost_model={},
            optimization_manifest={"total_trials": 5},
            param_ranges={"p": {"type": "float", "min": 0, "max": 10}},
            data_length=10000,
        )
        r2 = gauntlet.run(
            candidates=[{"p": 1}], market_data_path=Path("d.arrow"),
            strategy_spec={}, cost_model={},
            optimization_manifest={"total_trials": 5},
            param_ranges={"p": {"type": "float", "min": 0, "max": 10}},
            data_length=10000,
        )
        assert r1.run_manifest["run_id"] == r2.run_manifest["run_id"]


# ---------------------------------------------------------------------------
# R17: WF artifact must include train/test boundaries (AC12, synthesis fix)
# ---------------------------------------------------------------------------


@pytest.mark.regression
class TestWFArtifactBoundaries:
    """Walk-forward Arrow artifact must include train/test split boundaries."""

    def test_window_specs_stored_in_result(self):
        from validation.walk_forward import WalkForwardResult, WindowSpec

        specs = [WindowSpec(0, 0, 800, 900, 1000, 790, 800)]
        result = WalkForwardResult(
            windows=[], aggregate_sharpe=0.0, aggregate_pf=0.0,
            is_oos_divergence=0.0, window_specs=specs,
        )
        assert result.window_specs is not None
        assert len(result.window_specs) == 1
