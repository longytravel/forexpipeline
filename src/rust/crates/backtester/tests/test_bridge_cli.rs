//! CLI integration tests for the forex_backtester binary (Story 3-4).
//!
//! These tests exercise the binary as a subprocess, validating the CLI
//! contract that Python's BatchRunner depends on.

use std::path::PathBuf;
use std::process::Command;

/// Path to the compiled binary (assumes `cargo build` has been run).
fn binary_path() -> PathBuf {
    let mut path = PathBuf::from(env!("CARGO_MANIFEST_DIR"));
    path.pop(); // crates/
    path.pop(); // src/rust/
    path.push("target");
    path.push("debug");
    if cfg!(windows) {
        path.push("forex_backtester.exe");
    } else {
        path.push("forex_backtester");
    }
    path
}

/// Project root for finding test fixtures.
fn project_root() -> PathBuf {
    let mut path = PathBuf::from(env!("CARGO_MANIFEST_DIR"));
    path.pop(); // crates/
    path.pop(); // src/rust/
    path.pop(); // src/
    path
}

#[test]
fn test_help_flag() {
    let output = Command::new(binary_path())
        .arg("--help")
        .output()
        .expect("failed to run binary");

    assert!(output.status.success());
    let stdout = String::from_utf8_lossy(&output.stdout);
    assert!(stdout.contains("--spec"));
    assert!(stdout.contains("--data"));
    assert!(stdout.contains("--cost-model"));
    assert!(stdout.contains("--output"));
    assert!(stdout.contains("--config-hash"));
    assert!(stdout.contains("--memory-budget"));
    assert!(stdout.contains("--fold-boundaries"));
    assert!(stdout.contains("--param-batch"));
}

#[test]
fn test_missing_required_args() {
    let output = Command::new(binary_path())
        .output()
        .expect("failed to run binary");

    assert!(!output.status.success());
    let stderr = String::from_utf8_lossy(&output.stderr);
    // clap should report missing required arguments
    assert!(
        stderr.contains("required") || stderr.contains("Usage"),
        "Expected usage/required error, got: {stderr}"
    );
}

#[test]
fn test_nonexistent_spec_file() {
    let dir = std::env::temp_dir().join("test_cli_bad_spec");
    let _ = std::fs::remove_dir_all(&dir);
    std::fs::create_dir_all(&dir).unwrap();

    // Create a dummy data file and cost model
    let data = dir.join("data.arrow");
    std::fs::write(&data, b"stub").unwrap();
    let cost = dir.join("cost.json");
    std::fs::write(&cost, br#"{"pair":"EURUSD","version":"v001","source":"research","calibrated_at":"2026-03-15T00:00:00Z","sessions":{"asian":{"mean_spread_pips":1.2,"std_spread":0.4,"mean_slippage_pips":0.1,"std_slippage":0.05},"london":{"mean_spread_pips":0.8,"std_spread":0.3,"mean_slippage_pips":0.05,"std_slippage":0.03},"london_ny_overlap":{"mean_spread_pips":0.6,"std_spread":0.2,"mean_slippage_pips":0.03,"std_slippage":0.02},"new_york":{"mean_spread_pips":0.9,"std_spread":0.3,"mean_slippage_pips":0.06,"std_slippage":0.03},"off_hours":{"mean_spread_pips":1.5,"std_spread":0.6,"mean_slippage_pips":0.15,"std_slippage":0.08}}}"#).unwrap();

    let output = Command::new(binary_path())
        .args([
            "--spec", dir.join("nonexistent.toml").to_str().unwrap(),
            "--data", data.to_str().unwrap(),
            "--cost-model", cost.to_str().unwrap(),
            "--output", dir.join("out").to_str().unwrap(),
            "--config-hash", "test",
            "--memory-budget", "256",
        ])
        .output()
        .expect("failed to run binary");

    assert!(!output.status.success());
    let stderr = String::from_utf8_lossy(&output.stderr);
    // Should have structured JSON error on stderr
    assert!(
        stderr.contains("error_type") || stderr.contains("not found"),
        "Expected structured error about missing spec, got: {stderr}"
    );

    std::fs::remove_dir_all(&dir).ok();
}

#[test]
fn test_successful_run_with_valid_inputs() {
    let root = project_root();
    let spec = root.join("artifacts").join("strategies").join("ma-crossover").join("v001.toml");
    if !spec.exists() {
        // Skip if fixture doesn't exist (CI environment)
        return;
    }

    let dir = std::env::temp_dir().join("test_cli_success");
    let _ = std::fs::remove_dir_all(&dir);
    std::fs::create_dir_all(&dir).unwrap();

    // Create dummy inputs
    let data = dir.join("data.arrow");
    std::fs::write(&data, b"ARROW_STUB").unwrap();
    let cost = dir.join("cost.json");
    std::fs::write(&cost, br#"{"pair":"EURUSD","version":"v001","source":"research","calibrated_at":"2026-03-15T00:00:00Z","sessions":{"asian":{"mean_spread_pips":1.2,"std_spread":0.4,"mean_slippage_pips":0.1,"std_slippage":0.05},"london":{"mean_spread_pips":0.8,"std_spread":0.3,"mean_slippage_pips":0.05,"std_slippage":0.03},"london_ny_overlap":{"mean_spread_pips":0.6,"std_spread":0.2,"mean_slippage_pips":0.03,"std_slippage":0.02},"new_york":{"mean_spread_pips":0.9,"std_spread":0.3,"mean_slippage_pips":0.06,"std_slippage":0.03},"off_hours":{"mean_spread_pips":1.5,"std_spread":0.6,"mean_slippage_pips":0.15,"std_slippage":0.08}}}"#).unwrap();

    let out = dir.join("output");

    let output = Command::new(binary_path())
        .args([
            "--spec", spec.to_str().unwrap(),
            "--data", data.to_str().unwrap(),
            "--cost-model", cost.to_str().unwrap(),
            "--output", out.to_str().unwrap(),
            "--config-hash", "cli_test_hash",
            "--memory-budget", "256",
        ])
        .output()
        .expect("failed to run binary");

    assert!(output.status.success(), "Binary failed: {}", String::from_utf8_lossy(&output.stderr));

    // Verify output files
    assert!(out.join("trade-log.arrow").exists());
    assert!(out.join("equity-curve.arrow").exists());
    assert!(out.join("metrics.arrow").exists());
    assert!(out.join("progress.json").exists());
    assert!(out.join("run_metadata.json").exists());

    // Verify no .partial files
    let partials: Vec<_> = std::fs::read_dir(&out)
        .unwrap()
        .filter_map(|e| e.ok())
        .filter(|e| e.file_name().to_string_lossy().ends_with(".partial"))
        .collect();
    assert!(partials.is_empty(), "Partial files remain: {:?}", partials);

    std::fs::remove_dir_all(&dir).ok();
}
