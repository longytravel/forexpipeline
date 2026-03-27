"""Cost model builder — creates session-aware cost model artifacts (Story 2.6).

Supports three input modes:
  - research data (manual input)
  - historical tick data analysis (automated)
  - live calibration data (interface stub — Epic 7)

Source: architecture.md — D13; FR20, FR21, FR22.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from cost_model.schema import (
    REQUIRED_SESSIONS,
    VALID_SOURCES,
    CostModelArtifact,
    SessionProfile,
    validate_cost_model,
)
from cost_model.sessions import (
    get_session_for_time,
    load_session_definitions,
    validate_config_matches_boundaries,
)
from cost_model.storage import get_next_version
from logging_setup.setup import get_logger

_log = get_logger("cost_model.builder")

# JPY pairs use 0.01 as 1 pip; all others use 0.0001.
_JPY_PAIRS = frozenset([
    "USDJPY", "EURJPY", "GBPJPY", "AUDJPY", "NZDJPY", "CADJPY", "CHFJPY",
])


def _pip_multiplier(pair: str) -> int:
    """Return the multiplier to convert raw price spread to pips."""
    return 100 if pair.upper() in _JPY_PAIRS else 10000


# Default EURUSD research values — typical major pair ECN broker conditions.
_EURUSD_DEFAULTS: dict[str, dict[str, float]] = {
    "asian": {
        "mean_spread_pips": 1.2, "std_spread": 0.4,
        "mean_slippage_pips": 0.1, "std_slippage": 0.05,
    },
    "london": {
        "mean_spread_pips": 0.8, "std_spread": 0.3,
        "mean_slippage_pips": 0.05, "std_slippage": 0.03,
    },
    "london_ny_overlap": {
        "mean_spread_pips": 0.6, "std_spread": 0.2,
        "mean_slippage_pips": 0.03, "std_slippage": 0.02,
    },
    "new_york": {
        "mean_spread_pips": 0.9, "std_spread": 0.3,
        "mean_slippage_pips": 0.06, "std_slippage": 0.03,
    },
    "off_hours": {
        "mean_spread_pips": 1.5, "std_spread": 0.6,
        "mean_slippage_pips": 0.15, "std_slippage": 0.08,
    },
}


class CostModelBuilder:
    """Builds cost model artifacts from various data sources."""

    def __init__(
        self,
        config_path: Path,
        contracts_path: Path,
        artifacts_dir: Path,
    ) -> None:
        self.config_path = Path(config_path).resolve()
        self.contracts_path = Path(contracts_path).resolve()
        self.artifacts_dir = Path(artifacts_dir).resolve()
        self.schema_path = self.contracts_path / "cost_model_schema.toml"

        # Load session definitions from config and validate they match
        # the hardcoded label boundaries (fail-fast if config changed)
        self.session_defs = load_session_definitions(self.config_path)
        validate_config_matches_boundaries(self.config_path)

    def from_research_data(
        self, pair: str, research_data: dict[str, dict]
    ) -> CostModelArtifact:
        """Create artifact from manual research data.

        Args:
            pair: Currency pair (e.g. "EURUSD").
            research_data: Dict mapping session name -> dict with keys:
                mean_spread_pips, std_spread, mean_slippage_pips, std_slippage.

        Returns:
            Validated CostModelArtifact.

        Raises:
            ValueError: If required sessions are missing or validation fails.
        """
        _log.info(
            "cost_model_build_start",
            extra={"ctx": {
                "pair": pair,
                "source": "research",
                "session_count": len(research_data),
            }},
        )

        missing = set(REQUIRED_SESSIONS) - set(research_data.keys())
        if missing:
            raise ValueError(
                f"Research data missing required sessions: {sorted(missing)}"
            )

        sessions = {
            name: SessionProfile(**data)
            for name, data in research_data.items()
            if name in REQUIRED_SESSIONS
        }

        return self._build_artifact(pair, "research", sessions)

    def from_tick_data(
        self, pair: str, tick_data_path: Path
    ) -> CostModelArtifact:
        """Create artifact by analyzing historical bid/ask tick data.

        Computes per-session spread distributions from M1 bar data.
        Slippage uses conservative research-based estimates scaled
        relative to spread (live calibration in Epic 7).

        Args:
            pair: Currency pair.
            tick_data_path: Path to directory containing Parquet files with
                columns: bid_open, bid_close, ask_open, ask_close, timestamp.

        Returns:
            Validated CostModelArtifact with empirical spreads and
            research-estimated slippage.
        """
        import pyarrow as pa
        import pyarrow.parquet as pq

        _log.info(
            "cost_model_build_start",
            extra={"ctx": {
                "pair": pair,
                "source": "tick_analysis",
                "tick_data_path": str(tick_data_path),
            }},
        )

        tick_data_path = Path(tick_data_path).resolve()
        if not tick_data_path.exists():
            raise FileNotFoundError(
                f"Tick data path not found: {tick_data_path}"
            )

        # Find all parquet files
        parquet_files = sorted(tick_data_path.glob("*.parquet"))
        if not parquet_files:
            raise FileNotFoundError(
                f"No .parquet files found in {tick_data_path}"
            )

        # Read all parquet files into a single table
        table = pq.read_table(parquet_files[0])
        for pf in parquet_files[1:]:
            table = pa.concat_tables([table, pq.read_table(pf)])

        # Compute spread per bar: ask_open - bid_open (representative spread)
        ask_open = table.column("ask_open").to_pylist()
        bid_open = table.column("bid_open").to_pylist()
        timestamps = table.column("timestamp").to_pylist()

        # Group spreads by session
        session_spreads: dict[str, list[float]] = {
            name: [] for name in REQUIRED_SESSIONS
        }

        multiplier = _pip_multiplier(pair)
        for ask, bid, ts in zip(ask_open, bid_open, timestamps):
            spread = ask - bid
            spread_pips = spread * multiplier
            if hasattr(ts, "hour"):
                hour = ts.hour
            else:
                # Parse string timestamps robustly via fromisoformat
                hour = datetime.fromisoformat(
                    str(ts).replace("Z", "+00:00")
                ).hour
            session = get_session_for_time(hour)
            session_spreads[session].append(spread_pips)

        # Compute statistics per session
        sessions: dict[str, SessionProfile] = {}
        for name in REQUIRED_SESSIONS:
            spreads = session_spreads[name]
            if spreads:
                n = len(spreads)
                mean_spread = sum(spreads) / n
                variance = sum((s - mean_spread) ** 2 for s in spreads) / max(n - 1, 1)
                std_spread = variance ** 0.5
            else:
                # Fallback to EURUSD defaults if no data for this session
                if pair != "EURUSD":
                    _log.warning(
                        "No tick data for session '%s' on pair %s — "
                        "falling back to EURUSD research defaults. "
                        "Values may be inaccurate for this pair.",
                        name, pair,
                        extra={"ctx": {"pair": pair, "session": name}},
                    )
                mean_spread = _EURUSD_DEFAULTS[name]["mean_spread_pips"]
                std_spread = _EURUSD_DEFAULTS[name]["std_spread"]

            # Slippage: research-based estimate scaled relative to spread
            # Conservative ratio: slippage ~= 8% of mean spread
            mean_slippage = mean_spread * 0.08
            std_slippage = mean_slippage * 0.5

            sessions[name] = SessionProfile(
                mean_spread_pips=round(mean_spread, 4),
                std_spread=round(std_spread, 4),
                mean_slippage_pips=round(mean_slippage, 4),
                std_slippage=round(std_slippage, 4),
            )

        artifact = self._build_artifact(pair, "tick_analysis", sessions)

        # Annotate metadata with slippage source
        if artifact.metadata is None:
            artifact.metadata = {}
        artifact.metadata["slippage_source"] = "research_estimate"
        artifact.metadata["data_points"] = len(ask_open)

        return artifact

    def from_live_calibration(
        self, pair: str, calibration_data: dict
    ) -> CostModelArtifact:
        """Interface stub for live calibration data.

        Live calibration data integration available in Epic 7 (FR22).

        Raises:
            NotImplementedError: Always — this is a future integration point.
        """
        raise NotImplementedError(
            "Live calibration data integration available in Epic 7 (FR22)"
        )

    def build_default_eurusd(self) -> CostModelArtifact:
        """Create default EURUSD cost model using research-based values.

        Values represent typical major pair ECN broker conditions:
        tightest spreads during London/NY overlap (peak liquidity),
        wider during Asian session, widest during off-hours.
        """
        return self.from_research_data("EURUSD", _EURUSD_DEFAULTS)

    def _build_artifact(
        self,
        pair: str,
        source: str,
        sessions: dict[str, SessionProfile],
    ) -> CostModelArtifact:
        """Assemble, validate, and return a CostModelArtifact.

        Args:
            pair: Currency pair.
            source: One of VALID_SOURCES.
            sessions: Per-session cost profiles.

        Returns:
            Validated CostModelArtifact.

        Raises:
            ValueError: If source is invalid or schema validation fails.
        """
        if source not in VALID_SOURCES:
            raise ValueError(
                f"Invalid source '{source}': must be one of {VALID_SOURCES}"
            )

        version = get_next_version(pair, self.artifacts_dir)
        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

        artifact = CostModelArtifact(
            pair=pair,
            version=version,
            source=source,
            calibrated_at=now,
            sessions=sessions,
            metadata={
                "description": f"{source.replace('_', ' ').title()}-based "
                               f"{pair} cost model",
                "data_points": None,
                "confidence_level": "research_estimate"
                if source == "research" else "empirical",
            },
        )

        # Validate against schema before returning
        errors = validate_cost_model(artifact, self.schema_path)
        if errors:
            raise ValueError(
                f"Built artifact failed schema validation: {errors}"
            )

        _log.info(
            "cost_model_validated",
            extra={"ctx": {
                "pair": pair,
                "version": version,
                "validation_errors_count": 0,
            }},
        )

        # Log completion with session statistics
        session_stats = {
            name: profile.mean_spread_pips
            for name, profile in sessions.items()
        }
        _log.info(
            "cost_model_build_complete",
            extra={"ctx": {
                "pair": pair,
                "version": version,
                "source": source,
                "session_stats": session_stats,
            }},
        )

        return artifact
