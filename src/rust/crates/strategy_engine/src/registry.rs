use std::collections::BTreeMap;

use crate::types::IndicatorParams;
use crate::validator::ValidationError;

/// Definition of an indicator's parameter signature.
#[derive(Debug, Clone)]
pub struct ParamDef {
    pub name: String,
    pub param_type: ParamType,
    pub required: bool,
    pub min: Option<f64>,
    pub max: Option<f64>,
}

/// Types of indicator parameters.
#[derive(Debug, Clone)]
pub enum ParamType {
    /// Integer period (deserialized as toml integer, validated as > 0).
    Period,
    /// Floating-point multiplier/coefficient.
    Multiplier,
    /// String enum value (e.g., price_source).
    StringEnum(Vec<String>),
}

/// Definition of a registered indicator.
#[derive(Debug, Clone)]
pub struct IndicatorDef {
    pub name: String,
    pub category: String,
    pub description: String,
    pub params: Vec<ParamDef>,
}

/// Registry of all supported indicator types.
///
/// Uses BTreeMap for deterministic iteration order (reproducible validation output).
#[derive(Debug, Clone)]
pub struct IndicatorRegistry {
    indicators: BTreeMap<String, IndicatorDef>,
}

impl IndicatorRegistry {
    /// Create an empty registry.
    pub fn new() -> Self {
        Self {
            indicators: BTreeMap::new(),
        }
    }

    /// Look up an indicator definition by name.
    pub fn get(&self, name: &str) -> Option<&IndicatorDef> {
        self.indicators.get(name)
    }

    /// Register a new indicator definition. Enables extensibility for future indicators.
    pub fn register(&mut self, key: &str, def: IndicatorDef) {
        self.indicators.insert(key.to_string(), def);
    }

    /// Return all registered indicator keys in sorted order.
    pub fn indicator_names(&self) -> Vec<&str> {
        self.indicators.keys().map(|s| s.as_str()).collect()
    }

    /// Validate indicator parameters against this registry.
    /// Returns a list of validation errors (empty if valid).
    pub fn validate_params(
        &self,
        indicator_name: &str,
        params: &IndicatorParams,
        section: &str,
        field_prefix: &str,
    ) -> Vec<ValidationError> {
        let mut errors = Vec::new();

        let Some(def) = self.indicators.get(indicator_name) else {
            errors.push(ValidationError {
                section: section.to_string(),
                field: format!("{field_prefix}.indicator"),
                reason: format!(
                    "unknown indicator '{indicator_name}'. Known: {:?}",
                    self.indicator_names()
                ),
                severity: crate::validator::Severity::Error,
            });
            return errors;
        };

        // Check required params are present
        for param_def in &def.params {
            if param_def.required && !params.contains_key(&param_def.name) {
                errors.push(ValidationError {
                    section: section.to_string(),
                    field: format!("{field_prefix}.parameters.{}", param_def.name),
                    reason: format!(
                        "required parameter '{}' missing for indicator '{indicator_name}'",
                        param_def.name
                    ),
                    severity: crate::validator::Severity::Error,
                });
            }
        }

        // Check each provided param is known and has valid value
        let known_param_names: Vec<&str> = def.params.iter().map(|p| p.name.as_str()).collect();
        for (key, value) in params {
            if !known_param_names.contains(&key.as_str()) {
                errors.push(ValidationError {
                    section: section.to_string(),
                    field: format!("{field_prefix}.parameters.{key}"),
                    reason: format!(
                        "unknown parameter '{key}' for indicator '{indicator_name}'. Known: {known_param_names:?}"
                    ),
                    severity: crate::validator::Severity::Error,
                });
                continue;
            }

            let param_def = def.params.iter().find(|p| p.name == *key).unwrap();
            validate_param_value(param_def, key, value, indicator_name, section, field_prefix, &mut errors);
        }

        errors
    }
}

fn validate_param_value(
    param_def: &ParamDef,
    key: &str,
    value: &toml::Value,
    indicator_name: &str,
    section: &str,
    field_prefix: &str,
    errors: &mut Vec<ValidationError>,
) {
    match &param_def.param_type {
        ParamType::Period => {
            if let Some(v) = value.as_integer() {
                if v <= 0 {
                    errors.push(ValidationError {
                        section: section.to_string(),
                        field: format!("{field_prefix}.parameters.{key}"),
                        reason: format!(
                            "parameter '{key}' for '{indicator_name}' must be > 0, got {v}"
                        ),
                        severity: crate::validator::Severity::Error,
                    });
                }
                if let Some(min) = param_def.min {
                    if (v as f64) < min {
                        errors.push(ValidationError {
                            section: section.to_string(),
                            field: format!("{field_prefix}.parameters.{key}"),
                            reason: format!(
                                "parameter '{key}' for '{indicator_name}' must be >= {min}, got {v}"
                            ),
                            severity: crate::validator::Severity::Error,
                        });
                    }
                }
                if let Some(max) = param_def.max {
                    if (v as f64) > max {
                        errors.push(ValidationError {
                            section: section.to_string(),
                            field: format!("{field_prefix}.parameters.{key}"),
                            reason: format!(
                                "parameter '{key}' for '{indicator_name}' must be <= {max}, got {v}"
                            ),
                            severity: crate::validator::Severity::Error,
                        });
                    }
                }
            } else {
                errors.push(ValidationError {
                    section: section.to_string(),
                    field: format!("{field_prefix}.parameters.{key}"),
                    reason: format!(
                        "parameter '{key}' for '{indicator_name}' must be an integer, got {value}"
                    ),
                    severity: crate::validator::Severity::Error,
                });
            }
        }
        ParamType::Multiplier => {
            let fval = value.as_float().or_else(|| value.as_integer().map(|i| i as f64));
            if let Some(v) = fval {
                if let Some(min) = param_def.min {
                    if v < min {
                        errors.push(ValidationError {
                            section: section.to_string(),
                            field: format!("{field_prefix}.parameters.{key}"),
                            reason: format!(
                                "parameter '{key}' for '{indicator_name}' must be >= {min}, got {v}"
                            ),
                            severity: crate::validator::Severity::Error,
                        });
                    }
                }
                if let Some(max) = param_def.max {
                    if v > max {
                        errors.push(ValidationError {
                            section: section.to_string(),
                            field: format!("{field_prefix}.parameters.{key}"),
                            reason: format!(
                                "parameter '{key}' for '{indicator_name}' must be <= {max}, got {v}"
                            ),
                            severity: crate::validator::Severity::Error,
                        });
                    }
                }
            } else {
                errors.push(ValidationError {
                    section: section.to_string(),
                    field: format!("{field_prefix}.parameters.{key}"),
                    reason: format!(
                        "parameter '{key}' for '{indicator_name}' must be a number, got {value}"
                    ),
                    severity: crate::validator::Severity::Error,
                });
            }
        }
        ParamType::StringEnum(allowed) => {
            if let Some(s) = value.as_str() {
                if !allowed.contains(&s.to_string()) {
                    errors.push(ValidationError {
                        section: section.to_string(),
                        field: format!("{field_prefix}.parameters.{key}"),
                        reason: format!(
                            "parameter '{key}' for '{indicator_name}' must be one of {allowed:?}, got '{s}'"
                        ),
                        severity: crate::validator::Severity::Error,
                    });
                }
            } else {
                errors.push(ValidationError {
                    section: section.to_string(),
                    field: format!("{field_prefix}.parameters.{key}"),
                    reason: format!(
                        "parameter '{key}' for '{indicator_name}' must be a string, got {value}"
                    ),
                    severity: crate::validator::Severity::Error,
                });
            }
        }
    }
}

/// Create the default registry with V1 indicators (D10 minimum representable constructs).
/// Indicator names match contracts/indicator_registry.toml keys.
pub fn default_registry() -> IndicatorRegistry {
    let mut reg = IndicatorRegistry::new();

    // Trend: SMA
    reg.register("sma", IndicatorDef {
        name: "SMA".to_string(),
        category: "trend".to_string(),
        description: "Simple Moving Average".to_string(),
        params: vec![
            ParamDef {
                name: "period".to_string(),
                param_type: ParamType::Period,
                required: true,
                min: Some(1.0),
                max: Some(1000.0),
            },
        ],
    });

    // Trend: EMA
    reg.register("ema", IndicatorDef {
        name: "EMA".to_string(),
        category: "trend".to_string(),
        description: "Exponential Moving Average".to_string(),
        params: vec![
            ParamDef {
                name: "period".to_string(),
                param_type: ParamType::Period,
                required: true,
                min: Some(1.0),
                max: Some(1000.0),
            },
        ],
    });

    // Volatility: ATR
    reg.register("atr", IndicatorDef {
        name: "ATR".to_string(),
        category: "volatility".to_string(),
        description: "Average True Range (Wilder's smoothing)".to_string(),
        params: vec![
            ParamDef {
                name: "period".to_string(),
                param_type: ParamType::Period,
                required: true,
                min: Some(1.0),
                max: Some(1000.0),
            },
        ],
    });

    // Volatility: Bollinger Bands
    reg.register("bollinger_bands", IndicatorDef {
        name: "Bollinger Bands".to_string(),
        category: "volatility".to_string(),
        description: "Bollinger Bands (middle, upper, lower)".to_string(),
        params: vec![
            ParamDef {
                name: "period".to_string(),
                param_type: ParamType::Period,
                required: true,
                min: Some(1.0),
                max: Some(1000.0),
            },
            ParamDef {
                name: "num_std".to_string(),
                param_type: ParamType::Multiplier,
                required: true,
                min: Some(0.1),
                max: Some(10.0),
            },
        ],
    });

    // Trend: SMA Crossover
    reg.register("sma_crossover", IndicatorDef {
        name: "SMA Crossover".to_string(),
        category: "trend".to_string(),
        description: "SMA fast/slow crossover signal".to_string(),
        params: vec![
            ParamDef {
                name: "fast_period".to_string(),
                param_type: ParamType::Period,
                required: true,
                min: Some(1.0),
                max: Some(500.0),
            },
            ParamDef {
                name: "slow_period".to_string(),
                param_type: ParamType::Period,
                required: true,
                min: Some(1.0),
                max: Some(1000.0),
            },
        ],
    });

    // Price Action: Hidden Smash Day
    reg.register("hidden_smash_day", IndicatorDef {
        name: "Hidden Smash Day".to_string(),
        category: "price_action".to_string(),
        description: "Larry Williams Hidden Smash Day reversal pattern".to_string(),
        params: vec![
            ParamDef {
                name: "range_threshold".to_string(),
                param_type: ParamType::Multiplier,
                required: true,
                min: Some(0.05),
                max: Some(0.50),
            },
            ParamDef {
                name: "require_close_vs_open".to_string(),
                param_type: ParamType::StringEnum(vec!["true".to_string(), "false".to_string()]),
                required: false,
                min: None,
                max: None,
            },
            ParamDef {
                name: "confirmation_mode".to_string(),
                param_type: ParamType::StringEnum(vec!["immediate".to_string(), "confirmed".to_string()]),
                required: false,
                min: None,
                max: None,
            },
        ],
    });

    // Structure: Market Structure
    reg.register("market_structure", IndicatorDef {
        name: "Market Structure".to_string(),
        category: "structure".to_string(),
        description: "Market structure bias from swing sequences (HH+HL=bullish, LL+LH=bearish)".to_string(),
        params: vec![
            ParamDef {
                name: "swing_bars".to_string(),
                param_type: ParamType::Period,
                required: true,
                min: Some(1.0),
                max: Some(20.0),
            },
        ],
    });

    // Price Action: Channel Breakout (parallel channel detection + breakout)
    reg.register("channel_breakout", IndicatorDef {
        name: "Channel Breakout".to_string(),
        category: "price_action".to_string(),
        description: "Adaptive parallel channel breakout with structure alignment".to_string(),
        params: vec![
            ParamDef {
                name: "swing_bars".to_string(),
                param_type: ParamType::Period,
                required: true,
                min: Some(1.0),
                max: Some(20.0),
            },
            ParamDef {
                name: "atr_period".to_string(),
                param_type: ParamType::Period,
                required: true,
                min: Some(1.0),
                max: Some(1000.0),
            },
            ParamDef {
                name: "atr_multiplier".to_string(),
                param_type: ParamType::Multiplier,
                required: true,
                min: Some(0.1),
                max: Some(10.0),
            },
            ParamDef {
                name: "confirmation_bars".to_string(),
                param_type: ParamType::Period,
                required: true,
                min: Some(1.0),
                max: Some(10.0),
            },
            ParamDef {
                name: "use_close".to_string(),
                param_type: ParamType::StringEnum(vec!["true".to_string(), "false".to_string()]),
                required: false,
                min: None,
                max: None,
            },
        ],
    });

    // Price Action: Swing Pullback (multi-TF composite)
    reg.register("swing_pullback", IndicatorDef {
        name: "Swing Pullback".to_string(),
        category: "price_action".to_string(),
        description: "Multi-TF swing extreme pullback signal with ATR overextension filter".to_string(),
        params: vec![
            ParamDef {
                name: "swing_bars".to_string(),
                param_type: ParamType::Period,
                required: true,
                min: Some(1.0),
                max: Some(20.0),
            },
            ParamDef {
                name: "atr_period".to_string(),
                param_type: ParamType::Period,
                required: true,
                min: Some(1.0),
                max: Some(1000.0),
            },
            ParamDef {
                name: "atr_multiplier".to_string(),
                param_type: ParamType::Multiplier,
                required: true,
                min: Some(0.1),
                max: Some(10.0),
            },
            ParamDef {
                name: "htf_timeframe".to_string(),
                param_type: ParamType::StringEnum(vec![
                    "M1".to_string(), "M5".to_string(), "M15".to_string(),
                    "H1".to_string(), "H4".to_string(), "D1".to_string(),
                ]),
                required: true,
                min: None,
                max: None,
            },
        ],
    });

    reg
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_default_registry_contains_all_indicators() {
        let reg = default_registry();
        assert!(reg.get("sma").is_some(), "sma missing");
        assert!(reg.get("ema").is_some(), "ema missing");
        assert!(reg.get("atr").is_some(), "atr missing");
        assert!(reg.get("bollinger_bands").is_some(), "bollinger_bands missing");
        assert_eq!(reg.indicator_names().len(), 9);
    }

    #[test]
    fn test_registry_lookup_unknown_returns_none() {
        let reg = default_registry();
        assert!(reg.get("supertrend").is_none());
        assert!(reg.get("rsi").is_none());
        assert!(reg.get("").is_none());
    }

    #[test]
    fn test_validate_params_valid_sma() {
        let reg = default_registry();
        let mut params = BTreeMap::new();
        params.insert("period".to_string(), toml::Value::Integer(20));
        let errors = reg.validate_params("sma", &params, "entry_rules", "conditions[0]");
        assert!(errors.is_empty(), "Valid SMA params should produce no errors: {errors:?}");
    }

    #[test]
    fn test_validate_params_invalid_period() {
        let reg = default_registry();
        let mut params = BTreeMap::new();
        params.insert("period".to_string(), toml::Value::Integer(0));
        let errors = reg.validate_params("sma", &params, "entry_rules", "conditions[0]");
        assert!(!errors.is_empty(), "period=0 should produce error");
        assert!(
            errors[0].reason.contains("must be > 0"),
            "Error should mention > 0, got: {}",
            errors[0].reason
        );
    }

    #[test]
    fn test_registry_is_extensible() {
        let mut reg = default_registry();
        assert!(reg.get("rsi").is_none());
        reg.register("rsi", IndicatorDef {
            name: "RSI".to_string(),
            category: "momentum".to_string(),
            description: "Relative Strength Index".to_string(),
            params: vec![ParamDef {
                name: "period".to_string(),
                param_type: ParamType::Period,
                required: true,
                min: Some(1.0),
                max: Some(1000.0),
            }],
        });
        assert!(reg.get("rsi").is_some());
        assert_eq!(reg.indicator_names().len(), 10);
    }
}
