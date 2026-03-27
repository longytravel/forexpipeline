"""Strategy CLI dispatcher — operator-facing commands (D9, D10).

Usage:
    python -m strategy review <strategy_slug> [--version v001]
    python -m strategy confirm <strategy_slug> <version>
    python -m strategy modify <strategy_slug> --input '<json>'
    python -m strategy manifest <strategy_slug>

Uses argparse — no new dependencies.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Default paths (relative to project root)
_PROJECT_ROOT = Path(__file__).resolve().parents[3]
_ARTIFACTS_DIR = _PROJECT_ROOT / "artifacts"
_CONFIG_DIR = _PROJECT_ROOT / "config"


def _cmd_review(args: argparse.Namespace) -> None:
    """Review a strategy specification — generate human-readable summary."""
    from strategy.loader import load_strategy_spec
    from strategy.reviewer import (
        format_summary_text,
        generate_summary,
        save_summary_artifact,
    )
    from strategy.storage import load_latest_version

    artifacts_dir = Path(args.artifacts_dir).resolve()
    strategy_dir = artifacts_dir / "strategies" / args.strategy_slug

    if args.version:
        spec_path = strategy_dir / f"{args.version}.toml"
        spec = load_strategy_spec(spec_path)
        version = args.version
    else:
        spec, version = load_latest_version(strategy_dir)

    summary = generate_summary(spec)
    text = format_summary_text(summary)
    print(text)

    # Save review artifact
    save_summary_artifact(text, args.strategy_slug, version, artifacts_dir)
    print(f"\nReview saved to: artifacts/strategies/{args.strategy_slug}/reviews/{version}_summary.txt")


def _cmd_confirm(args: argparse.Namespace) -> None:
    """Confirm a strategy specification for pipeline use."""
    from strategy.confirmer import confirm_specification

    artifacts_dir = Path(args.artifacts_dir).resolve()
    config_dir = Path(args.config_dir).resolve()

    result = confirm_specification(
        strategy_slug=args.strategy_slug,
        version=args.version,
        artifacts_dir=artifacts_dir,
        config_dir=config_dir,
    )

    print(f"Strategy confirmed: {args.strategy_slug} {result.version}")
    print(f"  Status: confirmed")
    print(f"  Config hash: {result.config_hash[:16]}...")
    print(f"  Spec hash: {result.spec_hash[:16]}...")
    print(f"  Confirmed at: {result.confirmed_at}")
    print(f"  Manifest: {result.manifest_path}")


def _cmd_modify(args: argparse.Namespace) -> None:
    """Apply modifications to a strategy specification."""
    from strategy.modifier import apply_modifications, parse_modification_intent
    from strategy.versioner import format_diff_text

    artifacts_dir = Path(args.artifacts_dir).resolve()

    # Parse modification input
    try:
        structured_input = json.loads(args.input)
    except json.JSONDecodeError as e:
        print(f"Error: Invalid JSON input: {e}", file=sys.stderr)
        sys.exit(1)

    modifications = parse_modification_intent(structured_input)

    result = apply_modifications(
        strategy_slug=args.strategy_slug,
        modifications=modifications,
        artifacts_dir=artifacts_dir,
    )

    # Print diff
    diff_text = format_diff_text(result.diff)
    print(diff_text)
    print(f"\nNew version saved: {result.saved_path}")
    print(f"Manifest updated: {result.manifest_path}")


def _cmd_manifest(args: argparse.Namespace) -> None:
    """Display manifest summary for a strategy."""
    from strategy.versioner import load_manifest

    artifacts_dir = Path(args.artifacts_dir).resolve()
    manifest = load_manifest(args.strategy_slug, artifacts_dir)

    if manifest is None:
        print(f"No manifest found for strategy '{args.strategy_slug}'")
        sys.exit(1)

    print(f"Strategy: {manifest.strategy_slug}")
    print(f"Current version: {manifest.current_version}")
    print(f"Latest confirmed: {manifest.latest_confirmed_version or '(none)'}")
    print(f"\nVersion History:")
    for v in manifest.versions:
        status_marker = " [CONFIRMED]" if v.status == "confirmed" else ""
        print(f"  {v.version}: {v.status}{status_marker}")
        print(f"    Created: {v.created_at}")
        if v.confirmed_at:
            print(f"    Confirmed: {v.confirmed_at}")
        if v.config_hash:
            print(f"    Config hash: {v.config_hash[:16]}...")
        print(f"    Spec hash: {v.spec_hash[:16]}...")


def main() -> None:
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        prog="strategy",
        description="Strategy specification management CLI (D9/D10)",
    )
    parser.add_argument(
        "--artifacts-dir",
        default=str(_ARTIFACTS_DIR),
        help="Artifacts directory (default: PROJECT_ROOT/artifacts)",
    )
    parser.add_argument(
        "--config-dir",
        default=str(_CONFIG_DIR),
        help="Config directory (default: PROJECT_ROOT/config)",
    )

    sub = parser.add_subparsers(dest="command", required=True)

    # review
    review_parser = sub.add_parser("review", help="Review a strategy specification")
    review_parser.add_argument("strategy_slug", help="Strategy identifier slug")
    review_parser.add_argument("--version", default=None, help="Specific version (default: latest)")

    # confirm
    confirm_parser = sub.add_parser("confirm", help="Confirm a strategy for pipeline use")
    confirm_parser.add_argument("strategy_slug", help="Strategy identifier slug")
    confirm_parser.add_argument("version", help="Version to confirm (e.g., v001)")

    # modify
    modify_parser = sub.add_parser("modify", help="Modify a strategy specification")
    modify_parser.add_argument("strategy_slug", help="Strategy identifier slug")
    modify_parser.add_argument("--input", required=True, help="JSON modification input")

    # manifest
    manifest_parser = sub.add_parser("manifest", help="Show strategy manifest")
    manifest_parser.add_argument("strategy_slug", help="Strategy identifier slug")

    args = parser.parse_args()

    try:
        if args.command == "review":
            _cmd_review(args)
        elif args.command == "confirm":
            _cmd_confirm(args)
        elif args.command == "modify":
            _cmd_modify(args)
        elif args.command == "manifest":
            _cmd_manifest(args)
    except FileNotFoundError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
