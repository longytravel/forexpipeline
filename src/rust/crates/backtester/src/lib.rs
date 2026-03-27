//! Backtester crate — library-with-subprocess-wrapper pattern (D1).
//!
//! This crate is built as a library with a thin binary wrapper
//! (`bin/forex_backtester.rs`). The library exposes evaluation logic;
//! the binary handles CLI parsing, signal handling, and process lifecycle.
//!
//! Core evaluation logic lives here; binary handles CLI and I/O only.
//! This library-with-subprocess-wrapper pattern enables zero-cost PyO3
//! migration path (Research Brief 3A).

pub mod batch_eval;
pub mod engine;
pub mod fold;
pub mod memory;
pub mod metrics;
pub mod output;
pub mod position;
pub mod progress;
pub mod trade_simulator;
pub mod worker;
