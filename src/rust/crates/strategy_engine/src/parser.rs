use std::fs;
use std::path::Path;

use crate::error::StrategyEngineError;
use crate::types::StrategySpec;

/// Parse a strategy specification from a TOML file on disk.
pub fn parse_spec_from_file(path: &Path) -> Result<StrategySpec, StrategyEngineError> {
    let content = fs::read_to_string(path).map_err(StrategyEngineError::IoError)?;
    parse_spec_from_str(&content).map_err(|e| match e {
        StrategyEngineError::ParseError { details } => StrategyEngineError::ParseError {
            details: format!("{} (file: {})", details, path.display()),
        },
        other => other,
    })
}

/// Parse a strategy specification from a TOML string.
pub fn parse_spec_from_str(content: &str) -> Result<StrategySpec, StrategyEngineError> {
    toml::from_str(content).map_err(|e| StrategyEngineError::ParseError {
        details: e.to_string(),
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    const VALID_TOML: &str = r#"
[metadata]
schema_version = "1"
name = "test-strategy"
version = "v001"
pair = "EURUSD"
timeframe = "H1"
created_by = "test"
config_hash = "abc123"

[[entry_rules.conditions]]
indicator = "sma"
threshold = 0.0
comparator = "crosses_above"
[entry_rules.conditions.parameters]
period = 20

[[entry_rules.filters]]
type = "session"
[entry_rules.filters.params]
include = ["london", "new_york"]

[exit_rules.stop_loss]
type = "atr_multiple"
value = 2.0

[position_sizing]
method = "fixed_risk"
risk_percent = 1.0
max_lots = 1.0

[[optimization_plan.parameter_groups]]
name = "entry_timing"
parameters = ["sma_period"]
[optimization_plan.parameter_groups.ranges.sma_period]
min = 5.0
max = 50.0
step = 5.0

[optimization_plan]
objective_function = "sharpe"

[cost_model_reference]
version = "v001"
"#;

    #[test]
    fn test_parse_valid_toml_spec() {
        let spec = parse_spec_from_str(VALID_TOML).expect("should parse valid TOML");
        assert_eq!(spec.metadata.name, "test-strategy");
        assert_eq!(spec.metadata.pair, "EURUSD");
        assert_eq!(spec.entry_rules.conditions.len(), 1);
        assert_eq!(spec.entry_rules.filters.len(), 1);
        assert_eq!(spec.exit_rules.stop_loss.exit_type, "atr_multiple");
    }

    #[test]
    fn test_parse_malformed_toml_fails() {
        let result = parse_spec_from_str("{{{{ not valid toml");
        assert!(result.is_err());
        match result.unwrap_err() {
            StrategyEngineError::ParseError { .. } => {}
            other => panic!("Expected ParseError, got: {other}"),
        }
    }

    #[test]
    fn test_parse_unknown_fields_rejected() {
        let toml_with_extra = VALID_TOML.replace(
            "[metadata]",
            "[metadata]\nunknown_field = \"surprise\"",
        );
        let result = parse_spec_from_str(&toml_with_extra);
        assert!(result.is_err());
        match result.unwrap_err() {
            StrategyEngineError::ParseError { details } => {
                assert!(
                    details.contains("unknown field"),
                    "Expected 'unknown field' in error, got: {details}"
                );
            }
            other => panic!("Expected ParseError, got: {other}"),
        }
    }

    #[test]
    fn test_parse_error_is_distinct_from_validation_error() {
        // Malformed TOML should give ParseError, never ValidationErrors
        let result = parse_spec_from_str("not valid");
        assert!(result.is_err());
        let err = result.unwrap_err();
        assert!(
            matches!(err, StrategyEngineError::ParseError { .. }),
            "Expected ParseError variant, got: {err}"
        );
    }
}
