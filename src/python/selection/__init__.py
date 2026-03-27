"""Advanced candidate selection subsystem (Story 5.6, FR26/FR27/FR28).

Growth-phase module: HDBSCAN clustering, multi-objective ranking (TOPSIS+CRITIC),
MAP-Elites diversity archive, and equity curve quality metrics.
"""
from selection.executor import SelectionExecutor
from selection.orchestrator import SelectionOrchestrator

__all__ = ["SelectionExecutor", "SelectionOrchestrator"]
