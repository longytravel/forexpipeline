"""Cost model schema definitions and validation (Story 2.6).

Defines the CostModelArtifact and SessionProfile dataclasses, plus
validation against the contracts/cost_model_schema.toml schema.

Source: architecture.md — D13, D2; FR20, FR21.
"""

from __future__ import annotations

import re
import tomllib
from dataclasses import dataclass, field, fields
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

VALID_SOURCES = ("research", "tick_analysis", "live_calibration")
REQUIRED_SESSIONS = ("asian", "london", "new_york", "london_ny_overlap", "off_hours")

_VERSION_RE = re.compile(r"^v\d{3,}$")


@dataclass
class SessionProfile:
    """Statistical cost profile for a single trading session."""

    mean_spread_pips: float
    std_spread: float
    mean_slippage_pips: float
    std_slippage: float

    def to_dict(self) -> dict[str, float]:
        return {
            "mean_spread_pips": self.mean_spread_pips,
            "std_spread": self.std_spread,
            "mean_slippage_pips": self.mean_slippage_pips,
            "std_slippage": self.std_slippage,
        }


@dataclass
class CostModelArtifact:
    """Complete cost model artifact with per-session profiles."""

    pair: str
    version: str
    source: str
    calibrated_at: str
    sessions: dict[str, SessionProfile]
    metadata: dict[str, Any] | None = field(default=None)

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "pair": self.pair,
            "version": self.version,
            "source": self.source,
            "calibrated_at": self.calibrated_at,
            "sessions": {
                name: profile.to_dict()
                for name, profile in self.sessions.items()
            },
        }
        if self.metadata is not None:
            result["metadata"] = self.metadata
        return result

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CostModelArtifact:
        """Reconstruct a CostModelArtifact from a JSON-loaded dict."""
        _profile_fields = {f.name for f in fields(SessionProfile)}
        sessions = {
            name: SessionProfile(**{
                k: v for k, v in profile_data.items() if k in _profile_fields
            })
            for name, profile_data in data["sessions"].items()
        }
        return cls(
            pair=data["pair"],
            version=data["version"],
            source=data["source"],
            calibrated_at=data["calibrated_at"],
            sessions=sessions,
            metadata=data.get("metadata"),
        )


def load_schema(schema_path: Path) -> dict[str, Any]:
    """Load and parse the cost model schema from TOML."""
    schema_path = Path(schema_path).resolve()
    with open(schema_path, "rb") as f:
        return tomllib.load(f)


def validate_cost_model(
    artifact: CostModelArtifact, schema_path: Path
) -> list[str]:
    """Validate a CostModelArtifact against the TOML schema.

    Returns a list of validation errors (empty = valid).
    """
    errors: list[str] = []
    schema = load_schema(schema_path)

    # Validate top-level required fields
    artifact_schema = schema.get("artifact", {})
    required_fields = artifact_schema.get("required", [])
    artifact_dict = artifact.to_dict()
    for req in required_fields:
        if req not in artifact_dict or artifact_dict[req] is None:
            errors.append(f"Missing required field: {req}")

    # Validate version format
    version_schema = artifact_schema.get("version", {})
    if version_schema.get("pattern"):
        if not _VERSION_RE.match(artifact.version):
            errors.append(
                f"Invalid version format '{artifact.version}': "
                f"must match v followed by 3+ digits"
            )

    # Validate source enum
    source_schema = artifact_schema.get("source", {})
    valid_sources = source_schema.get("enum", list(VALID_SOURCES))
    if artifact.source not in valid_sources:
        errors.append(
            f"Invalid source '{artifact.source}': "
            f"must be one of {valid_sources}"
        )

    # Validate calibrated_at ISO 8601 UTC format
    if artifact.calibrated_at:
        try:
            parsed = datetime.fromisoformat(
                artifact.calibrated_at.replace("Z", "+00:00")
            )
            if parsed.tzinfo is None or parsed.utcoffset().total_seconds() != 0:
                errors.append(
                    f"calibrated_at must be UTC (offset 0), "
                    f"got offset {parsed.utcoffset()}"
                )
        except (ValueError, TypeError):
            errors.append(
                f"Invalid calibrated_at '{artifact.calibrated_at}': "
                f"must be ISO 8601 UTC datetime"
            )

    # Validate sessions
    sessions_schema = artifact_schema.get("sessions", {})
    required_sessions = sessions_schema.get("required_keys", list(REQUIRED_SESSIONS))
    for session_name in required_sessions:
        if session_name not in artifact.sessions:
            errors.append(f"Missing required session: {session_name}")

    # Validate each session profile
    profile_schema = schema.get("session_profile", {})
    profile_required = profile_schema.get("required", [])
    for session_name, profile in artifact.sessions.items():
        profile_dict = profile.to_dict()
        for req_field in profile_required:
            if req_field not in profile_dict:
                errors.append(
                    f"Session '{session_name}' missing required field: {req_field}"
                )
            else:
                val = profile_dict[req_field]
                if not isinstance(val, (int, float)):
                    errors.append(
                        f"Session '{session_name}' field '{req_field}' "
                        f"must be numeric, got {type(val).__name__}"
                    )
                elif val < 0:
                    errors.append(
                        f"Session '{session_name}' field '{req_field}' "
                        f"must be >= 0, got {val}"
                    )

    return errors
