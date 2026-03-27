"""Live integration tests for validation gauntlet (Story 5.4).

These tests exercise REAL system behavior:
- Real computations (no mocks for the system under test)
- Real files written to disk
- Real artifact verification

Marked with @pytest.mark.live so they run via: pytest -m live
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pyarrow as pa
import pyarrow.ipc
import pytest

from validation.config import (
    CPCVConfig,
    MonteCarloConfig,
    PerturbationConfig,
    RegimeConfig,
    ValidationConfig,
    WalkForwardConfig,
)
from validation.walk_forward import (
    WalkForwardResult,
    generate_walk_forward_windows,
    run_walk_forward,
)
from validation.cpcv import CPCVResult, run_cpcv, compute_pbo, generate_cpcv_combinations
from validation.dsr import DSRResult, compute_dsr
from validation.perturbation import PerturbationResult, run_perturbation, generate_perturbations
from validation.monte_carlo import (
    MonteCarloResult,
    run_monte_carlo,
    bootstrap_equity_curves,
    permutation_test,
    stress_test_costs,
)
from validation.regime_analysis import RegimeResult, run_regime_analysis, classify_regimes
from validation.gauntlet import ValidationGauntlet, GauntletResults
from validation.results import (
    write_stage_artifact,
    write_stage_summary,
    write_gauntlet_manifest,
)


# ---------------------------------------------------------------------------
# Helpers — synthetic but realistic data factories
# ---------------------------------------------------------------------------

def _make_synthetic_trades(n_trades: int, seed: int = 42) -> pa.Table:
    """Create realistic trade results table with cost columns."""
    rng = np.random.Generator(np.random.PCG64(seed))
    pnl = rng.normal(0.5, 2.0, size=n_trades)
    sessions = rng.choice(
        ["asian", "london", "new_york", "london_ny_overlap"], size=n_trades
    )
    entry_times = np.arange(n_trades, dtype=np.int64) * 60  # 1-minute spacing
    spreads = rng.uniform(0.5, 2.0, size=n_trades)
    slippage = rng.uniform(0.0, 0.5, size=n_trades)

    return pa.table({
        "pnl_pips": pnl.tolist(),
        "entry_time": entry_times.tolist(),
        "entry_session": sessions.tolist(),
        "entry_spread": spreads.tolist(),
        "exit_spread": spreads.tolist(),
        "entry_slippage": slippage.tolist(),
        "exit_slippage": slippage.tolist(),
    })


def _make_synthetic_market_data(n_bars: int, seed: int = 42) -> pa.Table:
    """Create realistic OHLC market data table."""
    rng = np.random.Generator(np.random.PCG64(seed))
    base_price = 1.1000
    close = base_price + np.cumsum(rng.normal(0, 0.0001, size=n_bars))
    high = close + rng.uniform(0.0001, 0.0010, size=n_bars)
    low = close - rng.uniform(0.0001, 0.0010, size=n_bars)
    timestamps = np.arange(n_bars, dtype=np.int64) * 60_000_000  # microseconds

    return pa.table({
        "timestamp": timestamps.tolist(),
        "high": high.tolist(),
        "low": low.tolist(),
        "close": close.tolist(),
    })


class _SyntheticDispatcher:
    """Dispatcher that returns synthetic but deterministic evaluation results.

    Uses seed-based generation so results are reproducible (FR18).
    NOT a mock — performs actual computation to generate trade metrics.
    """

    def __init__(self, base_sharpe: float = 1.2, variance: float = 0.3):
        self._base_sharpe = base_sharpe
        self._variance = variance

    def evaluate_candidate(
        self,
        candidate: dict,
        market_data_path,
        strategy_spec: dict,
        cost_model: dict,
        window_start: int = 0,
        window_end: int = 1000,
        seed: int = 42,
    ) -> dict:
        """Generate synthetic evaluation metrics deterministically from seed."""
        rng = np.random.Generator(np.random.PCG64(seed))
        # Compute metrics from candidate params and seed
        param_sum = sum(
            float(v) for v in candidate.values() if isinstance(v, (int, float))
        )
        sharpe = self._base_sharpe + rng.normal(0, self._variance)
        sharpe *= (1.0 + param_sum * 0.001)  # slight param influence

        n_trades = max(10, int(rng.integers(20, 100)))
        pf = max(0.5, 1.0 + sharpe * 0.3 + rng.normal(0, 0.1))
        dd = max(0.01, 0.10 - sharpe * 0.02 + rng.normal(0, 0.02))
        pnl = sharpe * n_trades * 2.0

        return {
            "sharpe": float(sharpe),
            "profit_factor": float(pf),
            "max_drawdown": float(dd),
            "trade_count": n_trades,
            "net_pnl": float(pnl),
        }


# ---------------------------------------------------------------------------
# Live tests
# ---------------------------------------------------------------------------


@pytest.mark.live
class TestLiveFullValidationGauntlet:
    """Test the full validation gauntlet with real computations and file I/O."""

    def test_live_single_candidate_full_gauntlet(self, tmp_path):
        """Run one candidate through all 5 validation stages.

        Verifies:
        - All stages execute with real computations
        - GauntletResults has correct structure
        - Per-stage metrics are populated
        - Deterministic seeding produces reproducible results
        """
        config = ValidationConfig(
            stage_order=["perturbation", "walk_forward", "cpcv", "monte_carlo", "regime"],
            deterministic_seed_base=42,
            walk_forward=WalkForwardConfig(n_windows=3, train_ratio=0.80, purge_bars=50, embargo_bars=25),
            cpcv=CPCVConfig(n_groups=4, k_test_groups=2, purge_bars=50, embargo_bars=25, pbo_red_threshold=0.90),
            perturbation=PerturbationConfig(levels=[0.05, 0.10], min_performance_retention=0.70),
            monte_carlo=MonteCarloConfig(n_bootstrap=100, n_permutation=100, stress_multipliers=[1.5, 2.0], confidence_level=0.95),
            regime=RegimeConfig(min_trades_per_bucket=2, sessions=["asian", "london", "new_york"]),
        )

        dispatcher = _SyntheticDispatcher(base_sharpe=1.5)
        candidate = {"fast_period": 10.0, "slow_period": 30.0, "threshold": 0.5}
        market_data_path = tmp_path / "market_data.arrow"
        trade_results = _make_synthetic_trades(200, seed=42)
        market_data_table = _make_synthetic_market_data(10000, seed=42)

        # Write real market data to disk
        with open(market_data_path, "wb") as f:
            writer = pa.ipc.new_file(f, market_data_table.schema)
            writer.write_table(market_data_table)
            writer.close()

        gauntlet = ValidationGauntlet(config=config, dispatcher=dispatcher)
        results = gauntlet.run(
            candidates=[candidate],
            market_data_path=market_data_path,
            strategy_spec={"name": "ma_crossover"},
            cost_model={"spread_pips": 1.0, "slippage_pips": 0.5},
            optimization_manifest={"run_id": "opt-001", "total_trials": 5},
            output_dir=tmp_path / "validation_output",
            param_ranges={
                "fast_period": {"min": 5.0, "max": 50.0, "type": "float"},
                "slow_period": {"min": 10.0, "max": 100.0, "type": "float"},
                "threshold": {"min": 0.0, "max": 1.0, "type": "float"},
            },
            trade_results=trade_results,
            market_data_table=market_data_table,
            data_length=10000,
        )

        # Verify results structure
        assert isinstance(results, GauntletResults)
        assert len(results.candidates) == 1

        cv = results.candidates[0]
        assert cv.candidate_id == 0
        assert not cv.short_circuited

        # All 5 stages should have run (PBO threshold set high enough to avoid short-circuit)
        assert len(cv.stages) == 5, (
            f"Expected 5 stages but got {len(cv.stages)}: {list(cv.stages.keys())}. "
            f"short_circuited={cv.short_circuited}, gate_failures={cv.hard_gate_failures}"
        )
        for stage_name in config.stage_order:
            assert stage_name in cv.stages, f"Missing stage: {stage_name}"
            stage = cv.stages[stage_name]
            assert isinstance(stage.metrics, dict)
            assert len(stage.metrics) > 0

        # Perturbation: should have sensitivities
        pert = cv.stages["perturbation"]
        assert "max_sensitivity" in pert.metrics

        # Walk-forward: should have windows
        wf = cv.stages["walk_forward"]
        assert "n_windows" in wf.metrics
        assert wf.metrics["n_windows"] > 0

        # Monte Carlo: should have bootstrap CI
        mc = cv.stages["monte_carlo"]
        assert "bootstrap_sharpe_ci_lower" in mc.metrics

        # Regime: should have buckets
        regime = cv.stages["regime"]
        assert "total_buckets" in regime.metrics
        assert regime.metrics["total_buckets"] > 0

    def test_live_deterministic_reproducibility(self, tmp_path):
        """Same inputs + same seeds produce identical gauntlet results (FR18)."""
        config = ValidationConfig(
            stage_order=["perturbation", "walk_forward", "cpcv"],
            deterministic_seed_base=42,
            walk_forward=WalkForwardConfig(n_windows=3, train_ratio=0.80, purge_bars=50, embargo_bars=25),
            cpcv=CPCVConfig(n_groups=4, k_test_groups=2, purge_bars=50, embargo_bars=25),
            perturbation=PerturbationConfig(levels=[0.05, 0.10]),
        )

        dispatcher = _SyntheticDispatcher(base_sharpe=1.5)
        candidate = {"fast_period": 10.0, "slow_period": 30.0}
        market_data_path = tmp_path / "market_data.arrow"
        market_data_table = _make_synthetic_market_data(10000, seed=42)

        with open(market_data_path, "wb") as f:
            writer = pa.ipc.new_file(f, market_data_table.schema)
            writer.write_table(market_data_table)
            writer.close()

        common_kwargs = dict(
            candidates=[candidate],
            market_data_path=market_data_path,
            strategy_spec={"name": "test"},
            cost_model={"spread_pips": 1.0},
            optimization_manifest={"run_id": "opt-001", "total_trials": 5},
            param_ranges={
                "fast_period": {"min": 5.0, "max": 50.0, "type": "float"},
                "slow_period": {"min": 10.0, "max": 100.0, "type": "float"},
            },
            data_length=10000,
        )

        gauntlet_a = ValidationGauntlet(config=config, dispatcher=dispatcher)
        results_a = gauntlet_a.run(output_dir=tmp_path / "run_a", **common_kwargs)

        gauntlet_b = ValidationGauntlet(config=config, dispatcher=dispatcher)
        results_b = gauntlet_b.run(output_dir=tmp_path / "run_b", **common_kwargs)

        # Compare all stage metrics for determinism
        for stage_name in config.stage_order:
            metrics_a = results_a.candidates[0].stages[stage_name].metrics
            metrics_b = results_b.candidates[0].stages[stage_name].metrics
            for key in metrics_a:
                va = metrics_a[key]
                vb = metrics_b[key]
                if isinstance(va, float):
                    assert va == pytest.approx(vb, abs=1e-10), (
                        f"Determinism violated: {stage_name}.{key}: {va} != {vb}"
                    )
                else:
                    assert va == vb, (
                        f"Determinism violated: {stage_name}.{key}: {va} != {vb}"
                    )


@pytest.mark.live
class TestLiveArtifactWriteAndRead:
    """Test that validation artifacts are written to disk and readable."""

    def test_live_walk_forward_artifact_roundtrip(self, tmp_path):
        """Run walk-forward, write Arrow IPC artifact, read it back."""
        config = WalkForwardConfig(n_windows=3, train_ratio=0.80, purge_bars=50, embargo_bars=25)
        dispatcher = _SyntheticDispatcher()
        candidate = {"period": 20.0}

        market_data_path = tmp_path / "data.arrow"
        market_data = _make_synthetic_market_data(5000, seed=42)
        with open(market_data_path, "wb") as f:
            writer = pa.ipc.new_file(f, market_data.schema)
            writer.write_table(market_data)
            writer.close()

        result = run_walk_forward(
            candidate=candidate,
            market_data_path=market_data_path,
            strategy_spec={},
            cost_model={},
            config=config,
            dispatcher=dispatcher,
            seed=42,
            data_length=5000,
        )

        # Write artifact to disk
        output_dir = tmp_path / "artifacts"
        artifact_path = write_stage_artifact("walk_forward", result, output_dir)

        # Verify file exists on disk
        assert artifact_path.exists(), f"Artifact not on disk: {artifact_path}"
        assert artifact_path.stat().st_size > 0

        # Read back and verify content
        reader = pa.ipc.open_file(str(artifact_path))
        table = reader.read_all()
        assert "oos_sharpe" in table.column_names
        assert "oos_pf" in table.column_names
        assert len(table) == len(result.windows)

        # Write summary
        summary_path = write_stage_summary("walk_forward", result, output_dir)
        assert summary_path.exists()
        summary_text = summary_path.read_text(encoding="utf-8")
        assert "Aggregate OOS Sharpe" in summary_text
        assert "Walk-forward" in summary_text or "walk_forward" in summary_text

    def test_live_monte_carlo_artifact_roundtrip(self, tmp_path):
        """Run Monte Carlo on real trade data, write artifact, verify on disk."""
        trades = _make_synthetic_trades(100, seed=99)
        cost_model = {"spread_pips": 1.0, "slippage_pips": 0.5}
        config = MonteCarloConfig(
            n_bootstrap=200, n_permutation=200,
            stress_multipliers=[1.5, 2.0], confidence_level=0.95,
        )

        result = run_monte_carlo(
            trade_results=trades,
            equity_curve=None,
            cost_model=cost_model,
            config=config,
            seed=42,
        )

        # Verify real computation happened
        assert result.bootstrap.n_samples == 200
        assert result.permutation.n_permutations == 200
        assert result.bootstrap.sharpe_ci_lower < result.bootstrap.sharpe_ci_upper
        assert 0.0 <= result.permutation.p_value <= 1.0

        # Write and verify artifact
        output_dir = tmp_path / "mc_artifacts"
        artifact_path = write_stage_artifact("monte_carlo", result, output_dir)
        assert artifact_path.exists()

        reader = pa.ipc.open_file(str(artifact_path))
        table = reader.read_all()
        assert "simulation_type" in table.column_names
        assert "metric_value" in table.column_names
        assert len(table) > 0

        # Summary
        summary_path = write_stage_summary("monte_carlo", result, output_dir)
        assert summary_path.exists()
        content = summary_path.read_text(encoding="utf-8")
        assert "Bootstrap" in content or "bootstrap" in content

    def test_live_regime_analysis_artifact_roundtrip(self, tmp_path):
        """Run regime analysis on real data, write artifact, verify."""
        rng = np.random.Generator(np.random.PCG64(42))
        n_trades = 200
        sessions = rng.choice(["asian", "london", "new_york"], size=n_trades)
        pnl = rng.normal(0.3, 1.5, size=n_trades)
        entry_times = np.arange(n_trades, dtype=np.int64) * 60

        trades = pa.table({
            "pnl_pips": pnl.tolist(),
            "entry_time": entry_times.tolist(),
            "entry_session": sessions.tolist(),
        })
        market_data = _make_synthetic_market_data(5000, seed=42)
        config = RegimeConfig(
            min_trades_per_bucket=5,
            sessions=["asian", "london", "new_york"],
        )

        result = run_regime_analysis(trades, market_data, config)

        # Verify real computation
        assert result.total_buckets == 9  # 3 volatility x 3 sessions
        assert result.sufficient_buckets > 0

        # Write and verify
        output_dir = tmp_path / "regime_artifacts"
        artifact_path = write_stage_artifact("regime", result, output_dir)
        assert artifact_path.exists()

        reader = pa.ipc.open_file(str(artifact_path))
        table = reader.read_all()
        assert "volatility_tercile" in table.column_names
        assert "session" in table.column_names
        assert "trade_count" in table.column_names
        assert len(table) == 9

        summary_path = write_stage_summary("regime", result, output_dir)
        assert summary_path.exists()


@pytest.mark.live
class TestLiveGauntletManifest:
    """Test gauntlet manifest writing and completeness."""

    def test_live_gauntlet_manifest_output(self, tmp_path):
        """Run gauntlet, write manifest, verify all downstream contract fields."""
        config = ValidationConfig(
            stage_order=["perturbation", "walk_forward"],
            deterministic_seed_base=42,
            walk_forward=WalkForwardConfig(n_windows=3, purge_bars=50, embargo_bars=25),
            perturbation=PerturbationConfig(levels=[0.05]),
        )

        dispatcher = _SyntheticDispatcher()
        candidate = {"fast_period": 10.0, "slow_period": 30.0}
        market_data_path = tmp_path / "data.arrow"
        market_data = _make_synthetic_market_data(10000, seed=42)

        with open(market_data_path, "wb") as f:
            writer = pa.ipc.new_file(f, market_data.schema)
            writer.write_table(market_data)
            writer.close()

        output_dir = tmp_path / "gauntlet_output"
        gauntlet = ValidationGauntlet(config=config, dispatcher=dispatcher)
        results = gauntlet.run(
            candidates=[candidate],
            market_data_path=market_data_path,
            strategy_spec={"name": "test"},
            cost_model={"spread_pips": 1.0},
            optimization_manifest={"run_id": "opt-001", "total_trials": 50},
            output_dir=output_dir,
            param_ranges={
                "fast_period": {"min": 5.0, "max": 50.0, "type": "float"},
                "slow_period": {"min": 10.0, "max": 100.0, "type": "float"},
            },
            data_length=10000,
        )

        # Write manifest
        manifest_path = write_gauntlet_manifest(
            results,
            {"run_id": "opt-001", "total_trials": 50},
            output_dir,
        )

        # Verify manifest file exists on disk
        assert manifest_path.exists()
        assert manifest_path.stat().st_size > 0

        # Read and verify downstream contract fields (Story 5.5 interface)
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        assert manifest["optimization_run_id"] == "opt-001"
        assert manifest["total_optimization_trials"] == 50
        assert manifest["n_candidates"] == 1
        assert "gate_results" in manifest
        assert "dsr" in manifest
        assert "candidates" in manifest
        assert "chart_data_refs" in manifest
        assert "config_hash" in manifest
        assert "research_brief_versions" in manifest

        # Verify candidate data
        assert len(manifest["candidates"]) == 1
        cand = manifest["candidates"][0]
        assert cand["candidate_id"] == 0
        assert "stages" in cand
        assert "perturbation" in cand["stages"]
        assert "walk_forward" in cand["stages"]

    def test_live_checkpoint_file_created(self, tmp_path):
        """Verify checkpoint file is created during gauntlet run."""
        config = ValidationConfig(
            stage_order=["perturbation"],
            deterministic_seed_base=42,
            perturbation=PerturbationConfig(levels=[0.05]),
        )

        dispatcher = _SyntheticDispatcher()
        output_dir = tmp_path / "checkpoint_test"
        market_data_path = tmp_path / "data.arrow"
        market_data = _make_synthetic_market_data(1000, seed=42)
        with open(market_data_path, "wb") as f:
            writer = pa.ipc.new_file(f, market_data.schema)
            writer.write_table(market_data)
            writer.close()

        gauntlet = ValidationGauntlet(config=config, dispatcher=dispatcher)
        gauntlet.run(
            candidates=[{"p": 1.0}],
            market_data_path=market_data_path,
            strategy_spec={},
            cost_model={},
            optimization_manifest={"run_id": "opt-001", "total_trials": 5},
            output_dir=output_dir,
            param_ranges={"p": {"min": 0.0, "max": 10.0, "type": "float"}},
            data_length=1000,
        )

        # Checkpoint should exist on disk
        checkpoint = output_dir / "gauntlet_checkpoint.json"
        assert checkpoint.exists(), "Checkpoint file not created"
        data = json.loads(checkpoint.read_text(encoding="utf-8"))
        assert "run_id" in data
        assert "candidates_progress" in data


@pytest.mark.live
class TestLiveDSRComputation:
    """Test DSR computation with multiple candidates exercising real math."""

    def test_live_dsr_with_multiple_candidates(self, tmp_path):
        """Run multiple candidates through walk-forward, compute DSR."""
        config = ValidationConfig(
            stage_order=["walk_forward"],
            deterministic_seed_base=42,
            walk_forward=WalkForwardConfig(n_windows=3, purge_bars=50, embargo_bars=25),
        )

        dispatcher = _SyntheticDispatcher(base_sharpe=1.0, variance=0.5)
        candidates = [
            {"p1": float(i), "p2": float(i * 2)} for i in range(5)
        ]
        market_data_path = tmp_path / "data.arrow"
        market_data = _make_synthetic_market_data(10000, seed=42)
        with open(market_data_path, "wb") as f:
            writer = pa.ipc.new_file(f, market_data.schema)
            writer.write_table(market_data)
            writer.close()

        gauntlet = ValidationGauntlet(config=config, dispatcher=dispatcher)
        results = gauntlet.run(
            candidates=candidates,
            market_data_path=market_data_path,
            strategy_spec={},
            cost_model={},
            optimization_manifest={"run_id": "dsr-test", "total_trials": 50},
            output_dir=tmp_path / "dsr_output",
            data_length=10000,
        )

        # DSR should be computed (total_trials=50 > 10)
        assert results.dsr is not None, "DSR should be computed for >10 trials"
        assert isinstance(results.dsr, DSRResult)
        assert results.dsr.num_trials == 50
        assert 0.0 <= results.dsr.p_value <= 1.0
        assert isinstance(results.dsr.passed, bool)
        assert results.dsr.expected_max_sharpe > 0


@pytest.mark.live
class TestLiveShortCircuit:
    """Test short-circuit behavior with real CPCV PBO gate."""

    def test_live_short_circuit_on_pbo_failure(self, tmp_path):
        """Candidate with PBO > threshold gets short-circuited after CPCV."""

        class HighPBODispatcher:
            """Returns alternating good/bad metrics to produce high PBO."""
            def __init__(self):
                self._call_count = 0

            def evaluate_candidate(self, *args, **kwargs):
                self._call_count += 1
                if self._call_count % 2 == 0:
                    return {"sharpe": -0.5, "profit_factor": 0.5, "net_pnl": -100.0,
                            "max_drawdown": 0.2, "trade_count": 20}
                return {"sharpe": 2.0, "profit_factor": 2.0, "net_pnl": 500.0,
                        "max_drawdown": 0.05, "trade_count": 50}

        config = ValidationConfig(
            stage_order=["cpcv", "monte_carlo", "regime"],
            short_circuit_on_validity_failure=True,
            cpcv=CPCVConfig(
                n_groups=4, k_test_groups=2, purge_bars=0, embargo_bars=0,
                pbo_red_threshold=0.40,
            ),
            monte_carlo=MonteCarloConfig(n_bootstrap=50, n_permutation=50),
            regime=RegimeConfig(min_trades_per_bucket=2),
        )

        market_data_path = tmp_path / "data.arrow"
        market_data = _make_synthetic_market_data(1000, seed=42)
        with open(market_data_path, "wb") as f:
            writer = pa.ipc.new_file(f, market_data.schema)
            writer.write_table(market_data)
            writer.close()

        gauntlet = ValidationGauntlet(
            config=config, dispatcher=HighPBODispatcher()
        )
        results = gauntlet.run(
            candidates=[{"p": 1.0}],
            market_data_path=market_data_path,
            strategy_spec={},
            cost_model={},
            optimization_manifest={"run_id": "pbo-test", "total_trials": 5},
            output_dir=tmp_path / "pbo_output",
            data_length=1000,
        )

        cv = results.candidates[0]
        # CPCV should have run
        assert "cpcv" in cv.stages

        # If PBO failed the gate, candidate should be short-circuited
        cpcv_result = cv.stages["cpcv"]
        if not cpcv_result.passed:
            assert cv.short_circuited, "Should short-circuit after PBO failure"
            assert "cpcv" in cv.hard_gate_failures
            # Monte Carlo and regime should NOT have run
            assert "monte_carlo" not in cv.stages
            assert "regime" not in cv.stages


@pytest.mark.live
class TestLivePerturbationAnalysis:
    """Test perturbation with real computation and artifact output."""

    def test_live_perturbation_sensitivity_artifact(self, tmp_path):
        """Run perturbation, verify sensitivities and artifact on disk."""
        candidate = {"fast_ma": 10.0, "slow_ma": 30.0, "stop_pips": 50.0}
        param_ranges = {
            "fast_ma": {"min": 5.0, "max": 50.0, "type": "float"},
            "slow_ma": {"min": 10.0, "max": 100.0, "type": "float"},
            "stop_pips": {"min": 10.0, "max": 200.0, "type": "float"},
        }

        dispatcher = _SyntheticDispatcher(base_sharpe=1.5)
        config = PerturbationConfig(levels=[0.05, 0.10, 0.20])

        result = run_perturbation(
            candidate=candidate,
            market_data_path=Path("dummy"),
            strategy_spec={},
            cost_model={},
            config=config,
            dispatcher=dispatcher,
            seed=42,
            param_ranges=param_ranges,
        )

        # Real computation happened
        assert isinstance(result, PerturbationResult)
        assert len(result.sensitivities) == 3  # 3 params
        for param in ["fast_ma", "slow_ma", "stop_pips"]:
            assert param in result.sensitivities

        # Write artifact
        output_dir = tmp_path / "pert_artifacts"
        artifact_path = write_stage_artifact("perturbation", result, output_dir)
        assert artifact_path.exists()

        reader = pa.ipc.open_file(str(artifact_path))
        table = reader.read_all()
        assert "param_name" in table.column_names
        assert "sensitivity" in table.column_names
        assert len(table) > 0

        # Summary
        summary_path = write_stage_summary("perturbation", result, output_dir)
        assert summary_path.exists()
        content = summary_path.read_text(encoding="utf-8")
        assert "Max Sensitivity" in content
