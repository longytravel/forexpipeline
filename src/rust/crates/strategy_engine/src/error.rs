use thiserror::Error;

use crate::validator::ValidationError;

/// Errors from the strategy engine crate.
///
/// Two distinct categories:
/// - `ParseError`: Structural failures from TOML deserialization. Fail-fast (single error).
/// - `ValidationErrors`: Semantic failures from `validate_spec()`. Collect-all (all errors at once).
#[derive(Debug, Error)]
pub enum StrategyEngineError {
    #[error("IO error: {0}")]
    IoError(#[from] std::io::Error),

    #[error("Parse error: {details}")]
    ParseError { details: String },

    #[error("Validation errors: {0:?}")]
    ValidationErrors(Vec<ValidationError>),
}
