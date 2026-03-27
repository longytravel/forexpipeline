"""Strategy specification package (D10 specification layer)."""

from strategy.confirmer import ConfirmationResult, confirm_specification
from strategy.defaults import apply_defaults
from strategy.dialogue_parser import (
    IntentCaptureError,
    StrategyIntent,
    parse_strategy_intent,
)
from strategy.hasher import compute_spec_hash, verify_spec_hash
from strategy.indicator_registry import get_indicator_params, is_indicator_known
from strategy.intent_capture import CaptureResult, capture_strategy_intent
from strategy.loader import load_strategy_spec, validate_or_die_strategy, validate_strategy_spec
from strategy.modifier import ModificationIntent, ModificationResult, apply_modifications
from strategy.reviewer import StrategySummary, format_summary_text, generate_summary
from strategy.spec_generator import generate_specification
from strategy.specification import StrategySpecification
from strategy.storage import list_versions, load_latest_version, save_strategy_spec
from strategy.versioner import (
    SpecificationManifest,
    VersionDiff,
    VersionEntry,
    compute_version_diff,
    format_diff_text,
    increment_version,
    load_manifest,
    save_manifest,
)

__all__ = [
    "StrategySpecification",
    "StrategyIntent",
    "CaptureResult",
    "IntentCaptureError",
    "load_strategy_spec",
    "validate_strategy_spec",
    "validate_or_die_strategy",
    "compute_spec_hash",
    "verify_spec_hash",
    "save_strategy_spec",
    "load_latest_version",
    "list_versions",
    "is_indicator_known",
    "get_indicator_params",
    "parse_strategy_intent",
    "apply_defaults",
    "generate_specification",
    "capture_strategy_intent",
    # Story 2.5: Review, Confirmation & Versioning
    "StrategySummary",
    "generate_summary",
    "format_summary_text",
    "VersionDiff",
    "VersionEntry",
    "SpecificationManifest",
    "increment_version",
    "compute_version_diff",
    "format_diff_text",
    "load_manifest",
    "save_manifest",
    "ConfirmationResult",
    "confirm_specification",
    "ModificationIntent",
    "ModificationResult",
    "apply_modifications",
]
