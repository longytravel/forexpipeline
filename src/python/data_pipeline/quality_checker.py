"""Data quality validation and scoring (Story 1.5).

Validates ingested market data for integrity and assigns a quality score
using the Architecture-specified formula:
  quality_score = 1.0 - (gap_penalty + integrity_penalty + staleness_penalty)

Adapted gap/anomaly detection from ClaudeBackTester baseline.
Quality scoring built new per Architecture spec (not ported).
"""
import json
import logging
import os
from collections import namedtuple
from datetime import date, datetime, time, timezone
from pathlib import Path
from typing import List, Optional, Tuple

import pandas as pd

from config_loader.hasher import compute_config_hash
from data_pipeline.utils.safe_write import crash_safe_write, safe_write_csv
from data_pipeline.session_labeler import assign_sessions_bulk

# ---------------------------------------------------------------------------
# Named tuples for structured results
# ---------------------------------------------------------------------------

GapRecord = namedtuple("GapRecord", ["start", "end", "duration_minutes", "is_weekend"])
IntegrityIssue = namedtuple("IntegrityIssue", ["timestamp", "issue_type", "detail", "severity"])
StaleRecord = namedtuple("StaleRecord", ["start", "end", "duration_bars", "stale_type"])
CompletenessIssue = namedtuple("CompletenessIssue", ["date", "issue_type", "detail"])
ValidationResult = namedtuple(
    "ValidationResult",
    ["quality_score", "rating", "report_path", "validated_df", "can_proceed"],
)


class DataQualityChecker:
    """Validates market data and computes quality scores.

    Checks: gap detection, price integrity, spread outliers, timezone
    alignment, stale quote detection, completeness. Produces a quality
    report artifact and marks quarantined periods.
    """

    def __init__(self, config: dict, logger: logging.Logger) -> None:
        quality_cfg = config.get("data", {}).get("quality", {})
        self._gap_threshold_bars = quality_cfg.get("gap_threshold_bars", 5)
        self._gap_warning_per_year = quality_cfg.get("gap_warning_per_year", 10)
        self._gap_error_per_year = quality_cfg.get("gap_error_per_year", 50)
        self._gap_error_minutes = quality_cfg.get("gap_error_minutes", 30)
        self._spread_multiplier = quality_cfg.get("spread_multiplier_threshold", 10.0)
        self._stale_consecutive = quality_cfg.get("stale_consecutive_bars", 5)
        self._green_threshold = quality_cfg.get("score_green_threshold", 0.95)
        self._yellow_threshold = quality_cfg.get("score_yellow_threshold", 0.80)

        self._config = config
        self._session_schedule = config.get("sessions", {})
        self._logger = logger

    # ------------------------------------------------------------------
    # Task 1: Gap detection
    # ------------------------------------------------------------------

    def _detect_gaps(
        self, df: pd.DataFrame, resolution: str
    ) -> List[GapRecord]:
        """Detect gaps in timestamp sequence.

        For M1: flag sequences of > gap_threshold_bars consecutive missing bars.
        For tick: flag gaps > 5 minutes with no ticks.
        Excludes weekend gaps (Friday 22:00 to Sunday 22:00 UTC).
        """
        if len(df) < 2:
            return []

        timestamps = pd.to_datetime(df["timestamp"], format="ISO8601")
        diffs = timestamps.diff()

        if resolution == "tick":
            expected_max = pd.Timedelta(minutes=5)
        else:
            # M1: expected interval is 1 minute, flag if > threshold bars
            expected_max = pd.Timedelta(minutes=self._gap_threshold_bars)

        gaps: List[GapRecord] = []
        gap_mask = diffs > expected_max
        gap_indices = gap_mask[gap_mask].index

        for idx in gap_indices:
            gap_start = timestamps.iloc[idx - 1]
            gap_end = timestamps.iloc[idx]
            duration = (gap_end - gap_start).total_seconds() / 60.0
            is_weekend = self._is_weekend_gap(gap_start, gap_end)
            gaps.append(GapRecord(
                start=gap_start,
                end=gap_end,
                duration_minutes=duration,
                is_weekend=is_weekend,
            ))

        self._logger.info(
            "Gap detection complete: %d total gaps, %d non-weekend",
            len(gaps),
            sum(1 for g in gaps if not g.is_weekend),
            extra={"ctx": {
                "component": "quality_checker",
                "stage": "data_pipeline",
                "total_gaps": len(gaps),
                "non_weekend_gaps": sum(1 for g in gaps if not g.is_weekend),
            }},
        )
        return gaps

    @staticmethod
    def _is_weekend_gap(start: pd.Timestamp, end: pd.Timestamp) -> bool:
        """Check if gap spans a forex weekend (Fri 22:00 to Sun 22:00 UTC).

        Ported from ClaudeBackTester — well-tested windowing logic.
        """
        start_weekday = start.weekday()  # 0=Mon, 4=Fri, 6=Sun

        # Gap starts on Friday at or after 20:00 UTC
        if start_weekday == 4 and start.hour >= 20:
            # Gap ends on Sunday at or after 21:00, or Monday before 01:00
            end_weekday = end.weekday()
            if (end_weekday == 6 and end.hour >= 21) or end_weekday == 0:
                return True

        return False

    def _classify_gap_severity(
        self, gaps: List[GapRecord], total_years: float
    ) -> str:
        """Classify overall gap severity.

        ok: gaps/year <= gap_warning_per_year and no single gap > gap_error_minutes.
        WARNING: gap_warning_per_year < gaps/year <= gap_error_per_year.
        ERROR: gaps/year > gap_error_per_year OR any gap > gap_error_minutes.
        """
        non_weekend = [g for g in gaps if not g.is_weekend]

        if not non_weekend:
            return "ok"

        if total_years <= 0:
            total_years = 1.0

        gaps_per_year = len(non_weekend) / total_years

        # Check for any single gap exceeding the error threshold
        max_gap = max(g.duration_minutes for g in non_weekend)
        if max_gap > self._gap_error_minutes:
            return "error"

        if gaps_per_year > self._gap_error_per_year:
            return "error"

        if gaps_per_year > self._gap_warning_per_year:
            return "warning"

        return "ok"

    # ------------------------------------------------------------------
    # Task 2: Price integrity checks
    # ------------------------------------------------------------------

    def _check_price_integrity(
        self, df: pd.DataFrame, session_schedule: dict
    ) -> List[IntegrityIssue]:
        """Check price integrity: bid > 0, ask > bid, OHLC consistency.

        Vectorized operations for performance with 5M+ rows.
        """
        issues: List[IntegrityIssue] = []
        has_ohlc = all(c in df.columns for c in ("open", "high", "low", "close"))

        # bid > 0
        if "bid" in df.columns:
            bad_bid = df[df["bid"] <= 0]
            for idx in bad_bid.index:
                issues.append(IntegrityIssue(
                    timestamp=df.at[idx, "timestamp"],
                    issue_type="non_positive_bid",
                    detail=f"bid={df.at[idx, 'bid']}",
                    severity="error",
                ))

        # ask > bid
        if "bid" in df.columns and "ask" in df.columns:
            valid = df["bid"].notna() & df["ask"].notna()
            inverted = df[valid & (df["ask"] <= df["bid"])]
            for idx in inverted.index:
                issues.append(IntegrityIssue(
                    timestamp=df.at[idx, "timestamp"],
                    issue_type="inverted_spread",
                    detail=f"bid={df.at[idx, 'bid']}, ask={df.at[idx, 'ask']}",
                    severity="error",
                ))

        # OHLC checks for M1 data
        if has_ohlc:
            # Positive prices
            for col in ("open", "high", "low", "close"):
                bad = df[df[col] <= 0]
                for idx in bad.index:
                    issues.append(IntegrityIssue(
                        timestamp=df.at[idx, "timestamp"],
                        issue_type=f"non_positive_{col}",
                        detail=f"{col}={df.at[idx, col]}",
                        severity="error",
                    ))

            # high >= low
            bad_hl = df[df["high"] < df["low"]]
            for idx in bad_hl.index:
                issues.append(IntegrityIssue(
                    timestamp=df.at[idx, "timestamp"],
                    issue_type="high_lt_low",
                    detail=f"high={df.at[idx, 'high']}, low={df.at[idx, 'low']}",
                    severity="error",
                ))

            # high >= open and high >= close
            bad_ho = df[df["high"] < df["open"]]
            for idx in bad_ho.index:
                issues.append(IntegrityIssue(
                    timestamp=df.at[idx, "timestamp"],
                    issue_type="high_lt_open",
                    detail=f"high={df.at[idx, 'high']}, open={df.at[idx, 'open']}",
                    severity="error",
                ))
            bad_hc = df[df["high"] < df["close"]]
            for idx in bad_hc.index:
                issues.append(IntegrityIssue(
                    timestamp=df.at[idx, "timestamp"],
                    issue_type="high_lt_close",
                    detail=f"high={df.at[idx, 'high']}, close={df.at[idx, 'close']}",
                    severity="error",
                ))

            # low <= open and low <= close
            bad_lo = df[df["low"] > df["open"]]
            for idx in bad_lo.index:
                issues.append(IntegrityIssue(
                    timestamp=df.at[idx, "timestamp"],
                    issue_type="low_gt_open",
                    detail=f"low={df.at[idx, 'low']}, open={df.at[idx, 'open']}",
                    severity="error",
                ))
            bad_lc = df[df["low"] > df["close"]]
            for idx in bad_lc.index:
                issues.append(IntegrityIssue(
                    timestamp=df.at[idx, "timestamp"],
                    issue_type="low_gt_close",
                    detail=f"low={df.at[idx, 'low']}, close={df.at[idx, 'close']}",
                    severity="error",
                ))

        self._logger.info(
            "Price integrity check complete: %d issues found",
            len(issues),
            extra={"ctx": {
                "component": "quality_checker",
                "stage": "data_pipeline",
                "issue_count": len(issues),
            }},
        )
        return issues

    def _check_spread_outliers(
        self, df: pd.DataFrame, session_schedule: dict
    ) -> List[IntegrityIssue]:
        """Flag spreads exceeding 10x median for each session.

        Vectorized: compute session labels, group by session, compare to median.
        """
        issues: List[IntegrityIssue] = []

        if "bid" not in df.columns or "ask" not in df.columns:
            return issues

        valid = df["bid"].notna() & df["ask"].notna()
        if not valid.any():
            return issues

        spread = df["ask"] - df["bid"]

        # Assign sessions
        sessions = assign_sessions_bulk(df, session_schedule)

        # Compute median spread per session
        spread_with_session = pd.DataFrame({
            "spread": spread,
            "session": sessions,
        }, index=df.index)

        # Only consider valid rows
        spread_with_session = spread_with_session[valid]
        median_by_session = spread_with_session.groupby("session")["spread"].median()

        # Flag outliers
        for session_name, median_val in median_by_session.items():
            if median_val <= 0:
                continue
            threshold = median_val * self._spread_multiplier
            session_mask = (sessions == session_name) & valid
            outlier_mask = session_mask & (spread > threshold)
            outlier_indices = outlier_mask[outlier_mask].index

            for idx in outlier_indices:
                issues.append(IntegrityIssue(
                    timestamp=df.at[idx, "timestamp"],
                    issue_type="spread_outlier",
                    detail=f"spread={spread[idx]:.6f}, median={median_val:.6f}, session={session_name}",
                    severity="error",
                ))

        self._logger.info(
            "Spread outlier check complete: %d outliers found",
            len(issues),
            extra={"ctx": {
                "component": "quality_checker",
                "stage": "data_pipeline",
                "outlier_count": len(issues),
            }},
        )
        return issues

    # ------------------------------------------------------------------
    # Task 3: Timezone alignment verification
    # ------------------------------------------------------------------

    def _verify_timezone_alignment(
        self, df: pd.DataFrame
    ) -> List[IntegrityIssue]:
        """Verify timestamps are UTC, monotonically increasing, no DST artifacts."""
        issues: List[IntegrityIssue] = []
        timestamps = pd.to_datetime(df["timestamp"], format="ISO8601")

        # Check for non-UTC timezone info
        if hasattr(timestamps.dt, "tz") and timestamps.dt.tz is not None:
            tz_str = str(timestamps.dt.tz)
            if tz_str not in ("UTC", "utc", "timezone.utc"):
                issues.append(IntegrityIssue(
                    timestamp=timestamps.iloc[0],
                    issue_type="non_utc_timezone",
                    detail=f"timezone={tz_str}",
                    severity="error",
                ))

        # Monotonically increasing
        diffs = timestamps.diff().dropna()
        non_monotonic = diffs[diffs <= pd.Timedelta(0)]
        for idx in non_monotonic.index:
            issues.append(IntegrityIssue(
                timestamp=df.at[idx, "timestamp"],
                issue_type="non_monotonic_timestamp",
                detail=f"diff={diffs[idx]}, prev={timestamps.iloc[idx - 1]}",
                severity="error",
            ))

        # No future dates
        now = pd.Timestamp.now(tz="UTC")
        # Make timestamps comparable
        ts_compare = timestamps
        if ts_compare.dt.tz is None:
            ts_compare = ts_compare.dt.tz_localize("UTC")
        future = ts_compare[ts_compare > now]
        if not future.empty:
            issues.append(IntegrityIssue(
                timestamp=future.iloc[0],
                issue_type="future_timestamp",
                detail=f"found {len(future)} future timestamps, first={future.iloc[0]}",
                severity="error",
            ))

        # DST artifact detection — look for suspicious 1-hour jumps near DST dates
        # US DST: second Sunday of March, first Sunday of November
        # EU DST: last Sunday of March/October
        if len(timestamps) > 1:
            hour_diffs = diffs[diffs == pd.Timedelta(hours=1)]
            for idx in hour_diffs.index:
                ts = timestamps.iloc[idx]
                month = ts.month
                day = ts.day
                # March or November (US DST), October (EU DST)
                if month in (3, 10, 11) and 7 <= day <= 31:
                    issues.append(IntegrityIssue(
                        timestamp=df.at[idx, "timestamp"],
                        issue_type="possible_dst_artifact",
                        detail=f"1-hour jump at {ts} near DST transition",
                        severity="warning",
                    ))

        self._logger.info(
            "Timezone alignment check complete: %d issues found",
            len(issues),
            extra={"ctx": {
                "component": "quality_checker",
                "stage": "data_pipeline",
                "issue_count": len(issues),
            }},
        )
        return issues

    # ------------------------------------------------------------------
    # Task 4: Stale quote detection
    # ------------------------------------------------------------------

    def _detect_stale_quotes(
        self, df: pd.DataFrame
    ) -> List[StaleRecord]:
        """Detect periods of stale quotes.

        Flags:
        - bid == ask (zero spread) for > stale_consecutive bars
        - All OHLC prices identical for > stale_consecutive bars (frozen price)
        """
        stale: List[StaleRecord] = []
        timestamps = pd.to_datetime(df["timestamp"], format="ISO8601")

        # Zero spread detection
        if "bid" in df.columns and "ask" in df.columns:
            valid = df["bid"].notna() & df["ask"].notna()
            zero_spread = valid & (df["bid"] == df["ask"])
            stale.extend(self._find_consecutive_runs(
                zero_spread, timestamps, "zero_spread",
            ))

        # Frozen price detection (M1 OHLC data)
        if all(c in df.columns for c in ("open", "high", "low", "close")):
            frozen = (
                (df["open"] == df["high"])
                & (df["high"] == df["low"])
                & (df["low"] == df["close"])
            )
            stale.extend(self._find_consecutive_runs(
                frozen, timestamps, "frozen_price",
            ))

        self._logger.info(
            "Stale quote detection complete: %d stale periods found",
            len(stale),
            extra={"ctx": {
                "component": "quality_checker",
                "stage": "data_pipeline",
                "stale_count": len(stale),
            }},
        )
        return stale

    def _find_consecutive_runs(
        self,
        mask: pd.Series,
        timestamps: pd.Series,
        stale_type: str,
    ) -> List[StaleRecord]:
        """Find consecutive runs of True values exceeding threshold."""
        records: List[StaleRecord] = []
        if not mask.any():
            return records

        # Group consecutive True values
        groups = (mask != mask.shift()).cumsum()
        for _, group_df in mask[mask].groupby(groups[mask]):
            if len(group_df) > self._stale_consecutive:
                start_idx = group_df.index[0]
                end_idx = group_df.index[-1]
                records.append(StaleRecord(
                    start=timestamps.iloc[start_idx] if start_idx < len(timestamps) else timestamps.loc[start_idx],
                    end=timestamps.iloc[end_idx] if end_idx < len(timestamps) else timestamps.loc[end_idx],
                    duration_bars=len(group_df),
                    stale_type=stale_type,
                ))
        return records

    # ------------------------------------------------------------------
    # Task 5: Completeness checks
    # ------------------------------------------------------------------

    def _check_completeness(
        self,
        df: pd.DataFrame,
        start_date: date,
        end_date: date,
    ) -> List[CompletenessIssue]:
        """Verify no unexpected missing weekday data.

        Generates expected trading days, checks each has data.
        Flags missing weekdays as ERROR, incomplete days (< 50% bars) as WARNING.
        """
        issues: List[CompletenessIssue] = []
        timestamps = pd.to_datetime(df["timestamp"], format="ISO8601")
        data_dates = timestamps.dt.date

        # Generate expected trading days (weekdays, excluding weekends)
        all_days = pd.date_range(start_date, end_date, freq="B")  # Business days

        # For each expected trading day, check if data exists
        bars_per_day = data_dates.value_counts()

        for day in all_days:
            day_date = day.date()
            count = bars_per_day.get(day_date, 0)

            if count == 0:
                # Check if it's in a weekend gap window
                # Friday after 22:00 through Sunday — skip
                weekday = day_date.weekday()
                if weekday in (5, 6):  # Saturday/Sunday
                    continue
                issues.append(CompletenessIssue(
                    date=day_date,
                    issue_type="missing_weekday",
                    detail=f"No data for {day_date} (weekday)",
                ))
            elif count < 720:  # < 50% of 1440 expected M1 bars
                issues.append(CompletenessIssue(
                    date=day_date,
                    issue_type="incomplete_day",
                    detail=f"Only {count} bars on {day_date} (expected ~1440)",
                ))

        self._logger.info(
            "Completeness check complete: %d issues found",
            len(issues),
            extra={"ctx": {
                "component": "quality_checker",
                "stage": "data_pipeline",
                "issue_count": len(issues),
            }},
        )
        return issues

    # ------------------------------------------------------------------
    # Task 6: Quality scoring
    # ------------------------------------------------------------------

    def _compute_quality_score(
        self,
        df: pd.DataFrame,
        gaps: List[GapRecord],
        integrity_issues: List[IntegrityIssue],
        stale_records: List[StaleRecord],
    ) -> Tuple[float, dict]:
        """Compute quality score using Architecture formula.

        quality_score = 1.0 - (gap_penalty + integrity_penalty + staleness_penalty)
        Each penalty is clamped to [0, 1]. Final score floored at 0.
        """
        total_bars = len(df)
        if total_bars == 0:
            return 0.0, {"gap_penalty": 1.0, "integrity_penalty": 1.0, "staleness_penalty": 1.0}

        # Gap penalty
        non_weekend_gaps = [g for g in gaps if not g.is_weekend]
        total_gap_minutes = sum(g.duration_minutes for g in non_weekend_gaps)

        # Estimate total expected trading minutes (exclude weekends)
        timestamps = pd.to_datetime(df["timestamp"], format="ISO8601")
        if len(timestamps) >= 2:
            total_range = (timestamps.max() - timestamps.min()).total_seconds() / 60.0
            # Approximate: remove ~2/7 for weekends
            total_expected_minutes = total_range * (5.0 / 7.0)
        else:
            total_expected_minutes = total_bars  # fallback

        if total_expected_minutes > 0:
            gap_penalty = min(1.0, total_gap_minutes / total_expected_minutes * 10)
        else:
            gap_penalty = 0.0

        # Integrity penalty
        bad_price_bars = len([i for i in integrity_issues if i.severity == "error"])
        integrity_penalty = min(1.0, bad_price_bars / total_bars * 100)

        # Staleness penalty
        stale_bars = sum(s.duration_bars for s in stale_records)
        staleness_penalty = min(1.0, stale_bars / total_bars * 50)

        quality_score = 1.0 - (gap_penalty + integrity_penalty + staleness_penalty)
        quality_score = max(0.0, quality_score)

        penalties = {
            "gap_penalty": round(gap_penalty, 6),
            "integrity_penalty": round(integrity_penalty, 6),
            "staleness_penalty": round(staleness_penalty, 6),
        }

        self._logger.info(
            "Quality score computed: %.4f (gap=%.4f, integrity=%.4f, stale=%.4f)",
            quality_score, gap_penalty, integrity_penalty, staleness_penalty,
            extra={"ctx": {
                "component": "quality_checker",
                "stage": "data_pipeline",
                "quality_score": quality_score,
                **penalties,
            }},
        )
        return quality_score, penalties

    def _classify_score(self, score: float) -> str:
        """Classify quality score into GREEN/YELLOW/RED rating."""
        if score >= self._green_threshold:
            return "GREEN"
        elif score >= self._yellow_threshold:
            return "YELLOW"
        else:
            return "RED"

    # ------------------------------------------------------------------
    # Task 7: Quarantine marking
    # ------------------------------------------------------------------

    def _mark_quarantined(
        self,
        df: pd.DataFrame,
        gaps: List[GapRecord],
        integrity_issues: List[IntegrityIssue],
        stale_records: List[StaleRecord],
    ) -> pd.DataFrame:
        """Add quarantined boolean column. Mark suspect periods True.

        Quarantined bars:
        - Bars adjacent to gap periods (unreliable)
        - Bars with price integrity ERROR issues
        - Bars within stale quote periods
        """
        result = df.copy()
        result["quarantined"] = False
        timestamps = pd.to_datetime(result["timestamp"])

        # Quarantine bars adjacent to gaps (bars right before and after each gap)
        for gap in gaps:
            if gap.is_weekend:
                continue
            mask = (timestamps >= gap.start) & (timestamps <= gap.end)
            result.loc[mask, "quarantined"] = True

        # Quarantine bars with integrity errors
        error_timestamps = set()
        for issue in integrity_issues:
            if issue.severity == "error":
                error_timestamps.add(issue.timestamp)
        if error_timestamps:
            result.loc[timestamps.isin(error_timestamps), "quarantined"] = True

        # Quarantine stale periods
        for stale in stale_records:
            mask = (timestamps >= stale.start) & (timestamps <= stale.end)
            result.loc[mask, "quarantined"] = True

        quarantined_count = result["quarantined"].sum()
        quarantined_pct = quarantined_count / len(result) if len(result) > 0 else 0

        self._logger.info(
            "Quarantine marking complete: %d bars (%.4f%%)",
            quarantined_count, quarantined_pct * 100,
            extra={"ctx": {
                "component": "quality_checker",
                "stage": "data_pipeline",
                "quarantined_count": int(quarantined_count),
                "quarantined_pct": round(quarantined_pct, 6),
            }},
        )
        return result

    # ------------------------------------------------------------------
    # Task 8: Quality report artifact
    # ------------------------------------------------------------------

    def _generate_quality_report(
        self,
        pair: str,
        resolution: str,
        start_date: date,
        end_date: date,
        quality_score: float,
        rating: str,
        penalty_breakdown: dict,
        gaps: List[GapRecord],
        integrity_issues: List[IntegrityIssue],
        timezone_issues: List[IntegrityIssue],
        stale_records: List[StaleRecord],
        completeness_issues: List[CompletenessIssue],
        quarantined_periods: List[dict],
        total_bars: int,
        gap_severity: str = "ok",
        config_hash: str = "",
        unique_quarantined_count: int | None = None,
    ) -> dict:
        """Build structured quality report dict."""
        dataset_id = f"{pair}_{start_date.isoformat()}_{end_date.isoformat()}_{resolution}"

        per_reason_total = sum(p.get("bar_count", 0) for p in quarantined_periods)
        # Use unique count (from boolean column) for percentage to avoid
        # double-counting bars quarantined for multiple reasons.
        quarantined_bar_count = (
            unique_quarantined_count if unique_quarantined_count is not None
            else per_reason_total
        )
        quarantined_pct = quarantined_bar_count / total_bars if total_bars > 0 else 0

        return {
            "dataset_id": dataset_id,
            "pair": pair,
            "resolution": resolution,
            "date_range": {
                "start": start_date.isoformat(),
                "end": end_date.isoformat(),
            },
            "total_bars": total_bars,
            "quality_score": round(quality_score, 6),
            "rating": rating,
            "penalty_breakdown": penalty_breakdown,
            "gap_severity": gap_severity,
            "gaps": [
                {
                    "start": str(g.start),
                    "end": str(g.end),
                    "duration_minutes": round(g.duration_minutes, 2),
                    "is_weekend": g.is_weekend,
                }
                for g in gaps
            ],
            "integrity_issues": [
                {
                    "timestamp": str(i.timestamp),
                    "issue_type": i.issue_type,
                    "detail": i.detail,
                    "severity": i.severity,
                }
                for i in integrity_issues
            ],
            "stale_periods": [
                {
                    "start": str(s.start),
                    "end": str(s.end),
                    "duration_bars": s.duration_bars,
                    "stale_type": s.stale_type,
                }
                for s in stale_records
            ],
            "completeness_issues": [
                {
                    "date": str(c.date),
                    "issue_type": c.issue_type,
                    "detail": c.detail,
                }
                for c in completeness_issues
            ],
            "timezone_issues": [
                {
                    "timestamp": str(i.timestamp),
                    "issue_type": i.issue_type,
                    "detail": i.detail,
                    "severity": i.severity,
                }
                for i in timezone_issues
            ],
            "quarantined_periods": quarantined_periods,
            "quarantined_bar_count": quarantined_bar_count,
            "quarantined_percentage": round(quarantined_pct, 6),
            "validation_timestamp": datetime.now(timezone.utc).isoformat(),
            "config_hash": config_hash,
        }

    def _save_quality_report(
        self, report: dict, storage_path: Path, dataset_id: str, version: str
    ) -> Path:
        """Save quality report JSON using crash-safe write pattern."""
        report_path = storage_path / "raw" / dataset_id / version / "quality-report.json"
        crash_safe_write(report_path, json.dumps(report, indent=2, default=str))

        self._logger.info(
            "Quality report saved: %s",
            str(report_path),
            extra={"ctx": {
                "component": "quality_checker",
                "stage": "data_pipeline",
                "path": str(report_path),
            }},
        )
        return report_path

    def _save_validated_data(
        self, df: pd.DataFrame, storage_path: Path, dataset_id: str, version: str
    ) -> Path:
        """Save validated DataFrame with quarantine column using crash-safe write.

        Uses Parquet for large datasets (>1M rows) to avoid pandas to_csv
        crash on Windows with large DataFrames (C extension segfault).
        """
        validated_dir = storage_path / "validated" / dataset_id / version
        validated_dir.mkdir(parents=True, exist_ok=True)

        if len(df) > 1_000_000:
            # Large dataset: write Parquet (faster, smaller, no C extension crash)
            target = validated_dir / f"{dataset_id}_validated.parquet"
            partial = target.with_name(target.name + ".partial")
            df.to_parquet(str(partial), index=False)
            import os
            with open(partial, "r+b") as f:
                f.flush()
                os.fsync(f.fileno())
            os.replace(str(partial), str(target))
        else:
            # Small dataset: CSV is fine
            target = validated_dir / f"{dataset_id}_validated.csv"
            write_df = df.copy()
            for col in write_df.columns:
                if pd.api.types.is_datetime64_any_dtype(write_df[col]) or hasattr(write_df[col].dtype, "tz"):
                    write_df[col] = write_df[col].astype(str)

            def _write_csv(partial_path: Path) -> None:
                write_df.to_csv(str(partial_path), index=False)

            safe_write_csv(_write_csv, target)

        self._logger.info(
            "Validated data saved: %s",
            str(target),
            extra={"ctx": {
                "component": "quality_checker",
                "stage": "data_pipeline",
                "path": str(target),
            }},
        )
        return target

    # ------------------------------------------------------------------
    # Task 9: Validation orchestration
    # ------------------------------------------------------------------

    def validate(
        self,
        df: pd.DataFrame,
        pair: str,
        resolution: str,
        start_date: date,
        end_date: date,
        storage_path: Path,
        dataset_id: str,
        version: str,
        config_hash: str = "",
    ) -> ValidationResult:
        """Run all validation checks, compute score, save artifacts.

        Sequence: gaps -> price integrity -> spread outliers -> timezone ->
        stale quotes -> completeness -> score -> quarantine -> report.

        Returns ValidationResult with quality_score, rating, report_path,
        validated_df, and can_proceed flag.
        """
        self._logger.info(
            "Starting validation for %s %s (%s to %s)",
            pair, resolution, start_date, end_date,
            extra={"ctx": {
                "component": "quality_checker",
                "stage": "data_pipeline",
                "pair": pair,
                "resolution": resolution,
            }},
        )

        # Auto-compute config_hash if caller didn't provide one (AC #6)
        # Use sha256: prefix for consistency with conversion manifests
        if not config_hash:
            config_hash = f"sha256:{compute_config_hash(self._config)}"

        # Run all checks
        gaps = self._detect_gaps(df, resolution)
        total_days = (end_date - start_date).days
        total_years = total_days / 365.25 if total_days > 0 else 1.0
        gap_severity = self._classify_gap_severity(gaps, total_years)

        integrity_issues = self._check_price_integrity(df, self._session_schedule)
        spread_issues = self._check_spread_outliers(df, self._session_schedule)
        all_integrity = integrity_issues + spread_issues

        timezone_issues = self._verify_timezone_alignment(df)
        stale_records = self._detect_stale_quotes(df)
        completeness_issues = self._check_completeness(df, start_date, end_date)

        # Compute quality score
        quality_score, penalties = self._compute_quality_score(
            df, gaps, all_integrity, stale_records
        )
        rating = self._classify_score(quality_score)

        # Quarantine marking
        validated_df = self._mark_quarantined(df, gaps, all_integrity, stale_records)

        # Build quarantined periods summary — account for ALL quarantine sources
        quarantined_periods: List[dict] = []
        timestamps = pd.to_datetime(validated_df["timestamp"])

        # From gaps — compute actual bar count within each gap range
        for g in gaps:
            if not g.is_weekend:
                gap_mask = (timestamps >= g.start) & (timestamps <= g.end)
                bar_count = int(gap_mask.sum())
                quarantined_periods.append({
                    "start": str(g.start),
                    "end": str(g.end),
                    "reason": "gap",
                    "bar_count": bar_count,
                })
        # From stale
        for s in stale_records:
            quarantined_periods.append({
                "start": str(s.start),
                "end": str(s.end),
                "reason": f"stale_{s.stale_type}",
                "bar_count": s.duration_bars,
            })
        # From integrity errors — group into contiguous periods
        # Errors more than 1 hour apart are separate periods to avoid
        # misleading operators with a single span over disjoint errors.
        error_timestamps = sorted(
            i.timestamp for i in all_integrity if i.severity == "error"
        )
        if error_timestamps:
            from datetime import timedelta
            gap_threshold = timedelta(hours=1)
            groups: list[list] = [[error_timestamps[0]]]
            for ts in error_timestamps[1:]:
                if (ts - groups[-1][-1]) > gap_threshold:
                    groups.append([ts])
                else:
                    groups[-1].append(ts)
            for group in groups:
                quarantined_periods.append({
                    "start": str(group[0]),
                    "end": str(group[-1]),
                    "reason": "integrity_error",
                    "bar_count": len(group),
                })

        # Unique quarantined bar count (avoids double-counting overlaps)
        unique_quarantined_count = int(validated_df["quarantined"].sum())

        # Generate and save report
        report = self._generate_quality_report(
            pair=pair,
            resolution=resolution,
            start_date=start_date,
            end_date=end_date,
            quality_score=quality_score,
            rating=rating,
            penalty_breakdown=penalties,
            gaps=gaps,
            integrity_issues=all_integrity,
            timezone_issues=timezone_issues,
            stale_records=stale_records,
            completeness_issues=completeness_issues,
            quarantined_periods=quarantined_periods,
            total_bars=len(df),
            gap_severity=gap_severity,
            config_hash=config_hash,
            unique_quarantined_count=unique_quarantined_count,
        )
        report_path = self._save_quality_report(report, storage_path, dataset_id, version)

        # Save validated data
        self._save_validated_data(validated_df, storage_path, dataset_id, version)

        # Determine can_proceed
        if rating == "GREEN":
            can_proceed = True
        elif rating == "YELLOW":
            can_proceed = "operator_review"
        else:
            can_proceed = False

        self._logger.info(
            "Validation complete: score=%.4f, rating=%s, can_proceed=%s",
            quality_score, rating, can_proceed,
            extra={"ctx": {
                "component": "quality_checker",
                "stage": "data_pipeline",
                "quality_score": quality_score,
                "rating": rating,
                "can_proceed": str(can_proceed),
            }},
        )

        return ValidationResult(
            quality_score=quality_score,
            rating=rating,
            report_path=report_path,
            validated_df=validated_df,
            can_proceed=can_proceed,
        )
