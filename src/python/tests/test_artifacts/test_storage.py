"""Tests for artifacts.storage."""
from pathlib import Path

from artifacts.storage import crash_safe_write, crash_safe_write_bytes, clean_partial_files


def test_crash_safe_write_creates_file(tmp_path):
    filepath = tmp_path / "test.txt"
    crash_safe_write(filepath, "hello world")
    assert filepath.exists()


def test_crash_safe_write_no_partial_left(tmp_path):
    filepath = tmp_path / "test.txt"
    crash_safe_write(filepath, "hello world")
    partial = filepath.with_name(filepath.name + ".partial")
    assert not partial.exists()


def test_crash_safe_write_content_correct(tmp_path):
    filepath = tmp_path / "test.txt"
    crash_safe_write(filepath, "hello world")
    assert filepath.read_text(encoding="utf-8") == "hello world"


def test_crash_safe_write_bytes(tmp_path):
    filepath = tmp_path / "test.bin"
    data = b"\x00\x01\x02\xff"
    crash_safe_write_bytes(filepath, data)
    assert filepath.read_bytes() == data


def test_clean_partial_files(tmp_path):
    # Create some partial files
    (tmp_path / "file1.partial").write_text("partial1")
    (tmp_path / "file2.partial").write_text("partial2")
    (tmp_path / "real_file.txt").write_text("real")

    deleted = clean_partial_files(tmp_path)
    assert len(deleted) == 2
    assert not (tmp_path / "file1.partial").exists()
    assert not (tmp_path / "file2.partial").exists()
    assert (tmp_path / "real_file.txt").exists()


def test_crash_safe_write_overwrites_existing(tmp_path):
    filepath = tmp_path / "test.txt"
    crash_safe_write(filepath, "original")
    crash_safe_write(filepath, "updated")
    assert filepath.read_text(encoding="utf-8") == "updated"


def test_clean_partial_files_nonexistent_dir(tmp_path):
    deleted = clean_partial_files(tmp_path / "nonexistent")
    assert deleted == []


def test_crash_safe_write_creates_parent_dirs(tmp_path):
    filepath = tmp_path / "sub" / "dir" / "test.txt"
    crash_safe_write(filepath, "nested")
    assert filepath.read_text(encoding="utf-8") == "nested"
