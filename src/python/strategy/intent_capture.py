"""Intent Capture Orchestrator — main entry point for strategy creation (D10, D9).

Orchestrates: parse -> defaults -> generate -> validate -> save -> log.
Single function the skill calls — clean interface boundary.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from logging_setup.setup import get_logger
from strategy.defaults import apply_defaults
from strategy.dialogue_parser import IntentCaptureError, parse_strategy_intent
from strategy.hasher import compute_spec_hash
from strategy.spec_generator import generate_specification
from strategy.specification import StrategySpecification
from strategy.storage import save_strategy_spec

logger = get_logger("strategy.intent_capture")


@dataclass
class CaptureResult:
    """Result of a successful strategy intent capture."""

    spec: StrategySpecification
    saved_path: Path
    version: str
    field_provenance: dict[str, str]
    spec_hash: str


def capture_strategy_intent(
    structured_input: dict,
    artifacts_dir: Path,
    defaults_path: Path | None = None,
) -> CaptureResult:
    """Main entry point for strategy intent capture.

    Orchestrates: parse -> defaults -> generate -> validate -> save -> log.

    Args:
        structured_input: Structured dict from Claude Code skill.
        artifacts_dir: Root directory for strategy artifacts.
        defaults_path: Optional path to defaults TOML.

    Returns:
        CaptureResult with spec, path, version, provenance, and hash.

    Raises:
        IntentCaptureError: If strategy-defining fields are missing.
        ValueError: If spec generation or validation fails.
    """
    raw_desc = structured_input.get("raw_description", "")

    # Log intent capture start
    logger.info(
        "Intent capture started",
        extra={
            "ctx": {
                "event": "intent_capture_start",
                "operator_input_summary": raw_desc[:200],
            },
        },
    )

    # Step 1: Parse structured input into StrategyIntent
    intent = parse_strategy_intent(structured_input)

    # Step 2: Apply defaults for missing non-identity fields
    intent = apply_defaults(intent, defaults_path=defaults_path)

    # Step 3: Generate StrategySpecification from intent
    spec = generate_specification(intent)

    # Step 4: Compute spec hash
    spec_hash = compute_spec_hash(spec)

    # Log spec generation
    fields_defaulted = [
        k for k, v in intent.field_provenance.items() if v == "default"
    ]
    fields_from_operator = [
        k for k, v in intent.field_provenance.items() if v == "operator"
    ]
    logger.info(
        "Specification generated",
        extra={
            "ctx": {
                "event": "spec_generated",
                "spec_version": "v001",
                "strategy_name": spec.metadata.name,
                "fields_defaulted": fields_defaulted,
                "fields_from_operator": fields_from_operator,
            },
        },
    )

    # Log validation result
    logger.info(
        "Specification validated",
        extra={
            "ctx": {
                "event": "spec_validated",
                "valid": True,
                "errors": [],
                "spec_hash": spec_hash,
            },
        },
    )

    # Step 5: Save versioned artifact
    strategy_dir = Path(artifacts_dir) / spec.metadata.name
    saved_path = save_strategy_spec(spec, strategy_dir)
    version = saved_path.stem  # "v001"

    # Log artifact saved
    logger.info(
        "Specification saved",
        extra={
            "ctx": {
                "event": "spec_saved",
                "path": str(saved_path),
                "version": version,
                "spec_hash": spec_hash,
                "status": "draft",
            },
        },
    )

    return CaptureResult(
        spec=spec,
        saved_path=saved_path,
        version=version,
        field_provenance=intent.field_provenance,
        spec_hash=spec_hash,
    )


if __name__ == "__main__":
    import json
    import sys

    if len(sys.argv) < 2:
        print(
            "Usage: python -m strategy.intent_capture '<json_structured_input>'",
            file=sys.stderr,
        )
        sys.exit(1)

    structured_input = json.loads(sys.argv[1])
    artifacts_dir = Path(
        structured_input.pop("artifacts_dir", "artifacts/strategies")
    )
    result = capture_strategy_intent(structured_input, artifacts_dir)
    print(
        json.dumps(
            {
                "saved_path": str(result.saved_path),
                "version": result.version,
                "spec_hash": result.spec_hash,
                "strategy_name": result.spec.metadata.name,
                "field_provenance": result.field_provenance,
            }
        )
    )
