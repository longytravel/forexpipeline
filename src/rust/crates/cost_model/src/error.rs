use thiserror::Error;

/// Errors that can occur during cost model loading and querying.
#[derive(Debug, Error)]
pub enum CostModelError {
    #[error("IO error: {0}")]
    IoError(#[from] std::io::Error),

    #[error("JSON parse error: {0}")]
    ParseError(#[from] serde_json::Error),

    #[error("Validation error: {0}")]
    ValidationError(String),

    #[error("Session not found: {0}")]
    SessionNotFound(String),
}
