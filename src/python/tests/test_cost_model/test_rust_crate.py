"""Live integration tests for Story 2.7: Cost Model Rust Crate.

These tests exercise the REAL compiled Rust binary and validate that:
1. cargo test passes for the cost_model crate
2. cargo clippy passes with zero warnings
3. The cost_model_cli binary validates/inspects real artifact files
4. The workspace dependency graph is correct (backtester -> cost_model)
"""

import json
import os
import subprocess
import tempfile
from pathlib import Path

import pytest

# Project root is 4 levels up from this test file
PROJECT_ROOT = Path(__file__).resolve().parents[4]
RUST_DIR = PROJECT_ROOT / "src" / "rust"
COST_MODEL_CRATE = RUST_DIR / "crates" / "cost_model"

# Valid EURUSD artifact matching Story 2.6 default values
VALID_ARTIFACT = {
    "pair": "EURUSD",
    "version": "v001",
    "source": "research",
    "calibrated_at": "2026-03-15T00:00:00Z",
    "sessions": {
        "asian": {
            "mean_spread_pips": 1.2,
            "std_spread": 0.4,
            "mean_slippage_pips": 0.1,
            "std_slippage": 0.05,
        },
        "london": {
            "mean_spread_pips": 0.8,
            "std_spread": 0.3,
            "mean_slippage_pips": 0.05,
            "std_slippage": 0.03,
        },
        "london_ny_overlap": {
            "mean_spread_pips": 0.6,
            "std_spread": 0.2,
            "mean_slippage_pips": 0.03,
            "std_slippage": 0.02,
        },
        "new_york": {
            "mean_spread_pips": 0.9,
            "std_spread": 0.3,
            "mean_slippage_pips": 0.06,
            "std_slippage": 0.03,
        },
        "off_hours": {
            "mean_spread_pips": 1.5,
            "std_spread": 0.6,
            "mean_slippage_pips": 0.15,
            "std_slippage": 0.08,
        },
    },
}

EXPECTED_SESSIONS = ["asian", "london", "new_york", "london_ny_overlap", "off_hours"]


def _run_cargo(args: list[str], cwd: Path = RUST_DIR, timeout: int = 300) -> subprocess.CompletedProcess:
    """Run a cargo command and return the result."""
    return subprocess.run(
        ["cargo"] + args,
        cwd=str(cwd),
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def _write_artifact(data: dict, path: Path) -> None:
    """Write a cost model artifact JSON file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f, indent=2)


def _find_cli_binary() -> Path:
    """Find the compiled cost_model_cli binary."""
    if os.name == "nt":
        binary = RUST_DIR / "target" / "debug" / "cost_model_cli.exe"
    else:
        binary = RUST_DIR / "target" / "debug" / "cost_model_cli"
    return binary


@pytest.mark.live
class TestRustCrateCargoTest:
    """Verify cargo test passes for the cost_model crate."""

    def test_live_cargo_test_passes(self):
        """Run cargo test -p cost_model and verify all tests pass."""
        result = _run_cargo(["test", "-p", "cost_model"])
        assert result.returncode == 0, (
            f"cargo test failed.\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        )
        # Verify test output mentions passed tests (cargo puts test results in stdout)
        combined = result.stdout + result.stderr
        assert "test result: ok" in combined, (
            f"Expected 'test result: ok' in output.\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        )

    def test_live_cargo_clippy_clean(self):
        """Run cargo clippy and verify zero warnings."""
        result = _run_cargo(["clippy", "-p", "cost_model", "--", "-D", "warnings"])
        assert result.returncode == 0, (
            f"cargo clippy failed with warnings.\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        )

    def test_live_workspace_dependency_graph(self):
        """Verify backtester depends on cost_model in the workspace."""
        result = _run_cargo(["tree", "-p", "backtester"])
        assert result.returncode == 0, f"cargo tree failed: {result.stderr}"
        assert "cost_model" in result.stdout, (
            f"backtester should depend on cost_model.\nOutput:\n{result.stdout}"
        )


@pytest.mark.live
class TestRustCrateCLI:
    """Exercise the cost_model_cli binary against real artifact files."""

    @pytest.fixture(autouse=True)
    def _build_binary(self):
        """Ensure the CLI binary is built before running CLI tests."""
        result = _run_cargo(["build", "-p", "cost_model"])
        assert result.returncode == 0, (
            f"cargo build failed.\nstderr:\n{result.stderr}"
        )
        self.cli = _find_cli_binary()
        assert self.cli.exists(), f"CLI binary not found at {self.cli}"

    def test_live_cli_validate_valid_artifact(self, tmp_path):
        """Validate a valid artifact file using the CLI."""
        artifact_path = tmp_path / "valid.json"
        _write_artifact(VALID_ARTIFACT, artifact_path)

        result = subprocess.run(
            [str(self.cli), "validate", str(artifact_path)],
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert result.returncode == 0, f"CLI validate failed: {result.stderr}"
        assert "Valid" in result.stdout
        assert "EURUSD" in result.stdout

    def test_live_cli_validate_invalid_artifact(self, tmp_path):
        """Validate an invalid artifact (wrong pair) exits with code 1."""
        bad_artifact = {**VALID_ARTIFACT, "pair": "USDJPY"}
        artifact_path = tmp_path / "invalid.json"
        _write_artifact(bad_artifact, artifact_path)

        result = subprocess.run(
            [str(self.cli), "validate", str(artifact_path)],
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert result.returncode == 1, "Should fail for non-EURUSD pair"
        assert "V1 only supports EURUSD" in result.stderr

    def test_live_cli_inspect_shows_all_sessions(self, tmp_path):
        """Inspect a valid artifact and verify all sessions are shown."""
        artifact_path = tmp_path / "inspect.json"
        _write_artifact(VALID_ARTIFACT, artifact_path)

        result = subprocess.run(
            [str(self.cli), "inspect", str(artifact_path)],
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert result.returncode == 0, f"CLI inspect failed: {result.stderr}"
        assert "EURUSD" in result.stdout
        for session in EXPECTED_SESSIONS:
            assert session in result.stdout, f"Session '{session}' missing from inspect output"

    def test_live_cli_validate_real_artifact_if_exists(self):
        """If Story 2.6 produced a real artifact, validate it with the CLI."""
        artifact_dir = PROJECT_ROOT / "artifacts" / "cost_models" / "EURUSD"
        if not artifact_dir.exists():
            pytest.skip("No real cost model artifacts found (Story 2.6 not yet run)")

        artifacts = sorted(artifact_dir.glob("v*.json"))
        if not artifacts:
            pytest.skip("No versioned artifact files found in EURUSD directory")

        latest = artifacts[-1]
        result = subprocess.run(
            [str(self.cli), "validate", str(latest)],
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert result.returncode == 0, (
            f"CLI validate failed on real artifact {latest.name}: {result.stderr}"
        )
        assert "Valid" in result.stdout
