"""End-to-end tests for cost model (Story 2.6)."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

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

_PROJECT_ROOT = Path(__file__).resolve().parents[4]
_CONFIG_PATH = _PROJECT_ROOT / "config" / "base.toml"
_CONTRACTS_PATH = _PROJECT_ROOT / "contracts"
_SCHEMA_PATH = _CONTRACTS_PATH / "cost_model_schema.toml"


class TestCreateDefaultEurusdE2E:
    def test_create_default_eurusd_e2e(self, tmp_path):
        """Full flow: build -> validate -> save -> load -> verify."""
        builder = CostModelBuilder(_CONFIG_PATH, _CONTRACTS_PATH, tmp_path)
        artifact = builder.build_default_eurusd()

        # Validate
        errors = validate_cost_model(artifact, _SCHEMA_PATH)
        assert errors == [], f"Validation errors: {errors}"

        # Save
        path = save_cost_model(artifact, tmp_path, _SCHEMA_PATH)
        assert path.exists()

        # Create manifest and approve
        save_manifest("EURUSD", artifact, tmp_path)
        approve_version("EURUSD", artifact.version, tmp_path)

        # Load and verify
        loaded = load_cost_model("EURUSD", artifact.version, tmp_path)
        assert loaded.pair == "EURUSD"
        assert loaded.source == "research"
        assert len(loaded.sessions) == 5

        # Verify manifest
        manifest = load_manifest("EURUSD", tmp_path)
        assert manifest["latest_approved_version"] == artifact.version
        assert manifest["versions"][artifact.version]["status"] == "approved"

        # Verify all sessions have statistical distribution params
        for name in REQUIRED_SESSIONS:
            session = loaded.sessions[name]
            assert session.mean_spread_pips >= 0
            assert session.std_spread >= 0
            assert session.mean_slippage_pips >= 0
            assert session.std_slippage >= 0


class TestVersionChainE2E:
    def test_version_chain_e2e(self, tmp_path):
        """Create v001, create v002, both loadable, manifest correct."""
        builder = CostModelBuilder(_CONFIG_PATH, _CONTRACTS_PATH, tmp_path)

        # Create v001
        a1 = builder.build_default_eurusd()
        save_cost_model(a1, tmp_path, _SCHEMA_PATH)
        save_manifest("EURUSD", a1, tmp_path)
        approve_version("EURUSD", "v001", tmp_path)

        # Create v002
        a2 = builder.build_default_eurusd()
        assert a2.version == "v002"
        save_cost_model(a2, tmp_path, _SCHEMA_PATH)
        save_manifest("EURUSD", a2, tmp_path)

        # Both loadable
        v1 = load_cost_model("EURUSD", "v001", tmp_path)
        v2 = load_cost_model("EURUSD", "v002", tmp_path)
        assert v1.version == "v001"
        assert v2.version == "v002"

        # Manifest correct — v001 approved, v002 draft
        manifest = load_manifest("EURUSD", tmp_path)
        assert manifest["latest_approved_version"] == "v001"
        assert manifest["versions"]["v001"]["status"] == "approved"
        assert manifest["versions"]["v002"]["status"] == "draft"
        assert list_versions("EURUSD", tmp_path) == ["v001", "v002"]


@pytest.mark.live
class TestCliCreateDefault:
    def test_cli_create_default(self, tmp_path, monkeypatch):
        """CLI command produces valid artifact file."""
        import shutil

        # Clean up any prior artifacts so this test is idempotent
        eurusd_dir = _PROJECT_ROOT / "artifacts" / "cost_models" / "EURUSD"
        if eurusd_dir.exists():
            shutil.rmtree(eurusd_dir)

        # Run the CLI as a subprocess from src/python directory
        src_python = _PROJECT_ROOT / "src" / "python"
        env = {
            **__import__("os").environ,
            "PYTHONPATH": str(src_python),
        }
        result = subprocess.run(
            [sys.executable, "-m", "cost_model", "create-default"],
            cwd=str(src_python),
            capture_output=True,
            text=True,
            env=env,
            timeout=30,
        )
        assert result.returncode == 0, f"CLI failed: {result.stderr}"
        assert "Default EURUSD cost model created" in result.stdout

        # Verify the artifact file was created
        artifact_path = eurusd_dir / "v001.json"
        assert artifact_path.exists(), f"Artifact not created at {artifact_path}"

        # Verify it's valid JSON with correct structure
        with open(artifact_path) as f:
            data = json.load(f)
        assert data["pair"] == "EURUSD"
        assert len(data["sessions"]) == 5
