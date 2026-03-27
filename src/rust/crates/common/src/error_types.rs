//! D8 structured error types for cross-process error propagation.
//!
//! The Rust binary writes structured JSON to stderr on failure.
//! Python `error_parser.py` reads and maps these to `PipelineError`.

use serde::Serialize;
use thiserror::Error;

/// D8 error schema — structured JSON errors on stderr.
/// Categories MUST match architecture D8 exactly.
#[derive(Debug, Serialize)]
pub struct StructuredError {
    pub error_type: String,
    pub category: ErrorCategory,
    pub message: String,
    pub context: serde_json::Value,
}

/// D8 error categories mapped to Python orchestrator recovery actions:
/// - `resource_pressure` → throttle (reduce concurrency/batch size)
/// - `data_logic` → stop + checkpoint (no retry)
/// - `external_failure` → retry with backoff
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum ErrorCategory {
    ResourcePressure,
    DataLogic,
    ExternalFailure,
}

impl StructuredError {
    /// Write this error as JSON to stderr for Python consumption.
    pub fn write_to_stderr(&self) {
        if let Ok(json) = serde_json::to_string(self) {
            eprintln!("{json}");
        }
    }

    /// Create a resource pressure error (OOM, budget exceeded).
    pub fn resource(error_type: &str, message: String, context: serde_json::Value) -> Self {
        Self {
            error_type: error_type.to_string(),
            category: ErrorCategory::ResourcePressure,
            message,
            context,
        }
    }

    /// Create a data/logic error (validation, corrupt data).
    pub fn data_logic(error_type: &str, message: String, context: serde_json::Value) -> Self {
        Self {
            error_type: error_type.to_string(),
            category: ErrorCategory::DataLogic,
            message,
            context,
        }
    }

    /// Create an external failure error (IO, network).
    pub fn external(error_type: &str, message: String, context: serde_json::Value) -> Self {
        Self {
            error_type: error_type.to_string(),
            category: ErrorCategory::ExternalFailure,
            message,
            context,
        }
    }
}

/// Unified error type for the backtester binary.
#[derive(Error, Debug)]
pub enum BacktesterError {
    #[error("Strategy spec error: {0}")]
    StrategySpec(String),

    #[error("Cost model error: {0}")]
    CostModel(String),

    #[error("Arrow IPC error: {0}")]
    ArrowIpc(String),

    #[error("Memory budget exceeded: requested {requested_mb}MB, available {available_mb}MB")]
    OomError { requested_mb: u64, available_mb: u64 },

    #[error("Cancellation signal received")]
    SignalReceived,

    #[error("IO error: {0}")]
    Io(#[from] std::io::Error),

    #[error("Validation error: {0}")]
    Validation(String),
}

impl BacktesterError {
    /// Convert this error into a `StructuredError` for stderr JSON output.
    pub fn to_structured(&self) -> StructuredError {
        match self {
            BacktesterError::StrategySpec(msg) => StructuredError::data_logic(
                "strategy_spec_error",
                msg.clone(),
                serde_json::json!({"component": "strategy_engine"}),
            ),
            BacktesterError::CostModel(msg) => StructuredError::data_logic(
                "cost_model_error",
                msg.clone(),
                serde_json::json!({"component": "cost_model"}),
            ),
            BacktesterError::ArrowIpc(msg) => StructuredError::data_logic(
                "arrow_ipc_error",
                msg.clone(),
                serde_json::json!({"component": "arrow_ipc"}),
            ),
            BacktesterError::OomError {
                requested_mb,
                available_mb,
            } => StructuredError::resource(
                "resource_exhaustion",
                format!(
                    "Memory budget exceeded: requested {requested_mb}MB, available {available_mb}MB"
                ),
                serde_json::json!({
                    "requested_mb": requested_mb,
                    "available_mb": available_mb,
                }),
            ),
            BacktesterError::SignalReceived => StructuredError::external(
                "cancellation",
                "Cancellation signal received".to_string(),
                serde_json::json!({}),
            ),
            BacktesterError::Io(e) => StructuredError::external(
                "io_error",
                e.to_string(),
                serde_json::json!({"kind": format!("{:?}", e.kind())}),
            ),
            BacktesterError::Validation(msg) => StructuredError::data_logic(
                "validation_error",
                msg.clone(),
                serde_json::json!({"component": "backtester"}),
            ),
        }
    }
}

/// Install a panic hook that writes structured JSON to stderr before aborting.
/// Call this once at binary startup.
pub fn install_panic_hook() {
    std::panic::set_hook(Box::new(|info| {
        let message = if let Some(s) = info.payload().downcast_ref::<&str>() {
            s.to_string()
        } else if let Some(s) = info.payload().downcast_ref::<String>() {
            s.clone()
        } else {
            "unknown panic".to_string()
        };

        let location = info
            .location()
            .map(|l| format!("{}:{}:{}", l.file(), l.line(), l.column()))
            .unwrap_or_default();

        let err = StructuredError::data_logic(
            "panic",
            message,
            serde_json::json!({ "location": location }),
        );
        err.write_to_stderr();
    }));
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_structured_error_serialization() {
        let err = StructuredError::resource(
            "resource_exhaustion",
            "OOM".to_string(),
            serde_json::json!({"mb": 512}),
        );
        let json = serde_json::to_string(&err).unwrap();
        assert!(json.contains("\"category\":\"resource_pressure\""));
        assert!(json.contains("\"error_type\":\"resource_exhaustion\""));
    }

    #[test]
    fn test_backtester_error_to_structured() {
        let err = BacktesterError::OomError {
            requested_mb: 1024,
            available_mb: 512,
        };
        let structured = err.to_structured();
        assert_eq!(structured.category, ErrorCategory::ResourcePressure);
        assert_eq!(structured.error_type, "resource_exhaustion");
    }

    #[test]
    fn test_io_error_maps_to_external() {
        let io_err = std::io::Error::new(std::io::ErrorKind::NotFound, "file not found");
        let err = BacktesterError::Io(io_err);
        let structured = err.to_structured();
        assert_eq!(structured.category, ErrorCategory::ExternalFailure);
    }

    #[test]
    fn test_error_category_serialization() {
        let json = serde_json::to_string(&ErrorCategory::DataLogic).unwrap();
        assert_eq!(json, "\"data_logic\"");
        let json = serde_json::to_string(&ErrorCategory::ResourcePressure).unwrap();
        assert_eq!(json, "\"resource_pressure\"");
        let json = serde_json::to_string(&ErrorCategory::ExternalFailure).unwrap();
        assert_eq!(json, "\"external_failure\"");
    }
}
