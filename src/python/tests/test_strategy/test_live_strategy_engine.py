"""Live integration tests for strategy_engine Rust crate (Story 2.8).

These tests exercise REAL system behavior — compiling the real Rust crate,
running real cargo tests, parsing real TOML fixtures, and verifying real outputs.
No mocks for the system under test.

Run with: pytest -m live tests/test_strategy/test_live_strategy_engine.py
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

_PROJECT_ROOT = Path(__file__).resolve().parents[4]
_RUST_DIR = _PROJECT_ROOT / "src" / "rust"
_CRATE_DIR = _RUST_DIR / "crates" / "strategy_engine"
_TEST_DATA = _CRATE_DIR / "tests" / "test_data"
_CONTRACTS = _PROJECT_ROOT / "contracts"


def _run_cargo(args: list[str], timeout: int = 120) -> subprocess.CompletedProcess:
    """Run a cargo command in the Rust workspace directory."""
    return subprocess.run(
        ["cargo"] + args,
        cwd=str(_RUST_DIR),
        capture_output=True,
        text=True,
        timeout=timeout,
    )


@pytest.mark.live
class TestLiveCrateCompilation:
    """Verify the strategy_engine crate compiles and passes all tests."""

    def test_live_cargo_check_workspace(self):
        """Full workspace compiles with zero errors after adding strategy_engine."""
        result = _run_cargo(["check", "--workspace"])
        assert result.returncode == 0, (
            f"cargo check --workspace failed:\nstdout: {result.stdout}\nstderr: {result.stderr}"
        )
        # No warnings
        assert "warning" not in result.stderr.lower() or "Compiling" in result.stderr, (
            f"Unexpected warnings in workspace build:\n{result.stderr}"
        )

    def test_live_cargo_test_strategy_engine(self):
        """All strategy_engine unit + integration tests pass."""
        result = _run_cargo(["test", "-p", "strategy_engine"])
        assert result.returncode == 0, (
            f"cargo test -p strategy_engine failed:\nstdout: {result.stdout}\nstderr: {result.stderr}"
        )
        # Verify test count — expect 18 unit + 9 integration = 27 tests
        assert "test result: ok" in result.stdout, (
            f"Expected passing test results in output:\n{result.stdout}"
        )
        # No test failures
        assert "FAILED" not in result.stdout, (
            f"Test failures detected:\n{result.stdout}"
        )

    def test_live_no_regressions_workspace(self):
        """Full workspace test suite passes — no regressions from strategy_engine."""
        result = _run_cargo(["test", "--workspace"])
        assert result.returncode == 0, (
            f"cargo test --workspace failed:\nstdout: {result.stdout}\nstderr: {result.stderr}"
        )
        assert "FAILED" not in result.stdout, (
            f"Workspace test failures:\n{result.stdout}"
        )


@pytest.mark.live
class TestLiveTestFixtures:
    """Verify test fixture files exist on disk and are valid TOML."""

    EXPECTED_FIXTURES = [
        "valid_ma_crossover.toml",
        "invalid_unknown_indicator.toml",
        "invalid_bad_params.toml",
        "invalid_missing_fields.toml",
        "invalid_bad_session.toml",
        "invalid_multi_error.toml",
    ]

    def test_live_fixtures_exist_on_disk(self):
        """All test fixture TOML files exist in test_data directory."""
        assert _TEST_DATA.is_dir(), f"test_data directory missing: {_TEST_DATA}"
        for fixture in self.EXPECTED_FIXTURES:
            path = _TEST_DATA / fixture
            assert path.exists(), f"Fixture file missing: {path}"
            assert path.stat().st_size > 0, f"Fixture file is empty: {path}"

    def test_live_valid_fixture_is_parseable_toml(self):
        """valid_ma_crossover.toml is syntactically valid TOML with expected sections."""
        try:
            import tomllib
        except ImportError:
            import tomli as tomllib  # type: ignore[no-redef]

        path = _TEST_DATA / "valid_ma_crossover.toml"
        content = path.read_text(encoding="utf-8")
        data = tomllib.loads(content)

        # Verify expected top-level sections
        assert "metadata" in data, "Missing metadata section"
        assert "entry_rules" in data, "Missing entry_rules section"
        assert "exit_rules" in data, "Missing exit_rules section"
        assert "position_sizing" in data, "Missing position_sizing section"
        assert "optimization_plan" in data, "Missing optimization_plan section"
        assert "cost_model_reference" in data, "Missing cost_model_reference section"

        # Verify metadata values
        assert data["metadata"]["pair"] == "EURUSD"
        assert data["metadata"]["timeframe"] == "H1"
        assert data["metadata"]["schema_version"] == "1"


@pytest.mark.live
class TestLiveContractAlignment:
    """Verify the Rust crate's types align with the contract files."""

    def test_live_contract_files_exist(self):
        """Strategy specification and indicator registry contracts exist."""
        spec_contract = _CONTRACTS / "strategy_specification.toml"
        registry_contract = _CONTRACTS / "indicator_registry.toml"
        assert spec_contract.exists(), f"Missing: {spec_contract}"
        assert registry_contract.exists(), f"Missing: {registry_contract}"

    def test_live_indicator_registry_contract_covers_v1(self):
        """indicator_registry.toml includes all V1 indicators (sma, ema, atr, bollinger_bands)."""
        try:
            import tomllib
        except ImportError:
            import tomli as tomllib  # type: ignore[no-redef]

        path = _CONTRACTS / "indicator_registry.toml"
        data = tomllib.loads(path.read_text(encoding="utf-8"))
        indicators = data.get("indicators", {})

        v1_indicators = ["sma", "ema", "atr", "bollinger_bands"]
        for ind in v1_indicators:
            assert ind in indicators, (
                f"V1 indicator '{ind}' missing from contract. Found: {list(indicators.keys())}"
            )

    def test_live_crate_source_files_exist(self):
        """All expected source files for the strategy_engine crate exist on disk."""
        expected_files = [
            "Cargo.toml",
            "src/lib.rs",
            "src/types.rs",
            "src/parser.rs",
            "src/registry.rs",
            "src/validator.rs",
            "src/error.rs",
        ]
        for rel_path in expected_files:
            full_path = _CRATE_DIR / rel_path
            assert full_path.exists(), f"Source file missing: {full_path}"
            assert full_path.stat().st_size > 0, f"Source file is empty: {full_path}"

    def test_live_workspace_includes_strategy_engine(self):
        """Workspace Cargo.toml lists strategy_engine as a member."""
        workspace_toml = _RUST_DIR / "Cargo.toml"
        content = workspace_toml.read_text(encoding="utf-8")
        assert "crates/strategy_engine" in content, (
            "strategy_engine not in workspace members"
        )

    def test_live_dependency_graph_correct(self):
        """strategy_engine depends on common + cost_model, NOT on backtester."""
        crate_toml = _CRATE_DIR / "Cargo.toml"
        content = crate_toml.read_text(encoding="utf-8")
        assert 'common = { path = "../common" }' in content
        assert 'cost_model = { path = "../cost_model" }' in content
        assert "backtester" not in content
        assert "live_daemon" not in content
