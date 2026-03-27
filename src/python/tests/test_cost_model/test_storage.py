"""Tests for versioned cost model storage (Story 2.6)."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from cost_model.schema import CostModelArtifact, SessionProfile, validate_cost_model
from cost_model.storage import (
    approve_version,
    get_next_version,
    list_versions,
    load_approved_cost_model,
    load_cost_model,
    load_latest_cost_model,
    load_manifest,
    save_cost_model,
    save_manifest,
)

_PROJECT_ROOT = Path(__file__).resolve().parents[4]
_SCHEMA_PATH = _PROJECT_ROOT / "contracts" / "cost_model_schema.toml"


def _make_artifact(pair: str = "EURUSD", version: str = "v001") -> CostModelArtifact:
    return CostModelArtifact(
        pair=pair,
        version=version,
        source="research",
        calibrated_at="2026-03-15T00:00:00Z",
        sessions={
            "asian": SessionProfile(1.2, 0.4, 0.1, 0.05),
            "london": SessionProfile(0.8, 0.3, 0.05, 0.03),
            "london_ny_overlap": SessionProfile(0.6, 0.2, 0.03, 0.02),
            "new_york": SessionProfile(0.9, 0.3, 0.06, 0.03),
            "off_hours": SessionProfile(1.5, 0.6, 0.15, 0.08),
        },
        metadata={"description": "test"},
    )


class TestSaveCostModel:
    def test_save_cost_model_creates_json(self, tmp_path):
        """File created at correct path."""
        artifact = _make_artifact()
        path = save_cost_model(artifact, tmp_path, _SCHEMA_PATH)
        assert path.exists()
        assert path.name == "v001.json"
        assert "EURUSD" in str(path)

    def test_save_cost_model_crash_safe(self, tmp_path):
        """Uses crash_safe_write (write .partial, rename)."""
        artifact = _make_artifact()
        # If crash_safe_write works, the file exists and no .partial remains
        path = save_cost_model(artifact, tmp_path, _SCHEMA_PATH)
        assert path.exists()
        partial = path.with_name(path.name + ".partial")
        assert not partial.exists()

    def test_save_cost_model_content_valid_json(self, tmp_path):
        """Saved file contains valid JSON matching the artifact."""
        artifact = _make_artifact()
        path = save_cost_model(artifact, tmp_path, _SCHEMA_PATH)
        with open(path) as f:
            data = json.load(f)
        assert data["pair"] == "EURUSD"
        assert data["version"] == "v001"
        assert len(data["sessions"]) == 5


class TestLoadCostModel:
    def test_load_cost_model_roundtrip(self, tmp_path):
        """Save then load preserves all data."""
        original = _make_artifact()
        save_cost_model(original, tmp_path, _SCHEMA_PATH)
        loaded = load_cost_model("EURUSD", "v001", tmp_path)
        assert loaded.pair == original.pair
        assert loaded.version == original.version
        assert loaded.source == original.source
        assert loaded.sessions["asian"].mean_spread_pips == 1.2
        assert loaded.sessions["off_hours"].std_slippage == 0.08

    def test_load_cost_model_not_found(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            load_cost_model("EURUSD", "v999", tmp_path)

    def test_load_latest_version(self, tmp_path):
        """Returns highest version."""
        save_cost_model(_make_artifact("EURUSD", "v001"), tmp_path)
        save_cost_model(_make_artifact("EURUSD", "v002"), tmp_path)
        latest = load_latest_cost_model("EURUSD", tmp_path)
        assert latest is not None
        assert latest.version == "v002"

    def test_load_latest_no_versions(self, tmp_path):
        """Returns None when no versions exist."""
        result = load_latest_cost_model("GBPUSD", tmp_path)
        assert result is None


class TestVersionManagement:
    def test_get_next_version_empty(self, tmp_path):
        """Returns 'v001' when no versions exist."""
        assert get_next_version("EURUSD", tmp_path) == "v001"

    def test_get_next_version_increment(self, tmp_path):
        """Returns 'v002' when v001 exists."""
        save_cost_model(_make_artifact("EURUSD", "v001"), tmp_path)
        assert get_next_version("EURUSD", tmp_path) == "v002"

    def test_get_next_version_supports_4_digits(self, tmp_path):
        """Handles 3+ digit versions correctly (Story 2.5 lesson)."""
        # Create v999
        save_cost_model(_make_artifact("EURUSD", "v999"), tmp_path)
        assert get_next_version("EURUSD", tmp_path) == "v1000"

    def test_version_collision_rejected(self, tmp_path):
        """Saving existing version fails with FileExistsError."""
        save_cost_model(_make_artifact("EURUSD", "v001"), tmp_path)
        with pytest.raises(FileExistsError, match="Version collision"):
            save_cost_model(_make_artifact("EURUSD", "v001"), tmp_path)

    def test_list_versions(self, tmp_path):
        """Returns sorted version list."""
        save_cost_model(_make_artifact("EURUSD", "v001"), tmp_path)
        save_cost_model(_make_artifact("EURUSD", "v002"), tmp_path)
        versions = list_versions("EURUSD", tmp_path)
        assert versions == ["v001", "v002"]

    def test_list_versions_numeric_sort(self, tmp_path):
        """Sorts numerically, not lexicographically (v1000 after v999)."""
        save_cost_model(_make_artifact("EURUSD", "v001"), tmp_path)
        save_cost_model(_make_artifact("EURUSD", "v999"), tmp_path)
        save_cost_model(_make_artifact("EURUSD", "v1000"), tmp_path)
        versions = list_versions("EURUSD", tmp_path)
        assert versions == ["v001", "v999", "v1000"]

    def test_previous_versions_preserved(self, tmp_path):
        """v001 unchanged after v002 created."""
        save_cost_model(_make_artifact("EURUSD", "v001"), tmp_path)
        save_cost_model(_make_artifact("EURUSD", "v002"), tmp_path)
        v1 = load_cost_model("EURUSD", "v001", tmp_path)
        assert v1.version == "v001"


class TestManifest:
    def test_manifest_creation(self, tmp_path):
        """manifest.json created on first save."""
        artifact = _make_artifact()
        save_cost_model(artifact, tmp_path)
        save_manifest("EURUSD", artifact, tmp_path)
        manifest = load_manifest("EURUSD", tmp_path)
        assert manifest is not None
        assert "v001" in manifest["versions"]

    def test_manifest_update(self, tmp_path):
        """manifest.json updated on subsequent saves."""
        a1 = _make_artifact("EURUSD", "v001")
        a2 = _make_artifact("EURUSD", "v002")
        save_cost_model(a1, tmp_path)
        save_manifest("EURUSD", a1, tmp_path)
        save_cost_model(a2, tmp_path)
        save_manifest("EURUSD", a2, tmp_path)
        manifest = load_manifest("EURUSD", tmp_path)
        assert "v001" in manifest["versions"]
        assert "v002" in manifest["versions"]

    def test_manifest_latest_approved_version(self, tmp_path):
        """latest_approved_version updated on approval, stable after new draft."""
        a1 = _make_artifact("EURUSD", "v001")
        a2 = _make_artifact("EURUSD", "v002")
        save_cost_model(a1, tmp_path)
        save_manifest("EURUSD", a1, tmp_path)
        approve_version("EURUSD", "v001", tmp_path)

        # After approving v001
        manifest = load_manifest("EURUSD", tmp_path)
        assert manifest["latest_approved_version"] == "v001"

        # Add v002 as draft — latest_approved should stay v001
        save_cost_model(a2, tmp_path)
        save_manifest("EURUSD", a2, tmp_path)
        manifest = load_manifest("EURUSD", tmp_path)
        assert manifest["latest_approved_version"] == "v001"
        assert manifest["versions"]["v002"]["status"] == "draft"

    def test_approve_version(self, tmp_path):
        """Sets status to 'approved', updates pointer."""
        artifact = _make_artifact()
        save_cost_model(artifact, tmp_path)
        save_manifest("EURUSD", artifact, tmp_path)
        approve_version("EURUSD", "v001", tmp_path)
        manifest = load_manifest("EURUSD", tmp_path)
        assert manifest["versions"]["v001"]["status"] == "approved"
        assert manifest["versions"]["v001"]["approved_at"] is not None
        assert manifest["latest_approved_version"] == "v001"

    def test_approve_nonexistent_version(self, tmp_path):
        """Approving version not in manifest raises ValueError."""
        artifact = _make_artifact()
        save_cost_model(artifact, tmp_path)
        save_manifest("EURUSD", artifact, tmp_path)
        with pytest.raises(ValueError, match="not found in manifest"):
            approve_version("EURUSD", "v999", tmp_path)

    def test_manifest_contains_hashes(self, tmp_path):
        """config_hash, artifact_hash, input_hash present in version entries."""
        artifact = _make_artifact()
        save_cost_model(artifact, tmp_path)
        save_manifest(
            "EURUSD", artifact, tmp_path,
            config_hash="sha256:abc123",
            input_hash="sha256:def456",
        )
        manifest = load_manifest("EURUSD", tmp_path)
        entry = manifest["versions"]["v001"]
        assert entry["config_hash"] == "sha256:abc123"
        assert entry["input_hash"] == "sha256:def456"
        assert entry["artifact_hash"].startswith("sha256:")

    def test_manifest_no_manifest_returns_none(self, tmp_path):
        """load_manifest returns None when no manifest exists."""
        assert load_manifest("GBPUSD", tmp_path) is None

    def test_approve_uses_max_not_last_touched(self, tmp_path):
        """latest_approved_version uses max() of approved, not last-touched.
        Lesson from Story 2.5: approving v001 after v002 is approved
        should NOT regress the pointer.
        """
        a1 = _make_artifact("EURUSD", "v001")
        a2 = _make_artifact("EURUSD", "v002")
        save_cost_model(a1, tmp_path)
        save_manifest("EURUSD", a1, tmp_path)
        save_cost_model(a2, tmp_path)
        save_manifest("EURUSD", a2, tmp_path)

        # Approve v002 first, then v001
        approve_version("EURUSD", "v002", tmp_path)
        approve_version("EURUSD", "v001", tmp_path)

        manifest = load_manifest("EURUSD", tmp_path)
        assert manifest["latest_approved_version"] == "v002"


class TestRegressions:
    @pytest.mark.regression
    def test_load_approved_cost_model_uses_manifest(self, tmp_path):
        """Regression: consumers must use manifest approved pointer, not raw latest."""
        a1 = _make_artifact("EURUSD", "v001")
        a2 = _make_artifact("EURUSD", "v002")
        save_cost_model(a1, tmp_path)
        save_manifest("EURUSD", a1, tmp_path)
        approve_version("EURUSD", "v001", tmp_path)
        save_cost_model(a2, tmp_path)
        save_manifest("EURUSD", a2, tmp_path)
        # v002 is draft, v001 is approved
        # load_latest returns v002 (raw latest), load_approved returns v001
        latest = load_latest_cost_model("EURUSD", tmp_path)
        approved = load_approved_cost_model("EURUSD", tmp_path)
        assert latest.version == "v002"
        assert approved.version == "v001"

    @pytest.mark.regression
    def test_load_approved_returns_none_when_no_approval(self, tmp_path):
        """Regression: load_approved returns None when no versions are approved."""
        a1 = _make_artifact("EURUSD", "v001")
        save_cost_model(a1, tmp_path)
        save_manifest("EURUSD", a1, tmp_path)
        # No approval — should return None
        result = load_approved_cost_model("EURUSD", tmp_path)
        assert result is None

    @pytest.mark.regression
    def test_save_cost_model_validates_without_explicit_schema(self, tmp_path):
        """Regression: save_cost_model auto-discovers schema when not provided."""
        # Create the contracts dir structure so auto-discovery works
        project_root = tmp_path / "project"
        artifacts_dir = project_root / "artifacts"
        contracts_dir = project_root / "contracts"
        contracts_dir.mkdir(parents=True)
        artifacts_dir.mkdir(parents=True)
        # Copy schema to discoverable location
        import shutil
        shutil.copy(_SCHEMA_PATH, contracts_dir / "cost_model_schema.toml")

        artifact = _make_artifact()
        # Pass no schema_path — should auto-discover and validate
        path = save_cost_model(artifact, artifacts_dir)
        assert path.exists()

    @pytest.mark.regression
    def test_manifest_hashes_non_null_after_cli_create(self, tmp_path):
        """Regression: config_hash and input_hash must not be null in manifest."""
        artifact = _make_artifact()
        save_cost_model(artifact, tmp_path)
        save_manifest(
            "EURUSD", artifact, tmp_path,
            config_hash="sha256:abc123",
            input_hash="sha256:def456",
        )
        manifest = load_manifest("EURUSD", tmp_path)
        entry = manifest["versions"]["v001"]
        assert entry["config_hash"] is not None
        assert entry["input_hash"] is not None
        assert entry["artifact_hash"] is not None

    @pytest.mark.regression
    def test_save_warns_when_schema_undiscoverable(self, tmp_path, caplog):
        """Regression: save_cost_model logs warning when schema can't be found (AC5).

        When neither schema_path is provided nor auto-discovery succeeds,
        the save must warn — not silently skip validation.
        """
        import logging

        artifact = _make_artifact()
        with caplog.at_level(logging.WARNING, logger="cost_model.storage"):
            save_cost_model(artifact, tmp_path)
        assert "cost_model_save_unvalidated" in caplog.text
        assert "AC5" in caplog.text
