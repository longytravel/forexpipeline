"""Session management for cost model (Story 2.6).

Loads session time boundaries from config/base.toml and provides
session label assignment with priority resolution:
  overlap > specific session > off_hours

Source: architecture.md — D7, session architecture (lines 146-222).
"""

from __future__ import annotations

import tomllib
from pathlib import Path

SESSION_NAMES = ("asian", "london", "new_york", "london_ny_overlap", "off_hours")

# Non-overlapping label assignment boundaries (priority-resolved).
# config/base.toml defines overlapping market presence (London 08-16, NY 13-21).
# For label assignment, overlap range gets its own label:
#   asian: 00-08, london: 08-13, london_ny_overlap: 13-16,
#   new_york: 16-21, off_hours: 21-00
_LABEL_BOUNDARIES: list[tuple[str, int, int]] = [
    ("asian", 0, 8),
    ("london", 8, 13),
    ("london_ny_overlap", 13, 16),
    ("new_york", 16, 21),
    ("off_hours", 21, 24),
]


def load_session_definitions(config_path: Path) -> dict[str, dict]:
    """Load session time boundaries from config/base.toml.

    Returns dict mapping session name -> {start_utc, end_utc, description, label}.
    These are the raw market-presence boundaries from config, NOT the
    priority-resolved label boundaries.
    """
    config_path = Path(config_path).resolve()
    with open(config_path, "rb") as f:
        config = tomllib.load(f)

    sessions_config = config.get("sessions", {})
    result: dict[str, dict] = {}

    for session_name in SESSION_NAMES:
        session_data = sessions_config.get(session_name)
        if session_data is None:
            raise ValueError(
                f"Session '{session_name}' not found in {config_path}. "
                f"All 5 sessions are required: {SESSION_NAMES}"
            )
        start_str = session_data.get("start", "")
        end_str = session_data.get("end", "")
        start_hour = int(start_str.split(":")[0])
        end_hour = int(end_str.split(":")[0])

        result[session_name] = {
            "start_utc": start_hour,
            "end_utc": end_hour,
            "description": session_data.get("label", session_name),
            "label": session_data.get("label", session_name),
        }

    return result


def validate_session_coverage(sessions: dict[str, dict]) -> list[str]:
    """Verify all 5 required sessions are defined and label boundaries cover 24h.

    Uses the priority-resolved label boundaries to verify full coverage.
    Returns list of validation errors (empty = valid).
    """
    errors: list[str] = []

    # Check all required sessions present
    for name in SESSION_NAMES:
        if name not in sessions:
            errors.append(f"Missing required session: {name}")

    # Verify label boundaries cover all 24 hours without gaps
    covered = set()
    for _name, start, end in _LABEL_BOUNDARIES:
        for h in range(start, end):
            covered.add(h)

    missing_hours = set(range(24)) - covered
    if missing_hours:
        errors.append(
            f"Session label boundaries have gaps at hours: "
            f"{sorted(missing_hours)}"
        )

    return errors


def validate_config_matches_boundaries(config_path: Path) -> None:
    """Assert config/base.toml session boundaries match hardcoded label boundaries.

    Call this at builder init time so that changes to config are not silently
    ignored. Raises ValueError if the config-derived label boundaries differ
    from _LABEL_BOUNDARIES.
    """
    defs = load_session_definitions(config_path)
    # Derive expected label boundaries from config using priority resolution:
    # The config defines overlapping market presence; we resolve to
    # non-overlapping labels the same way _LABEL_BOUNDARIES was built.
    # Note: end_utc=0 means midnight wrap → normalize to 24 for comparison.
    def _norm(hour: int) -> int:
        return 24 if hour == 0 else hour

    expected = {
        "asian": (defs["asian"]["start_utc"], _norm(defs["asian"]["end_utc"])),
        "london": (defs["london"]["start_utc"], defs["london_ny_overlap"]["start_utc"]),
        "london_ny_overlap": (defs["london_ny_overlap"]["start_utc"], defs["london_ny_overlap"]["end_utc"]),
        "new_york": (defs["london_ny_overlap"]["end_utc"], defs["new_york"]["end_utc"]),
        "off_hours": (defs["off_hours"]["start_utc"], _norm(defs["off_hours"]["end_utc"])),
    }
    hardcoded = {name: (start, end) for name, start, end in _LABEL_BOUNDARIES}

    mismatches = []
    for name in SESSION_NAMES:
        if expected.get(name) != hardcoded.get(name):
            mismatches.append(
                f"  {name}: config-derived={expected.get(name)}, "
                f"hardcoded={hardcoded.get(name)}"
            )
    if mismatches:
        raise ValueError(
            "config/base.toml session boundaries have changed but "
            "_LABEL_BOUNDARIES in sessions.py has not been updated:\n"
            + "\n".join(mismatches)
        )


def get_session_for_time(hour_utc: int) -> str:
    """Return session label for a given UTC hour.

    Uses priority resolution: overlap > specific session > off_hours.
    Label boundaries are derived from the architecture spec and validated
    against config/base.toml at builder init time via
    ``validate_config_matches_boundaries()``.

    Args:
        hour_utc: Hour in UTC (0-23).

    Returns:
        Session label string.

    Raises:
        ValueError: If hour_utc is not in 0-23 range.
    """
    if not 0 <= hour_utc <= 23:
        raise ValueError(f"hour_utc must be 0-23, got {hour_utc}")

    for name, start, end in _LABEL_BOUNDARIES:
        if start <= hour_utc < end:
            return name

    # Should never reach here given _LABEL_BOUNDARIES covers 0-24
    return "off_hours"  # pragma: no cover
