"""CLI entrypoint for cost model operations (Story 2.6).

Usage (from src/python):
  python -m cost_model create-default
  python -m cost_model create <pair> --source research --data '<json>'
  python -m cost_model create <pair> --source tick_analysis --tick-data <path>
  python -m cost_model show <pair> [--version v001]
  python -m cost_model list <pair>
  python -m cost_model validate <pair> [--version v001]
  python -m cost_model approve <pair> --version <version>

No new dependencies — argparse, json, pathlib only.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path


def _resolve_project_root() -> Path:
    """Walk up from this file to find the project root (contains config/)."""
    current = Path(__file__).resolve().parent
    for _ in range(10):
        if (current / "config").is_dir():
            return current
        current = current.parent
    # Fallback: assume src/python/cost_model -> 3 levels up
    return Path(__file__).resolve().parent.parent.parent


def _default_paths() -> tuple[Path, Path, Path]:
    """Return (config_path, contracts_path, artifacts_dir)."""
    root = _resolve_project_root()
    return (
        root / "config" / "base.toml",
        root / "contracts",
        root / "artifacts",
    )


def _compute_file_hash(path: Path) -> str:
    """Compute SHA-256 hash of a file with sha256: prefix."""
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    return f"sha256:{digest}"


def _compute_string_hash(content: str) -> str:
    """Compute SHA-256 hash of a string with sha256: prefix."""
    digest = hashlib.sha256(content.encode("utf-8")).hexdigest()
    return f"sha256:{digest}"


def cmd_create_default(args: argparse.Namespace) -> None:
    from cost_model.builder import CostModelBuilder, _EURUSD_DEFAULTS
    from cost_model.storage import approve_version, save_cost_model, save_manifest

    config_path, contracts_path, artifacts_dir = _default_paths()
    builder = CostModelBuilder(config_path, contracts_path, artifacts_dir)
    schema_path = contracts_path / "cost_model_schema.toml"

    artifact = builder.build_default_eurusd()
    path = save_cost_model(artifact, artifacts_dir, schema_path)

    # Compute reproducibility hashes (AC10)
    config_hash = _compute_file_hash(config_path)
    input_hash = _compute_string_hash(json.dumps(_EURUSD_DEFAULTS, sort_keys=True))

    save_manifest(
        artifact.pair, artifact, artifacts_dir,
        config_hash=config_hash,
        input_hash=input_hash,
    )
    # Auto-approve v001 baseline for pipeline proofs
    approve_version(artifact.pair, artifact.version, artifacts_dir)

    print(f"Default EURUSD cost model created: {path}")
    print(f"Version {artifact.version} auto-approved as baseline")


def cmd_create(args: argparse.Namespace) -> None:
    from cost_model.builder import CostModelBuilder
    from cost_model.storage import save_cost_model, save_manifest

    config_path, contracts_path, artifacts_dir = _default_paths()
    builder = CostModelBuilder(config_path, contracts_path, artifacts_dir)
    schema_path = contracts_path / "cost_model_schema.toml"

    if args.source == "research":
        if not args.data:
            print("Error: --data required for research source", file=sys.stderr)
            sys.exit(1)
        research_data = json.loads(args.data)
        artifact = builder.from_research_data(args.pair, research_data)
    elif args.source == "tick_analysis":
        if not args.tick_data:
            print("Error: --tick-data required for tick_analysis source",
                  file=sys.stderr)
            sys.exit(1)
        artifact = builder.from_tick_data(args.pair, Path(args.tick_data))
    elif args.source == "live_calibration":
        print("Error: Live calibration not available until Epic 7",
              file=sys.stderr)
        sys.exit(1)
    else:
        print(f"Error: Unknown source '{args.source}'", file=sys.stderr)
        sys.exit(1)

    path = save_cost_model(artifact, artifacts_dir, schema_path)

    # Compute reproducibility hashes (AC10)
    config_hash = _compute_file_hash(config_path)
    if args.source == "research" and args.data:
        input_hash = _compute_string_hash(args.data)
    elif args.source == "tick_analysis" and args.tick_data:
        input_hash = _compute_string_hash(str(Path(args.tick_data).resolve()))
    else:
        input_hash = None

    save_manifest(args.pair, artifact, artifacts_dir, config_hash=config_hash, input_hash=input_hash)
    print(f"Cost model created: {path}")


def cmd_show(args: argparse.Namespace) -> None:
    from cost_model.storage import load_approved_cost_model, load_cost_model

    _config_path, _contracts_path, artifacts_dir = _default_paths()

    if args.version:
        artifact = load_cost_model(args.pair, args.version, artifacts_dir)
    else:
        artifact = load_approved_cost_model(args.pair, artifacts_dir)
        if artifact is None:
            print(f"No approved cost models found for {args.pair}", file=sys.stderr)
            sys.exit(1)

    print(json.dumps(artifact.to_dict(), indent=2))


def cmd_list(args: argparse.Namespace) -> None:
    from cost_model.storage import list_versions, load_manifest

    _config_path, _contracts_path, artifacts_dir = _default_paths()
    versions = list_versions(args.pair, artifacts_dir)

    if not versions:
        print(f"No versions found for {args.pair}")
        return

    manifest = load_manifest(args.pair, artifacts_dir)
    latest_approved = manifest.get("latest_approved_version") if manifest else None

    for v in versions:
        status = ""
        if manifest and v in manifest.get("versions", {}):
            status = f" [{manifest['versions'][v]['status']}]"
        if v == latest_approved:
            status += " <- latest_approved"
        print(f"  {v}{status}")


def cmd_validate(args: argparse.Namespace) -> None:
    from cost_model.schema import validate_cost_model
    from cost_model.storage import load_approved_cost_model, load_cost_model

    _config_path, contracts_path, artifacts_dir = _default_paths()
    schema_path = contracts_path / "cost_model_schema.toml"

    if args.version:
        artifact = load_cost_model(args.pair, args.version, artifacts_dir)
    else:
        artifact = load_approved_cost_model(args.pair, artifacts_dir)
        if artifact is None:
            print(f"No approved cost models found for {args.pair}", file=sys.stderr)
            sys.exit(1)

    errors = validate_cost_model(artifact, schema_path)
    if errors:
        print(f"Validation FAILED ({len(errors)} errors):")
        for err in errors:
            print(f"  - {err}")
        sys.exit(1)
    else:
        print(f"Validation PASSED: {args.pair} {artifact.version}")


def cmd_approve(args: argparse.Namespace) -> None:
    from cost_model.storage import approve_version

    _config_path, _contracts_path, artifacts_dir = _default_paths()
    path = approve_version(args.pair, args.version, artifacts_dir)
    print(f"Approved {args.pair} {args.version} — manifest updated: {path}")


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="cost_model",
        description="Execution cost model builder and manager (Story 2.6)",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # create-default
    sub.add_parser("create-default", help="Build default EURUSD cost model")

    # create
    p_create = sub.add_parser("create", help="Create cost model from data")
    p_create.add_argument("pair", help="Currency pair (e.g. EURUSD)")
    p_create.add_argument(
        "--source", required=True,
        choices=["research", "tick_analysis", "live_calibration"],
    )
    p_create.add_argument("--data", help="JSON research data string")
    p_create.add_argument("--tick-data", help="Path to tick data directory")

    # show
    p_show = sub.add_parser("show", help="Display cost model artifact")
    p_show.add_argument("pair", help="Currency pair")
    p_show.add_argument("--version", help="Specific version (default: latest)")

    # list
    p_list = sub.add_parser("list", help="List versions for a pair")
    p_list.add_argument("pair", help="Currency pair")

    # validate
    p_val = sub.add_parser("validate", help="Validate artifact against schema")
    p_val.add_argument("pair", help="Currency pair")
    p_val.add_argument("--version", help="Specific version (default: latest)")

    # approve
    p_approve = sub.add_parser("approve", help="Approve a version")
    p_approve.add_argument("pair", help="Currency pair")
    p_approve.add_argument("--version", required=True, help="Version to approve")

    args = parser.parse_args()

    dispatch = {
        "create-default": cmd_create_default,
        "create": cmd_create,
        "show": cmd_show,
        "list": cmd_list,
        "validate": cmd_validate,
        "approve": cmd_approve,
    }
    dispatch[args.command](args)


if __name__ == "__main__":
    main()
