"""Python-Rust bridge: subprocess dispatch, error parsing, output verification (D1)."""
from rust_bridge.batch_runner import BacktestJob, BatchResult, BatchRunner, ProgressReport
from rust_bridge.error_parser import RustError, map_to_pipeline_error, parse_rust_error
from rust_bridge.output_verifier import BacktestOutputRef, validate_schemas, verify_output
from rust_bridge.backtest_executor import BacktestExecutor
from rust_bridge.result_ingester import ResultIngester
from rust_bridge.result_processor import ProcessingResult, ResultProcessor, ResultProcessingError
from rust_bridge.result_executor import ResultExecutor
from rust_bridge.worker_client import PersistentWorker, WorkerError, WorkerPool

__all__ = [
    "BacktestExecutor",
    "BacktestJob",
    "BacktestOutputRef",
    "BatchResult",
    "BatchRunner",
    "PersistentWorker",
    "ProcessingResult",
    "ProgressReport",
    "ResultExecutor",
    "ResultIngester",
    "ResultProcessor",
    "ResultProcessingError",
    "RustError",
    "WorkerError",
    "WorkerPool",
    "map_to_pipeline_error",
    "parse_rust_error",
    "validate_schemas",
    "verify_output",
]
