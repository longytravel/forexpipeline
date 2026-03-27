"""Session assignment utility (Story 1.5).

Assigns forex trading session labels to timestamps based on config.
Sessions are read from config/base.toml [sessions] section.
Reused in Story 1.6 for Arrow IPC session column stamping.
"""
from datetime import time

import pandas as pd


def _parse_time(time_str: str) -> time:
    """Parse HH:MM string to time object."""
    parts = time_str.split(":")
    return time(int(parts[0]), int(parts[1]))


def assign_session(timestamp: pd.Timestamp, session_schedule: dict) -> str:
    """Assign a session label to a single UTC timestamp.

    Args:
        timestamp: UTC timestamp to classify.
        session_schedule: Session config dict from config/base.toml [sessions].
            Keys: asian, london, new_york, london_ny_overlap, off_hours.
            Each has 'start', 'end', 'label' fields.

    Returns:
        Session label string: "asian", "london", "new_york",
        "london_ny_overlap", or "off_hours".
    """
    t = timestamp.time() if hasattr(timestamp, 'time') else timestamp

    # Check overlap first — it's the most specific match
    if "london_ny_overlap" in session_schedule:
        ovl = session_schedule["london_ny_overlap"]
        ovl_start = _parse_time(ovl["start"])
        ovl_end = _parse_time(ovl["end"])
        if ovl_start <= t < ovl_end:
            return "london_ny_overlap"

    # Check remaining sessions (excluding timezone and london_ny_overlap)
    for key in ("asian", "london", "new_york", "off_hours"):
        if key not in session_schedule:
            continue
        sess = session_schedule[key]
        s = _parse_time(sess["start"])
        e = _parse_time(sess["end"])

        if s < e:
            # Normal range (e.g., 00:00-08:00)
            if s <= t < e:
                return key
        else:
            # Wraps midnight (e.g., 21:00-00:00)
            if t >= s or t < e:
                return key

    return "off_hours"


def assign_sessions_bulk(df: pd.DataFrame, session_schedule: dict) -> pd.Series:
    """Vectorized session assignment for a DataFrame.

    Args:
        df: DataFrame with a 'timestamp' column (datetime64).
        session_schedule: Session config dict from config/base.toml [sessions].

    Returns:
        pd.Series of session label strings, indexed like df.
    """
    timestamps = pd.to_datetime(df["timestamp"], format="ISO8601")
    hours = timestamps.dt.hour
    minutes = timestamps.dt.minute
    # Total minutes since midnight for vectorized comparison
    total_minutes = hours * 60 + minutes

    # Parse session boundaries as total minutes
    boundaries = {}
    for key in ("asian", "london", "new_york", "london_ny_overlap", "off_hours"):
        if key not in session_schedule:
            continue
        sess = session_schedule[key]
        s = _parse_time(sess["start"])
        e = _parse_time(sess["end"])
        boundaries[key] = (s.hour * 60 + s.minute, e.hour * 60 + e.minute)

    # Default to off_hours
    result = pd.Series("off_hours", index=df.index)

    # Assign in order: broader sessions first, then overlap overrides
    for key in ("asian", "london", "new_york", "off_hours"):
        if key not in boundaries:
            continue
        s_min, e_min = boundaries[key]
        if s_min < e_min:
            mask = (total_minutes >= s_min) & (total_minutes < e_min)
        else:
            # Wraps midnight
            mask = (total_minutes >= s_min) | (total_minutes < e_min)
        result[mask] = key

    # Overlap takes priority — overwrite where both london and new_york apply
    if "london_ny_overlap" in boundaries:
        s_min, e_min = boundaries["london_ny_overlap"]
        mask = (total_minutes >= s_min) & (total_minutes < e_min)
        result[mask] = "london_ny_overlap"

    return result
