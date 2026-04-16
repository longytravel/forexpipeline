use serde::{Deserialize, Serialize};
use std::collections::BTreeMap;

/// Top-level strategy specification, aligned with contracts/strategy_specification.toml.
#[derive(Debug, Clone, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct StrategySpec {
    pub metadata: Metadata,
    pub entry_rules: EntryRules,
    pub exit_rules: ExitRules,
    pub position_sizing: PositionSizing,
    #[serde(default)]
    pub account: Option<AccountConfig>,
    pub optimization_plan: OptimizationPlan,
    pub cost_model_reference: CostModelReference,
}

/// Strategy identity and versioning metadata.
#[derive(Debug, Clone, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct Metadata {
    pub schema_version: String,
    pub name: String,
    pub version: String,
    pub pair: String,
    pub timeframe: String,
    pub created_by: String,
    #[serde(default)]
    pub config_hash: Option<String>,
}

/// Entry signal conditions, filters, and confirmations.
#[derive(Debug, Clone, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct EntryRules {
    pub conditions: Vec<Condition>,
    #[serde(default)]
    pub filters: Vec<Filter>,
    #[serde(default)]
    pub confirmation: Vec<Condition>,
}

/// An indicator-based condition (used for both entry and confirmation).
#[derive(Debug, Clone, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct Condition {
    pub indicator: String,
    pub parameters: IndicatorParams,
    pub threshold: f64,
    pub comparator: String,
}

/// Indicator parameters — a generic key-value map.
/// The indicator registry validates which params are required/valid per indicator type.
/// This keeps the parser and registry concerns separate (anti-pattern #3).
pub type IndicatorParams = BTreeMap<String, toml::Value>;

/// Pre-entry filter (session, volatility, day_of_week).
/// Adjacently tagged by `type` with type-specific `params`.
#[derive(Debug, Clone, Deserialize, Serialize)]
#[serde(tag = "type", content = "params")]
#[serde(deny_unknown_fields)]
pub enum Filter {
    #[serde(rename = "session")]
    Session(SessionFilterParams),
    #[serde(rename = "volatility")]
    Volatility(VolatilityFilterParams),
    #[serde(rename = "day_of_week")]
    DayOfWeek(DayOfWeekFilterParams),
}

#[derive(Debug, Clone, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct SessionFilterParams {
    pub include: Vec<String>,
}

#[derive(Debug, Clone, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct VolatilityFilterParams {
    pub indicator: String,
    pub period: u32,
    #[serde(default)]
    pub min_value: Option<f64>,
    #[serde(default)]
    pub max_value: Option<f64>,
}

#[derive(Debug, Clone, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct DayOfWeekFilterParams {
    pub include: Vec<u8>,
}

/// Exit rule definitions.
#[derive(Debug, Clone, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct ExitRules {
    pub stop_loss: ExitConfig,
    #[serde(default)]
    pub take_profit: Option<ExitConfig>,
    #[serde(default)]
    pub trailing: Option<TrailingConfig>,
}

/// Exit configuration for stop_loss and take_profit.
#[derive(Debug, Clone, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct ExitConfig {
    #[serde(rename = "type")]
    pub exit_type: String,
    pub value: f64,
}

/// Trailing stop configuration, adjacently tagged by `type`.
#[derive(Debug, Clone, Deserialize, Serialize)]
#[serde(tag = "type", content = "params")]
#[serde(deny_unknown_fields)]
pub enum TrailingConfig {
    #[serde(rename = "trailing_stop")]
    TrailingStop(TrailingStopParams),
    #[serde(rename = "chandelier")]
    Chandelier(ChandelierParams),
}

#[derive(Debug, Clone, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct TrailingStopParams {
    pub distance_pips: f64,
}

#[derive(Debug, Clone, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct ChandelierParams {
    pub atr_period: u32,
    pub atr_multiplier: f64,
}

/// Position sizing method and constraints.
#[derive(Debug, Clone, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct PositionSizing {
    pub method: String,
    pub risk_percent: f64,
    pub max_lots: f64,
    #[serde(default = "default_min_lots")]
    pub min_lots: f64,
    #[serde(default = "default_lot_step")]
    pub lot_step: f64,
}

fn default_min_lots() -> f64 { 0.01 }
fn default_lot_step() -> f64 { 0.01 }

/// Backtest account configuration.
#[derive(Debug, Clone, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct AccountConfig {
    pub starting_balance: f64,
    pub currency: String,
    #[serde(default = "default_leverage")]
    pub leverage: u32,
}

fn default_leverage() -> u32 { 100 }

/// Parameter optimization configuration (supports v1 parameter_groups and v2 flat registry).
///
/// Serde tries V1 first (legacy format with parameter_groups), then V2
/// (schema_version=2 flat parameters). Both formats are valid and fully validated.
#[derive(Debug, Clone, Deserialize, Serialize)]
#[serde(untagged)]
pub enum OptimizationPlan {
    V1(OptimizationPlanV1),
    V2(OptimizationPlanV2),
}

impl OptimizationPlan {
    /// Returns the objective function regardless of schema version.
    pub fn objective_function(&self) -> &str {
        match self {
            OptimizationPlan::V1(v1) => &v1.objective_function,
            OptimizationPlan::V2(v2) => &v2.objective_function,
        }
    }
}

/// V1: Grouped parameter optimization (legacy format).
#[derive(Debug, Clone, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct OptimizationPlanV1 {
    pub parameter_groups: Vec<ParameterGroup>,
    #[serde(default)]
    pub group_dependencies: Vec<String>,
    pub objective_function: String,
}

/// V2: Flat parameter registry (schema_version = 2).
#[derive(Debug, Clone, Deserialize, Serialize)]
pub struct OptimizationPlanV2 {
    pub schema_version: u32,
    pub objective_function: String,
    pub parameters: BTreeMap<String, SearchParameter>,
    #[serde(default)]
    pub year_range: Option<Vec<u32>>,
    #[serde(default)]
    pub prescreening: Option<toml::Value>,
}

/// A single search parameter in the v2 flat registry.
#[derive(Debug, Clone, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct SearchParameter {
    #[serde(rename = "type")]
    pub param_type: String,
    #[serde(default)]
    pub min: Option<f64>,
    #[serde(default)]
    pub max: Option<f64>,
    #[serde(default)]
    pub step: Option<f64>,
    #[serde(default)]
    pub choices: Option<Vec<String>>,
    #[serde(default)]
    pub condition: Option<ParameterCondition>,
}

/// Conditional activation for a v2 search parameter.
#[derive(Debug, Clone, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct ParameterCondition {
    pub parent: String,
    pub value: String,
}

/// A group of parameters for staged optimization (v1).
#[derive(Debug, Clone, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct ParameterGroup {
    pub name: String,
    pub parameters: Vec<String>,
    pub ranges: BTreeMap<String, ParamRange>,
}

/// Min/max/step for an optimization parameter (v1).
#[derive(Debug, Clone, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct ParamRange {
    pub min: f64,
    pub max: f64,
    pub step: f64,
}

/// Reference to a versioned cost model artifact.
#[derive(Debug, Clone, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct CostModelReference {
    pub version: String,
}

/// Newtype wrapper guaranteeing the spec passed validation.
#[derive(Debug, Clone, Serialize)]
pub struct ValidatedSpec(pub StrategySpec);

impl ValidatedSpec {
    /// Access the inner validated spec.
    pub fn spec(&self) -> &StrategySpec {
        &self.0
    }
}

/// Valid comparator values per contracts/strategy_specification.toml.
pub const VALID_COMPARATORS: [&str; 7] = [
    ">", "<", "==", ">=", "<=", "crosses_above", "crosses_below",
];

/// Valid timeframe values per contracts/strategy_specification.toml.
pub const VALID_TIMEFRAMES: [&str; 6] = ["M1", "M5", "M15", "H1", "H4", "D1"];

/// Valid stop_loss exit types.
pub const VALID_STOP_LOSS_TYPES: [&str; 3] = ["fixed_pips", "atr_multiple", "percentage"];

/// Valid take_profit exit types.
pub const VALID_TAKE_PROFIT_TYPES: [&str; 4] =
    ["fixed_pips", "atr_multiple", "percentage", "risk_reward"];

/// Valid position sizing methods.
pub const VALID_SIZING_METHODS: [&str; 2] = ["fixed_risk", "fixed_lots"];

/// Valid objective function metrics.
pub const VALID_OBJECTIVES: [&str; 5] = ["sharpe", "calmar", "profit_factor", "expectancy", "composite"];

/// Canonical session labels — shared with cost_model crate.
pub const VALID_SESSIONS: [&str; 5] = ["asian", "london", "new_york", "london_ny_overlap", "off_hours"];
