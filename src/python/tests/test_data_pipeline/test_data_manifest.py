"""Tests for data_pipeline.data_manifest (Story 1.8)."""
import json
from pathlib import Path

import pytest

from data_pipeline.data_manifest import create_data_manifest, write_manifest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _sample_split_metadata() -> dict:
    return {
        "split_mode": "ratio",
        "configured_ratio": 0.7,
        "split_ratio_actual": 0.6998,
        "split_timestamp_us": 1_719_792_000_000_000,
        "split_date_iso": "2024-07-01T00:00:00Z",
        "train_bar_count": 367_920,
        "test_bar_count": 157_680,
    }


def _sample_file_paths() -> dict:
    return {
        "base_files": {
            "full": "EURUSD_2024-01-01_2024-12-31_M1.arrow",
            "train": "EURUSD_2024-01-01_2024-12-31_M1_train.arrow",
            "test": "EURUSD_2024-01-01_2024-12-31_M1_test.arrow",
            "full_parquet": "EURUSD_2024-01-01_2024-12-31_M1.parquet",
            "train_parquet": "EURUSD_2024-01-01_2024-12-31_M1_train.parquet",
            "test_parquet": "EURUSD_2024-01-01_2024-12-31_M1_test.parquet",
        },
        "timeframes": {
            "H1": {
                "train": "EURUSD_2024-01-01_2024-12-31_H1_train.arrow",
                "test": "EURUSD_2024-01-01_2024-12-31_H1_test.arrow",
                "train_parquet": "EURUSD_2024-01-01_2024-12-31_H1_train.parquet",
                "test_parquet": "EURUSD_2024-01-01_2024-12-31_H1_test.parquet",
            },
        },
    }


def _make_manifest() -> dict:
    return create_data_manifest(
        dataset_id="EURUSD_2024-01-01_2024-12-31_dukascopy_a3b8f2c1",
        config_hash="b4c5d6e7f8a9b0c1d2e3f4a5b6c7d8e9",
        split_metadata=_sample_split_metadata(),
        file_paths=_sample_file_paths(),
        pair="EURUSD",
        start_date="2024-01-01",
        end_date="2024-12-31",
        source="dukascopy",
        data_hash="a3b8f2c1d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8a9b0c1d2e3f4a5b6c7d8e9f0a1",
    )


# ---------------------------------------------------------------------------
# create_data_manifest
# ---------------------------------------------------------------------------

class TestCreateDataManifest:
    def test_all_required_fields_present(self):
        """Manifest includes all required top-level fields (AC #6, #7)."""
        manifest = _make_manifest()
        required = {
            "dataset_id", "pair", "start_date", "end_date", "source",
            "data_hash", "config_hash", "created_at", "split", "files",
            "timeframes",
        }
        assert required.issubset(manifest.keys())

    def test_includes_config_hash(self):
        """AC #7: manifest includes the config hash used to produce it."""
        manifest = _make_manifest()
        assert manifest["config_hash"] == "b4c5d6e7f8a9b0c1d2e3f4a5b6c7d8e9"

    def test_includes_data_hash(self):
        manifest = _make_manifest()
        assert manifest["data_hash"].startswith("a3b8f2c1")

    def test_split_section_fields(self):
        """Split section contains mode, ratio, timestamp, counts."""
        manifest = _make_manifest()
        split = manifest["split"]
        assert split["mode"] == "ratio"
        assert split["configured_ratio"] == 0.7
        assert split["actual_ratio"] == 0.6998
        assert split["split_timestamp_us"] == 1_719_792_000_000_000
        assert split["train_bar_count"] == 367_920
        assert split["test_bar_count"] == 157_680

    def test_files_section_has_base_files(self):
        manifest = _make_manifest()
        files = manifest["files"]
        assert "full" in files
        assert "train" in files
        assert "test" in files
        assert files["train"].endswith("_train.arrow")

    def test_timeframes_section(self):
        manifest = _make_manifest()
        assert "H1" in manifest["timeframes"]
        h1 = manifest["timeframes"]["H1"]
        assert "train" in h1
        assert "test" in h1

    def test_correct_file_paths_all_timeframes(self):
        """File paths for all timeframes are recorded correctly."""
        manifest = _make_manifest()
        # Base (M1)
        assert "M1_train.arrow" in manifest["files"]["train"]
        assert "M1_test.arrow" in manifest["files"]["test"]
        # H1
        h1 = manifest["timeframes"]["H1"]
        assert "H1_train.arrow" in h1["train"]

    def test_created_at_is_iso_utc(self):
        manifest = _make_manifest()
        assert manifest["created_at"].endswith("Z")

    def test_dataset_id_matches_input(self):
        manifest = _make_manifest()
        assert manifest["dataset_id"] == "EURUSD_2024-01-01_2024-12-31_dukascopy_a3b8f2c1"

    def test_json_serializable(self):
        """Manifest can be serialized to JSON without errors."""
        manifest = _make_manifest()
        json_str = json.dumps(manifest, indent=2)
        roundtrip = json.loads(json_str)
        assert roundtrip == manifest


# ---------------------------------------------------------------------------
# write_manifest
# ---------------------------------------------------------------------------

class TestWriteManifest:
    def test_writes_file(self, tmp_path):
        manifest = _make_manifest()
        path = write_manifest(manifest, tmp_path)
        assert path.exists()

    def test_filename_matches_dataset_id(self, tmp_path):
        manifest = _make_manifest()
        path = write_manifest(manifest, tmp_path)
        expected_name = f"{manifest['dataset_id']}_manifest.json"
        assert path.name == expected_name

    def test_content_is_valid_json(self, tmp_path):
        manifest = _make_manifest()
        path = write_manifest(manifest, tmp_path)
        loaded = json.loads(path.read_text())
        assert loaded["dataset_id"] == manifest["dataset_id"]

    def test_crash_safe_no_partial_left(self, tmp_path):
        """After write, no .partial file should remain."""
        manifest = _make_manifest()
        write_manifest(manifest, tmp_path)
        partials = list(tmp_path.glob("*.partial"))
        assert partials == []

    def test_manifest_content_complete(self, tmp_path):
        """Written manifest contains all expected fields."""
        manifest = _make_manifest()
        path = write_manifest(manifest, tmp_path)
        loaded = json.loads(path.read_text())
        assert loaded["config_hash"] == manifest["config_hash"]
        assert loaded["split"]["train_bar_count"] == 367_920
