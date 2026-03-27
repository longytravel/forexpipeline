//! E2E integration tests for cost_model crate (Story 2-9).
//!
//! These tests load the REAL EURUSD cost model artifact from the project's
//! artifacts directory and verify the crate can parse, validate, and apply
//! costs correctly.

use std::path::PathBuf;

use cost_model::{load_from_file, Direction, EXPECTED_SESSIONS, PIP_VALUE};

/// Get project root by navigating up from CARGO_MANIFEST_DIR.
fn project_root() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .ancestors()
        .nth(4)
        .expect("Could not find project root")
        .to_path_buf()
}

/// Path to the real EURUSD cost model artifact.
fn eurusd_artifact_path() -> PathBuf {
    project_root().join("artifacts/cost_models/EURUSD/v001.json")
}

#[test]
fn test_e2e_load_eurusd_artifact() {
    let path = eurusd_artifact_path();
    assert!(path.exists(), "EURUSD artifact not found at {:?}", path);

    let model = load_from_file(&path).expect("Failed to load EURUSD cost model");

    // Verify artifact metadata
    assert_eq!(model.pair(), "EURUSD");
    assert_eq!(model.version(), "v001");
    assert_eq!(model.source(), "research");
    assert!(!model.calibrated_at().is_empty());

    // All 5 sessions present
    let sessions = model.sessions();
    for expected in &EXPECTED_SESSIONS {
        assert!(
            sessions.contains_key(*expected),
            "Missing session: {}",
            expected
        );
    }
    assert_eq!(sessions.len(), 5);
}

#[test]
fn test_e2e_session_cost_lookup() {
    let path = eurusd_artifact_path();
    let model = load_from_file(&path).expect("Failed to load EURUSD cost model");

    // Verify each session returns valid profiles with specific expected values
    for session in &EXPECTED_SESSIONS {
        let profile = model
            .get_cost(session)
            .unwrap_or_else(|e| panic!("get_cost({}) failed: {}", session, e));

        // All values must be positive
        assert!(
            profile.mean_spread_pips > 0.0,
            "{}: mean_spread_pips not positive",
            session
        );
        assert!(
            profile.std_spread > 0.0,
            "{}: std_spread not positive",
            session
        );
        assert!(
            profile.mean_slippage_pips > 0.0,
            "{}: mean_slippage_pips not positive",
            session
        );
        assert!(
            profile.std_slippage > 0.0,
            "{}: std_slippage not positive",
            session
        );
    }

    // Verify specific known values for london session
    let london = model.get_cost("london").unwrap();
    assert!(
        (london.mean_spread_pips - 0.8).abs() < 0.01,
        "London mean_spread_pips expected ~0.8, got {}",
        london.mean_spread_pips
    );
    assert!(
        (london.mean_slippage_pips - 0.05).abs() < 0.01,
        "London mean_slippage_pips expected ~0.05, got {}",
        london.mean_slippage_pips
    );

    // Unknown session should error
    assert!(model.get_cost("nonexistent").is_err());
}

#[test]
fn test_e2e_apply_cost_buy_sell() {
    let path = eurusd_artifact_path();
    let model = load_from_file(&path).expect("Failed to load EURUSD cost model");

    let fill_price = 1.10000_f64;

    // Buy: adjusted price should be HIGHER (spread + slippage added)
    let buy_price = model
        .apply_cost(fill_price, "london", Direction::Buy)
        .expect("apply_cost Buy failed");
    assert!(
        buy_price > fill_price,
        "Buy adjusted price {} should be > fill price {}",
        buy_price,
        fill_price
    );

    // Sell: adjusted price should be LOWER (spread + slippage subtracted)
    let sell_price = model
        .apply_cost(fill_price, "london", Direction::Sell)
        .expect("apply_cost Sell failed");
    assert!(
        sell_price < fill_price,
        "Sell adjusted price {} should be < fill price {}",
        sell_price,
        fill_price
    );

    // Cost magnitude should be reasonable (< 10 pips for EURUSD london)
    let buy_cost_pips = (buy_price - fill_price) / PIP_VALUE;
    assert!(
        buy_cost_pips < 10.0 && buy_cost_pips > 0.0,
        "Buy cost {} pips out of reasonable range",
        buy_cost_pips
    );

    let sell_cost_pips = (fill_price - sell_price) / PIP_VALUE;
    assert!(
        sell_cost_pips < 10.0 && sell_cost_pips > 0.0,
        "Sell cost {} pips out of reasonable range",
        sell_cost_pips
    );

    // All 5 sessions should work without panics
    for session in &EXPECTED_SESSIONS {
        let _ = model
            .apply_cost(fill_price, session, Direction::Buy)
            .unwrap_or_else(|e| panic!("apply_cost Buy for {} failed: {}", session, e));
        let _ = model
            .apply_cost(fill_price, session, Direction::Sell)
            .unwrap_or_else(|e| panic!("apply_cost Sell for {} failed: {}", session, e));
    }
}
