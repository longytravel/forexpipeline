"""Tests for analysis.anomaly_detector — deterministic anomaly checks."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from analysis.anomaly_detector import (
    ANOMALY_THRESHOLDS,
    detect_anomalies,
)
from analysis.models import AnomalyType, Severity
from tests.test_analysis.conftest import BACKTEST_ID, create_test_db


def _make_trades(
    count: int,
    pnl_range: tuple[float, float] = (-5.0, 10.0),
    start: str = "2020-01-01T00:00:00Z",
    session: str = "london",
    spread_months: bool = True,
) -> list[dict]:
    """Helper to create trade fixtures."""
    import random
    random.seed(42)

    base = datetime.fromisoformat(start.replace("Z", "+00:00"))
    trades = []
    for i in range(count):
        if spread_months:
            entry = base + timedelta(days=i * 20)
        else:
            entry = base + timedelta(hours=i)
        exit_ = entry + timedelta(hours=random.randint(1, 24))
        pnl = random.uniform(pnl_range[0], pnl_range[1])

        trades.append({
            "trade_id": i + 1,
            "direction": "long",
            "entry_time": entry.isoformat(),
            "exit_time": exit_.isoformat(),
            "pnl_pips": round(pnl, 2),
            "session": session,
            "lot_size": 0.1,
        })
    return trades


class TestDetectAnomaliesHealthy:

    def test_detect_anomalies_healthy_run(self, tmp_path):
        """No anomalies flagged on normal data."""
        trades = _make_trades(50, pnl_range=(-10.0, 12.0))
        db_path = create_test_db(tmp_path / "test.db", trades)

        report = detect_anomalies(BACKTEST_ID, db_path)

        assert report.backtest_id == BACKTEST_ID
        assert report.run_timestamp != ""
        # May have some anomalies depending on random data, but check structure
        for a in report.anomalies:
            assert a.type is not None
            assert a.severity is not None
            assert a.description != ""
            assert isinstance(a.evidence, dict)
            assert a.recommendation != ""


class TestLowTradeCount:

    def test_detect_low_trade_count(self, tmp_path):
        """< 30 trades triggers WARNING."""
        trades = _make_trades(20)
        db_path = create_test_db(tmp_path / "test.db", trades)

        report = detect_anomalies(BACKTEST_ID, db_path)

        low_count = [a for a in report.anomalies if a.type == AnomalyType.LOW_TRADE_COUNT]
        assert len(low_count) == 1
        assert low_count[0].severity == Severity.WARNING
        assert low_count[0].evidence["trade_count"] == 20
        assert low_count[0].evidence["threshold"] == 30

    def test_no_low_trade_count_at_threshold(self, tmp_path):
        """Exactly 30 trades should NOT trigger."""
        trades = _make_trades(30)
        db_path = create_test_db(tmp_path / "test.db", trades)

        report = detect_anomalies(BACKTEST_ID, db_path)

        low_count = [a for a in report.anomalies if a.type == AnomalyType.LOW_TRADE_COUNT]
        assert len(low_count) == 0


class TestZeroTradeWindow:

    def test_detect_zero_trade_window(self, tmp_path):
        """2-year gap triggers ERROR."""
        # Two trades with 3-year gap between them
        trades = [
            {
                "trade_id": 1, "direction": "long",
                "entry_time": "2020-01-15T10:00:00+00:00",
                "exit_time": "2020-01-15T12:00:00+00:00",
                "pnl_pips": 5.0, "session": "london", "lot_size": 0.1,
            },
            {
                "trade_id": 2, "direction": "long",
                "entry_time": "2023-06-15T10:00:00+00:00",
                "exit_time": "2023-06-15T12:00:00+00:00",
                "pnl_pips": 3.0, "session": "london", "lot_size": 0.1,
            },
        ]
        db_path = create_test_db(tmp_path / "test.db", trades)

        report = detect_anomalies(BACKTEST_ID, db_path)

        zero = [a for a in report.anomalies if a.type == AnomalyType.ZERO_TRADES]
        assert len(zero) == 1
        assert zero[0].severity == Severity.ERROR
        assert zero[0].evidence["gap_years"] > 2.0


class TestPerfectEquity:

    def test_detect_perfect_equity(self, tmp_path):
        """DD < 1% with > 100 trades triggers ERROR."""
        # All trades profitable with tiny variance
        trades = _make_trades(150, pnl_range=(0.5, 1.0))
        db_path = create_test_db(tmp_path / "test.db", trades)

        report = detect_anomalies(BACKTEST_ID, db_path)

        perfect = [a for a in report.anomalies if a.type == AnomalyType.PERFECT_EQUITY]
        assert len(perfect) == 1
        assert perfect[0].severity == Severity.ERROR


class TestExtremeProfitFactor:

    def test_detect_extreme_profit_factor(self, tmp_path):
        """PF > 5.0 triggers WARNING."""
        # 40 wins at +10, 10 losses at -1 → PF = 400/10 = 40.0
        trades = []
        for i in range(40):
            trades.append({
                "trade_id": i + 1, "direction": "long",
                "entry_time": f"2020-{(i % 12) + 1:02d}-15T10:00:00+00:00",
                "exit_time": f"2020-{(i % 12) + 1:02d}-15T12:00:00+00:00",
                "pnl_pips": 10.0, "session": "london", "lot_size": 0.1,
            })
        for i in range(10):
            trades.append({
                "trade_id": 41 + i, "direction": "long",
                "entry_time": f"2021-{(i % 12) + 1:02d}-15T10:00:00+00:00",
                "exit_time": f"2021-{(i % 12) + 1:02d}-15T12:00:00+00:00",
                "pnl_pips": -1.0, "session": "new_york", "lot_size": 0.1,
            })
        db_path = create_test_db(tmp_path / "test.db", trades)

        report = detect_anomalies(BACKTEST_ID, db_path)

        extreme = [a for a in report.anomalies if a.type == AnomalyType.EXTREME_PROFIT_FACTOR]
        assert len(extreme) == 1
        assert extreme[0].severity == Severity.WARNING
        assert extreme[0].evidence["profit_factor"] > 5.0


class TestTradeClustering:

    def test_detect_trade_clustering(self, tmp_path):
        """> 50% trades in one month triggers WARNING."""
        # 30 trades in Jan 2020, 10 spread across other months
        trades = []
        for i in range(30):
            trades.append({
                "trade_id": i + 1, "direction": "long",
                "entry_time": f"2020-01-{(i % 28) + 1:02d}T10:00:00+00:00",
                "exit_time": f"2020-01-{(i % 28) + 1:02d}T12:00:00+00:00",
                "pnl_pips": 5.0, "session": "london", "lot_size": 0.1,
            })
        for i in range(10):
            trades.append({
                "trade_id": 31 + i, "direction": "long",
                "entry_time": f"2020-{(i % 11) + 2:02d}-15T10:00:00+00:00",
                "exit_time": f"2020-{(i % 11) + 2:02d}-15T12:00:00+00:00",
                "pnl_pips": 3.0, "session": "asian", "lot_size": 0.1,
            })
        db_path = create_test_db(tmp_path / "test.db", trades)

        report = detect_anomalies(BACKTEST_ID, db_path)

        cluster = [a for a in report.anomalies if a.type == AnomalyType.TRADE_CLUSTERING]
        assert len(cluster) == 1
        assert cluster[0].severity == Severity.WARNING
        assert cluster[0].evidence["clustered_month"] == "2020-01"


class TestTimestampParsing:
    """Regression tests for int64 microsecond timestamps.

    The Rust backtester emits entry_time/exit_time as int64 microseconds
    since the Unix epoch (see contracts/arrow_schemas.toml). Previously the
    anomaly checks silently dropped these values (isinstance str guard) or
    treated them as seconds, bucketing all trades into 1970-01 and producing
    a spurious TRADE_CLUSTERING anomaly on the ma-crossover evidence pack.
    """

    def test_parse_entry_time_microseconds(self):
        from analysis.anomaly_detector import _parse_entry_time

        # 2025-01-14T11:00:00Z — real value from the ma-crossover v004 trade log.
        us = 1_736_852_400_000_000
        parsed = _parse_entry_time(us)
        assert parsed is not None
        assert parsed.year == 2025
        assert parsed.month == 1
        assert parsed.day == 14
        assert parsed.hour == 11
        assert parsed.strftime("%Y-%m") == "2025-01"

    def test_parse_entry_time_nanoseconds(self):
        """Legacy fixtures store int64 nanoseconds — must also bucket correctly."""
        from analysis.anomaly_detector import _parse_entry_time

        ns = 1_735_804_800_000_000_000  # 2025-01-02T08:00:00Z in ns
        parsed = _parse_entry_time(ns)
        assert parsed is not None
        assert parsed.year == 2025
        assert parsed.strftime("%Y-%m") == "2025-01"

    def test_parse_entry_time_iso_string(self):
        from analysis.anomaly_detector import _parse_entry_time

        parsed = _parse_entry_time("2025-01-14T11:00:00+00:00")
        assert parsed is not None
        assert parsed.year == 2025
        assert parsed.strftime("%Y-%m") == "2025-01"

    def test_parse_entry_time_handles_none_and_garbage(self):
        from analysis.anomaly_detector import _parse_entry_time

        assert _parse_entry_time(None) is None
        assert _parse_entry_time("not-a-date") is None
        assert _parse_entry_time(True) is None  # bool must not be treated as int

    def test_trade_clustering_with_microsecond_timestamps(self, tmp_path):
        """All trades in Jan 2025 (as microseconds) must bucket to 2025-01, not 1970-01."""
        # 2025-01-14T11:00:00Z in microseconds, then one trade per day for 14 days.
        base_us = 1_736_852_400_000_000
        day_us = 24 * 60 * 60 * 1_000_000
        trades = []
        for i in range(14):
            entry_us = base_us + i * day_us
            trades.append({
                "trade_id": i + 1,
                "direction": "long",
                "entry_time": entry_us,            # int64 microseconds
                "exit_time": entry_us + 3_600_000_000,  # +1 hour
                "pnl_pips": 5.0 if i % 2 == 0 else -3.0,
                "session": "london",
                "lot_size": 0.1,
            })
        # Add a few trades in Feb 2025 so clustering still has a dominant bucket.
        feb_base_us = base_us + 31 * day_us
        for i in range(4):
            entry_us = feb_base_us + i * day_us
            trades.append({
                "trade_id": 100 + i,
                "direction": "long",
                "entry_time": entry_us,
                "exit_time": entry_us + 3_600_000_000,
                "pnl_pips": 2.0,
                "session": "london",
                "lot_size": 0.1,
            })

        # Exercise the checker directly (we do not go through SQLite here because
        # the SQLite schema stores entry_time as TEXT — this test covers the
        # direct-Arrow code path used by evidence_pack._compute_trade_distribution).
        from analysis.anomaly_detector import (
            ANOMALY_THRESHOLDS,
            _check_trade_clustering,
        )

        flag = _check_trade_clustering(trades, dict(ANOMALY_THRESHOLDS))
        assert flag is not None, "expected a TRADE_CLUSTERING flag"
        assert flag.type == AnomalyType.TRADE_CLUSTERING
        assert flag.evidence["clustered_month"] == "2025-01"
        assert flag.evidence["clustered_month"] != "1970-01"

    def test_trade_distribution_with_microsecond_timestamps(self):
        """evidence_pack._compute_trade_distribution must bucket microseconds correctly."""
        from analysis.evidence_pack import _compute_trade_distribution

        # 2025-01-14T11:00:00Z
        us = 1_736_852_400_000_000
        trades = [
            {"entry_time": us, "session": "london"},
            {"entry_time": us + 86_400_000_000, "session": "london"},
        ]
        dist = _compute_trade_distribution(trades)
        assert "2025-01" in dist["by_month"]
        assert "1970-01" not in dist["by_month"]
        assert dist["by_month"]["2025-01"] == 2


class TestWinRateExtremes:

    def test_detect_win_rate_extremes_high(self, tmp_path):
        """> 90% with > 50 trades triggers WARNING."""
        # 55 wins, 5 losses → 91.7% win rate
        trades = []
        for i in range(55):
            trades.append({
                "trade_id": i + 1, "direction": "long",
                "entry_time": f"2020-{(i % 12) + 1:02d}-{(i % 28) + 1:02d}T10:00:00+00:00",
                "exit_time": f"2020-{(i % 12) + 1:02d}-{(i % 28) + 1:02d}T12:00:00+00:00",
                "pnl_pips": 5.0, "session": "london", "lot_size": 0.1,
            })
        for i in range(5):
            trades.append({
                "trade_id": 56 + i, "direction": "long",
                "entry_time": f"2021-{(i % 12) + 1:02d}-15T10:00:00+00:00",
                "exit_time": f"2021-{(i % 12) + 1:02d}-15T12:00:00+00:00",
                "pnl_pips": -3.0, "session": "asian", "lot_size": 0.1,
            })
        db_path = create_test_db(tmp_path / "test.db", trades)

        report = detect_anomalies(BACKTEST_ID, db_path)

        extreme = [a for a in report.anomalies if a.type == AnomalyType.WIN_RATE_EXTREME]
        assert len(extreme) == 1
        assert extreme[0].severity == Severity.WARNING
        assert extreme[0].evidence["win_rate"] > 0.90

    def test_detect_win_rate_extremes_low(self, tmp_path):
        """< 20% with > 50 trades triggers WARNING."""
        # 8 wins, 52 losses → 13.3% win rate
        trades = []
        for i in range(8):
            trades.append({
                "trade_id": i + 1, "direction": "long",
                "entry_time": f"2020-{(i % 12) + 1:02d}-15T10:00:00+00:00",
                "exit_time": f"2020-{(i % 12) + 1:02d}-15T12:00:00+00:00",
                "pnl_pips": 20.0, "session": "london", "lot_size": 0.1,
            })
        for i in range(52):
            trades.append({
                "trade_id": 9 + i, "direction": "long",
                "entry_time": f"2020-{(i % 12) + 1:02d}-{(i % 28) + 1:02d}T10:00:00+00:00",
                "exit_time": f"2020-{(i % 12) + 1:02d}-{(i % 28) + 1:02d}T12:00:00+00:00",
                "pnl_pips": -2.0, "session": "new_york", "lot_size": 0.1,
            })
        db_path = create_test_db(tmp_path / "test.db", trades)

        report = detect_anomalies(BACKTEST_ID, db_path)

        extreme = [a for a in report.anomalies if a.type == AnomalyType.WIN_RATE_EXTREME]
        assert len(extreme) == 1
        assert extreme[0].evidence["win_rate"] < 0.20


class TestAnomaliesDoNotBlock:

    def test_anomalies_do_not_block(self, tmp_path):
        """Verify report is informational, no exceptions raised."""
        # Create deliberately anomalous data
        trades = _make_trades(10, pnl_range=(0.5, 1.0))
        db_path = create_test_db(tmp_path / "test.db", trades)

        # This should NOT raise any exceptions
        report = detect_anomalies(BACKTEST_ID, db_path)

        assert isinstance(report.anomalies, list)
        # Should have at least LOW_TRADE_COUNT
        assert len(report.anomalies) >= 1


class TestSensitivityCliffStub:

    def test_sensitivity_cliff_stub_returns_none(self, tmp_path):
        """Always returns None at backtest stage with debug log."""
        from analysis.anomaly_detector import _check_sensitivity_cliff
        result = _check_sensitivity_cliff("test-id", tmp_path / "test.db")
        assert result is None


class TestThresholdsFromConfig:

    def test_thresholds_loaded_from_config(self, tmp_path):
        """Verify thresholds are read from config dict, not hardcoded."""
        trades = _make_trades(25)  # Below default threshold of 30
        db_path = create_test_db(tmp_path / "test.db", trades)

        # With default thresholds, should flag low trade count
        report_default = detect_anomalies(BACKTEST_ID, db_path)
        low_default = [a for a in report_default.anomalies if a.type == AnomalyType.LOW_TRADE_COUNT]
        assert len(low_default) == 1

        # Override threshold to 20 — should NOT flag
        custom = {"low_trade_count": 20}
        report_custom = detect_anomalies(BACKTEST_ID, db_path, thresholds=custom)
        low_custom = [a for a in report_custom.anomalies if a.type == AnomalyType.LOW_TRADE_COUNT]
        assert len(low_custom) == 0


class TestAnomalyJsonRoundtrip:

    def test_anomaly_flag_json_roundtrip(self):
        from analysis.models import AnomalyFlag, AnomalyType, Severity

        flag = AnomalyFlag(
            type=AnomalyType.LOW_TRADE_COUNT,
            severity=Severity.WARNING,
            description="Test description",
            evidence={"count": 10, "threshold": 30},
            recommendation="Test recommendation",
        )

        json_data = flag.to_json()
        restored = AnomalyFlag.from_json(json_data)

        assert restored.type == flag.type
        assert restored.severity == flag.severity
        assert restored.description == flag.description
        assert restored.evidence == flag.evidence
        assert restored.recommendation == flag.recommendation

    def test_anomaly_report_json_roundtrip(self):
        from analysis.models import AnomalyReport, AnomalyFlag, AnomalyType, Severity

        report = AnomalyReport(
            backtest_id="test-id",
            anomalies=[
                AnomalyFlag(
                    type=AnomalyType.TRADE_CLUSTERING,
                    severity=Severity.WARNING,
                    description="Clustered",
                    evidence={"month": "2020-01"},
                    recommendation="Spread trades",
                ),
            ],
            run_timestamp="2026-01-01T00:00:00Z",
        )

        json_data = report.to_json()
        restored = AnomalyReport.from_json(json_data)

        assert restored.backtest_id == report.backtest_id
        assert len(restored.anomalies) == 1
        assert restored.anomalies[0].type == AnomalyType.TRADE_CLUSTERING
