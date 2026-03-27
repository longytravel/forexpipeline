"""Algorithm portfolio manager (Story 5.3, AC #1, #6, #7, #10).

Manages CMA-ES, DE, and Sobol quasi-random instances using ask/tell.
Population sizes scale with parameter dimensionality.
"""
from __future__ import annotations

import math
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

import numpy as np
from scipy.stats import qmc

from logging_setup.setup import get_logger
from optimization.parameter_space import ParameterSpace, to_cmaes_bounds

logger = get_logger("optimization.portfolio")


class AlgorithmInstance(ABC):
    """Protocol for ask/tell algorithm instances."""

    @abstractmethod
    def ask(self, n: int) -> np.ndarray:
        """Request n candidate vectors. Returns (n, dims) array."""
        ...

    @abstractmethod
    def tell(self, candidates: np.ndarray, scores: np.ndarray) -> None:
        """Feed scores back for the given candidates."""
        ...

    @abstractmethod
    def converged(self) -> bool:
        """Whether this instance has converged."""
        ...

    @abstractmethod
    def state_dict(self) -> dict:
        """Serialize instance state for checkpointing."""
        ...

    @abstractmethod
    def load_state(self, state: dict) -> None:
        """Restore instance state from checkpoint."""
        ...


class CMAESInstance(AlgorithmInstance):
    """CMA-ES instance via cmaes library with BIPOP restart logic."""

    def __init__(
        self,
        space: ParameterSpace,
        population_size: int,
        seed: int,
        tolfun: float = 1e-3,
        stagnation_limit: int = 50,
        max_restarts: int = 5,
    ):
        from cmaes import CMA

        lower, upper = to_cmaes_bounds(space)
        self._dims = space.n_dims
        self._pop_size = population_size
        self._seed = seed
        self._tolfun = tolfun
        self._stagnation_limit = stagnation_limit
        self._max_restarts = max_restarts
        self._stagnation_count = 0
        self._best_score = float("-inf")
        self._converged = False
        self._generation = 0
        self._restart_count = 0

        mean = (lower + upper) / 2.0
        sigma = float(np.max(upper - lower)) / 4.0

        self._optimizer = CMA(
            mean=mean,
            sigma=sigma,
            bounds=np.column_stack([lower, upper]),
            seed=seed,
            population_size=population_size,
        )
        self._lower = lower
        self._upper = upper
        self._pending_candidates: list[np.ndarray] = []
        self._pending_scores: list[float] = []

    def ask(self, n: int) -> np.ndarray:
        """Request n candidate vectors from CMA-ES.

        Each candidate is clipped to parameter bounds.
        """
        candidates = []
        for _ in range(n):
            x = self._optimizer.ask()
            x = np.clip(x, self._lower, self._upper)
            candidates.append(x)
        return np.array(candidates)

    def tell(self, candidates: np.ndarray, scores: np.ndarray) -> None:
        """Buffer scores and flush to CMA-ES when pop_size pairs accumulate.

        CMA-ES requires exactly pop_size solutions per tell() call.
        This buffers partial batches and flushes complete generations.
        """
        for c, s in zip(candidates, scores):
            self._pending_candidates.append(c)
            self._pending_scores.append(float(s))

        # Flush complete generations
        while len(self._pending_candidates) >= self._pop_size:
            batch_c = self._pending_candidates[:self._pop_size]
            batch_s = self._pending_scores[:self._pop_size]
            self._pending_candidates = self._pending_candidates[self._pop_size:]
            self._pending_scores = self._pending_scores[self._pop_size:]

            # cmaes minimizes, so negate scores (we maximize)
            solutions = [(c, -s) for c, s in zip(batch_c, batch_s)]
            self._optimizer.tell(solutions)
            self._generation += 1

            best_this_gen = max(batch_s)
            if best_this_gen > self._best_score + self._tolfun:
                self._best_score = best_this_gen
                self._stagnation_count = 0
            else:
                self._stagnation_count += 1

            # BIPOP restart on stagnation
            if self._stagnation_count >= self._stagnation_limit:
                if self._restart_count >= self._max_restarts:
                    self._converged = True
                    logger.info(
                        f"CMA-ES converged after {self._max_restarts} restarts",
                        extra={
                            "component": "optimization.portfolio",
                            "ctx": {"restarts": self._restart_count, "generation": self._generation},
                        },
                    )
                else:
                    self._restart()

    def _restart(self) -> None:
        """BIPOP restart: alternate between small and large populations."""
        from cmaes import CMA

        self._restart_count += 1
        new_seed = self._seed + self._restart_count * 1000

        # BIPOP: alternate between large and small populations
        if self._restart_count % 2 == 0:
            pop = min(self._pop_size * 2, 4096)
        else:
            pop = max(self._pop_size // 2, 16)

        mean = (self._lower + self._upper) / 2.0
        sigma = float(np.max(self._upper - self._lower)) / 4.0

        self._optimizer = CMA(
            mean=mean,
            sigma=sigma,
            bounds=np.column_stack([self._lower, self._upper]),
            seed=new_seed,
            population_size=pop,
        )
        self._pop_size = pop  # Track actual pop size after restart
        self._stagnation_count = 0
        self._best_score = float("-inf")
        self._pending_candidates = []
        self._pending_scores = []

        logger.info(
            f"CMA-ES restart #{self._restart_count} (pop={pop})",
            extra={
                "component": "optimization.portfolio",
                "ctx": {"restart": self._restart_count, "pop": pop, "seed": new_seed},
            },
        )

    def narrow_bounds(self, narrowed_bounds: dict[str, tuple[float, float]]) -> None:
        """Narrow parameter bounds and reinitialize the CMA-ES optimizer.

        Clamps existing lower/upper to the narrowed range, then creates a
        fresh CMA-ES instance centred on the new bounds.

        Args:
            narrowed_bounds: Mapping of param_name -> (new_lower, new_upper).
                Note: bounds are applied positionally — the dict values are
                used if the parameter's positional name matches.  For
                simplicity, this accepts index-keyed bounds too.
        """
        from cmaes import CMA

        # Apply narrowing per dimension (names aren't stored here, so we
        # accept positional index as string key too)
        for key, (new_lo, new_hi) in narrowed_bounds.items():
            idx = None
            if isinstance(key, int):
                idx = key
            elif isinstance(key, str) and key.isdigit():
                idx = int(key)
            if idx is not None and 0 <= idx < self._dims:
                self._lower[idx] = max(self._lower[idx], new_lo)
                self._upper[idx] = min(self._upper[idx], new_hi)
                # Ensure lower <= upper
                if self._lower[idx] > self._upper[idx]:
                    mid = (new_lo + new_hi) / 2.0
                    self._lower[idx] = mid
                    self._upper[idx] = mid

        mean = (self._lower + self._upper) / 2.0
        sigma = float(np.max(self._upper - self._lower)) / 4.0
        sigma = max(sigma, 1e-8)  # Avoid zero sigma

        self._optimizer = CMA(
            mean=mean,
            sigma=sigma,
            bounds=np.column_stack([self._lower, self._upper]),
            seed=self._seed + self._restart_count * 1000 + 500,
            population_size=self._pop_size,
        )
        self._stagnation_count = 0
        self._pending_candidates = []
        self._pending_scores = []

    def set_initial_mean(self, candidate: np.ndarray) -> None:
        """Reinitialize this CMA-ES instance with a specific mean vector.

        Used for warm-starting from pre-screening top candidates.

        Args:
            candidate: Parameter vector to use as the initial mean.
        """
        from cmaes import CMA

        mean = np.clip(candidate, self._lower, self._upper).astype(np.float64)
        sigma = float(np.max(self._upper - self._lower)) / 4.0

        self._optimizer = CMA(
            mean=mean,
            sigma=sigma,
            bounds=np.column_stack([self._lower, self._upper]),
            seed=self._seed,
            population_size=self._pop_size,
        )
        self._stagnation_count = 0
        self._pending_candidates = []
        self._pending_scores = []

    def converged(self) -> bool:
        return self._converged

    def state_dict(self) -> dict:
        return {
            "type": "cmaes",
            "generation": self._generation,
            "restart_count": self._restart_count,
            "stagnation_count": self._stagnation_count,
            "best_score": self._best_score,
            "seed": self._seed,
            "pop_size": self._pop_size,
            "converged": self._converged,
            "pending_candidates": [c.tolist() for c in self._pending_candidates],
            "pending_scores": list(self._pending_scores),
        }

    def load_state(self, state: dict) -> None:
        self._generation = state["generation"]
        self._restart_count = state["restart_count"]
        self._stagnation_count = state["stagnation_count"]
        self._best_score = state["best_score"]
        self._converged = state.get("converged", False)
        self._pending_candidates = [
            np.array(c) for c in state.get("pending_candidates", [])
        ]
        self._pending_scores = list(state.get("pending_scores", []))


class DEInstance(AlgorithmInstance):
    """Differential Evolution instance via Nevergrad TwoPointsDE."""

    def __init__(
        self,
        space: ParameterSpace,
        population_size: int,
        seed: int,
        stagnation_limit: int = 50,
        improvement_threshold: float = 1e-3,
    ):
        import nevergrad as ng
        from optimization.parameter_space import to_nevergrad_params

        self._dims = space.n_dims
        self._pop_size = population_size
        self._seed = seed
        self._generation = 0
        self._best_score = float("-inf")
        self._converged = False
        self._stagnation_count = 0
        self._stagnation_limit = stagnation_limit
        self._improvement_threshold = improvement_threshold

        ng_params = to_nevergrad_params(space)
        instrumentation = ng.p.Instrumentation(**ng_params)

        self._optimizer = ng.optimizers.TwoPointsDE(
            parametrization=instrumentation,
            budget=population_size * 10000,
            num_workers=population_size,
        )
        self._optimizer.parametrization.random_state = np.random.RandomState(seed)
        self._space = space
        self._pending: list[Any] = []

    def ask(self, n: int) -> np.ndarray:
        candidates = []
        self._pending = []
        for _ in range(n):
            x = self._optimizer.ask()
            self._pending.append(x)
            # Convert to flat vector
            vec = self._ng_to_vec(x)
            candidates.append(vec)
        return np.array(candidates)

    def _ng_to_vec(self, x: Any) -> np.ndarray:
        """Convert Nevergrad candidate to flat numpy vector."""
        kwargs = x.kwargs
        vec = np.zeros(self._dims, dtype=np.float64)
        for i, p in enumerate(self._space.parameters):
            val = kwargs.get(p.name, 0.0)
            if isinstance(val, (int, float)):
                vec[i] = float(val)
            elif isinstance(val, str) and p.choices:
                vec[i] = float(p.choices.index(val)) if val in p.choices else 0.0
            else:
                vec[i] = float(val) if val is not None else 0.0
        return vec

    def tell(self, candidates: np.ndarray, scores: np.ndarray) -> None:
        # Nevergrad minimizes, negate scores
        n = min(len(self._pending), len(scores))
        for i in range(n):
            self._optimizer.tell(self._pending[i], -float(scores[i]))
        self._generation += 1
        best = float(np.max(scores))
        if best > self._best_score + self._improvement_threshold:
            self._best_score = best
            self._stagnation_count = 0
        else:
            self._stagnation_count += 1

        if self._stagnation_count >= self._stagnation_limit and not self._converged:
            self._converged = True
            logger.info(
                f"DE converged after {self._generation} generations (stagnation)",
                extra={
                    "component": "optimization.portfolio",
                    "ctx": {
                        "generation": self._generation,
                        "stagnation_count": self._stagnation_count,
                        "best_score": self._best_score,
                    },
                },
            )
        self._pending = []

    def converged(self) -> bool:
        return self._converged

    def state_dict(self) -> dict:
        return {
            "type": "de",
            "generation": self._generation,
            "best_score": self._best_score,
            "seed": self._seed,
            "pop_size": self._pop_size,
            "converged": self._converged,
            "stagnation_count": self._stagnation_count,
        }

    def load_state(self, state: dict) -> None:
        self._generation = state["generation"]
        self._best_score = state["best_score"]
        self._converged = state.get("converged", False)
        self._stagnation_count = state.get("stagnation_count", 0)


class SobolExplorer(AlgorithmInstance):
    """Quasi-random Sobol sampling for exploration coverage."""

    def __init__(self, space: ParameterSpace, seed: int):
        self._dims = space.n_dims
        self._seed = seed
        self._space = space
        self._index = 0
        self._sampler = qmc.Sobol(d=max(1, self._dims), seed=seed)
        lower, upper = to_cmaes_bounds(space)
        self._lower = lower
        self._upper = upper

    def ask(self, n: int) -> np.ndarray:
        # Power-of-2 sampling for Sobol, then take first n
        m = max(n, 1)
        power = max(1, math.ceil(math.log2(m)))
        draw_count = 2**power
        samples = self._sampler.random(draw_count)[:n]
        # Scale from [0,1] to parameter bounds
        scaled = qmc.scale(samples, self._lower, self._upper)
        # Track actual positions consumed (power-of-2), not just n
        self._index += draw_count
        return scaled

    def tell(self, candidates: np.ndarray, scores: np.ndarray) -> None:
        pass  # Sobol doesn't learn from scores

    def converged(self) -> bool:
        return False  # Never converges — always explores

    def state_dict(self) -> dict:
        return {
            "type": "sobol",
            "index": self._index,
            "seed": self._seed,
        }

    def load_state(self, state: dict) -> None:
        self._index = state["index"]
        # Re-advance sampler to exact index position
        if self._index > 0:
            self._sampler = qmc.Sobol(d=max(1, self._dims), seed=self._seed)
            self._sampler.fast_forward(self._index)


@dataclass
class InstanceAllocation:
    """Tracks which candidates belong to which instance."""
    instance_idx: int
    instance_type: str
    start: int  # index into batch
    count: int


class PortfolioManager:
    """Manages all algorithm instances and distributes batch budget."""

    def __init__(self, space: ParameterSpace, config: dict, master_seed: int = 42):
        opt_config = config.get("optimization", {})
        portfolio_config = opt_config.get("portfolio", {})

        n_params = space.n_dims
        pop_scaling = portfolio_config.get("pop_scaling_factor", 5)
        min_pop = portfolio_config.get("min_pop", 128)
        cmaes_pop_base = portfolio_config.get("cmaes_pop_base", 128)
        de_pop_base = portfolio_config.get("de_pop_base", 150)
        n_cmaes = portfolio_config.get("cmaes_instances", 10)
        n_de = portfolio_config.get("de_instances", 3)
        tolfun = opt_config.get("convergence_tolfun", 1e-3)
        stagnation = opt_config.get("stagnation_generations", 50)
        sobol_fraction = opt_config.get("sobol_fraction", 0.1)

        # Pop sizing: max(min_pop, pop_scaling * N_params)
        cmaes_pop = max(min_pop, pop_scaling * n_params, cmaes_pop_base)
        de_pop = max(min_pop, pop_scaling * n_params, de_pop_base)

        # Scale instance count inversely with dimensionality
        if n_params > 20:
            n_cmaes = max(3, n_cmaes // 2)
            n_de = max(1, n_de // 2)

        self._instances: list[AlgorithmInstance] = []
        self._instance_types: list[str] = []
        self._sobol_fraction = sobol_fraction

        # Create CMA-ES instances
        for i in range(n_cmaes):
            seed = master_seed + i
            inst = CMAESInstance(
                space=space,
                population_size=cmaes_pop,
                seed=seed,
                tolfun=tolfun,
                stagnation_limit=stagnation,
            )
            self._instances.append(inst)
            self._instance_types.append("cmaes")

        # Create DE instances
        for i in range(n_de):
            seed = master_seed + 1000 + i
            inst = DEInstance(
                space=space,
                population_size=de_pop,
                seed=seed,
                stagnation_limit=stagnation,
            )
            self._instances.append(inst)
            self._instance_types.append("de")

        # Sobol explorer
        self._sobol = SobolExplorer(space=space, seed=master_seed + 2000)
        self._instances.append(self._sobol)
        self._instance_types.append("sobol")

        self._allocations: list[InstanceAllocation] = []

        logger.info(
            f"Portfolio: {n_cmaes} CMA-ES (pop={cmaes_pop}), "
            f"{n_de} DE (pop={de_pop}), 1 Sobol",
            extra={
                "component": "optimization.portfolio",
                "ctx": {
                    "n_cmaes": n_cmaes,
                    "n_de": n_de,
                    "cmaes_pop": cmaes_pop,
                    "de_pop": de_pop,
                    "n_params": n_params,
                },
            },
        )

    def ask_batch(self, batch_size: int) -> np.ndarray:
        """Collect candidates from all instances up to batch_size."""
        sobol_count = max(1, int(batch_size * self._sobol_fraction))
        algo_budget = batch_size - sobol_count
        n_algo = len(self._instances) - 1  # exclude sobol

        per_instance = max(1, algo_budget // max(1, n_algo))

        all_candidates: list[np.ndarray] = []
        self._allocations = []
        offset = 0

        # Ask from algorithm instances
        for i, inst in enumerate(self._instances[:-1]):
            count = min(per_instance, batch_size - offset - sobol_count)
            if count <= 0:
                break
            candidates = inst.ask(count)
            all_candidates.append(candidates)
            self._allocations.append(InstanceAllocation(
                instance_idx=i,
                instance_type=self._instance_types[i],
                start=offset,
                count=len(candidates),
            ))
            offset += len(candidates)

        # Ask from Sobol explorer
        sobol_candidates = self._sobol.ask(sobol_count)
        all_candidates.append(sobol_candidates)
        self._allocations.append(InstanceAllocation(
            instance_idx=len(self._instances) - 1,
            instance_type="sobol",
            start=offset,
            count=len(sobol_candidates),
        ))

        return np.vstack(all_candidates)

    def tell_batch(self, candidates: np.ndarray, scores: np.ndarray) -> None:
        """Route scores back to originating instances."""
        for alloc in self._allocations:
            inst = self._instances[alloc.instance_idx]
            c = candidates[alloc.start:alloc.start + alloc.count]
            s = scores[alloc.start:alloc.start + alloc.count]
            if len(c) > 0:
                inst.tell(c, s)

    def check_convergence(self) -> bool:
        """Check if all algorithm instances have converged."""
        # Sobol never converges — only check algo instances
        return all(
            inst.converged()
            for inst in self._instances[:-1]
        )

    @property
    def instance_types(self) -> list[str]:
        return list(self._instance_types)

    @property
    def allocations(self) -> list[InstanceAllocation]:
        return list(self._allocations)

    def get_candidate_instance_types(self) -> list[str]:
        """Return per-candidate instance type labels from last ask_batch allocations."""
        result: list[str] = []
        for alloc in self._allocations:
            result.extend([alloc.instance_type] * alloc.count)
        return result

    def narrow_bounds(self, narrowed_bounds: dict[str, tuple[float, float]]) -> None:
        """Narrow parameter bounds and restart CMA-ES instances.

        For each CMA-ES instance, clamp its lower/upper bounds to the
        narrowed range, then reinitialize the optimizer with the new bounds.
        DE and Sobol instances are not affected (DE uses Nevergrad's internal
        bounds; Sobol is purely exploratory).

        Args:
            narrowed_bounds: Mapping of param_name -> (new_lower, new_upper).
        """
        for inst in self._instances:
            if isinstance(inst, CMAESInstance):
                inst.narrow_bounds(narrowed_bounds)

    def warm_start(self, top_candidates: list[np.ndarray]) -> None:
        """Seed CMA-ES instances with pre-screening top candidates.

        Distributes top candidates across CMA-ES instances as initial mean
        vectors.  Each CMA-ES instance gets one candidate (round-robin).

        Args:
            top_candidates: List of parameter vectors to use as initial means.
        """
        cmaes_instances = [
            inst for inst in self._instances if isinstance(inst, CMAESInstance)
        ]
        if not cmaes_instances or not top_candidates:
            return
        for i, inst in enumerate(cmaes_instances):
            candidate = top_candidates[i % len(top_candidates)]
            inst.set_initial_mean(candidate)
        logger.info(
            f"Warm-started {len(cmaes_instances)} CMA-ES instances with "
            f"{len(top_candidates)} candidates",
            extra={
                "component": "optimization.portfolio",
                "ctx": {
                    "n_cmaes": len(cmaes_instances),
                    "n_candidates": len(top_candidates),
                },
            },
        )

    def state_dict(self) -> dict:
        return {
            "instances": [inst.state_dict() for inst in self._instances],
            "sobol_fraction": self._sobol_fraction,
        }

    def load_state(self, state: dict) -> None:
        for inst, inst_state in zip(self._instances, state.get("instances", [])):
            inst.load_state(inst_state)
