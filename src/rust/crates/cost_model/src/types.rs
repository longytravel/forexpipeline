use serde::{Deserialize, Serialize};
use std::collections::BTreeMap;
use std::fmt;

/// Expected session keys matching contracts/session_schema.toml.
pub const ASIAN: &str = "asian";
pub const LONDON: &str = "london";
pub const NEW_YORK: &str = "new_york";
pub const LONDON_NY_OVERLAP: &str = "london_ny_overlap";
pub const OFF_HOURS: &str = "off_hours";

/// All valid session keys in canonical order.
pub const EXPECTED_SESSIONS: [&str; 5] = [ASIAN, LONDON, NEW_YORK, LONDON_NY_OVERLAP, OFF_HOURS];

/// Pip value for EURUSD (standard forex pip).
// TODO: Epic 3 — generalize pip_value for JPY pairs (0.01)
pub const PIP_VALUE: f64 = 0.0001;

/// Cost parameters for a single trading session.
#[derive(Debug, Clone, Deserialize, Serialize)]
#[serde(rename_all = "snake_case")]
#[serde(deny_unknown_fields)]
pub struct CostProfile {
    pub mean_spread_pips: f64,
    pub std_spread: f64,
    pub mean_slippage_pips: f64,
    pub std_slippage: f64,
}

impl fmt::Display for CostProfile {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(
            f,
            "spread: {:.4}±{:.4} pips, slippage: {:.4}±{:.4} pips",
            self.mean_spread_pips, self.std_spread, self.mean_slippage_pips, self.std_slippage
        )
    }
}

/// Trade direction for cost application.
#[derive(Debug, Clone, Deserialize, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum Direction {
    Buy,
    Sell,
}

/// Raw JSON artifact structure produced by Story 2.6's Python builder.
#[derive(Debug, Clone, Deserialize, Serialize)]
#[serde(rename_all = "snake_case")]
#[serde(deny_unknown_fields)]
pub struct CostModelArtifact {
    pub pair: String,
    pub version: String,
    pub source: String,
    pub calibrated_at: String,
    pub sessions: BTreeMap<String, CostProfile>,
    /// Opaque metadata from the Python builder (description, data_points, confidence_level).
    /// The Rust crate stores but does not interpret it.
    pub metadata: Option<serde_json::Value>,
}

/// Loaded, validated, ready-to-query cost model.
#[derive(Debug, Clone)]
pub struct CostModel {
    pub(crate) artifact: CostModelArtifact,
}
