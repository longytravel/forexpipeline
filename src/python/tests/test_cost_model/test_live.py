"""Live integration tests for cost model (Story 2.6).

These tests exercise REAL system behavior — building actual artifacts,
writing real files to disk, and validating real outputs. No mocks.

Run with: pytest -m live tests/test_cost_model/test_live.py
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

_PROJECT_ROOT = Path(__file__).resolve().parents[4]
_CONFIG_PATH = _PROJECT_ROOT / "config" / "base.toml"
_CONTRACTS_PATH = _PROJECT_ROOT / "contracts"
_SCHEMA_PATH = _CONTRACTS_PATH / "cost_model_schema.toml"
_SRC_PYTHON = _PROJECT_ROOT / "src" / "python"


@pytest.mark.live
class TestLiveFullValidation:
    """Full end-to-end: build, save, validate, approve, reload — real disk."""

    def test_live_full_validation(self, tmp_path):
        """Build default EURUSD, save to real disk, validate, approve, reload."""
        from cost_model.builder import CostModelBuilder
        from cost_model.schema import REQUIRED_SESSIONS, validate_cost_model
        from cost_model.storage import (
            approve_version,
            list_versions,
            load_cost_model,
            load_manifest,
            save_cost_model,
            save_manifest,
        )

        artifacts_dir = tmp_path / "artifacts"

        # Build
        builder = CostModelBuilder(_CONFIG_PATH, _CONTRACTS_PATH, artifacts_dir)
        artifact = builder.build_default_eurusd()

        # Validate against schema
        errors = validate_cost_model(artifact, _SCHEMA_PATH)
        assert errors == [], f"Schema validation failed: {errors}"

        # Save to disk
        path = save_cost_model(artifact, artifacts_dir, _SCHEMA_PATH)
        assert path.exists(), f"Artifact file not created at {path}"
        assert path.stat().st_size > 0, "Artifact file is empty"

        # Verify no .partial file remains (crash-safe write completed)
        partial = path.with_name(path.name + ".partial")
        assert not partial.exists(), ".partial file should not remain after save"

        # Create manifest
        save_manifest("EURUSD", artifact, artifacts_dir)
        manifest_path = artifacts_dir / "cost_models" / "EURUSD" / "manifest.json"
        assert manifest_path.exists(), "Manifest not created"

        # Approve
        approve_version("EURUSD", artifact.version, artifacts_dir)

        # Reload and verify content
        loaded = load_cost_model("EURUSD", artifact.version, artifacts_dir)
        assert loaded.pair == "EURUSD"
        assert loaded.source == "research"
        assert loaded.version == artifact.version

        # Verify all 5 sessions have statistical distribution parameters
        for name in REQUIRED_SESSIONS:
            session = loaded.sessions[name]
            assert session.mean_spread_pips > 0, f"{name}: mean_spread must be > 0"
            assert session.std_spread > 0, f"{name}: std_spread must be > 0"
            assert session.mean_slippage_pips >= 0, f"{name}: mean_slippage must be >= 0"
            assert session.std_slippage >= 0, f"{name}: std_slippage must be >= 0"

        # Verify manifest has correct approval pointer
        manifest = load_manifest("EURUSD", artifacts_dir)
        assert manifest["latest_approved_version"] == artifact.version
        assert manifest["versions"][artifact.version]["status"] == "approved"
        assert manifest["versions"][artifact.version]["approved_at"] is not None
        assert manifest["versions"][artifact.version]["artifact_hash"].startswith("sha256:")

        # Verify versions list
        versions = list_versions("EURUSD", artifacts_dir)
        assert versions == [artifact.version]

        # Read raw JSON and verify structure matches D13 contract
        with open(path) as f:
            raw = json.load(f)
        assert set(raw["sessions"].keys()) == set(REQUIRED_SESSIONS)
        for session_data in raw["sessions"].values():
            assert "mean_spread_pips" in session_data
            assert "std_spread" in session_data
            assert "mean_slippage_pips" in session_data
            assert "std_slippage" in session_data


@pytest.mark.live
class TestLiveVersionChain:
    """Multi-version chain with real disk writes and manifest integrity."""

    def test_live_version_chain(self, tmp_path):
        """Create v001, approve, create v002 draft — verify immutability."""
        from cost_model.builder import CostModelBuilder
        from cost_model.storage import (
            approve_version,
            list_versions,
            load_cost_model,
            load_manifest,
            save_cost_model,
            save_manifest,
        )

        artifacts_dir = tmp_path / "artifacts"
        builder = CostModelBuilder(_CONFIG_PATH, _CONTRACTS_PATH, artifacts_dir)

        # v001
        a1 = builder.build_default_eurusd()
        p1 = save_cost_model(a1, artifacts_dir, _SCHEMA_PATH)
        save_manifest("EURUSD", a1, artifacts_dir)
        approve_version("EURUSD", "v001", artifacts_dir)

        # v002
        a2 = builder.build_default_eurusd()
        assert a2.version == "v002", "Second build should be v002"
        p2 = save_cost_model(a2, artifacts_dir, _SCHEMA_PATH)
        save_manifest("EURUSD", a2, artifacts_dir)

        # Both files exist on disk
        assert p1.exists()
        assert p2.exists()

        # v001 unchanged after v002 created (immutability)
        v1 = load_cost_model("EURUSD", "v001", artifacts_dir)
        assert v1.version == "v001"

        # Manifest: v001 approved, v002 draft, pointer at v001
        manifest = load_manifest("EURUSD", artifacts_dir)
        assert manifest["latest_approved_version"] == "v001"
        assert manifest["versions"]["v001"]["status"] == "approved"
        assert manifest["versions"]["v002"]["status"] == "draft"
        assert list_versions("EURUSD", artifacts_dir) == ["v001", "v002"]


@pytest.mark.live
class TestLiveCLI:
    """CLI produces real artifacts on disk."""

    def test_live_cli_create_default(self):
        """Run CLI create-default command, verify real artifact on disk."""
        import os
        import shutil

        # Clean up any prior artifacts so this test is idempotent
        eurusd_dir = _PROJECT_ROOT / "artifacts" / "cost_models" / "EURUSD"
        if eurusd_dir.exists():
            shutil.rmtree(eurusd_dir)

        env = {**os.environ, "PYTHONPATH": str(_SRC_PYTHON)}

        result = subprocess.run(
            [sys.executable, "-m", "cost_model", "create-default"],
            cwd=str(_SRC_PYTHON),
            capture_output=True,
            text=True,
            env=env,
            timeout=30,
        )
        assert result.returncode == 0, f"CLI failed: {result.stderr}"
        assert "Default EURUSD cost model created" in result.stdout

        # Verify artifact exists
        artifact_path = eurusd_dir / "v001.json"
        assert artifact_path.exists(), f"Artifact not at {artifact_path}"

        # Verify manifest exists
        manifest_path = eurusd_dir / "manifest.json"
        assert manifest_path.exists(), f"Manifest not at {manifest_path}"

        # Verify artifact content
        with open(artifact_path) as f:
            data = json.load(f)
        assert data["pair"] == "EURUSD"
        assert data["version"] == "v001"
        assert data["source"] == "research"
        assert len(data["sessions"]) == 5

        # Verify manifest has approval
        with open(manifest_path) as f:
            manifest = json.load(f)
        assert manifest["latest_approved_version"] == "v001"
        assert manifest["versions"]["v001"]["status"] == "approved"

        # Verify validate command works on the real artifact
        result2 = subprocess.run(
            [sys.executable, "-m", "cost_model", "validate", "EURUSD"],
            cwd=str(_SRC_PYTHON),
            capture_output=True,
            text=True,
            env=env,
            timeout=30,
        )
        assert result2.returncode == 0
        assert "Validation PASSED" in result2.stdout
