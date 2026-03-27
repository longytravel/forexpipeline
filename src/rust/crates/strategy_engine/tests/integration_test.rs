use std::path::PathBuf;

use strategy_engine::{
    default_registry, parse_spec_from_file, parse_spec_from_str, validate_spec, ValidatedSpec,
};

fn test_data_dir() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("tests/test_data")
}

#[test]
fn test_full_parse_and_validate_roundtrip() {
    let path = test_data_dir().join("valid_ma_crossover.toml");
    let spec = parse_spec_from_file(&path).expect("should parse valid fixture");

    // Verify key fields parsed correctly
    assert_eq!(spec.metadata.name, "ma-crossover-eurusd");
    assert_eq!(spec.metadata.pair, "EURUSD");
    assert_eq!(spec.metadata.timeframe, "H1");
    assert_eq!(spec.entry_rules.conditions.len(), 1);
    assert_eq!(spec.entry_rules.filters.len(), 2);
    assert_eq!(spec.entry_rules.confirmation.len(), 1);
    assert!(spec.exit_rules.trailing.is_some());
    match &spec.optimization_plan {
        strategy_engine::OptimizationPlan::V1(v1) => {
            assert_eq!(v1.parameter_groups.len(), 1);
        }
        _ => panic!("Expected V1 optimization plan in fixture"),
    }
    assert_eq!(spec.cost_model_reference.version, "v001");

    // Validate
    let registry = default_registry();
    let result = validate_spec(&spec, &registry, None);
    assert!(result.is_ok(), "Valid fixture should validate: {result:?}");

    let validated: ValidatedSpec = result.unwrap();
    assert_eq!(validated.spec().metadata.name, "ma-crossover-eurusd");
}

#[test]
fn test_parse_invalid_unknown_indicator_fixture() {
    let path = test_data_dir().join("invalid_unknown_indicator.toml");
    let spec = parse_spec_from_file(&path).expect("should parse structurally valid TOML");

    let registry = default_registry();
    let result = validate_spec(&spec, &registry, None);
    assert!(result.is_err(), "Should fail validation");
    let errs = result.unwrap_err();
    assert!(
        errs.iter().any(|e| e.reason.contains("supertrend")),
        "Should mention unknown indicator: {errs:?}"
    );
}

#[test]
fn test_parse_invalid_bad_params_fixture() {
    let path = test_data_dir().join("invalid_bad_params.toml");
    let spec = parse_spec_from_file(&path).expect("should parse structurally valid TOML");

    let registry = default_registry();
    let result = validate_spec(&spec, &registry, None);
    assert!(result.is_err(), "Should fail validation");
    let errs = result.unwrap_err();
    // period=0 and step=0 should both be flagged
    assert!(
        errs.iter().any(|e| e.reason.contains("must be > 0")),
        "Should flag out-of-range param: {errs:?}"
    );
}

#[test]
fn test_parse_invalid_missing_fields_fixture() {
    let path = test_data_dir().join("invalid_missing_fields.toml");
    // This file has no conditions array — TOML deserialization requires Vec<Condition>
    // which defaults to empty via serde default, but our struct doesn't have default
    // for conditions. Let's check what happens.
    let result = parse_spec_from_file(&path);
    match result {
        Ok(spec) => {
            // If parsing succeeds (conditions defaults to empty), validation should catch it
            let registry = default_registry();
            let val_result = validate_spec(&spec, &registry, None);
            assert!(val_result.is_err(), "Empty conditions should fail validation");
            let errs = val_result.unwrap_err();
            assert!(
                errs.iter()
                    .any(|e| e.reason.contains("at least one entry condition")),
                "Should require conditions: {errs:?}"
            );
        }
        Err(e) => {
            // Parse error is also acceptable — missing required field
            assert!(
                e.to_string().contains("Parse error"),
                "Should be a parse error: {e}"
            );
        }
    }
}

#[test]
fn test_parse_invalid_bad_session_fixture() {
    let path = test_data_dir().join("invalid_bad_session.toml");
    let spec = parse_spec_from_file(&path).expect("should parse structurally valid TOML");

    let registry = default_registry();
    let result = validate_spec(&spec, &registry, None);
    assert!(result.is_err(), "Should fail validation");
    let errs = result.unwrap_err();
    assert!(
        errs.iter().any(|e| e.reason.contains("tokyo")),
        "Should mention invalid session 'tokyo': {errs:?}"
    );
}

#[test]
fn test_parse_invalid_multi_error_fixture() {
    let path = test_data_dir().join("invalid_multi_error.toml");
    let spec = parse_spec_from_file(&path).expect("should parse structurally valid TOML");

    let registry = default_registry();
    let result = validate_spec(&spec, &registry, None);
    assert!(result.is_err(), "Should fail validation");
    let errs = result.unwrap_err();
    // Should collect ALL errors, not fail on first
    assert!(
        errs.len() >= 3,
        "Should have at least 3 distinct errors, got {}: {errs:?}",
        errs.len()
    );
    // Verify specific errors present
    assert!(errs.iter().any(|e| e.reason.contains("timeframe")), "Missing timeframe error");
    assert!(
        errs.iter().any(|e| e.reason.contains("unknown indicator")),
        "Missing unknown indicator error"
    );
    assert!(errs.iter().any(|e| e.reason.contains("tokyo")), "Missing session error");
    assert!(
        errs.iter().any(|e| e.reason.contains("max_lots")),
        "Missing max_lots error"
    );
    assert!(
        errs.iter().any(|e| e.reason.contains("objective")),
        "Missing objective error"
    );
}

#[test]
fn test_cargo_workspace_dependency_graph() {
    // Verify strategy_engine depends on common and cost_model only
    let cargo_toml =
        std::fs::read_to_string(PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("Cargo.toml"))
            .expect("should read Cargo.toml");

    // Should have common and cost_model dependencies
    assert!(
        cargo_toml.contains("common = { path = \"../common\" }"),
        "Should depend on common"
    );
    assert!(
        cargo_toml.contains("cost_model = { path = \"../cost_model\" }"),
        "Should depend on cost_model"
    );

    // Should NOT depend on backtester, optimizer, validator, or live_daemon
    assert!(
        !cargo_toml.contains("backtester"),
        "Should NOT depend on backtester"
    );
    assert!(
        !cargo_toml.contains("optimizer"),
        "Should NOT depend on optimizer"
    );
    assert!(
        !cargo_toml.contains("live_daemon"),
        "Should NOT depend on live_daemon"
    );
}

#[test]
fn test_validated_spec_serialization() {
    // Ensure ValidationError can be serialized to JSON (for Story 2.9 evidence packs)
    let path = test_data_dir().join("invalid_multi_error.toml");
    let spec = parse_spec_from_file(&path).unwrap();
    let registry = default_registry();
    let result = validate_spec(&spec, &registry, None);
    let errs = result.unwrap_err();

    let json = serde_json::to_string_pretty(&errs).expect("ValidationErrors should serialize");
    assert!(json.contains("section"));
    assert!(json.contains("field"));
    assert!(json.contains("reason"));
    assert!(json.contains("severity"));
}

#[test]
fn test_parse_and_reserialize_roundtrip() {
    let path = test_data_dir().join("valid_ma_crossover.toml");
    let spec = parse_spec_from_file(&path).expect("should parse");

    // Serialize back to TOML
    let toml_str = toml::to_string_pretty(&spec).expect("should serialize");

    // Re-parse the serialized TOML
    let spec2 = parse_spec_from_str(&toml_str).expect("round-trip should parse");
    assert_eq!(spec2.metadata.name, spec.metadata.name);
    assert_eq!(spec2.entry_rules.conditions.len(), spec.entry_rules.conditions.len());
}
