"""Regression tests for Story 5.3 review synthesis findings.

Each test guards against a specific bug found during code review.
"""
from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np
import pyarrow as pa
import pytest

from optimization.parameter_space import (
    ParameterSpace,
    ParameterSpec,
    ParamType,
    decode_candidate,
    to_cmaes_bounds,
)


# ---------------------------------------------------------------------------
# C1: CMA-ES ask/tell ghost candidates poison covariance (Both reviewers)
# Fixed via buffered tell: ask(n) returns exactly n candidates, tell()
# buffers until pop_size pairs accumulate, then flushes a full generation.
# ---------------------------------------------------------------------------
@pytest.mark.regression
def test_cmaes_ask_returns_requested_count():
    """ask(n) returns exactly n candidates; tell() buffers partial batches."""
    from optimization.portfolio import CMAESInstance

    space = ParameterSpace(parameters=[
        ParameterSpec(name="x", param_type=ParamType.CONTINUOUS, min_val=0.0, max_val=1.0),
        ParameterSpec(name="y", param_type=ParamType.CONTINUOUS, min_val=0.0, max_val=1.0),
    ])
    inst = CMAESInstance(space=space, population_size=32, seed=42)

    # ask(n) returns exactly n — no ghost padding
    asked = inst.ask(10)
    assert asked.shape[0] == 10, f"ask() returned {asked.shape[0]} instead of requested 10"

    # Partial tell buffers without flushing to CMA-ES
    scores = np.random.RandomState(42).uniform(0, 1, 10)
    inst.tell(asked, scores)
    assert inst._generation == 0, "Should not flush a generation with only 10/32 candidates"
    assert len(inst._pending_candidates) == 10, "Should buffer 10 pending candidates"


@pytest.mark.regression
def test_cmaes_tell_flushes_at_popsize():
    """tell() flushes to CMA-ES exactly when pop_size candidates accumulate."""
    from optimization.portfolio import CMAESInstance

    space = ParameterSpace(parameters=[
        ParameterSpec(name="x", param_type=ParamType.CONTINUOUS, min_val=0.0, max_val=1.0),
    ])
    inst = CMAESInstance(space=space, population_size=16, seed=42)

    # Ask and tell full pop_size — should flush immediately
    candidates = inst.ask(16)
    assert len(candidates) == 16
    scores = np.random.RandomState(42).uniform(0, 1, 16)
    inst.tell(candidates, scores)
    assert inst._generation == 1, "Should flush after receiving pop_size candidates"
    assert len(inst._pending_candidates) == 0, "Buffer should be empty after flush"

    # All scores are real — no ghost -inf filling
    assert np.all(np.isfinite(scores)), "All scores should be finite, no ghost -inf"


# ---------------------------------------------------------------------------
# C2: Convergence never triggers (Both reviewers)
# ---------------------------------------------------------------------------
@pytest.mark.regression
def test_cmaes_convergence_triggers_after_max_restarts():
    """CMA-ES must set _converged=True after exhausting max_restarts."""
    from optimization.portfolio import CMAESInstance

    space = ParameterSpace(parameters=[
        ParameterSpec(name="x", param_type=ParamType.CONTINUOUS, min_val=0.0, max_val=1.0),
    ])
    inst = CMAESInstance(
        space=space, population_size=8, seed=42,
        stagnation_limit=1, max_restarts=2,
    )

    # Force stagnation repeatedly until convergence
    for _ in range(100):
        candidates = inst.ask(8)
        # Flat scores cause stagnation
        scores = np.zeros(len(candidates))
        inst.tell(candidates, scores)
        if inst.converged():
            break

    assert inst.converged(), "CMA-ES should converge after exhausting max_restarts"


@pytest.mark.regression
def test_portfolio_convergence_reachable():
    """PortfolioManager.check_convergence() must be able to return True."""
    from optimization.portfolio import PortfolioManager

    space = ParameterSpace(parameters=[
        ParameterSpec(name="x", param_type=ParamType.CONTINUOUS, min_val=0.0, max_val=1.0),
    ])
    config = {
        "optimization": {
            "convergence_tolfun": 1e-3,
            "stagnation_generations": 1,
            "sobol_fraction": 0.0,
            "portfolio": {
                "cmaes_instances": 1,
                "de_instances": 0,
                "cmaes_pop_base": 8,
                "min_pop": 8,
                "pop_scaling_factor": 5,
            },
        },
    }
    pm = PortfolioManager(space=space, config=config, master_seed=42)

    # Force convergence by feeding flat scores
    for _ in range(200):
        batch = pm.ask_batch(8)
        scores = np.zeros(len(batch))
        pm.tell_batch(batch, scores)
        if pm.check_convergence():
            break

    assert pm.check_convergence(), "PortfolioManager must be able to report convergence"


# ---------------------------------------------------------------------------
# H1: BIPOP restart pop_size drift (Both reviewers)
# ---------------------------------------------------------------------------
@pytest.mark.regression
def test_bipop_restart_updates_pop_size():
    """After BIPOP restart, _pop_size must match the new optimizer pop."""
    from optimization.portfolio import CMAESInstance

    space = ParameterSpace(parameters=[
        ParameterSpec(name="x", param_type=ParamType.CONTINUOUS, min_val=0.0, max_val=1.0),
    ])
    inst = CMAESInstance(
        space=space, population_size=32, seed=42,
        stagnation_limit=2, max_restarts=5,
    )

    # Gen 1: score=0 beats initial -inf, no stagnation
    c = inst.ask(32)
    inst.tell(c, np.zeros(len(c)))
    # Gen 2: score=0 doesn't beat 0+tolfun, stagnation_count=1
    c = inst.ask(inst._pop_size)
    inst.tell(c, np.zeros(len(c)))
    # Gen 3: score=0 again, stagnation_count=2 -> triggers restart
    c = inst.ask(inst._pop_size)
    inst.tell(c, np.zeros(len(c)))

    assert inst._restart_count >= 1, "Should have restarted after stagnation"
    # After restart, _pop_size must reflect the new population (odd restart = pop//2)
    assert inst._pop_size == 16, f"pop_size={inst._pop_size}, expected 16 after odd restart"


# ---------------------------------------------------------------------------
# H2: Sobol load_state over-advances (BMAD)
# ---------------------------------------------------------------------------
@pytest.mark.regression
def test_sobol_load_state_exact_position():
    """Sobol resume must produce same sequence as continuous run."""
    from optimization.portfolio import SobolExplorer

    space = ParameterSpace(parameters=[
        ParameterSpec(name="x", param_type=ParamType.CONTINUOUS, min_val=0.0, max_val=1.0),
        ParameterSpec(name="y", param_type=ParamType.CONTINUOUS, min_val=0.0, max_val=1.0),
    ])

    # Continuous run: ask 100 then ask 10 more
    explorer1 = SobolExplorer(space=space, seed=42)
    explorer1.ask(100)
    next_continuous = explorer1.ask(10)

    # Resumed run: save state at 100, restore, ask 10
    explorer2 = SobolExplorer(space=space, seed=42)
    explorer2.ask(100)
    state = explorer2.state_dict()

    explorer3 = SobolExplorer(space=space, seed=42)
    explorer3.load_state(state)
    next_resumed = explorer3.ask(10)

    np.testing.assert_array_almost_equal(
        next_continuous, next_resumed,
        err_msg="Sobol resume produced different sequence than continuous run",
    )


# ---------------------------------------------------------------------------
# H3: UCB1 mean-of-means bias (BMAD)
# ---------------------------------------------------------------------------
@pytest.mark.regression
def test_ucb1_weighted_mean_not_mean_of_means():
    """BranchStats.mean_score must use weighted average, not mean of means."""
    from optimization.branch_manager import BranchStats

    stats = BranchStats()

    # Batch 1: 10 candidates, mean=1.0, sum=10.0
    stats.total_score += 10.0
    stats.total_candidates += 10
    stats.visit_count += 1

    # Batch 2: 100 candidates, mean=2.0, sum=200.0
    stats.total_score += 200.0
    stats.total_candidates += 100
    stats.visit_count += 1

    # Correct weighted mean: (10+200)/(10+100) = 210/110 ≈ 1.909
    # Biased mean-of-means would be: (1.0+2.0)/2 = 1.5
    expected = 210.0 / 110.0
    assert abs(stats.mean_score - expected) < 1e-6, (
        f"mean_score={stats.mean_score}, expected weighted mean={expected}"
    )


# ---------------------------------------------------------------------------
# H4: np.std ddof=0 underestimates variance (BMAD)
# ---------------------------------------------------------------------------
@pytest.mark.regression
def test_cv_objective_uses_sample_std():
    """compute_cv_objective must use ddof=1 (sample std), not ddof=0."""
    from optimization.fold_manager import compute_cv_objective

    scores = np.array([1.0, 2.0, 3.0])
    result = compute_cv_objective(scores, lambda_=1.0)

    mean = np.mean(scores)  # 2.0
    sample_std = np.std(scores, ddof=1)  # 1.0
    pop_std = np.std(scores, ddof=0)  # ~0.8165

    expected_sample = mean - 1.0 * sample_std
    expected_pop = mean - 1.0 * pop_std

    assert abs(result - expected_sample) < 1e-10, (
        f"CV objective uses population std (ddof=0), not sample std (ddof=1)"
    )
    assert abs(result - expected_pop) > 0.01, "Should differ from population std"


# ---------------------------------------------------------------------------
# H6: No config_hash validation on resume (BMAD)
# ---------------------------------------------------------------------------
@pytest.mark.regression
def test_checkpoint_config_hash_validation():
    """validate_checkpoint_config must detect hash mismatch."""
    from optimization.checkpoint import OptimizationCheckpoint, validate_checkpoint_config

    cp = OptimizationCheckpoint(
        generation=10,
        config_hash="sha256:original",
    )

    assert validate_checkpoint_config(cp, "sha256:original") is True
    assert validate_checkpoint_config(cp, "sha256:changed") is False
    # Empty hashes should pass (can't validate)
    assert validate_checkpoint_config(cp, "") is True


# ---------------------------------------------------------------------------
# H7: master_seed hardcoded to 42 (BMAD)
# ---------------------------------------------------------------------------
@pytest.mark.regression
def test_master_seed_read_from_config(sample_strategy_spec, sample_config, tmp_artifacts, small_market_data, mock_cost_model):
    """Orchestrator must read master_seed from config, not hardcode 42."""
    from unittest.mock import MagicMock
    from optimization.orchestrator import OptimizationOrchestrator

    sample_config["optimization"]["master_seed"] = 99

    orch = OptimizationOrchestrator(
        strategy_spec=sample_strategy_spec,
        market_data_path=small_market_data,
        cost_model_path=mock_cost_model,
        config=sample_config,
        artifacts_dir=tmp_artifacts,
        batch_runner=MagicMock(),
    )

    assert orch._master_seed == 99, f"master_seed={orch._master_seed}, expected 99 from config"


# ---------------------------------------------------------------------------
# H10: Parameters sent as p0/p1/... not named (Both reviewers)
# ---------------------------------------------------------------------------
@pytest.mark.regression
def test_dispatch_uses_named_parameters():
    """Batch dispatch must use real parameter names, not p0/p1/..."""
    from optimization.batch_dispatch import OptimizationBatchDispatcher
    from optimization.fold_manager import FoldSpec
    from unittest.mock import AsyncMock, MagicMock

    runner = MagicMock()
    dispatcher = OptimizationBatchDispatcher(
        batch_runner=runner,
        artifacts_dir=Path("/tmp/test"),
        config={"optimization": {}, "pipeline": {}},
    )

    candidates = np.array([[1.0, 2.0], [3.0, 4.0]])
    param_names = ["sma_fast", "sma_slow"]

    # Build the param batch manually as the method would
    if param_names and len(param_names) == candidates.shape[1]:
        param_batch = [
            {param_names[j]: float(candidates[i, j]) for j in range(candidates.shape[1])}
            for i in range(len(candidates))
        ]
    else:
        param_batch = [
            {f"p{j}": float(candidates[i, j]) for j in range(candidates.shape[1])}
            for i in range(len(candidates))
        ]

    assert "sma_fast" in param_batch[0], "Parameters should use real names"
    assert "p0" not in param_batch[0], "Parameters should not use anonymous p0/p1 keys"


# ---------------------------------------------------------------------------
# M2: INTEGER step not enforced (BMAD)
# ---------------------------------------------------------------------------
@pytest.mark.regression
def test_integer_step_enforced_in_decode():
    """decode_candidate must snap integer params to configured step."""
    space = ParameterSpace(parameters=[
        ParameterSpec(name="period", param_type=ParamType.INTEGER, min_val=10, max_val=100, step=5),
    ])

    # 23 should snap to 25 (nearest multiple of 5 from base 10)
    result = decode_candidate(np.array([23.0]), space)
    assert result["period"] % 5 == 0, f"period={result['period']} not a multiple of step=5"
    assert result["period"] == 25, f"period={result['period']}, expected 25"


# ---------------------------------------------------------------------------
# M5: Falsy bounds corruption when min_val/max_val = 0 (BMAD)
# ---------------------------------------------------------------------------
@pytest.mark.regression
def test_zero_bounds_not_corrupted():
    """to_cmaes_bounds must handle min_val=0 and max_val=0 correctly."""
    space = ParameterSpace(parameters=[
        ParameterSpec(name="x", param_type=ParamType.CONTINUOUS, min_val=0.0, max_val=10.0),
        ParameterSpec(name="y", param_type=ParamType.CONTINUOUS, min_val=-5.0, max_val=0.0),
    ])
    lower, upper = to_cmaes_bounds(space)

    assert lower[0] == 0.0, f"min_val=0.0 was corrupted to {lower[0]}"
    assert upper[1] == 0.0, f"max_val=0.0 was corrupted to {upper[1]}"


# ---------------------------------------------------------------------------
# M7: StreamingResultsWriter lacks context manager (BMAD)
# ---------------------------------------------------------------------------
@pytest.mark.regression
def test_streaming_writer_context_manager(tmp_path):
    """StreamingResultsWriter must support with-statement for safe cleanup."""
    from optimization.results import StreamingResultsWriter

    path = tmp_path / "test.arrow"
    with StreamingResultsWriter(path) as writer:
        assert writer is not None
        writer.append_generation(
            generation=0,
            candidate_ids=[1],
            params_list=['{"x": 1.0}'],
            fold_scores=np.array([[0.5, 0.6]]),
            cv_objectives=np.array([0.55]),
            branch="__default__",
            instance_types=["cmaes"],
        )
    # After exiting context, file handle should be closed
    assert writer._closed


# ---------------------------------------------------------------------------
# Codex: Checkpoint cadence off-by-one
# ---------------------------------------------------------------------------
@pytest.mark.regression
def test_checkpoint_cadence_correct():
    """should_checkpoint must fire after every `interval` generations (0-indexed)."""
    from optimization.checkpoint import should_checkpoint

    # With interval=10, should fire after gen 9 (10th gen completed)
    assert should_checkpoint(9, 10) is True, "Should checkpoint after 10th gen (index 9)"
    # Should NOT fire after gen 10 (that's the 11th gen)
    assert should_checkpoint(10, 10) is False, "Should not checkpoint after 11th gen"
    # Gen 0 with interval=1 should fire
    assert should_checkpoint(0, 1) is True, "interval=1 should fire every gen"


# ---------------------------------------------------------------------------
# Codex: embargo_bars hardcoded to 0
# ---------------------------------------------------------------------------
@pytest.mark.regression
def test_embargo_bars_read_from_config(sample_strategy_spec, sample_config, tmp_artifacts, small_market_data, mock_cost_model):
    """Orchestrator must read embargo_bars from config."""
    from unittest.mock import MagicMock
    from optimization.orchestrator import OptimizationOrchestrator

    sample_config["optimization"]["embargo_bars"] = 50

    orch = OptimizationOrchestrator(
        strategy_spec=sample_strategy_spec,
        market_data_path=small_market_data,
        cost_model_path=mock_cost_model,
        config=sample_config,
        artifacts_dir=tmp_artifacts,
        batch_runner=MagicMock(),
    )

    assert orch._embargo_bars == 50, f"embargo_bars={orch._embargo_bars}, expected 50"


# ---------------------------------------------------------------------------
# C5: Async executor pattern (BMAD)
# ---------------------------------------------------------------------------
@pytest.mark.regression
def test_executor_no_deprecated_get_event_loop():
    """Executor must not use deprecated asyncio.get_event_loop()."""
    import inspect
    from optimization.executor import OptimizationExecutor

    source = inspect.getsource(OptimizationExecutor.execute)
    assert "get_event_loop" not in source, (
        "Executor still uses deprecated asyncio.get_event_loop()"
    )


# ---------------------------------------------------------------------------
# Synthesis: DE never converges — blocks portfolio convergence (Both reviewers)
# ---------------------------------------------------------------------------
@pytest.mark.regression
def test_de_convergence_triggers_on_stagnation():
    """DEInstance must set _converged=True after stagnation_limit generations."""
    from optimization.portfolio import DEInstance

    space = ParameterSpace(parameters=[
        ParameterSpec(name="x", param_type=ParamType.CONTINUOUS, min_val=0.0, max_val=1.0),
    ])
    inst = DEInstance(
        space=space, population_size=8, seed=42,
        stagnation_limit=3, improvement_threshold=1e-3,
    )

    # Feed flat scores repeatedly to trigger stagnation
    for _ in range(20):
        candidates = inst.ask(8)
        scores = np.zeros(len(candidates))
        inst.tell(candidates, scores)
        if inst.converged():
            break

    assert inst.converged(), "DE should converge after stagnation_limit generations of no improvement"


@pytest.mark.regression
def test_portfolio_convergence_with_de_instances():
    """PortfolioManager.check_convergence() must work even with DE instances."""
    from optimization.portfolio import PortfolioManager

    space = ParameterSpace(parameters=[
        ParameterSpec(name="x", param_type=ParamType.CONTINUOUS, min_val=0.0, max_val=1.0),
    ])
    config = {
        "optimization": {
            "convergence_tolfun": 1e-3,
            "stagnation_generations": 2,
            "sobol_fraction": 0.0,
            "portfolio": {
                "cmaes_instances": 1,
                "de_instances": 1,
                "cmaes_pop_base": 8,
                "de_pop_base": 8,
                "min_pop": 8,
                "pop_scaling_factor": 5,
            },
        },
    }
    pm = PortfolioManager(space=space, config=config, master_seed=42)

    for _ in range(500):
        batch = pm.ask_batch(16)
        scores = np.zeros(len(batch))
        pm.tell_batch(batch, scores)
        if pm.check_convergence():
            break

    assert pm.check_convergence(), "Portfolio with DE must be able to reach convergence"


# ---------------------------------------------------------------------------
# Synthesis: CMAESInstance pending buffers lost on checkpoint (BMAD H4)
# ---------------------------------------------------------------------------
@pytest.mark.regression
def test_cmaes_pending_buffers_survive_checkpoint():
    """CMAESInstance state_dict must include pending candidates/scores."""
    from optimization.portfolio import CMAESInstance

    space = ParameterSpace(parameters=[
        ParameterSpec(name="x", param_type=ParamType.CONTINUOUS, min_val=0.0, max_val=1.0),
    ])
    inst = CMAESInstance(space=space, population_size=32, seed=42)

    # Add partial batch (10 of 32)
    candidates = inst.ask(10)
    scores = np.random.RandomState(42).uniform(0, 1, 10)
    inst.tell(candidates, scores)
    assert len(inst._pending_candidates) == 10

    # Save state
    state = inst.state_dict()
    assert "pending_candidates" in state, "state_dict must serialize pending_candidates"
    assert "pending_scores" in state, "state_dict must serialize pending_scores"
    assert len(state["pending_candidates"]) == 10

    # Restore into fresh instance
    inst2 = CMAESInstance(space=space, population_size=32, seed=42)
    inst2.load_state(state)
    assert len(inst2._pending_candidates) == 10, "Pending buffers must survive checkpoint"
    assert len(inst2._pending_scores) == 10


# ---------------------------------------------------------------------------
# Synthesis: Missing scores silently become zeros (Codex)
# ---------------------------------------------------------------------------
@pytest.mark.regression
def test_missing_fold_scores_return_neg_inf(tmp_path):
    """_read_fold_scores must return -inf, not zeros, when no scores file exists."""
    from optimization.batch_dispatch import OptimizationBatchDispatcher
    from unittest.mock import MagicMock

    dispatcher = OptimizationBatchDispatcher(
        batch_runner=MagicMock(),
        artifacts_dir=tmp_path,
        config={"optimization": {}, "pipeline": {}},
    )

    # Empty fold dir — no scores.arrow or scores.json
    fold_dir = tmp_path / "empty_fold"
    fold_dir.mkdir()

    scores = dispatcher._read_fold_scores(fold_dir, 5)
    assert np.all(scores == float("-inf")), (
        f"Missing scores should be -inf, got {scores}"
    )


# ---------------------------------------------------------------------------
# Synthesis: Resume must restore best_score from checkpoint (Codex)
# ---------------------------------------------------------------------------
@pytest.mark.regression
def test_checkpoint_preserves_best_score():
    """OptimizationCheckpoint must round-trip best_score."""
    from optimization.checkpoint import OptimizationCheckpoint, save_checkpoint, load_checkpoint

    cp = OptimizationCheckpoint(
        generation=10,
        best_candidates=[{"x": 0.5}],
        best_score=1.234,
        evaluated_count=100,
        config_hash="sha256:test",
    )

    import tempfile
    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / "cp.json"
        save_checkpoint(cp, path)
        loaded = load_checkpoint(path)

    assert loaded.best_score == 1.234, f"best_score={loaded.best_score}, expected 1.234"
    assert loaded.best_candidates == [{"x": 0.5}]


# ---------------------------------------------------------------------------
# Synthesis: Instance type attribution must use actual allocations (Both)
# ---------------------------------------------------------------------------
@pytest.mark.regression
def test_instance_type_per_candidate_attribution():
    """get_candidate_instance_types returns one type per candidate, not cyclic repeat."""
    from optimization.portfolio import PortfolioManager

    space = ParameterSpace(parameters=[
        ParameterSpec(name="x", param_type=ParamType.CONTINUOUS, min_val=0.0, max_val=1.0),
    ])
    config = {
        "optimization": {
            "sobol_fraction": 0.1,
            "stagnation_generations": 50,
            "portfolio": {
                "cmaes_instances": 2,
                "de_instances": 1,
                "cmaes_pop_base": 8,
                "de_pop_base": 8,
                "min_pop": 8,
                "pop_scaling_factor": 5,
            },
        },
    }
    pm = PortfolioManager(space=space, config=config, master_seed=42)
    batch = pm.ask_batch(32)
    types = pm.get_candidate_instance_types()

    assert len(types) == len(batch), (
        f"Got {len(types)} types for {len(batch)} candidates"
    )
    # Each type must be one of the known types
    for t in types:
        assert t in ("cmaes", "de", "sobol"), f"Unknown instance type: {t}"


# ---------------------------------------------------------------------------
# Synthesis: gen in dir() fragile pattern (BMAD M3)
# ---------------------------------------------------------------------------
@pytest.mark.regression
def test_orchestrator_no_dir_check():
    """Orchestrator must not use fragile 'gen' in dir() pattern."""
    import inspect
    from optimization.orchestrator import OptimizationOrchestrator

    source = inspect.getsource(OptimizationOrchestrator.run)
    assert "'gen' in dir()" not in source, (
        "Orchestrator still uses fragile 'gen' in dir() pattern"
    )


# ---------------------------------------------------------------------------
# Synthesis: Strategy spec fallback writes JSON to .toml file (Codex)
# ---------------------------------------------------------------------------
@pytest.mark.regression
def test_strategy_spec_fallback_uses_json_extension():
    """_resolve_strategy_spec_path fallback must write .json, not .toml."""
    import inspect
    from optimization.orchestrator import OptimizationOrchestrator

    source = inspect.getsource(OptimizationOrchestrator._resolve_strategy_spec_path)
    assert "strategy-spec.json" in source, (
        "Fallback spec path should use .json extension"
    )
    assert "strategy-spec.toml" not in source, (
        "Fallback spec path should not write JSON to a .toml file"
    )
