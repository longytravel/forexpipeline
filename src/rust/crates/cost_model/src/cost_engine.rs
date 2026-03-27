use std::collections::BTreeMap;

use crate::error::CostModelError;
use crate::types::{CostModel, CostProfile, Direction, PIP_VALUE};

impl CostModel {
    /// O(1) lookup of cost profile for a given session label.
    pub fn get_cost(&self, session: &str) -> Result<&CostProfile, CostModelError> {
        self.artifact
            .sessions
            .get(session)
            .ok_or_else(|| CostModelError::SessionNotFound(session.to_string()))
    }

    /// Apply session-aware spread and slippage to a fill price.
    ///
    /// - **Buy:** `fill_price + (mean_spread + mean_slippage) * pip_value` (worse fill = higher)
    /// - **Sell:** `fill_price - (mean_spread + mean_slippage) * pip_value` (worse fill = lower)
    ///
    /// V1 uses deterministic mean values only. std_* fields are stored for future
    /// stochastic sampling but NOT consumed here.
    pub fn apply_cost(
        &self,
        fill_price: f64,
        session: &str,
        direction: Direction,
    ) -> Result<f64, CostModelError> {
        let profile = self.get_cost(session)?;
        let cost_pips = profile.mean_spread_pips + profile.mean_slippage_pips;
        let cost_price = cost_pips * PIP_VALUE;

        let adjusted = match direction {
            Direction::Buy => fill_price + cost_price,
            Direction::Sell => fill_price - cost_price,
        };

        Ok(adjusted)
    }

    /// Returns the pair this model covers.
    pub fn pair(&self) -> &str {
        &self.artifact.pair
    }

    /// Returns the artifact version string.
    pub fn version(&self) -> &str {
        &self.artifact.version
    }

    /// Returns all session profiles.
    pub fn sessions(&self) -> &BTreeMap<String, CostProfile> {
        &self.artifact.sessions
    }

    /// Returns the source descriptor (e.g., "research", "research+live_calibration").
    pub fn source(&self) -> &str {
        &self.artifact.source
    }

    /// Returns the calibration timestamp (ISO 8601).
    pub fn calibrated_at(&self) -> &str {
        &self.artifact.calibrated_at
    }

    /// Returns the optional metadata from the Python builder.
    pub fn metadata(&self) -> Option<&serde_json::Value> {
        self.artifact.metadata.as_ref()
    }
}
