"""Tests for optimization.signal_cache (cache key isolation).

Covers: year_range and output_resolution affect cache keys,
ensuring filtered vs unfiltered and M1 vs H1 caches don't collide.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from optimization.signal_cache import SignalCacheManager


def _make_mock_classification():
    """Create a minimal mock ParamClassification."""
    mock = MagicMock()
    mock.has_signal_params = False
    mock.signal_indices = []
    mock.spec_override_params = {}
    return mock


class TestCacheKeyIsolation:
    """Cache keys must differ when year_range or output_resolution differ."""

    def test_different_year_ranges_produce_different_keys(self, tmp_path):
        """Same signal params but different year_range -> different cache keys."""
        classification = _make_mock_classification()

        cache_no_yr = SignalCacheManager(
            cache_dir=tmp_path / "cache1",
            strategy_spec={},
            market_data_path=tmp_path / "data.arrow",
            data_hash="sha256:abc123",
            classification=classification,
            year_range=None,
        )
        cache_yr_2020_2023 = SignalCacheManager(
            cache_dir=tmp_path / "cache2",
            strategy_spec={},
            market_data_path=tmp_path / "data.arrow",
            data_hash="sha256:abc123",
            classification=classification,
            year_range=(2020, 2023),
        )
        cache_yr_2018_2025 = SignalCacheManager(
            cache_dir=tmp_path / "cache3",
            strategy_spec={},
            market_data_path=tmp_path / "data.arrow",
            data_hash="sha256:abc123",
            classification=classification,
            year_range=(2018, 2025),
        )

        params = {"fast_period": 20, "slow_period": 50}

        key_none = cache_no_yr.compute_cache_key(params)
        key_2020 = cache_yr_2020_2023.compute_cache_key(params)
        key_2018 = cache_yr_2018_2025.compute_cache_key(params)

        # All three must be different
        assert key_none != key_2020
        assert key_none != key_2018
        assert key_2020 != key_2018

    def test_different_output_resolutions_produce_different_keys(self, tmp_path):
        """Same params, same year_range, different resolution -> different keys."""
        classification = _make_mock_classification()

        cache_m1 = SignalCacheManager(
            cache_dir=tmp_path / "cache_m1",
            strategy_spec={},
            market_data_path=tmp_path / "data.arrow",
            data_hash="sha256:abc123",
            classification=classification,
            output_resolution="M1",
        )
        cache_h1 = SignalCacheManager(
            cache_dir=tmp_path / "cache_h1",
            strategy_spec={},
            market_data_path=tmp_path / "data.arrow",
            data_hash="sha256:abc123",
            classification=classification,
            output_resolution="H1",
        )

        params = {"fast_period": 20, "slow_period": 50}

        key_m1 = cache_m1.compute_cache_key(params)
        key_h1 = cache_h1.compute_cache_key(params)

        assert key_m1 != key_h1

    def test_same_config_produces_same_key(self, tmp_path):
        """Identical config should always produce the same cache key."""
        classification = _make_mock_classification()

        cache1 = SignalCacheManager(
            cache_dir=tmp_path / "cache1",
            strategy_spec={},
            market_data_path=tmp_path / "data.arrow",
            data_hash="sha256:abc123",
            classification=classification,
            year_range=(2020, 2025),
            output_resolution="H1",
        )
        cache2 = SignalCacheManager(
            cache_dir=tmp_path / "cache2",
            strategy_spec={},
            market_data_path=tmp_path / "data.arrow",
            data_hash="sha256:abc123",
            classification=classification,
            year_range=(2020, 2025),
            output_resolution="H1",
        )

        params = {"fast_period": 20, "slow_period": 50}
        assert cache1.compute_cache_key(params) == cache2.compute_cache_key(params)

    def test_default_m1_no_year_range_backwards_compatible(self, tmp_path):
        """Default (M1, no year_range) key matches the original formula."""
        classification = _make_mock_classification()

        cache = SignalCacheManager(
            cache_dir=tmp_path / "cache",
            strategy_spec={},
            market_data_path=tmp_path / "data.arrow",
            data_hash="sha256:abc123",
            classification=classification,
        )

        params = {"fast_period": 20, "slow_period": 50}
        key = cache.compute_cache_key(params)

        # Manually compute expected key (original formula: data_hash:canonical)
        canonical = json.dumps(params, sort_keys=True, default=str)
        payload = f"sha256:abc123:{canonical}"
        expected = hashlib.sha256(payload.encode()).hexdigest()[:16]

        assert key == expected

    def test_cache_key_is_16_chars(self, tmp_path):
        """Cache keys should always be 16 hex characters."""
        classification = _make_mock_classification()

        for yr, res in [(None, "M1"), ((2020, 2025), "M1"), ((2020, 2025), "H1")]:
            cache = SignalCacheManager(
                cache_dir=tmp_path / f"cache_{yr}_{res}",
                strategy_spec={},
                market_data_path=tmp_path / "data.arrow",
                data_hash="sha256:abc123",
                classification=classification,
                year_range=yr,
                output_resolution=res,
            )
            key = cache.compute_cache_key({"p": 1})
            assert len(key) == 16
            assert all(c in "0123456789abcdef" for c in key)
