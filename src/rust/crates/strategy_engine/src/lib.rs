mod error;
mod parser;
pub mod registry;
mod types;
pub mod validator;

pub use error::StrategyEngineError;
pub use parser::{parse_spec_from_file, parse_spec_from_str};
pub use registry::{default_registry, IndicatorDef, IndicatorRegistry, ParamDef, ParamType};
pub use types::{
    ChandelierParams, Condition, CostModelReference, DayOfWeekFilterParams, EntryRules,
    ExitConfig, ExitRules, Filter, IndicatorParams, Metadata, OptimizationPlan,
    OptimizationPlanV1, OptimizationPlanV2, ParamRange, ParameterCondition, ParameterGroup,
    PositionSizing, SearchParameter, SessionFilterParams, StrategySpec, TrailingConfig,
    TrailingStopParams, ValidatedSpec, VolatilityFilterParams, VALID_COMPARATORS,
    VALID_OBJECTIVES, VALID_SESSIONS, VALID_SIZING_METHODS, VALID_STOP_LOSS_TYPES,
    VALID_TAKE_PROFIT_TYPES, VALID_TIMEFRAMES,
};
pub use validator::{validate_spec, Severity, ValidationError};
