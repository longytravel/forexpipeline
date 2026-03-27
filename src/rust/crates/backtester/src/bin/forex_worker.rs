//! Forex worker binary — persistent subprocess for optimization engine (D1).
//!
//! Keeps market data in memory across evaluations, communicating with the
//! Python optimization orchestrator via JSON-lines on stdin/stdout.
//! Stderr is reserved for structured tracing logs.

use std::process;

use common::error_types::install_panic_hook;

fn main() {
    install_panic_hook();

    // Direct structured logs to stderr (matching forex_backtester convention)
    eprintln!("{{\"level\":\"info\",\"msg\":\"forex_worker starting\"}}");

    if let Err(e) = backtester::worker::run() {
        e.to_structured().write_to_stderr();
        process::exit(1);
    }
}
