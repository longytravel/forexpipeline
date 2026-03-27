"""Tests for data_pipeline.dataset_hasher (Story 1.8, 1.10)."""
import hashlib
import json
from pathlib import Path

import pytest

from data_pipeline.dataset_hasher import (
    check_existing_dataset,
    compute_dataset_id,
    compute_file_hash,
    ensure_no_overwrite,
)


# ---------------------------------------------------------------------------
# compute_dataset_id
# ---------------------------------------------------------------------------

class TestComputeDatasetId:
    def test_format(self):
        """Dataset ID follows {pair}_{start}_{end}_{source}_{hash8} format."""
        result = compute_dataset_id(
            "EURUSD", "2024-01-01", "2024-12-31", "dukascopy",
            "a3b8f2c1d4e5f6a7b8c9d0e1f2a3b4c5",
        )
        assert result == "EURUSD_2024-01-01_2024-12-31_dukascopy_a3b8f2c1"

    def test_hash_truncated_to_8_chars(self):
        full_hash = "abcdef0123456789" * 4  # 64 chars
        result = compute_dataset_id("GBPUSD", "2020-01-01", "2020-12-31", "dukascopy", full_hash)
        assert result.endswith("_abcdef01")

    def test_different_hashes_produce_different_ids(self):
        id1 = compute_dataset_id("EURUSD", "2024-01-01", "2024-12-31", "dukascopy", "aaaa" * 16)
        id2 = compute_dataset_id("EURUSD", "2024-01-01", "2024-12-31", "dukascopy", "bbbb" * 16)
        assert id1 != id2

    def test_different_pairs_produce_different_ids(self):
        hash_val = "a1b2c3d4" * 8
        id1 = compute_dataset_id("EURUSD", "2024-01-01", "2024-12-31", "dukascopy", hash_val)
        id2 = compute_dataset_id("GBPUSD", "2024-01-01", "2024-12-31", "dukascopy", hash_val)
        assert id1 != id2

    def test_deterministic(self):
        """Same inputs always produce the same ID."""
        args = ("EURUSD", "2024-01-01", "2024-12-31", "dukascopy", "a1b2c3d4" * 8)
        assert compute_dataset_id(*args) == compute_dataset_id(*args)


# ---------------------------------------------------------------------------
# compute_file_hash
# ---------------------------------------------------------------------------

class TestComputeFileHash:
    def test_consistent_hash(self, tmp_path):
        """Hashing the same file twice produces identical results."""
        f = tmp_path / "data.bin"
        f.write_bytes(b"hello world" * 1000)
        assert compute_file_hash(f) == compute_file_hash(f)

    def test_matches_hashlib(self, tmp_path):
        """Result matches direct hashlib computation."""
        content = b"test content for hashing"
        f = tmp_path / "test.bin"
        f.write_bytes(content)
        expected = hashlib.sha256(content).hexdigest()
        assert compute_file_hash(f) == expected

    def test_returns_64_char_hex(self, tmp_path):
        f = tmp_path / "small.bin"
        f.write_bytes(b"x")
        result = compute_file_hash(f)
        assert len(result) == 64
        assert all(c in "0123456789abcdef" for c in result)

    def test_different_content_different_hash(self, tmp_path):
        f1 = tmp_path / "a.bin"
        f2 = tmp_path / "b.bin"
        f1.write_bytes(b"content A")
        f2.write_bytes(b"content B")
        assert compute_file_hash(f1) != compute_file_hash(f2)

    def test_file_not_found(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            compute_file_hash(tmp_path / "nonexistent.bin")


# ---------------------------------------------------------------------------
# check_existing_dataset
# ---------------------------------------------------------------------------

class TestCheckExistingDataset:
    def test_returns_path_when_manifest_exists(self, tmp_path):
        dataset_id = "EURUSD_2024-01-01_2024-12-31_dukascopy_a3b8f2c1"
        manifest = tmp_path / f"{dataset_id}_manifest.json"
        manifest.write_text('{"dataset_id": "test"}')

        result = check_existing_dataset(dataset_id, tmp_path)
        assert result == manifest

    def test_returns_none_when_no_manifest(self, tmp_path):
        result = check_existing_dataset("nonexistent_dataset", tmp_path)
        assert result is None

    def test_returns_none_for_empty_dir(self, tmp_path):
        result = check_existing_dataset("any_id", tmp_path)
        assert result is None

    def test_config_hash_match_returns_path(self, tmp_path):
        """AC #3: Matching config_hash allows reuse."""
        dataset_id = "EURUSD_2024-01-01_2024-12-31_dukascopy_a3b8f2c1"
        manifest = tmp_path / f"{dataset_id}_manifest.json"
        manifest.write_text(json.dumps({"dataset_id": dataset_id, "config_hash": "abc123"}))

        result = check_existing_dataset(dataset_id, tmp_path, config_hash="abc123")
        assert result == manifest

    def test_config_hash_mismatch_returns_none(self, tmp_path):
        """AC #3: Different config_hash invalidates cache — no false reuse."""
        dataset_id = "EURUSD_2024-01-01_2024-12-31_dukascopy_a3b8f2c1"
        manifest = tmp_path / f"{dataset_id}_manifest.json"
        manifest.write_text(json.dumps({"dataset_id": dataset_id, "config_hash": "old_hash"}))

        result = check_existing_dataset(dataset_id, tmp_path, config_hash="new_hash")
        assert result is None

    def test_no_config_hash_skips_check(self, tmp_path):
        """Backward compat: no config_hash means skip the check."""
        dataset_id = "EURUSD_2024-01-01_2024-12-31_dukascopy_a3b8f2c1"
        manifest = tmp_path / f"{dataset_id}_manifest.json"
        manifest.write_text(json.dumps({"dataset_id": dataset_id}))

        result = check_existing_dataset(dataset_id, tmp_path)
        assert result == manifest


# ---------------------------------------------------------------------------
# ensure_no_overwrite
# ---------------------------------------------------------------------------

class TestEnsureNoOverwrite:
    def test_new_file_returns_true(self, tmp_path):
        """Non-existent file is safe to write."""
        assert ensure_no_overwrite(tmp_path / "new.arrow") is True

    def test_existing_file_no_hash_returns_false(self, tmp_path):
        """Existing file with no expected hash — skip (idempotent)."""
        f = tmp_path / "existing.arrow"
        f.write_bytes(b"data")
        assert ensure_no_overwrite(f) is False

    def test_existing_file_matching_hash_returns_false(self, tmp_path):
        """Existing file with matching hash — skip."""
        content = b"deterministic content"
        f = tmp_path / "existing.arrow"
        f.write_bytes(content)
        expected_hash = hashlib.sha256(content).hexdigest()
        assert ensure_no_overwrite(f, expected_hash) is False

    def test_existing_file_different_hash_raises(self, tmp_path):
        """Existing file with different hash — refuse to overwrite."""
        f = tmp_path / "conflict.arrow"
        f.write_bytes(b"original content")
        with pytest.raises(ValueError, match="DIFFERENT hash"):
            ensure_no_overwrite(f, "0000000000000000" * 4)

    def test_never_overwrites_existing_artifacts(self, tmp_path):
        """AC #5: new downloads never overwrite existing files."""
        f = tmp_path / "immutable.arrow"
        original = b"original data"
        f.write_bytes(original)

        # ensure_no_overwrite returns False — caller should skip
        assert ensure_no_overwrite(f) is False
        # Original content preserved
        assert f.read_bytes() == original
