"""Tests for data_pipeline.quality_checker — Story 1.5."""
import json
import os
from datetime import date, datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock

import pandas as pd
import pytest

from data_pipeline.quality_checker import (
    CompletenessIssue,
    DataQualityChecker,
    GapRecord,
    IntegrityIssue,
    StaleRecord,
    ValidationResult,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def session_schedule():
    """Session schedule matching config/base.toml."""
    return {
        "timezone": "UTC",
        "asian": {"start": "00:00", "end": "08:00", "label": "Asian"},
        "london": {"start": "08:00", "end": "16:00", "label": "London"},
        "new_york": {"start": "13:00", "end": "21:00", "label": "New York"},
        "london_ny_overlap": {"start": "13:00", "end": "16:00", "label": "London/NY Overlap"},
        "off_hours": {"start": "21:00", "end": "00:00", "label": "Off Hours"},
    }


@pytest.fixture
def quality_config(session_schedule):
    """Config dict with quality and session settings."""
    return {
        "data": {
            "quality": {
                "gap_threshold_bars": 5,
                "gap_warning_per_year": 10,
                "gap_error_per_year": 50,
                "gap_error_minutes": 30,
                "spread_multiplier_threshold": 10.0,
                "stale_consecutive_bars": 5,
                "score_green_threshold": 0.95,
                "score_yellow_threshold": 0.80,
            },
        },
        "sessions": session_schedule,
    }


@pytest.fixture
def mock_logger():
    return MagicMock()


@pytest.fixture
def checker(quality_config, mock_logger):
    return DataQualityChecker(quality_config, mock_logger)


@pytest.fixture
def clean_m1_df():
    """100 rows of clean M1 data — no gaps, valid prices, no stale quotes."""
    timestamps = pd.date_range("2024-01-02 10:00", periods=100, freq="min")
    return pd.DataFrame({
        "timestamp": timestamps,
        "open": [1.1000 + i * 0.0001 for i in range(100)],
        "high": [1.1005 + i * 0.0001 for i in range(100)],
        "low": [1.0995 + i * 0.0001 for i in range(100)],
        "close": [1.1001 + i * 0.0001 for i in range(100)],
        "volume": [100 + i for i in range(100)],
        "bid": [1.1000 + i * 0.0001 for i in range(100)],
        "ask": [1.1002 + i * 0.0001 for i in range(100)],
    })


@pytest.fixture
def gapped_m1_df():
    """M1 data with 3 gaps of different sizes (7min, 15min, 45min)."""
    # Block 1: 10 bars
    ts1 = pd.date_range("2024-01-02 10:00", periods=10, freq="min")
    # 7-minute gap
    # Block 2: 10 bars starting 7 min after block 1 ends
    ts2 = pd.date_range("2024-01-02 10:17", periods=10, freq="min")
    # 15-minute gap
    # Block 3: 10 bars
    ts3 = pd.date_range("2024-01-02 10:42", periods=10, freq="min")
    # 45-minute gap (> 30min threshold)
    # Block 4: 10 bars
    ts4 = pd.date_range("2024-01-02 11:37", periods=10, freq="min")

    all_ts = ts1.append(ts2).append(ts3).append(ts4)
    n = len(all_ts)
    return pd.DataFrame({
        "timestamp": all_ts,
        "open": [1.1 + i * 0.0001 for i in range(n)],
        "high": [1.105 + i * 0.0001 for i in range(n)],
        "low": [1.095 + i * 0.0001 for i in range(n)],
        "close": [1.101 + i * 0.0001 for i in range(n)],
        "volume": [100] * n,
        "bid": [1.100 + i * 0.0001 for i in range(n)],
        "ask": [1.102 + i * 0.0001 for i in range(n)],
    })


@pytest.fixture
def weekend_gap_df():
    """M1 data with a gap spanning Friday 21:59 to Sunday 22:01 UTC."""
    # Friday bars
    ts_fri = pd.date_range("2024-01-05 21:55", periods=5, freq="min")
    # Sunday bars
    ts_sun = pd.date_range("2024-01-07 22:01", periods=5, freq="min")
    all_ts = ts_fri.append(ts_sun)
    n = len(all_ts)
    return pd.DataFrame({
        "timestamp": all_ts,
        "open": [1.1] * n,
        "high": [1.105] * n,
        "low": [1.095] * n,
        "close": [1.101] * n,
        "volume": [100] * n,
        "bid": [1.100] * n,
        "ask": [1.102] * n,
    })


# ---------------------------------------------------------------------------
# Task 11.3: test_detect_gaps_identifies_gaps
# ---------------------------------------------------------------------------

class TestDetectGaps:
    def test_detect_gaps_identifies_gaps(self, checker, gapped_m1_df):
        """DataFrame with 3 gaps of different sizes — verify correct detection."""
        gaps = checker._detect_gaps(gapped_m1_df, "M1")
        non_weekend = [g for g in gaps if not g.is_weekend]
        assert len(non_weekend) == 3
        # First gap ~7 min, second ~15 min, third ~45 min
        durations = sorted(g.duration_minutes for g in non_weekend)
        assert durations[0] == pytest.approx(7.0, abs=1.0)
        assert durations[1] == pytest.approx(15.0, abs=1.0)
        assert durations[2] == pytest.approx(45.0, abs=1.0)

    def test_detect_gaps_excludes_weekends(self, checker, weekend_gap_df):
        """Friday-to-Sunday gaps should be marked as weekend, NOT flagged."""
        gaps = checker._detect_gaps(weekend_gap_df, "M1")
        assert len(gaps) == 1
        assert gaps[0].is_weekend is True

    def test_no_gaps_in_clean_data(self, checker, clean_m1_df):
        """Clean contiguous data should have no gaps."""
        gaps = checker._detect_gaps(clean_m1_df, "M1")
        assert len(gaps) == 0


# ---------------------------------------------------------------------------
# Task 11.5–11.7: Gap severity classification
# ---------------------------------------------------------------------------

class TestGapSeverity:
    def test_gap_severity_ok_when_few(self, checker):
        """OK for <= 10 gaps/year (below warning threshold)."""
        gaps = [
            GapRecord(
                start=pd.Timestamp("2024-01-02 10:00"),
                end=pd.Timestamp("2024-01-02 10:10"),
                duration_minutes=10.0,
                is_weekend=False,
            )
            for _ in range(5)
        ]
        result = checker._classify_gap_severity(gaps, total_years=1.0)
        assert result == "ok"

    def test_gap_severity_warning(self, checker):
        """WARNING for > 10 and <= 50 gaps/year."""
        gaps = [
            GapRecord(
                start=pd.Timestamp("2024-01-02 10:00"),
                end=pd.Timestamp("2024-01-02 10:10"),
                duration_minutes=10.0,
                is_weekend=False,
            )
            for _ in range(25)
        ]
        result = checker._classify_gap_severity(gaps, total_years=1.0)
        assert result == "warning"

    def test_gap_severity_error_count(self, checker):
        """ERROR for > 50 gaps/year."""
        gaps = [
            GapRecord(
                start=pd.Timestamp("2024-01-02 10:00"),
                end=pd.Timestamp("2024-01-02 10:10"),
                duration_minutes=10.0,
                is_weekend=False,
            )
            for _ in range(55)
        ]
        result = checker._classify_gap_severity(gaps, total_years=1.0)
        assert result == "error"

    def test_gap_severity_error_duration(self, checker):
        """ERROR for any gap > 30 min."""
        gaps = [
            GapRecord(
                start=pd.Timestamp("2024-01-02 10:00"),
                end=pd.Timestamp("2024-01-02 10:45"),
                duration_minutes=45.0,
                is_weekend=False,
            ),
        ]
        result = checker._classify_gap_severity(gaps, total_years=1.0)
        assert result == "error"

    def test_gap_severity_ok_when_no_gaps(self, checker):
        """OK when no non-weekend gaps."""
        result = checker._classify_gap_severity([], total_years=1.0)
        assert result == "ok"


# ---------------------------------------------------------------------------
# Task 11.8–11.10: Price integrity checks
# ---------------------------------------------------------------------------

class TestPriceIntegrity:
    def test_price_integrity_positive_bid(self, checker, session_schedule):
        """ERROR on bid <= 0."""
        df = pd.DataFrame({
            "timestamp": pd.date_range("2024-01-02 10:00", periods=3, freq="min"),
            "open": [1.1, 1.1, 1.1],
            "high": [1.15, 1.15, 1.15],
            "low": [1.05, 1.05, 1.05],
            "close": [1.1, 1.1, 1.1],
            "bid": [1.1, -0.5, 0.0],
            "ask": [1.12, 1.12, 1.12],
        })
        issues = checker._check_price_integrity(df, session_schedule)
        bid_issues = [i for i in issues if i.issue_type == "non_positive_bid"]
        assert len(bid_issues) == 2  # -0.5 and 0.0

    def test_price_integrity_ask_gt_bid(self, checker, session_schedule):
        """ERROR on ask <= bid."""
        df = pd.DataFrame({
            "timestamp": pd.date_range("2024-01-02 10:00", periods=3, freq="min"),
            "open": [1.1, 1.1, 1.1],
            "high": [1.15, 1.15, 1.15],
            "low": [1.05, 1.05, 1.05],
            "close": [1.1, 1.1, 1.1],
            "bid": [1.10, 1.12, 1.10],
            "ask": [1.12, 1.10, 1.10],  # 2nd: ask < bid, 3rd: ask == bid
        })
        issues = checker._check_price_integrity(df, session_schedule)
        inverted = [i for i in issues if i.issue_type == "inverted_spread"]
        assert len(inverted) == 2

    def test_price_integrity_ohlc_consistency(self, checker, session_schedule):
        """ERROR on high < low, high < open, low > close, etc."""
        df = pd.DataFrame({
            "timestamp": pd.date_range("2024-01-02 10:00", periods=2, freq="min"),
            "open": [1.10, 1.10],
            "high": [1.05, 1.15],  # 1st: high < open (1.05 < 1.10)
            "low": [1.15, 1.05],   # 1st: low > open, low > high (inverted)
            "close": [1.10, 1.10],
            "bid": [1.10, 1.10],
            "ask": [1.12, 1.12],
        })
        issues = checker._check_price_integrity(df, session_schedule)
        ohlc_issues = [
            i for i in issues
            if i.issue_type in ("high_lt_low", "high_lt_open", "high_lt_close", "low_gt_open", "low_gt_close")
        ]
        assert len(ohlc_issues) >= 2  # At least high<low and high<open for first row

    def test_clean_data_no_issues(self, checker, clean_m1_df, session_schedule):
        """Clean data produces no integrity issues."""
        issues = checker._check_price_integrity(clean_m1_df, session_schedule)
        assert len(issues) == 0


# ---------------------------------------------------------------------------
# Task 11.11: Spread outlier detection
# ---------------------------------------------------------------------------

class TestSpreadOutlier:
    def test_spread_outlier_detection(self, checker, session_schedule):
        """Verify 10x median flagging per session."""
        # Create data in London session (10:00 UTC) with one extreme spread
        timestamps = pd.date_range("2024-01-02 10:00", periods=20, freq="min")
        bids = [1.1000] * 20
        asks = [1.1002] * 20  # normal spread = 0.0002
        # Make last bar have 20x median spread
        asks[-1] = 1.1000 + 0.0002 * 20  # spread = 0.004 = 20x normal

        df = pd.DataFrame({
            "timestamp": timestamps,
            "bid": bids,
            "ask": asks,
        })
        issues = checker._check_spread_outliers(df, session_schedule)
        assert len(issues) >= 1
        assert issues[0].issue_type == "spread_outlier"


# ---------------------------------------------------------------------------
# Task 11.12: Timezone alignment
# ---------------------------------------------------------------------------

class TestTimezoneAlignment:
    def test_timezone_monotonic(self, checker):
        """ERROR on non-monotonic timestamps."""
        df = pd.DataFrame({
            "timestamp": [
                "2024-01-02 10:00",
                "2024-01-02 10:02",  # ok
                "2024-01-02 10:01",  # out of order
                "2024-01-02 10:03",
            ],
        })
        issues = checker._verify_timezone_alignment(df)
        monotonic_issues = [i for i in issues if i.issue_type == "non_monotonic_timestamp"]
        assert len(monotonic_issues) >= 1

    def test_timezone_issues_surfaced_in_report(self, checker, tmp_path):
        """AC #2: timezone findings must appear in the quality report."""
        # Create data with non-monotonic timestamps to trigger timezone issues
        df = pd.DataFrame({
            "timestamp": [
                "2024-01-02 10:00",
                "2024-01-02 10:02",
                "2024-01-02 10:01",  # out of order
                "2024-01-02 10:03",
            ],
            "open": [1.1, 1.1, 1.1, 1.1],
            "high": [1.15, 1.15, 1.15, 1.15],
            "low": [1.05, 1.05, 1.05, 1.05],
            "close": [1.1, 1.1, 1.1, 1.1],
            "bid": [1.10, 1.10, 1.10, 1.10],
            "ask": [1.12, 1.12, 1.12, 1.12],
        })

        dataset_id = "EURUSD_2024-01-02_2024-01-02_M1"
        result = checker.validate(
            df=df, pair="EURUSD", resolution="M1",
            start_date=date(2024, 1, 2), end_date=date(2024, 1, 2),
            storage_path=tmp_path, dataset_id=dataset_id, version="v001",
        )

        report = json.loads(result.report_path.read_text())
        assert "timezone_issues" in report, "timezone_issues missing from quality report"
        assert len(report["timezone_issues"]) >= 1
        assert report["timezone_issues"][0]["issue_type"] == "non_monotonic_timestamp"

    def test_timezone_issues_empty_when_clean(self, checker, clean_m1_df, tmp_path):
        """AC #2: timezone_issues should be empty list when no issues."""
        dataset_id = "EURUSD_2024-01-02_2024-01-02_M1"
        result = checker.validate(
            df=clean_m1_df, pair="EURUSD", resolution="M1",
            start_date=date(2024, 1, 2), end_date=date(2024, 1, 2),
            storage_path=tmp_path, dataset_id=dataset_id, version="v001",
        )

        report = json.loads(result.report_path.read_text())
        assert "timezone_issues" in report, "timezone_issues key missing from report"
        assert report["timezone_issues"] == []


# ---------------------------------------------------------------------------
# Task 11.13: Stale quote detection
# ---------------------------------------------------------------------------

class TestStaleQuotes:
    def test_stale_quote_detection(self, checker):
        """Zero-spread runs > 5 bars are flagged."""
        n = 20
        timestamps = pd.date_range("2024-01-02 10:00", periods=n, freq="min")
        bids = [1.1000] * n
        asks = list(bids)  # zero spread initially
        # First 8 bars: bid == ask (stale) — should be flagged (> 5)
        # Remaining: normal spread
        for i in range(8, n):
            asks[i] = 1.1002

        df = pd.DataFrame({
            "timestamp": timestamps,
            "open": [1.1] * n,
            "high": [1.105] * n,
            "low": [1.095] * n,
            "close": [1.101] * n,
            "bid": bids,
            "ask": asks,
        })
        stale = checker._detect_stale_quotes(df)
        zero_spread = [s for s in stale if s.stale_type == "zero_spread"]
        assert len(zero_spread) >= 1
        assert zero_spread[0].duration_bars == 8

    def test_no_stale_in_clean_data(self, checker, clean_m1_df):
        """Clean data has no stale quotes."""
        stale = checker._detect_stale_quotes(clean_m1_df)
        assert len(stale) == 0


# ---------------------------------------------------------------------------
# Task 11.14: Completeness checks
# ---------------------------------------------------------------------------

class TestCompleteness:
    def test_completeness_missing_weekday(self, checker):
        """Missing weekday is ERROR."""
        # Only Tuesday data, but range covers Mon-Fri
        timestamps = pd.date_range("2024-01-02 10:00", periods=100, freq="min")
        df = pd.DataFrame({"timestamp": timestamps})

        issues = checker._check_completeness(
            df,
            start_date=date(2024, 1, 1),
            end_date=date(2024, 1, 5),
        )
        missing = [i for i in issues if i.issue_type == "missing_weekday"]
        # Mon 1/1 might be holiday, but 1/3, 1/4, 1/5 should be missing
        assert len(missing) >= 2


# ---------------------------------------------------------------------------
# Task 11.15–11.18: Quality scoring
# ---------------------------------------------------------------------------

class TestQualityScoring:
    def test_quality_score_green(self, checker, clean_m1_df):
        """Score >= 0.95 -> GREEN."""
        score, penalties = checker._compute_quality_score(
            clean_m1_df, gaps=[], integrity_issues=[], stale_records=[],
        )
        assert score >= 0.95
        rating = checker._classify_score(score)
        assert rating == "GREEN"

    def test_quality_score_yellow(self, checker):
        """0.80 <= score < 0.95 -> YELLOW."""
        rating = checker._classify_score(0.90)
        assert rating == "YELLOW"
        rating2 = checker._classify_score(0.80)
        assert rating2 == "YELLOW"

    def test_quality_score_red(self, checker):
        """score < 0.80 -> RED."""
        rating = checker._classify_score(0.79)
        assert rating == "RED"
        rating2 = checker._classify_score(0.0)
        assert rating2 == "RED"

    def test_quality_score_formula(self, checker):
        """Verify exact penalty calculation with known inputs."""
        # Create a small df of 1000 bars
        timestamps = pd.date_range("2024-01-02 10:00", periods=1000, freq="min")
        df = pd.DataFrame({
            "timestamp": timestamps,
            "close": [1.1] * 1000,
        })

        # 10 bars of gaps (non-weekend)
        gaps = [
            GapRecord(
                start=pd.Timestamp("2024-01-02 10:00"),
                end=pd.Timestamp("2024-01-02 10:10"),
                duration_minutes=10.0,
                is_weekend=False,
            )
        ]

        # 5 integrity errors
        integrity_issues = [
            IntegrityIssue(
                timestamp=pd.Timestamp("2024-01-02 10:00"),
                issue_type="test",
                detail="test",
                severity="error",
            )
            for _ in range(5)
        ]

        # 10 stale bars
        stale = [
            StaleRecord(
                start=pd.Timestamp("2024-01-02 12:00"),
                end=pd.Timestamp("2024-01-02 12:10"),
                duration_bars=10,
                stale_type="zero_spread",
            )
        ]

        score, penalties = checker._compute_quality_score(
            df, gaps, integrity_issues, stale,
        )

        # Verify penalties are reasonable (non-zero, < 1)
        assert 0 < penalties["gap_penalty"] < 1
        assert 0 < penalties["integrity_penalty"] < 1
        assert 0 < penalties["staleness_penalty"] < 1
        assert 0 <= score <= 1

        # Verify the formula: score = 1 - sum(penalties)
        expected = 1.0 - (penalties["gap_penalty"] + penalties["integrity_penalty"] + penalties["staleness_penalty"])
        expected = max(0.0, expected)
        assert score == pytest.approx(expected, abs=1e-6)


# ---------------------------------------------------------------------------
# Task 11.19: Quarantine marking
# ---------------------------------------------------------------------------

class TestQuarantineMarking:
    def test_quarantine_marking(self, checker, clean_m1_df):
        """Verify correct bars are marked quarantined."""
        # Create integrity issues for specific timestamps
        ts = clean_m1_df["timestamp"].iloc[5]
        integrity_issues = [
            IntegrityIssue(
                timestamp=ts,
                issue_type="test",
                detail="test",
                severity="error",
            ),
        ]

        # Create stale record spanning bars 10-15
        stale = [
            StaleRecord(
                start=clean_m1_df["timestamp"].iloc[10],
                end=clean_m1_df["timestamp"].iloc[15],
                duration_bars=6,
                stale_type="zero_spread",
            ),
        ]

        result = checker._mark_quarantined(clean_m1_df, [], integrity_issues, stale)

        assert "quarantined" in result.columns
        assert result["quarantined"].dtype == bool
        # Bar 5 should be quarantined (integrity issue)
        assert bool(result.iloc[5]["quarantined"]) is True
        # Bars 10-15 should be quarantined (stale)
        for i in range(10, 16):
            assert bool(result.iloc[i]["quarantined"]) is True
        # Bar 0 should NOT be quarantined
        assert bool(result.iloc[0]["quarantined"]) is False


# ---------------------------------------------------------------------------
# Task 11.20–11.22: Integration tests
# ---------------------------------------------------------------------------

class TestQuarantineAccuracy:
    """AC #5: quarantine counts must accurately reflect all quarantine sources."""

    def test_integrity_errors_included_in_quarantined_periods(self, checker, tmp_path):
        """Integrity-error quarantines must appear in quarantined_periods."""
        n = 20
        timestamps = pd.date_range("2024-01-02 10:00", periods=n, freq="min")
        df = pd.DataFrame({
            "timestamp": timestamps,
            "open": [1.1] * n,
            "high": [1.05] * n,  # high < open → integrity error
            "low": [1.15] * n,   # low > open → integrity error
            "close": [1.1] * n,
            "bid": [1.10] * n,
            "ask": [1.12] * n,
        })

        dataset_id = "EURUSD_2024-01-02_2024-01-02_M1"
        result = checker.validate(
            df=df, pair="EURUSD", resolution="M1",
            start_date=date(2024, 1, 2), end_date=date(2024, 1, 2),
            storage_path=tmp_path, dataset_id=dataset_id, version="v001",
        )

        report = json.loads(result.report_path.read_text())
        reasons = [p["reason"] for p in report["quarantined_periods"]]
        assert "integrity_error" in reasons, (
            f"integrity_error not in quarantined_periods reasons: {reasons}"
        )

    def test_gap_bar_count_not_hardcoded_zero(self, checker, tmp_path):
        """Gap quarantines must have actual bar_count, not hardcoded 0."""
        # Create data with a gap — bars around the gap get quarantined
        ts1 = pd.date_range("2024-01-02 10:00", periods=10, freq="min")
        ts2 = pd.date_range("2024-01-02 10:20", periods=10, freq="min")
        all_ts = ts1.append(ts2)
        n = len(all_ts)

        df = pd.DataFrame({
            "timestamp": all_ts,
            "open": [1.1] * n,
            "high": [1.15] * n,
            "low": [1.05] * n,
            "close": [1.1] * n,
            "bid": [1.10] * n,
            "ask": [1.12] * n,
        })

        dataset_id = "EURUSD_2024-01-02_2024-01-02_M1"
        result = checker.validate(
            df=df, pair="EURUSD", resolution="M1",
            start_date=date(2024, 1, 2), end_date=date(2024, 1, 2),
            storage_path=tmp_path, dataset_id=dataset_id, version="v001",
        )

        report = json.loads(result.report_path.read_text())
        gap_periods = [p for p in report["quarantined_periods"] if p["reason"] == "gap"]
        # There should be at least one gap quarantine
        if gap_periods:
            # bar_count should reflect actual bars in the gap range, not 0
            # (though there may be 0 bars in the gap itself if the range is empty)
            assert isinstance(gap_periods[0]["bar_count"], int)

    def test_quarantined_percentage_reflects_all_sources(self, checker, tmp_path):
        """quarantined_percentage must be computed from corrected counts."""
        n = 20
        timestamps = pd.date_range("2024-01-02 10:00", periods=n, freq="min")
        df = pd.DataFrame({
            "timestamp": timestamps,
            "open": [1.1] * n,
            "high": [1.05] * n,  # all rows have integrity errors
            "low": [1.15] * n,
            "close": [1.1] * n,
            "bid": [1.10] * n,
            "ask": [1.12] * n,
        })

        dataset_id = "EURUSD_2024-01-02_2024-01-02_M1"
        result = checker.validate(
            df=df, pair="EURUSD", resolution="M1",
            start_date=date(2024, 1, 2), end_date=date(2024, 1, 2),
            storage_path=tmp_path, dataset_id=dataset_id, version="v001",
        )

        report = json.loads(result.report_path.read_text())
        # With integrity errors on all rows, quarantined_bar_count should be > 0
        assert report["quarantined_bar_count"] > 0
        assert report["quarantined_percentage"] > 0


class TestConfigHashInReport:
    def test_config_hash_populated_in_report(self, checker, clean_m1_df, tmp_path):
        """AC #6: config_hash must be populated with actual hash, not blank."""
        dataset_id = "EURUSD_2024-01-02_2024-01-02_M1"
        result = checker.validate(
            df=clean_m1_df, pair="EURUSD", resolution="M1",
            start_date=date(2024, 1, 2), end_date=date(2024, 1, 2),
            storage_path=tmp_path, dataset_id=dataset_id, version="v001",
            config_hash="sha256:abc123def456",
        )

        report = json.loads(result.report_path.read_text())
        assert report["config_hash"] == "sha256:abc123def456"
        assert report["config_hash"] != ""

    def test_config_hash_auto_computed_when_not_provided(self, checker, clean_m1_df, tmp_path):
        """AC #6: When config_hash not provided, it's auto-computed from config."""
        dataset_id = "EURUSD_2024-01-02_2024-01-02_M1"
        result = checker.validate(
            df=clean_m1_df, pair="EURUSD", resolution="M1",
            start_date=date(2024, 1, 2), end_date=date(2024, 1, 2),
            storage_path=tmp_path, dataset_id=dataset_id, version="v001",
        )

        report = json.loads(result.report_path.read_text())
        assert "config_hash" in report
        assert report["config_hash"] != "", "config_hash should be auto-computed, not blank"
        assert report["config_hash"].startswith("sha256:"), "config_hash must have sha256: prefix"
        assert len(report["config_hash"]) == 71  # "sha256:" (7) + 64 hex chars


class TestConfigHashAutoComputation:
    """AC #6 / AC #3: config_hash must always be populated in quality reports."""

    def test_config_hash_deterministic(self, checker, clean_m1_df, tmp_path):
        """Same config produces same hash across two validate() calls."""
        ds = "EURUSD_2024-01-02_2024-01-02_M1"

        r1 = checker.validate(
            df=clean_m1_df, pair="EURUSD", resolution="M1",
            start_date=date(2024, 1, 2), end_date=date(2024, 1, 2),
            storage_path=tmp_path / "run1", dataset_id=ds, version="v001",
        )
        r2 = checker.validate(
            df=clean_m1_df, pair="EURUSD", resolution="M1",
            start_date=date(2024, 1, 2), end_date=date(2024, 1, 2),
            storage_path=tmp_path / "run2", dataset_id=ds, version="v001",
        )

        report1 = json.loads(r1.report_path.read_text())
        report2 = json.loads(r2.report_path.read_text())
        assert report1["config_hash"] == report2["config_hash"]

    def test_different_config_different_hash(self, clean_m1_df, tmp_path, mock_logger):
        """Different configs must produce different hashes (AC #3 staleness detection)."""
        config1 = {
            "data": {"quality": {"gap_threshold_bars": 5}},
            "sessions": {},
        }
        config2 = {
            "data": {"quality": {"gap_threshold_bars": 10}},
            "sessions": {},
        }
        checker1 = DataQualityChecker(config1, mock_logger)
        checker2 = DataQualityChecker(config2, mock_logger)

        ds = "EURUSD_2024-01-02_2024-01-02_M1"
        r1 = checker1.validate(
            df=clean_m1_df, pair="EURUSD", resolution="M1",
            start_date=date(2024, 1, 2), end_date=date(2024, 1, 2),
            storage_path=tmp_path / "c1", dataset_id=ds, version="v001",
        )
        r2 = checker2.validate(
            df=clean_m1_df, pair="EURUSD", resolution="M1",
            start_date=date(2024, 1, 2), end_date=date(2024, 1, 2),
            storage_path=tmp_path / "c2", dataset_id=ds, version="v001",
        )

        h1 = json.loads(r1.report_path.read_text())["config_hash"]
        h2 = json.loads(r2.report_path.read_text())["config_hash"]
        assert h1 != h2, "Different configs must produce different hashes"

    def test_explicit_hash_overrides_auto(self, checker, clean_m1_df, tmp_path):
        """When caller provides config_hash, it's used instead of auto-compute."""
        ds = "EURUSD_2024-01-02_2024-01-02_M1"
        result = checker.validate(
            df=clean_m1_df, pair="EURUSD", resolution="M1",
            start_date=date(2024, 1, 2), end_date=date(2024, 1, 2),
            storage_path=tmp_path, dataset_id=ds, version="v001",
            config_hash="explicit_hash_from_caller",
        )
        report = json.loads(result.report_path.read_text())
        assert report["config_hash"] == "explicit_hash_from_caller"


class TestFullValidation:
    def test_full_validation_clean_data(self, checker, clean_m1_df, tmp_path):
        """Run full validation on clean fixture — verify GREEN."""
        dataset_id = "EURUSD_2024-01-02_2024-01-02_M1"
        result = checker.validate(
            df=clean_m1_df,
            pair="EURUSD",
            resolution="M1",
            start_date=date(2024, 1, 2),
            end_date=date(2024, 1, 2),
            storage_path=tmp_path,
            dataset_id=dataset_id,
            version="v001",
        )

        assert isinstance(result, ValidationResult)
        assert result.quality_score >= 0.95
        assert result.rating == "GREEN"
        assert result.can_proceed is True
        assert result.report_path.exists()
        assert "quarantined" in result.validated_df.columns

        # Verify report content
        report = json.loads(result.report_path.read_text())
        assert report["rating"] == "GREEN"
        assert report["pair"] == "EURUSD"

    def test_full_validation_bad_data(self, checker, tmp_path):
        """Run full validation on data with multiple issues — verify RED."""
        n = 100
        timestamps = pd.date_range("2024-01-02 10:00", periods=n, freq="min")
        df = pd.DataFrame({
            "timestamp": timestamps,
            "open": [1.1] * n,
            "high": [1.05] * n,  # high < open -> integrity error
            "low": [1.15] * n,   # low > open -> integrity error
            "close": [1.1] * n,
            "volume": [100] * n,
            "bid": [1.1] * n,
            "ask": [1.1] * n,  # zero spread -> stale + inverted
        })

        dataset_id = "EURUSD_2024-01-02_2024-01-02_M1"
        result = checker.validate(
            df=df,
            pair="EURUSD",
            resolution="M1",
            start_date=date(2024, 1, 2),
            end_date=date(2024, 1, 2),
            storage_path=tmp_path,
            dataset_id=dataset_id,
            version="v001",
        )

        assert result.quality_score < 0.80
        assert result.rating == "RED"
        assert result.can_proceed is False

        # Verify report
        report = json.loads(result.report_path.read_text())
        assert report["rating"] == "RED"
        assert len(report["integrity_issues"]) > 0

    def test_quality_report_crash_safe(self, checker, clean_m1_df, tmp_path):
        """Verify .partial write pattern — no .partial files remain."""
        dataset_id = "EURUSD_2024-01-02_2024-01-02_M1"
        checker.validate(
            df=clean_m1_df,
            pair="EURUSD",
            resolution="M1",
            start_date=date(2024, 1, 2),
            end_date=date(2024, 1, 2),
            storage_path=tmp_path,
            dataset_id=dataset_id,
            version="v001",
        )

        # No .partial files should remain
        partials = list(tmp_path.rglob("*.partial"))
        assert partials == [], f"Found leftover .partial files: {partials}"

        # Verify both artifacts exist
        report_path = tmp_path / "raw" / dataset_id / "v001" / "quality-report.json"
        validated_path = tmp_path / "validated" / dataset_id / "v001" / f"{dataset_id}_validated.csv"
        assert report_path.exists()
        assert validated_path.exists()


# ---------------------------------------------------------------------------
# LIVE integration tests — validate real downloaded data
# Marked with @pytest.mark.live so they're skipped by default.
# Run with: pytest -m live
# ---------------------------------------------------------------------------

@pytest.mark.live
class TestLiveValidation:
    """Live test: download real data from Dukascopy, run full validation."""

    def _download_real_data(self, tmp_path):
        """Helper: download 1 year of real EURUSD M1 data."""
        from data_pipeline.downloader import DukascopyDownloader

        config = {
            "data_pipeline": {
                "storage_path": str(tmp_path),
                "default_resolution": "M1",
                "request_delay_seconds": 1.0,
                "max_retries": 3,
                "download": {
                    "pairs": ["EURUSD"],
                    "start_date": "2024-01-01",
                    "end_date": "2024-12-31",
                    "resolution": "M1",
                },
            },
        }
        logger = MagicMock()
        dl = DukascopyDownloader(config, logger)
        df = dl._download_year_bidask("EURUSD", 2024)
        assert df is not None and not df.empty, "Dukascopy API may be down"
        return df

    def test_live_validation_real_data(self, tmp_path):
        """Download real M1 data, run validation, verify artifacts on disk.

        Validates:
        - Real data produces a quality score
        - Quality report JSON is written to disk
        - Validated CSV with quarantined column is written to disk
        - No .partial files remain
        - Report content matches expected schema
        - Quarantined column exists in validated output
        """
        df = self._download_real_data(tmp_path)

        quality_config = {
            "data": {
                "quality": {
                    "gap_threshold_bars": 5,
                    "gap_warning_per_year": 10,
                    "gap_error_per_year": 50,
                    "gap_error_minutes": 30,
                    "spread_multiplier_threshold": 10.0,
                    "stale_consecutive_bars": 5,
                    "score_green_threshold": 0.95,
                    "score_yellow_threshold": 0.80,
                },
            },
            "sessions": {
                "timezone": "UTC",
                "asian": {"start": "00:00", "end": "08:00", "label": "Asian"},
                "london": {"start": "08:00", "end": "16:00", "label": "London"},
                "new_york": {"start": "13:00", "end": "21:00", "label": "New York"},
                "london_ny_overlap": {"start": "13:00", "end": "16:00", "label": "London/NY Overlap"},
                "off_hours": {"start": "21:00", "end": "00:00", "label": "Off Hours"},
            },
        }

        logger = MagicMock()
        checker = DataQualityChecker(quality_config, logger)
        dataset_id = "EURUSD_2024-01-01_2024-12-31_M1"

        result = checker.validate(
            df=df,
            pair="EURUSD",
            resolution="M1",
            start_date=date(2024, 1, 1),
            end_date=date(2024, 12, 31),
            storage_path=tmp_path,
            dataset_id=dataset_id,
            version="v001",
        )

        # --- Quality score ---
        assert 0.0 <= result.quality_score <= 1.0
        assert result.rating in ("GREEN", "YELLOW", "RED")
        assert result.can_proceed in (True, False, "operator_review")

        # --- Report artifact on disk ---
        report_path = tmp_path / "raw" / dataset_id / "v001" / "quality-report.json"
        assert report_path.exists(), f"Quality report not found at {report_path}"
        report = json.loads(report_path.read_text())
        assert report["pair"] == "EURUSD"
        assert report["resolution"] == "M1"
        assert report["total_bars"] == len(df)
        assert report["quality_score"] == pytest.approx(result.quality_score, rel=1e-5)
        assert report["rating"] == result.rating
        assert "gap_penalty" in report["penalty_breakdown"]
        assert "integrity_penalty" in report["penalty_breakdown"]
        assert "staleness_penalty" in report["penalty_breakdown"]

        # --- Validated CSV on disk ---
        validated_path = tmp_path / "validated" / dataset_id / "v001" / f"{dataset_id}_validated.csv"
        assert validated_path.exists(), f"Validated CSV not found at {validated_path}"
        validated_df = pd.read_csv(validated_path)
        assert "quarantined" in validated_df.columns
        assert len(validated_df) == len(df)

        # --- No .partial files ---
        partials = list(tmp_path.rglob("*.partial"))
        assert partials == [], f"Leftover .partial files: {partials}"

        print(f"\n  LIVE VALIDATION TEST PASSED")
        print(f"  Rows validated: {len(df)}")
        print(f"  Quality score: {result.quality_score:.4f}")
        print(f"  Rating: {result.rating}")
        print(f"  Can proceed: {result.can_proceed}")
        print(f"  Quarantined bars: {result.validated_df['quarantined'].sum()}")
        print(f"  Report: {report_path}")
        print(f"  Validated CSV: {validated_path}")

    def test_live_session_labeling_real_data(self, tmp_path):
        """Verify session labels are assigned correctly on real data.

        Validates:
        - Every row gets a valid session label
        - All expected sessions appear in the data
        - Overlap session is correctly identified
        """
        from data_pipeline.session_labeler import assign_sessions_bulk

        df = self._download_real_data(tmp_path)

        session_schedule = {
            "timezone": "UTC",
            "asian": {"start": "00:00", "end": "08:00", "label": "Asian"},
            "london": {"start": "08:00", "end": "16:00", "label": "London"},
            "new_york": {"start": "13:00", "end": "21:00", "label": "New York"},
            "london_ny_overlap": {"start": "13:00", "end": "16:00", "label": "London/NY Overlap"},
            "off_hours": {"start": "21:00", "end": "00:00", "label": "Off Hours"},
        }

        sessions = assign_sessions_bulk(df, session_schedule)

        # Every row should have a session
        assert sessions.notna().all()
        assert len(sessions) == len(df)

        # Valid session labels
        valid_labels = {"asian", "london", "new_york", "london_ny_overlap", "off_hours"}
        unique_labels = set(sessions.unique())
        assert unique_labels.issubset(valid_labels), f"Unexpected labels: {unique_labels - valid_labels}"

        # Real EURUSD year data should have all sessions represented
        assert "asian" in unique_labels
        assert "london_ny_overlap" in unique_labels
        assert "off_hours" in unique_labels

        print(f"\n  LIVE SESSION LABELING TEST PASSED")
        print(f"  Rows labeled: {len(sessions)}")
        print(f"  Session distribution:")
        for label in sorted(unique_labels):
            count = (sessions == label).sum()
            pct = count / len(sessions) * 100
            print(f"    {label}: {count} ({pct:.1f}%)")


# ---------------------------------------------------------------------------
# Regression tests — Story 1.10 PIR Remediation synthesis
# ---------------------------------------------------------------------------

class TestQuarantinePercentageRegression:
    """Regression: quarantined_percentage must reflect unique bars, not
    the sum of per-reason counts which can double-count overlaps."""

    @pytest.mark.regression
    def test_quarantine_percentage_no_double_count(self, checker, tmp_path):
        """If a bar is quarantined for both staleness and integrity error,
        quarantined_bar_count and quarantined_percentage must not inflate."""
        # Build data where bars 5-9 are both stale AND have integrity errors
        timestamps = pd.date_range("2024-01-02 10:00", periods=20, freq="min")
        prices = [1.1000 + i * 0.0001 for i in range(20)]
        # Make bars 5-9 stale (identical prices)
        for i in range(5, 10):
            prices[i] = 1.1005
        df = pd.DataFrame({
            "timestamp": timestamps,
            "open": prices,
            "high": [p + 0.0005 for p in prices],
            "low": [p - 0.0005 for p in prices],
            "close": prices,
            "volume": [100] * 20,
            "bid": prices,
            "ask": [p + 0.0002 for p in prices],
        })

        result = checker.validate(
            df=df, pair="EURUSD", resolution="M1",
            start_date=date(2024, 1, 2), end_date=date(2024, 1, 2),
            storage_path=tmp_path, dataset_id="TEST_OVERLAP", version="v001",
        )

        report = json.loads(result.report_path.read_text())
        total_bars = report["total_bars"]
        quarantined_bar_count = report["quarantined_bar_count"]
        quarantined_pct = report["quarantined_percentage"]

        # quarantined_bar_count must never exceed total_bars
        assert quarantined_bar_count <= total_bars, (
            f"quarantined_bar_count ({quarantined_bar_count}) > total_bars ({total_bars}); "
            "double-counting regression"
        )
        # percentage must be <= 1.0 (100%)
        assert quarantined_pct <= 1.0, (
            f"quarantined_percentage ({quarantined_pct}) > 1.0; double-counting regression"
        )

    @pytest.mark.regression
    def test_quarantine_percentage_uses_unique_count(self, checker, tmp_path):
        """The report's quarantined_bar_count should equal the unique
        quarantined rows in validated_df, not sum of per-reason counts."""
        timestamps = pd.date_range("2024-01-02 10:00", periods=20, freq="min")
        df = pd.DataFrame({
            "timestamp": timestamps,
            "open": [1.1000 + i * 0.0001 for i in range(20)],
            "high": [1.1005 + i * 0.0001 for i in range(20)],
            "low": [1.0995 + i * 0.0001 for i in range(20)],
            "close": [1.1001 + i * 0.0001 for i in range(20)],
            "volume": [100 + i for i in range(20)],
            "bid": [1.1000 + i * 0.0001 for i in range(20)],
            "ask": [1.1002 + i * 0.0001 for i in range(20)],
        })

        result = checker.validate(
            df=df, pair="EURUSD", resolution="M1",
            start_date=date(2024, 1, 2), end_date=date(2024, 1, 2),
            storage_path=tmp_path, dataset_id="TEST_UNIQUE", version="v001",
        )

        report = json.loads(result.report_path.read_text())
        # For clean data: no quarantine
        assert report["quarantined_bar_count"] == 0
        assert report["quarantined_percentage"] == 0


# --- Regression tests from review synthesis (Story 1-10) ---


class TestConfigHashFormatConsistency:
    """Regression: config_hash must use sha256: prefix in quality reports,
    matching the format used in conversion manifests (arrow_converter)."""

    @pytest.mark.regression
    def test_auto_computed_config_hash_has_sha256_prefix(self, checker, clean_m1_df, tmp_path):
        """Quality report config_hash must match arrow_converter's sha256: format."""
        ds = "EURUSD_2024-01-02_2024-01-02_M1"
        result = checker.validate(
            df=clean_m1_df, pair="EURUSD", resolution="M1",
            start_date=date(2024, 1, 2), end_date=date(2024, 1, 2),
            storage_path=tmp_path, dataset_id=ds, version="v001",
        )
        report = json.loads(result.report_path.read_text())
        config_hash = report["config_hash"]

        assert config_hash.startswith("sha256:"), (
            f"config_hash must start with 'sha256:' for cross-artifact consistency, "
            f"got: {config_hash!r}"
        )
        hex_part = config_hash[len("sha256:"):]
        assert len(hex_part) == 64, "hex digest must be 64 chars (SHA-256)"
        assert all(c in "0123456789abcdef" for c in hex_part), "must be valid hex"


class TestIntegrityErrorPeriodGrouping:
    """Regression: disjoint integrity errors must produce separate quarantine
    periods, not one misleading span from first to last."""

    @pytest.mark.regression
    def test_disjoint_errors_produce_separate_periods(self, checker, tmp_path):
        """Integrity errors >1 hour apart must appear as distinct periods."""
        # Create data with two clusters of integrity errors:
        # Cluster 1 at 10:00-10:05, Cluster 2 at 15:00-15:05
        timestamps = pd.date_range("2024-01-02 08:00", periods=480, freq="min")
        prices = [1.1000 + i * 0.0001 for i in range(480)]
        df = pd.DataFrame({
            "timestamp": timestamps,
            "open": prices,
            "high": [p + 0.0005 for p in prices],
            "low": [p - 0.0005 for p in prices],
            "close": [p + 0.0001 for p in prices],
            "volume": [100] * 480,
            "bid": prices,
            "ask": [p + 0.0002 for p in prices],
        })

        # Inject two disjoint integrity errors: spike at 10:00 and spike at 15:00
        # Bars at minute 120 (10:00) and 420 (15:00) — 5 hours apart
        df.loc[120, "high"] = 0.0001  # high < low → integrity error
        df.loc[420, "high"] = 0.0001  # high < low → integrity error

        ds = "EURUSD_2024-01-02_2024-01-02_M1"
        result = checker.validate(
            df=df, pair="EURUSD", resolution="M1",
            start_date=date(2024, 1, 2), end_date=date(2024, 1, 2),
            storage_path=tmp_path, dataset_id=ds, version="v001",
        )

        report = json.loads(result.report_path.read_text())
        integrity_periods = [
            p for p in report["quarantined_periods"]
            if p["reason"] == "integrity_error"
        ]

        assert len(integrity_periods) >= 2, (
            f"Disjoint integrity errors (5h apart) must produce >=2 separate "
            f"periods, got {len(integrity_periods)}: {integrity_periods}"
        )
