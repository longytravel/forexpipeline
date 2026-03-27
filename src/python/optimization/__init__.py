"""Optimization orchestrator package (Epic 5, Story 5.3).

Manages portfolio-based optimization via ask/tell with CMA-ES, DE, and
Sobol quasi-random exploration.  Dispatches batch evaluations to the Rust
evaluator with CV-inside-objective fold management.
"""
