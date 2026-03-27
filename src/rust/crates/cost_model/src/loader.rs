use std::fs;
use std::path::Path;

use crate::error::CostModelError;
use crate::types::{CostModel, CostModelArtifact, CostProfile, EXPECTED_SESSIONS};

/// Valid source values for the cost model artifact.
const VALID_SOURCES: [&str; 3] = ["research", "tick_analysis", "live_calibration"];

/// Load a cost model artifact from a JSON file on disk.
pub fn load_from_file(path: &Path) -> Result<CostModel, CostModelError> {
    let json = fs::read_to_string(path)?;
    load_from_str(&json)
}

/// Load a cost model artifact from a JSON string (useful for testing).
pub fn load_from_str(json: &str) -> Result<CostModel, CostModelError> {
    let artifact: CostModelArtifact =
        serde_json::from_str(json).map_err(CostModelError::ParseError)?;
    validate(&artifact)?;
    Ok(CostModel { artifact })
}

/// Validate a deserialized artifact. Fail-loud on ANY issue (D7 pattern).
fn validate(artifact: &CostModelArtifact) -> Result<(), CostModelError> {
    // Pair must be non-empty
    if artifact.pair.is_empty() {
        return Err(CostModelError::ValidationError(
            "pair field is empty".to_string(),
        ));
    }

    // V1: only EURUSD supported (pip_value hardcoded to 0.0001)
    if artifact.pair != "EURUSD" {
        return Err(CostModelError::ValidationError(format!(
            "V1 only supports EURUSD (pip_value is hardcoded to 0.0001; \
             JPY pairs require 0.01). Got pair: '{}'",
            artifact.pair
        )));
    }

    // Version must match v\d{3} pattern (e.g., v001, v999)
    validate_version(&artifact.version)?;

    // Source must be valid
    validate_source(&artifact.source)?;

    // calibrated_at must be valid ISO 8601
    validate_calibrated_at(&artifact.calibrated_at)?;

    // Sessions must contain exactly the 5 expected keys
    validate_sessions(&artifact.sessions)?;

    Ok(())
}

fn validate_version(version: &str) -> Result<(), CostModelError> {
    if version.len() < 2 {
        return Err(CostModelError::ValidationError(format!(
            "version must match pattern v\\d{{3}} (e.g., v001). Got: '{version}'"
        )));
    }

    let (prefix, digits) = version.split_at(1);
    if prefix != "v" || digits.is_empty() || digits.len() != 3 || !digits.chars().all(|c| c.is_ascii_digit()) {
        return Err(CostModelError::ValidationError(format!(
            "version must match pattern v\\d{{3}} (e.g., v001). Got: '{version}'"
        )));
    }

    Ok(())
}

fn validate_source(source: &str) -> Result<(), CostModelError> {
    if source.is_empty() {
        return Err(CostModelError::ValidationError(
            "source field is empty".to_string(),
        ));
    }

    // Source can be a single value or '+'-separated combination
    for part in source.split('+') {
        if !VALID_SOURCES.contains(&part) {
            return Err(CostModelError::ValidationError(format!(
                "invalid source component: '{}'. Valid sources: {:?}",
                part, VALID_SOURCES
            )));
        }
    }

    Ok(())
}

fn validate_calibrated_at(calibrated_at: &str) -> Result<(), CostModelError> {
    // Validate ISO 8601 format: YYYY-MM-DDTHH:MM:SSZ
    let bytes = calibrated_at.as_bytes();

    // Check length and fixed characters
    if bytes.len() != 20
        || bytes[4] != b'-'
        || bytes[7] != b'-'
        || bytes[10] != b'T'
        || bytes[13] != b':'
        || bytes[16] != b':'
        || bytes[19] != b'Z'
    {
        return Err(CostModelError::ValidationError(format!(
            "calibrated_at must be ISO 8601 format (YYYY-MM-DDTHH:MM:SSZ). Got: '{calibrated_at}'"
        )));
    }

    // Check digit positions
    let digit_positions = [0, 1, 2, 3, 5, 6, 8, 9, 11, 12, 14, 15, 17, 18];
    for &pos in &digit_positions {
        if !bytes[pos].is_ascii_digit() {
            return Err(CostModelError::ValidationError(format!(
                "calibrated_at must be ISO 8601 format (YYYY-MM-DDTHH:MM:SSZ). Got: '{calibrated_at}'"
            )));
        }
    }

    Ok(())
}

fn validate_sessions(
    sessions: &std::collections::BTreeMap<String, CostProfile>,
) -> Result<(), CostModelError> {
    // Check for exactly the expected session keys
    for expected in &EXPECTED_SESSIONS {
        if !sessions.contains_key(*expected) {
            return Err(CostModelError::ValidationError(format!(
                "missing required session: '{expected}'. \
                 Expected sessions: {EXPECTED_SESSIONS:?}"
            )));
        }
    }

    if sessions.len() != EXPECTED_SESSIONS.len() {
        let unexpected: Vec<&String> = sessions
            .keys()
            .filter(|k| !EXPECTED_SESSIONS.contains(&k.as_str()))
            .collect();
        return Err(CostModelError::ValidationError(format!(
            "unexpected session keys: {unexpected:?}. \
             Expected exactly: {EXPECTED_SESSIONS:?}"
        )));
    }

    // Validate each CostProfile
    for (session, profile) in sessions {
        validate_cost_profile(session, profile)?;
    }

    Ok(())
}

fn validate_cost_profile(session: &str, profile: &CostProfile) -> Result<(), CostModelError> {
    let fields = [
        ("mean_spread_pips", profile.mean_spread_pips),
        ("std_spread", profile.std_spread),
        ("mean_slippage_pips", profile.mean_slippage_pips),
        ("std_slippage", profile.std_slippage),
    ];

    for (name, value) in &fields {
        if !value.is_finite() {
            return Err(CostModelError::ValidationError(format!(
                "session '{session}': {name} must be finite, got {value}"
            )));
        }
        if *value < 0.0 {
            return Err(CostModelError::ValidationError(format!(
                "session '{session}': {name} must be non-negative, got {value}"
            )));
        }
    }

    Ok(())
}
