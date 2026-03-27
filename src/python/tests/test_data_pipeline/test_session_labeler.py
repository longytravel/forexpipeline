"""Tests for data_pipeline.session_labeler — Story 1.5 Task 10."""
import pandas as pd
import pytest

from data_pipeline.session_labeler import assign_session, assign_sessions_bulk


@pytest.fixture
def session_schedule():
    return {
        "timezone": "UTC",
        "asian": {"start": "00:00", "end": "08:00", "label": "Asian"},
        "london": {"start": "08:00", "end": "16:00", "label": "London"},
        "new_york": {"start": "13:00", "end": "21:00", "label": "New York"},
        "london_ny_overlap": {"start": "13:00", "end": "16:00", "label": "London/NY Overlap"},
        "off_hours": {"start": "21:00", "end": "00:00", "label": "Off Hours"},
    }


# ---------------------------------------------------------------------------
# Task 11.23: test_assign_session
# ---------------------------------------------------------------------------

class TestAssignSession:
    def test_asian_session(self, session_schedule):
        ts = pd.Timestamp("2024-01-02 03:00")
        assert assign_session(ts, session_schedule) == "asian"

    def test_london_session(self, session_schedule):
        ts = pd.Timestamp("2024-01-02 09:00")
        assert assign_session(ts, session_schedule) == "london"

    def test_new_york_session(self, session_schedule):
        ts = pd.Timestamp("2024-01-02 18:00")
        assert assign_session(ts, session_schedule) == "new_york"

    def test_off_hours_session(self, session_schedule):
        ts = pd.Timestamp("2024-01-02 22:00")
        assert assign_session(ts, session_schedule) == "off_hours"

    def test_session_boundaries(self, session_schedule):
        """Exact boundary: 00:00 is asian start, 08:00 is london start."""
        assert assign_session(pd.Timestamp("2024-01-02 00:00"), session_schedule) == "asian"
        assert assign_session(pd.Timestamp("2024-01-02 08:00"), session_schedule) == "london"
        assert assign_session(pd.Timestamp("2024-01-02 21:00"), session_schedule) == "off_hours"


# ---------------------------------------------------------------------------
# Task 11.24: test_assign_session_overlap
# ---------------------------------------------------------------------------

class TestAssignSessionOverlap:
    def test_london_ny_overlap(self, session_schedule):
        """London/NY overlap (13:00-16:00) should return london_ny_overlap."""
        ts = pd.Timestamp("2024-01-02 14:00")
        assert assign_session(ts, session_schedule) == "london_ny_overlap"

    def test_overlap_start_boundary(self, session_schedule):
        """13:00 exactly should be london_ny_overlap."""
        ts = pd.Timestamp("2024-01-02 13:00")
        assert assign_session(ts, session_schedule) == "london_ny_overlap"

    def test_overlap_end_boundary(self, session_schedule):
        """16:00 exactly should NOT be overlap (overlap is 13:00-16:00 exclusive end)."""
        ts = pd.Timestamp("2024-01-02 16:00")
        result = assign_session(ts, session_schedule)
        assert result != "london_ny_overlap"


# ---------------------------------------------------------------------------
# Bulk assignment
# ---------------------------------------------------------------------------

class TestBulkAssignment:
    def test_bulk_matches_individual(self, session_schedule):
        """Vectorized bulk results must match individual assign_session."""
        timestamps = pd.date_range("2024-01-02 00:00", periods=24 * 60, freq="min")
        df = pd.DataFrame({"timestamp": timestamps})

        bulk = assign_sessions_bulk(df, session_schedule)

        # Check a sample of timestamps
        for idx in [0, 180, 500, 800, 1200]:
            ts = timestamps[idx]
            expected = assign_session(ts, session_schedule)
            assert bulk.iloc[idx] == expected, (
                f"Mismatch at {ts}: bulk={bulk.iloc[idx]}, individual={expected}"
            )
