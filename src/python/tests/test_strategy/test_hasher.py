"""Tests for strategy specification hasher (AC #6)."""

from pathlib import Path

from strategy.hasher import compute_spec_hash, verify_spec_hash
from strategy.indicator_registry import reset_registry
from strategy.loader import load_strategy_spec

import pytest

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture(autouse=True)
def _clear_registry():
    reset_registry()
    yield
    reset_registry()


def test_spec_hash_deterministic():
    """Same spec -> same hash, multiple calls."""
    spec = load_strategy_spec(FIXTURES / "valid_ma_crossover.toml")
    h1 = compute_spec_hash(spec)
    h2 = compute_spec_hash(spec)
    assert h1 == h2
    assert len(h1) == 64  # SHA-256 hex digest


def test_spec_hash_changes_on_modification():
    """Modified spec -> different hash."""
    spec1 = load_strategy_spec(FIXTURES / "valid_ma_crossover.toml")
    h1 = compute_spec_hash(spec1)

    # Modify a field
    spec2 = spec1.model_copy(
        update={"position_sizing": spec1.position_sizing.model_copy(update={"risk_percent": 2.0})}
    )
    h2 = compute_spec_hash(spec2)

    assert h1 != h2


def test_spec_hash_verify_roundtrip():
    """compute -> verify returns True."""
    spec = load_strategy_spec(FIXTURES / "valid_ma_crossover.toml")
    h = compute_spec_hash(spec)
    assert verify_spec_hash(spec, h) is True
    assert verify_spec_hash(spec, "wrong_hash") is False


@pytest.mark.regression
class TestSpecHashLifecycleStability:
    """Regression: spec_hash must be a content hash that excludes lifecycle metadata.

    Both BMAD (M6) and Codex (MEDIUM-3) flagged that status, config_hash,
    confirmed_at, and created_at were included in spec_hash, meaning the
    same strategy content produced different hashes before/after confirmation.
    """

    def _make_spec(self, **meta_overrides):
        """Build a minimal spec with optional metadata overrides."""
        from strategy.specification import StrategySpecification

        base = {
            "metadata": {
                "schema_version": "1",
                "name": "test-strategy",
                "version": "v001",
                "pair": "EURUSD",
                "timeframe": "H1",
                "created_by": "test",
                "status": "draft",
            },
            "entry_rules": {
                "conditions": [
                    {
                        "indicator": "sma_crossover",
                        "parameters": {"fast_period": 20, "slow_period": 50},
                        "threshold": 0.0,
                        "comparator": "crosses_above",
                    }
                ],
                "filters": [],
                "confirmation": [],
            },
            "exit_rules": {
                "stop_loss": {"type": "atr_multiple", "value": 1.5},
                "take_profit": {"type": "risk_reward", "value": 3.0},
            },
            "position_sizing": {
                "method": "fixed_risk",
                "risk_percent": 1.0,
                "max_lots": 1.0,
            },
        }
        for key, val in meta_overrides.items():
            base["metadata"][key] = val
        return StrategySpecification.model_validate(base)

    def test_hash_stable_across_status_change(self):
        """Same content with status=draft vs status=confirmed must produce same hash."""
        draft = self._make_spec(status="draft")
        confirmed = self._make_spec(status="confirmed", config_hash="abc123")
        assert compute_spec_hash(draft) == compute_spec_hash(confirmed)

    def test_hash_stable_across_timestamp_changes(self):
        """Timestamps (created_at, confirmed_at) must not affect content hash."""
        no_ts = self._make_spec()
        with_ts = self._make_spec(
            created_at="2026-03-15T10:00:00Z",
            confirmed_at="2026-03-15T10:05:00Z",
        )
        assert compute_spec_hash(no_ts) == compute_spec_hash(with_ts)

    def test_hash_stable_across_config_hash_change(self):
        """config_hash must not affect content hash."""
        no_cfg = self._make_spec()
        with_cfg = self._make_spec(config_hash="a1b2c3d4e5f6g7h8")
        assert compute_spec_hash(no_cfg) == compute_spec_hash(with_cfg)

    def test_hash_changes_on_real_content_change(self):
        """Changing actual strategy content must change the hash."""
        spec1 = self._make_spec()
        spec2 = spec1.model_copy(
            update={
                "position_sizing": spec1.position_sizing.model_copy(
                    update={"risk_percent": 2.0}
                )
            }
        )
        assert compute_spec_hash(spec1) != compute_spec_hash(spec2)
