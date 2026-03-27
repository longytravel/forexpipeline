use std::io::Write;
use std::process::Command;

use cost_model::{load_from_file, EXPECTED_SESSIONS};
use tempfile::NamedTempFile;

fn valid_artifact_json() -> &'static str {
    r#"{
        "pair": "EURUSD",
        "version": "v001",
        "source": "research",
        "calibrated_at": "2026-03-15T00:00:00Z",
        "sessions": {
            "asian":             { "mean_spread_pips": 1.2, "std_spread": 0.4, "mean_slippage_pips": 0.1, "std_slippage": 0.05 },
            "london":            { "mean_spread_pips": 0.8, "std_spread": 0.3, "mean_slippage_pips": 0.05, "std_slippage": 0.03 },
            "london_ny_overlap": { "mean_spread_pips": 0.6, "std_spread": 0.2, "mean_slippage_pips": 0.03, "std_slippage": 0.02 },
            "new_york":          { "mean_spread_pips": 0.9, "std_spread": 0.3, "mean_slippage_pips": 0.06, "std_slippage": 0.03 },
            "off_hours":         { "mean_spread_pips": 1.5, "std_spread": 0.6, "mean_slippage_pips": 0.15, "std_slippage": 0.08 }
        }
    }"#
}

fn invalid_artifact_json() -> &'static str {
    r#"{ "pair": "USDJPY", "version": "v001", "source": "research", "calibrated_at": "2026-03-15T00:00:00Z", "sessions": {} }"#
}

fn write_temp_artifact(json: &str) -> NamedTempFile {
    let mut file = NamedTempFile::new().expect("create temp file");
    file.write_all(json.as_bytes())
        .expect("write to temp file");
    file.flush().expect("flush temp file");
    file
}

/// Find the cost_model_cli binary path. cargo test builds to target/debug/.
fn cli_binary_path() -> std::path::PathBuf {
    // The binary is built alongside tests in the target directory
    let mut path = std::env::current_exe()
        .expect("get current exe path")
        .parent()
        .expect("get parent dir")
        .parent()
        .expect("get target/debug dir")
        .to_path_buf();
    if cfg!(windows) {
        path.push("cost_model_cli.exe");
    } else {
        path.push("cost_model_cli");
    }
    path
}

#[test]
fn test_load_from_file() {
    let file = write_temp_artifact(valid_artifact_json());
    let model = load_from_file(file.path()).expect("should load from file");
    assert_eq!(model.pair(), "EURUSD");
    assert_eq!(model.version(), "v001");
    assert_eq!(model.sessions().len(), 5);

    for session in &EXPECTED_SESSIONS {
        assert!(
            model.get_cost(session).is_ok(),
            "session '{session}' should be present"
        );
    }
}

#[test]
fn test_cli_validate_valid() {
    let file = write_temp_artifact(valid_artifact_json());
    let output = Command::new(cli_binary_path())
        .args(["validate", file.path().to_str().unwrap()])
        .output()
        .expect("run CLI");

    assert!(
        output.status.success(),
        "CLI validate should succeed for valid artifact. stderr: {}",
        String::from_utf8_lossy(&output.stderr)
    );

    let stdout = String::from_utf8_lossy(&output.stdout);
    assert!(stdout.contains("Valid"), "Output should contain 'Valid'");
    assert!(stdout.contains("EURUSD"), "Output should contain pair");
}

#[test]
fn test_cli_validate_invalid() {
    let file = write_temp_artifact(invalid_artifact_json());
    let output = Command::new(cli_binary_path())
        .args(["validate", file.path().to_str().unwrap()])
        .output()
        .expect("run CLI");

    assert!(
        !output.status.success(),
        "CLI validate should fail for invalid artifact"
    );
    assert_eq!(
        output.status.code(),
        Some(1),
        "Exit code should be 1 for invalid artifact"
    );
}

#[test]
fn test_cli_inspect() {
    let file = write_temp_artifact(valid_artifact_json());
    let output = Command::new(cli_binary_path())
        .args(["inspect", file.path().to_str().unwrap()])
        .output()
        .expect("run CLI");

    assert!(
        output.status.success(),
        "CLI inspect should succeed. stderr: {}",
        String::from_utf8_lossy(&output.stderr)
    );

    let stdout = String::from_utf8_lossy(&output.stdout);
    assert!(stdout.contains("EURUSD"), "Should contain pair name");
    for session in &EXPECTED_SESSIONS {
        assert!(
            stdout.contains(session),
            "Should contain session '{session}'"
        );
    }
}
