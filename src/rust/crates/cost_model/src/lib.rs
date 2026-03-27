mod cost_engine;
mod error;
mod loader;
mod types;

pub use error::CostModelError;
pub use loader::{load_from_file, load_from_str};
pub use types::{
    CostModel, CostModelArtifact, CostProfile, Direction, ASIAN, EXPECTED_SESSIONS,
    LONDON, LONDON_NY_OVERLAP, NEW_YORK, OFF_HOURS, PIP_VALUE,
};

#[cfg(test)]
mod tests {
    use super::*;

    /// Valid EURUSD artifact JSON matching Story 2.6 default values.
    fn valid_artifact_json() -> String {
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
        .to_string()
    }

    /// Helper to replace a key-value in the JSON string.
    fn replace_field(json: &str, field: &str, new_value: &str) -> String {
        // Find "field": <value> and replace the value
        let pattern = format!("\"{field}\": ");
        if let Some(start) = json.find(&pattern) {
            let value_start = start + pattern.len();
            let rest = &json[value_start..];
            // Determine end of the value (handle strings, numbers, objects)
            let value_end = if rest.starts_with('"') {
                // String value — find closing quote
                let inner = &rest[1..];
                1 + inner.find('"').unwrap() + 1
            } else if rest.starts_with('{') {
                // Object — find matching brace
                let mut depth = 0;
                let mut end = 0;
                for (i, c) in rest.char_indices() {
                    match c {
                        '{' => depth += 1,
                        '}' => {
                            depth -= 1;
                            if depth == 0 {
                                end = i + 1;
                                break;
                            }
                        }
                        _ => {}
                    }
                }
                end
            } else {
                // Number or other — find comma, whitespace, or closing brace
                rest.find(|c: char| c == ',' || c == '}' || c == '\n')
                    .unwrap_or(rest.len())
            };
            format!(
                "{}{}{}{}",
                &json[..value_start],
                new_value,
                &json[value_start + value_end..],
                ""
            )
        } else {
            json.to_string()
        }
    }

    // ==================== Loader Tests ====================

    #[test]
    fn test_load_valid_artifact() {
        let model = load_from_str(&valid_artifact_json()).expect("should load valid artifact");
        assert_eq!(model.pair(), "EURUSD");
        assert_eq!(model.version(), "v001");
        assert_eq!(model.source(), "research");
        assert_eq!(model.calibrated_at(), "2026-03-15T00:00:00Z");
        assert_eq!(model.sessions().len(), 5);
    }

    #[test]
    fn test_load_invalid_missing_session() {
        // Remove off_hours session
        let json = valid_artifact_json().replace(
            r#""off_hours":         { "mean_spread_pips": 1.5, "std_spread": 0.6, "mean_slippage_pips": 0.15, "std_slippage": 0.08 }"#,
            "",
        );
        // Clean up trailing comma
        let json = json.replace(
            r#""new_york":          { "mean_spread_pips": 0.9, "std_spread": 0.3, "mean_slippage_pips": 0.06, "std_slippage": 0.03 },"#,
            r#""new_york":          { "mean_spread_pips": 0.9, "std_spread": 0.3, "mean_slippage_pips": 0.06, "std_slippage": 0.03 }"#,
        );
        let err = load_from_str(&json).unwrap_err();
        let msg = err.to_string();
        assert!(
            msg.contains("missing required session") && msg.contains("off_hours"),
            "Expected missing session error, got: {msg}"
        );
    }

    #[test]
    fn test_load_invalid_negative_spread() {
        let json = valid_artifact_json().replace(
            r#""mean_spread_pips": 1.2"#,
            r#""mean_spread_pips": -0.5"#,
        );
        let err = load_from_str(&json).unwrap_err();
        let msg = err.to_string();
        assert!(
            msg.contains("non-negative") || msg.contains("negative"),
            "Expected negative value error, got: {msg}"
        );
    }

    #[test]
    fn test_load_invalid_json() {
        let err = load_from_str("{ not valid json }").unwrap_err();
        assert!(
            matches!(err, CostModelError::ParseError(_)),
            "Expected ParseError, got: {err}"
        );
    }

    #[test]
    fn test_load_missing_file() {
        let err = load_from_file(std::path::Path::new("/nonexistent/artifact.json")).unwrap_err();
        assert!(
            matches!(err, CostModelError::IoError(_)),
            "Expected IoError, got: {err}"
        );
    }

    #[test]
    fn test_load_artifact_with_metadata() {
        let json = valid_artifact_json().replace(
            r#""pair": "EURUSD""#,
            r#""pair": "EURUSD", "metadata": {"description": "test model", "data_points": 1000, "confidence_level": "high"}"#,
        );
        let model = load_from_str(&json).expect("should load artifact with metadata");
        assert_eq!(model.pair(), "EURUSD");
        let metadata = model.metadata().expect("metadata should be present");
        assert_eq!(metadata["description"], "test model");
        assert_eq!(metadata["data_points"], 1000);
        assert_eq!(metadata["confidence_level"], "high");
    }

    #[test]
    fn test_load_artifact_without_metadata() {
        // The default valid_artifact_json has no metadata field
        let model = load_from_str(&valid_artifact_json()).expect("should load without metadata");
        assert_eq!(model.pair(), "EURUSD");
        assert!(model.metadata().is_none(), "metadata should be None when not provided");
    }

    // ==================== Version Validation ====================

    #[test]
    fn test_version_format_validation() {
        // Valid versions
        let json = replace_field(&valid_artifact_json(), "version", "\"v001\"");
        assert!(load_from_str(&json).is_ok(), "v001 should be valid");

        let json = replace_field(&valid_artifact_json(), "version", "\"v999\"");
        assert!(load_from_str(&json).is_ok(), "v999 should be valid");

        let json = replace_field(&valid_artifact_json(), "version", "\"v1000\"");
        assert!(load_from_str(&json).is_err(), "v1000 should fail (exactly 3 digits required)");

        // Invalid versions
        let json = replace_field(&valid_artifact_json(), "version", "\"1\"");
        assert!(load_from_str(&json).is_err(), "\"1\" should fail");

        let json = replace_field(&valid_artifact_json(), "version", "\"v1\"");
        assert!(load_from_str(&json).is_err(), "\"v1\" should fail (too few digits)");

        let json = replace_field(&valid_artifact_json(), "version", "\"v01\"");
        assert!(load_from_str(&json).is_err(), "\"v01\" should fail (too few digits)");
    }

    // ==================== Source Validation ====================

    #[test]
    fn test_source_field_validation() {
        // Valid single source
        let json = replace_field(&valid_artifact_json(), "source", "\"research\"");
        assert!(load_from_str(&json).is_ok(), "research should be valid");

        let json = replace_field(&valid_artifact_json(), "source", "\"tick_analysis\"");
        assert!(load_from_str(&json).is_ok(), "tick_analysis should be valid");

        // Valid combined source
        let json = replace_field(
            &valid_artifact_json(),
            "source",
            "\"research+live_calibration\"",
        );
        assert!(
            load_from_str(&json).is_ok(),
            "research+live_calibration should be valid"
        );

        // Invalid source
        let json = replace_field(&valid_artifact_json(), "source", "\"invalid_source\"");
        let err = load_from_str(&json).unwrap_err();
        assert!(
            err.to_string().contains("invalid source"),
            "Expected invalid source error, got: {err}"
        );
    }

    // ==================== calibrated_at Validation ====================

    #[test]
    fn test_calibrated_at_validation() {
        // Valid
        let json = replace_field(
            &valid_artifact_json(),
            "calibrated_at",
            "\"2026-03-15T00:00:00Z\"",
        );
        assert!(load_from_str(&json).is_ok());

        // Invalid — no Z suffix
        let json = replace_field(
            &valid_artifact_json(),
            "calibrated_at",
            "\"2026-03-15T00:00:00\"",
        );
        assert!(load_from_str(&json).is_err(), "missing Z should fail");

        // Invalid — wrong format
        let json = replace_field(
            &valid_artifact_json(),
            "calibrated_at",
            "\"March 15, 2026\"",
        );
        assert!(load_from_str(&json).is_err(), "non-ISO format should fail");
    }

    // ==================== Pair Validation ====================

    #[test]
    fn test_pair_eurusd_only_v1() {
        // EURUSD passes
        let json = replace_field(&valid_artifact_json(), "pair", "\"EURUSD\"");
        assert!(load_from_str(&json).is_ok());

        // USDJPY fails with descriptive error
        let json = replace_field(&valid_artifact_json(), "pair", "\"USDJPY\"");
        let err = load_from_str(&json).unwrap_err();
        let msg = err.to_string();
        assert!(
            msg.contains("V1 only supports EURUSD") && msg.contains("pip_value"),
            "Expected V1 EURUSD-only error with pip_value explanation, got: {msg}"
        );
    }

    // ==================== CostProfile deny_unknown_fields ====================

    #[test]
    fn test_cost_profile_unknown_fields_rejected() {
        // Add an extra field to a CostProfile
        let json = valid_artifact_json().replace(
            r#""mean_spread_pips": 1.2, "std_spread": 0.4"#,
            r#""mean_spread_pips": 1.2, "std_spread": 0.4, "max_spread": 2.0"#,
        );
        let err = load_from_str(&json).unwrap_err();
        assert!(
            matches!(err, CostModelError::ParseError(_)),
            "Expected ParseError from deny_unknown_fields, got: {err}"
        );
        assert!(
            err.to_string().contains("unknown field"),
            "Error should mention unknown field, got: {err}"
        );
    }

    // ==================== Artifact deny_unknown_fields (D7 fail-loud) ====================

    /// Regression: unknown top-level artifact fields must be rejected (deny_unknown_fields).
    #[test]
    fn test_artifact_unknown_top_level_fields_rejected() {
        let json = valid_artifact_json().replace(
            r#""pair": "EURUSD""#,
            r#""pair": "EURUSD", "extra_field": "should_fail""#,
        );
        let err = load_from_str(&json).unwrap_err();
        assert!(
            matches!(err, CostModelError::ParseError(_)),
            "Expected ParseError from deny_unknown_fields on artifact, got: {err}"
        );
        assert!(
            err.to_string().contains("unknown field"),
            "Error should mention unknown field, got: {err}"
        );
    }

    // ==================== Cost Engine Tests ====================

    #[test]
    fn test_get_cost_all_sessions() {
        let model = load_from_str(&valid_artifact_json()).unwrap();
        for session in &EXPECTED_SESSIONS {
            let profile = model.get_cost(session).expect("session should exist");
            assert!(profile.mean_spread_pips >= 0.0);
            assert!(profile.std_spread >= 0.0);
            assert!(profile.mean_slippage_pips >= 0.0);
            assert!(profile.std_slippage >= 0.0);
        }
    }

    /// Regression: verify exact session-to-profile mapping so swapped sessions would be caught.
    #[test]
    fn test_get_cost_exact_session_values() {
        let model = load_from_str(&valid_artifact_json()).unwrap();

        // Asian: spread 1.2±0.4, slippage 0.1±0.05
        let asian = model.get_cost(ASIAN).unwrap();
        assert!((asian.mean_spread_pips - 1.2).abs() < 1e-10);
        assert!((asian.std_spread - 0.4).abs() < 1e-10);
        assert!((asian.mean_slippage_pips - 0.1).abs() < 1e-10);
        assert!((asian.std_slippage - 0.05).abs() < 1e-10);

        // London: spread 0.8±0.3, slippage 0.05±0.03
        let london = model.get_cost(LONDON).unwrap();
        assert!((london.mean_spread_pips - 0.8).abs() < 1e-10);
        assert!((london.std_spread - 0.3).abs() < 1e-10);
        assert!((london.mean_slippage_pips - 0.05).abs() < 1e-10);
        assert!((london.std_slippage - 0.03).abs() < 1e-10);

        // London-NY Overlap: spread 0.6±0.2, slippage 0.03±0.02
        let overlap = model.get_cost(LONDON_NY_OVERLAP).unwrap();
        assert!((overlap.mean_spread_pips - 0.6).abs() < 1e-10);
        assert!((overlap.std_spread - 0.2).abs() < 1e-10);
        assert!((overlap.mean_slippage_pips - 0.03).abs() < 1e-10);
        assert!((overlap.std_slippage - 0.02).abs() < 1e-10);

        // New York: spread 0.9±0.3, slippage 0.06±0.03
        let ny = model.get_cost(NEW_YORK).unwrap();
        assert!((ny.mean_spread_pips - 0.9).abs() < 1e-10);
        assert!((ny.std_spread - 0.3).abs() < 1e-10);
        assert!((ny.mean_slippage_pips - 0.06).abs() < 1e-10);
        assert!((ny.std_slippage - 0.03).abs() < 1e-10);

        // Off Hours: spread 1.5±0.6, slippage 0.15±0.08
        let off = model.get_cost(OFF_HOURS).unwrap();
        assert!((off.mean_spread_pips - 1.5).abs() < 1e-10);
        assert!((off.std_spread - 0.6).abs() < 1e-10);
        assert!((off.mean_slippage_pips - 0.15).abs() < 1e-10);
        assert!((off.std_slippage - 0.08).abs() < 1e-10);
    }

    #[test]
    fn test_get_cost_unknown_session() {
        let model = load_from_str(&valid_artifact_json()).unwrap();
        let err = model.get_cost("tokyo").unwrap_err();
        assert!(
            matches!(err, CostModelError::SessionNotFound(_)),
            "Expected SessionNotFound, got: {err}"
        );
    }

    #[test]
    fn test_apply_cost_buy() {
        let model = load_from_str(&valid_artifact_json()).unwrap();
        let fill_price = 1.10000;
        let adjusted = model
            .apply_cost(fill_price, LONDON, Direction::Buy)
            .unwrap();
        // London: mean_spread=0.8, mean_slippage=0.05 → total=0.85 pips
        // Cost = 0.85 * 0.0001 = 0.000085
        // Buy: price goes UP
        let expected = fill_price + 0.85 * PIP_VALUE;
        assert!(
            (adjusted - expected).abs() < 1e-10,
            "Buy adjustment incorrect: got {adjusted}, expected {expected}"
        );
    }

    #[test]
    fn test_apply_cost_sell() {
        let model = load_from_str(&valid_artifact_json()).unwrap();
        let fill_price = 1.10000;
        let adjusted = model
            .apply_cost(fill_price, LONDON, Direction::Sell)
            .unwrap();
        // Sell: price goes DOWN
        let expected = fill_price - 0.85 * PIP_VALUE;
        assert!(
            (adjusted - expected).abs() < 1e-10,
            "Sell adjustment incorrect: got {adjusted}, expected {expected}"
        );
    }

    #[test]
    fn test_apply_cost_symmetry() {
        let model = load_from_str(&valid_artifact_json()).unwrap();
        let fill_price = 1.10000;

        for session in &EXPECTED_SESSIONS {
            let buy = model
                .apply_cost(fill_price, session, Direction::Buy)
                .unwrap();
            let sell = model
                .apply_cost(fill_price, session, Direction::Sell)
                .unwrap();
            let buy_delta = (buy - fill_price).abs();
            let sell_delta = (fill_price - sell).abs();
            assert!(
                (buy_delta - sell_delta).abs() < 1e-10,
                "Session '{session}': buy and sell adjustments are not symmetric \
                 (buy_delta={buy_delta}, sell_delta={sell_delta})"
            );
        }
    }
}
