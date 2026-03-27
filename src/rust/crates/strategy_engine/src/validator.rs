use std::path::Path;

use serde::Serialize;

use crate::registry::IndicatorRegistry;
use crate::types::*;

/// Severity of a validation finding.
#[derive(Debug, Clone, Serialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum Severity {
    Error,
    Warning,
}

/// A structured validation error identifying section, field, and reason.
#[derive(Debug, Clone, Serialize)]
pub struct ValidationError {
    pub section: String,
    pub field: String,
    pub reason: String,
    pub severity: Severity,
}

impl std::fmt::Display for ValidationError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        write!(
            f,
            "[{}] {}.{}: {}",
            match self.severity {
                Severity::Error => "ERROR",
                Severity::Warning => "WARN",
            },
            self.section,
            self.field,
            self.reason
        )
    }
}

/// Validate a parsed strategy specification against the registry and constraints.
///
/// Collects ALL errors (never fail-on-first) per D8 architecture decision.
/// If `cost_model_path` is provided, cross-validates the cost model reference.
pub fn validate_spec(
    spec: &StrategySpec,
    registry: &IndicatorRegistry,
    cost_model_path: Option<&Path>,
) -> Result<ValidatedSpec, Vec<ValidationError>> {
    let mut errors = Vec::new();

    validate_metadata(&spec.metadata, &mut errors);
    validate_entry_rules(&spec.entry_rules, registry, &mut errors);
    validate_exit_rules(&spec.exit_rules, registry, &mut errors);
    validate_filters(&spec.entry_rules.filters, registry, &mut errors);
    validate_position_sizing(&spec.position_sizing, &mut errors);
    validate_optimization_plan(&spec.optimization_plan, &mut errors);
    validate_cost_model_reference(&spec.cost_model_reference, cost_model_path, &mut errors);

    if errors.iter().any(|e| e.severity == Severity::Error) {
        Err(errors)
    } else {
        Ok(ValidatedSpec(spec.clone()))
    }
}

/// Check if a version string matches the contract pattern v\d{3} (e.g., v001, v002).
fn is_valid_version_pattern(v: &str) -> bool {
    v.len() == 4 && v.starts_with('v') && v[1..].chars().all(|c| c.is_ascii_digit())
}

fn validate_metadata(meta: &Metadata, errors: &mut Vec<ValidationError>) {
    if meta.name.is_empty() {
        errors.push(ValidationError {
            section: "metadata".to_string(),
            field: "name".to_string(),
            reason: "name must not be empty".to_string(),
            severity: Severity::Error,
        });
    }

    if meta.pair.is_empty() {
        errors.push(ValidationError {
            section: "metadata".to_string(),
            field: "pair".to_string(),
            reason: "pair must not be empty".to_string(),
            severity: Severity::Error,
        });
    }

    if !VALID_TIMEFRAMES.contains(&meta.timeframe.as_str()) {
        errors.push(ValidationError {
            section: "metadata".to_string(),
            field: "timeframe".to_string(),
            reason: format!(
                "invalid timeframe '{}'. Valid: {:?}",
                meta.timeframe, VALID_TIMEFRAMES
            ),
            severity: Severity::Error,
        });
    }

    // Pair must be a known major pair
    const VALID_PAIRS: [&str; 8] = [
        "EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "USDCAD", "USDCHF", "NZDUSD", "XAUUSD",
    ];
    if !VALID_PAIRS.contains(&meta.pair.as_str()) {
        errors.push(ValidationError {
            section: "metadata".to_string(),
            field: "pair".to_string(),
            reason: format!(
                "invalid pair '{}'. Valid: {:?}",
                meta.pair, VALID_PAIRS
            ),
            severity: Severity::Error,
        });
    }

    // version must match pattern v\d{3} per contract
    if !is_valid_version_pattern(&meta.version) {
        errors.push(ValidationError {
            section: "metadata".to_string(),
            field: "version".to_string(),
            reason: format!(
                "version must match pattern 'vNNN' (e.g., v001), got '{}'",
                meta.version
            ),
            severity: Severity::Error,
        });
    }

    if let Some(ref hash) = meta.config_hash {
        if hash.is_empty() {
            errors.push(ValidationError {
                section: "metadata".to_string(),
                field: "config_hash".to_string(),
                reason: "config_hash must not be empty when present".to_string(),
                severity: Severity::Error,
            });
        }
    }
}

fn validate_entry_rules(
    rules: &EntryRules,
    registry: &IndicatorRegistry,
    errors: &mut Vec<ValidationError>,
) {
    if rules.conditions.is_empty() {
        errors.push(ValidationError {
            section: "entry_rules".to_string(),
            field: "conditions".to_string(),
            reason: "at least one entry condition is required".to_string(),
            severity: Severity::Error,
        });
    }

    for (i, cond) in rules.conditions.iter().enumerate() {
        validate_condition(cond, registry, "entry_rules", &format!("conditions[{i}]"), errors);
    }

    for (i, cond) in rules.confirmation.iter().enumerate() {
        validate_condition(cond, registry, "entry_rules", &format!("confirmation[{i}]"), errors);
    }
}

/// Raw price fields that are always available on every bar (not computed indicators).
const PRICE_FIELDS: [&str; 4] = ["close", "open", "high", "low"];

fn validate_condition(
    cond: &Condition,
    registry: &IndicatorRegistry,
    section: &str,
    field_prefix: &str,
    errors: &mut Vec<ValidationError>,
) {
    // Raw price fields (close, open, high, low) are always valid — skip registry check
    if PRICE_FIELDS.contains(&cond.indicator.as_str()) {
        // Price fields take no parameters; warn if any were provided
        if !cond.parameters.is_empty() {
            errors.push(ValidationError {
                section: section.to_string(),
                field: format!("{field_prefix}.parameters"),
                reason: format!(
                    "price field '{}' does not accept parameters, but {} were provided",
                    cond.indicator,
                    cond.parameters.len()
                ),
                severity: Severity::Warning,
            });
        }
    } else if registry.get(&cond.indicator).is_none() {
        // Validate indicator exists in registry
        errors.push(ValidationError {
            section: section.to_string(),
            field: format!("{field_prefix}.indicator"),
            reason: format!(
                "unknown indicator '{}'. Known: {:?}",
                cond.indicator,
                registry.indicator_names()
            ),
            severity: Severity::Error,
        });
    } else {
        // Validate params against registry definition
        let param_errors =
            registry.validate_params(&cond.indicator, &cond.parameters, section, field_prefix);
        errors.extend(param_errors);
    }

    // Validate comparator
    if !VALID_COMPARATORS.contains(&cond.comparator.as_str()) {
        errors.push(ValidationError {
            section: section.to_string(),
            field: format!("{field_prefix}.comparator"),
            reason: format!(
                "invalid comparator '{}'. Valid: {:?}",
                cond.comparator, VALID_COMPARATORS
            ),
            severity: Severity::Error,
        });
    }
}

fn validate_exit_rules(
    rules: &ExitRules,
    registry: &IndicatorRegistry,
    errors: &mut Vec<ValidationError>,
) {
    // stop_loss is required (enforced by struct, but validate values)
    validate_exit_config(
        &rules.stop_loss,
        &VALID_STOP_LOSS_TYPES,
        "exit_rules",
        "stop_loss",
        errors,
    );

    if let Some(ref tp) = rules.take_profit {
        validate_exit_config(tp, &VALID_TAKE_PROFIT_TYPES, "exit_rules", "take_profit", errors);
    }

    if let Some(ref trailing) = rules.trailing {
        validate_trailing(trailing, registry, errors);
    }
}

fn validate_exit_config(
    config: &ExitConfig,
    valid_types: &[&str],
    section: &str,
    field: &str,
    errors: &mut Vec<ValidationError>,
) {
    if !valid_types.contains(&config.exit_type.as_str()) {
        errors.push(ValidationError {
            section: section.to_string(),
            field: format!("{field}.type"),
            reason: format!(
                "invalid exit type '{}'. Valid: {valid_types:?}",
                config.exit_type
            ),
            severity: Severity::Error,
        });
    }

    if config.value <= 0.0 {
        errors.push(ValidationError {
            section: section.to_string(),
            field: format!("{field}.value"),
            reason: format!("value must be > 0, got {}", config.value),
            severity: Severity::Error,
        });
    }
}

fn validate_trailing(
    trailing: &TrailingConfig,
    _registry: &IndicatorRegistry,
    errors: &mut Vec<ValidationError>,
) {
    match trailing {
        TrailingConfig::TrailingStop(params) => {
            if params.distance_pips <= 0.0 {
                errors.push(ValidationError {
                    section: "exit_rules".to_string(),
                    field: "trailing.params.distance_pips".to_string(),
                    reason: format!(
                        "distance_pips must be > 0, got {}",
                        params.distance_pips
                    ),
                    severity: Severity::Error,
                });
            }
        }
        TrailingConfig::Chandelier(params) => {
            if params.atr_period == 0 {
                errors.push(ValidationError {
                    section: "exit_rules".to_string(),
                    field: "trailing.params.atr_period".to_string(),
                    reason: "atr_period must be > 0".to_string(),
                    severity: Severity::Error,
                });
            }
            if params.atr_multiplier <= 0.0 {
                errors.push(ValidationError {
                    section: "exit_rules".to_string(),
                    field: "trailing.params.atr_multiplier".to_string(),
                    reason: format!(
                        "atr_multiplier must be > 0, got {}",
                        params.atr_multiplier
                    ),
                    severity: Severity::Error,
                });
            }
        }
    }
}

fn validate_filters(
    filters: &[Filter],
    registry: &IndicatorRegistry,
    errors: &mut Vec<ValidationError>,
) {
    for (i, filter) in filters.iter().enumerate() {
        match filter {
            Filter::Session(params) => {
                if params.include.is_empty() {
                    errors.push(ValidationError {
                        section: "entry_rules".to_string(),
                        field: format!("filters[{i}].params.include"),
                        reason: "session filter must include at least one session".to_string(),
                        severity: Severity::Error,
                    });
                }
                for label in &params.include {
                    if !VALID_SESSIONS.contains(&label.as_str()) {
                        errors.push(ValidationError {
                            section: "entry_rules".to_string(),
                            field: format!("filters[{i}].params.include"),
                            reason: format!(
                                "invalid session label '{label}'. Valid: {:?}",
                                VALID_SESSIONS
                            ),
                            severity: Severity::Error,
                        });
                    }
                }
            }
            Filter::Volatility(params) => {
                if registry.get(&params.indicator).is_none() {
                    errors.push(ValidationError {
                        section: "entry_rules".to_string(),
                        field: format!("filters[{i}].params.indicator"),
                        reason: format!(
                            "volatility filter references unknown indicator '{}'. Known: {:?}",
                            params.indicator,
                            registry.indicator_names()
                        ),
                        severity: Severity::Error,
                    });
                }
                if params.period == 0 {
                    errors.push(ValidationError {
                        section: "entry_rules".to_string(),
                        field: format!("filters[{i}].params.period"),
                        reason: "volatility filter period must be > 0".to_string(),
                        severity: Severity::Error,
                    });
                }
                // Cross-validate min_value < max_value when both present
                if let (Some(min_val), Some(max_val)) = (params.min_value, params.max_value) {
                    if min_val >= max_val {
                        errors.push(ValidationError {
                            section: "entry_rules".to_string(),
                            field: format!("filters[{i}].params"),
                            reason: format!(
                                "volatility filter min_value ({min_val}) must be < max_value ({max_val})"
                            ),
                            severity: Severity::Error,
                        });
                    }
                }
            }
            Filter::DayOfWeek(params) => {
                if params.include.is_empty() {
                    errors.push(ValidationError {
                        section: "entry_rules".to_string(),
                        field: format!("filters[{i}].params.include"),
                        reason: "day_of_week filter must include at least one day".to_string(),
                        severity: Severity::Error,
                    });
                }
                for &day in &params.include {
                    if day > 6 {
                        errors.push(ValidationError {
                            section: "entry_rules".to_string(),
                            field: format!("filters[{i}].params.include"),
                            reason: format!(
                                "invalid day_of_week value {day}. Must be 0-6 (0=Monday, 6=Sunday)"
                            ),
                            severity: Severity::Error,
                        });
                    }
                }
            }
        }
    }
}

fn validate_position_sizing(sizing: &PositionSizing, errors: &mut Vec<ValidationError>) {
    if !VALID_SIZING_METHODS.contains(&sizing.method.as_str()) {
        errors.push(ValidationError {
            section: "position_sizing".to_string(),
            field: "method".to_string(),
            reason: format!(
                "invalid sizing method '{}'. Valid: {:?}",
                sizing.method, VALID_SIZING_METHODS
            ),
            severity: Severity::Error,
        });
    }

    if sizing.method == "fixed_risk" && (sizing.risk_percent < 0.1 || sizing.risk_percent > 10.0) {
        errors.push(ValidationError {
            section: "position_sizing".to_string(),
            field: "risk_percent".to_string(),
            reason: format!(
                "risk_percent must be in [0.1, 10.0] for fixed_risk per contract, got {}",
                sizing.risk_percent
            ),
            severity: Severity::Error,
        });
    }

    if sizing.max_lots < 0.01 || sizing.max_lots > 100.0 {
        errors.push(ValidationError {
            section: "position_sizing".to_string(),
            field: "max_lots".to_string(),
            reason: format!(
                "max_lots must be in [0.01, 100.0] per contract, got {}",
                sizing.max_lots
            ),
            severity: Severity::Error,
        });
    }
}

fn validate_optimization_plan(plan: &OptimizationPlan, errors: &mut Vec<ValidationError>) {
    // Validate objective function (common to both versions)
    if !VALID_OBJECTIVES.contains(&plan.objective_function()) {
        errors.push(ValidationError {
            section: "optimization_plan".to_string(),
            field: "objective_function".to_string(),
            reason: format!(
                "invalid objective '{}'. Valid: {:?}",
                plan.objective_function(), VALID_OBJECTIVES
            ),
            severity: Severity::Error,
        });
    }

    match plan {
        OptimizationPlan::V1(v1) => validate_optimization_plan_v1(v1, errors),
        OptimizationPlan::V2(v2) => validate_optimization_plan_v2(v2, errors),
    }
}

fn validate_optimization_plan_v1(plan: &OptimizationPlanV1, errors: &mut Vec<ValidationError>) {
    // Collect all group names for dependency validation
    let group_names: Vec<&str> = plan
        .parameter_groups
        .iter()
        .map(|g| g.name.as_str())
        .collect();

    for (i, group) in plan.parameter_groups.iter().enumerate() {
        if group.name.is_empty() {
            errors.push(ValidationError {
                section: "optimization_plan".to_string(),
                field: format!("parameter_groups[{i}].name"),
                reason: "group name must not be empty".to_string(),
                severity: Severity::Error,
            });
        }

        for (param_name, range) in &group.ranges {
            validate_range(i, param_name, range, errors);
        }

        // Cross-validate parameters list vs ranges keys
        let range_keys: Vec<&str> = group.ranges.keys().map(|s| s.as_str()).collect();
        for param in &group.parameters {
            if !range_keys.contains(&param.as_str()) {
                errors.push(ValidationError {
                    section: "optimization_plan".to_string(),
                    field: format!("parameter_groups[{i}].parameters"),
                    reason: format!(
                        "parameter '{param}' listed but has no corresponding range definition"
                    ),
                    severity: Severity::Error,
                });
            }
        }
        for range_key in &range_keys {
            if !group.parameters.iter().any(|p| p.as_str() == *range_key) {
                errors.push(ValidationError {
                    section: "optimization_plan".to_string(),
                    field: format!("parameter_groups[{i}].ranges"),
                    reason: format!(
                        "range defined for '{range_key}' but not listed in parameters array"
                    ),
                    severity: Severity::Error,
                });
            }
        }
    }

    // Validate group dependencies reference existing groups
    for dep in &plan.group_dependencies {
        if !group_names.contains(&dep.as_str()) {
            errors.push(ValidationError {
                section: "optimization_plan".to_string(),
                field: "group_dependencies".to_string(),
                reason: format!(
                    "dependency references unknown group '{dep}'. Known groups: {group_names:?}"
                ),
                severity: Severity::Error,
            });
        }
    }
}

fn validate_optimization_plan_v2(plan: &OptimizationPlanV2, errors: &mut Vec<ValidationError>) {
    if plan.schema_version != 2 {
        errors.push(ValidationError {
            section: "optimization_plan".to_string(),
            field: "schema_version".to_string(),
            reason: format!("expected schema_version = 2, got {}", plan.schema_version),
            severity: Severity::Error,
        });
    }

    let valid_types = ["integer", "continuous", "categorical"];

    for (name, param) in &plan.parameters {
        if !valid_types.contains(&param.param_type.as_str()) {
            errors.push(ValidationError {
                section: "optimization_plan".to_string(),
                field: format!("parameters.{name}.type"),
                reason: format!(
                    "invalid type '{}'. Valid: {:?}",
                    param.param_type, valid_types
                ),
                severity: Severity::Error,
            });
        }

        match param.param_type.as_str() {
            "integer" | "continuous" => {
                let (Some(min), Some(max)) = (param.min, param.max) else {
                    errors.push(ValidationError {
                        section: "optimization_plan".to_string(),
                        field: format!("parameters.{name}"),
                        reason: format!("{} parameter requires min and max", param.param_type),
                        severity: Severity::Error,
                    });
                    continue;
                };
                if min >= max {
                    errors.push(ValidationError {
                        section: "optimization_plan".to_string(),
                        field: format!("parameters.{name}"),
                        reason: format!("min ({min}) must be < max ({max})"),
                        severity: Severity::Error,
                    });
                }
                if let Some(step) = param.step {
                    if step <= 0.0 {
                        errors.push(ValidationError {
                            section: "optimization_plan".to_string(),
                            field: format!("parameters.{name}.step"),
                            reason: format!("step must be > 0, got {step}"),
                            severity: Severity::Error,
                        });
                    } else if step > (max - min) {
                        errors.push(ValidationError {
                            section: "optimization_plan".to_string(),
                            field: format!("parameters.{name}.step"),
                            reason: format!(
                                "step ({step}) must be <= (max - min) = {}",
                                max - min
                            ),
                            severity: Severity::Error,
                        });
                    }
                }
            }
            "categorical" => {
                match &param.choices {
                    Some(choices) if choices.len() < 2 => {
                        errors.push(ValidationError {
                            section: "optimization_plan".to_string(),
                            field: format!("parameters.{name}.choices"),
                            reason: "categorical parameter requires at least 2 choices".to_string(),
                            severity: Severity::Error,
                        });
                    }
                    None => {
                        errors.push(ValidationError {
                            section: "optimization_plan".to_string(),
                            field: format!("parameters.{name}.choices"),
                            reason: "categorical parameter requires choices field".to_string(),
                            severity: Severity::Error,
                        });
                    }
                    _ => {}
                }
            }
            _ => {}
        }

        // Validate condition references
        if let Some(cond) = &param.condition {
            if let Some(parent) = plan.parameters.get(&cond.parent) {
                if parent.param_type != "categorical" {
                    errors.push(ValidationError {
                        section: "optimization_plan".to_string(),
                        field: format!("parameters.{name}.condition.parent"),
                        reason: format!(
                            "condition parent '{}' must be categorical, got '{}'",
                            cond.parent, parent.param_type
                        ),
                        severity: Severity::Error,
                    });
                } else if let Some(choices) = &parent.choices {
                    if !choices.contains(&cond.value) {
                        errors.push(ValidationError {
                            section: "optimization_plan".to_string(),
                            field: format!("parameters.{name}.condition.value"),
                            reason: format!(
                                "condition value '{}' not in parent '{}' choices: {:?}",
                                cond.value, cond.parent, choices
                            ),
                            severity: Severity::Error,
                        });
                    }
                }
            } else {
                errors.push(ValidationError {
                    section: "optimization_plan".to_string(),
                    field: format!("parameters.{name}.condition.parent"),
                    reason: format!("condition references unknown parameter '{}'", cond.parent),
                    severity: Severity::Error,
                });
            }
        }
    }
}

fn validate_range(group_idx: usize, param_name: &str, range: &ParamRange, errors: &mut Vec<ValidationError>) {
    if range.min >= range.max {
        errors.push(ValidationError {
            section: "optimization_plan".to_string(),
            field: format!("parameter_groups[{group_idx}].ranges.{param_name}"),
            reason: format!("min ({}) must be < max ({})", range.min, range.max),
            severity: Severity::Error,
        });
    }
    if range.step <= 0.0 {
        errors.push(ValidationError {
            section: "optimization_plan".to_string(),
            field: format!("parameter_groups[{group_idx}].ranges.{param_name}.step"),
            reason: format!("step must be > 0, got {}", range.step),
            severity: Severity::Error,
        });
    }
    if range.step > 0.0 && range.max > range.min && range.step > (range.max - range.min) {
        errors.push(ValidationError {
            section: "optimization_plan".to_string(),
            field: format!("parameter_groups[{group_idx}].ranges.{param_name}.step"),
            reason: format!(
                "step ({}) must be <= (max - min) = {}",
                range.step, range.max - range.min
            ),
            severity: Severity::Error,
        });
    }
}

fn validate_cost_model_reference(
    reference: &CostModelReference,
    cost_model_path: Option<&Path>,
    errors: &mut Vec<ValidationError>,
) {
    if reference.version.is_empty() {
        errors.push(ValidationError {
            section: "cost_model_reference".to_string(),
            field: "version".to_string(),
            reason: "cost model version must not be empty".to_string(),
            severity: Severity::Error,
        });
    } else if !is_valid_version_pattern(&reference.version) {
        errors.push(ValidationError {
            section: "cost_model_reference".to_string(),
            field: "version".to_string(),
            reason: format!(
                "cost model version must match pattern 'vNNN' (e.g., v001), got '{}'",
                reference.version
            ),
            severity: Severity::Error,
        });
    }

    // Cross-validate against actual cost model artifact if path provided.
    // The path may be a direct file (e.g., cost.json from CLI --cost-model)
    // or a directory containing per-pair artifacts (e.g., data/cost_models/).
    if let Some(base_path) = cost_model_path {
        let artifact_path = if base_path.is_file() {
            base_path.to_path_buf()
        } else {
            base_path.join(format!("EURUSD_{}.json", reference.version))
        };
        match cost_model::load_from_file(&artifact_path) {
            Ok(_) => {} // Valid
            Err(e) => {
                errors.push(ValidationError {
                    section: "cost_model_reference".to_string(),
                    field: "version".to_string(),
                    reason: format!(
                        "cost model artifact at '{}' could not be loaded: {e}",
                        artifact_path.display()
                    ),
                    severity: Severity::Error,
                });
            }
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::registry::default_registry;
    use std::collections::BTreeMap;

    fn valid_spec() -> StrategySpec {
        let mut params = BTreeMap::new();
        params.insert("period".to_string(), toml::Value::Integer(20));

        StrategySpec {
            metadata: Metadata {
                schema_version: "1".to_string(),
                name: "test-strategy".to_string(),
                version: "v001".to_string(),
                pair: "EURUSD".to_string(),
                timeframe: "H1".to_string(),
                created_by: "test".to_string(),
                config_hash: Some("abc123".to_string()),
            },
            entry_rules: EntryRules {
                conditions: vec![Condition {
                    indicator: "sma".to_string(),
                    parameters: params,
                    threshold: 0.0,
                    comparator: "crosses_above".to_string(),
                }],
                filters: vec![Filter::Session(SessionFilterParams {
                    include: vec!["london".to_string(), "new_york".to_string()],
                })],
                confirmation: vec![],
            },
            exit_rules: ExitRules {
                stop_loss: ExitConfig {
                    exit_type: "atr_multiple".to_string(),
                    value: 2.0,
                },
                take_profit: Some(ExitConfig {
                    exit_type: "risk_reward".to_string(),
                    value: 2.0,
                }),
                trailing: None,
            },
            position_sizing: PositionSizing {
                method: "fixed_risk".to_string(),
                risk_percent: 1.0,
                max_lots: 1.0,
                min_lots: 0.01,
                lot_step: 0.01,
            },
            account: None,
            optimization_plan: OptimizationPlan::V1(OptimizationPlanV1 {
                parameter_groups: vec![ParameterGroup {
                    name: "entry_timing".to_string(),
                    parameters: vec!["sma_period".to_string()],
                    ranges: {
                        let mut m = BTreeMap::new();
                        m.insert(
                            "sma_period".to_string(),
                            ParamRange {
                                min: 5.0,
                                max: 50.0,
                                step: 5.0,
                            },
                        );
                        m
                    },
                }],
                group_dependencies: vec!["entry_timing".to_string()],
                objective_function: "sharpe".to_string(),
            }),
            cost_model_reference: CostModelReference {
                version: "v001".to_string(),
            },
        }
    }

    #[test]
    fn test_validate_valid_spec_returns_ok() {
        let reg = default_registry();
        let spec = valid_spec();
        let result = validate_spec(&spec, &reg, None);
        assert!(result.is_ok(), "Valid spec should pass: {result:?}");
    }

    #[test]
    fn test_validate_unknown_indicator_error() {
        let reg = default_registry();
        let mut spec = valid_spec();
        spec.entry_rules.conditions[0].indicator = "supertrend".to_string();
        let result = validate_spec(&spec, &reg, None);
        assert!(result.is_err());
        let errs = result.unwrap_err();
        assert!(
            errs.iter().any(|e| e.reason.contains("unknown indicator")),
            "Should mention unknown indicator: {errs:?}"
        );
    }

    #[test]
    fn test_validate_bad_params_error() {
        let reg = default_registry();
        let mut spec = valid_spec();
        spec.entry_rules.conditions[0]
            .parameters
            .insert("period".to_string(), toml::Value::Integer(0));
        let result = validate_spec(&spec, &reg, None);
        assert!(result.is_err());
        let errs = result.unwrap_err();
        assert!(
            errs.iter().any(|e| e.reason.contains("must be > 0")),
            "Should mention > 0: {errs:?}"
        );
    }

    #[test]
    fn test_validate_missing_stop_loss_value() {
        let reg = default_registry();
        let mut spec = valid_spec();
        spec.exit_rules.stop_loss.value = 0.0;
        let result = validate_spec(&spec, &reg, None);
        assert!(result.is_err());
        let errs = result.unwrap_err();
        assert!(
            errs.iter()
                .any(|e| e.field.contains("stop_loss") && e.reason.contains("must be > 0")),
            "Should flag stop_loss value: {errs:?}"
        );
    }

    #[test]
    fn test_validate_bad_session_label_error() {
        let reg = default_registry();
        let mut spec = valid_spec();
        spec.entry_rules.filters = vec![Filter::Session(SessionFilterParams {
            include: vec!["tokyo".to_string()],
        })];
        let result = validate_spec(&spec, &reg, None);
        assert!(result.is_err());
        let errs = result.unwrap_err();
        assert!(
            errs.iter().any(|e| e.reason.contains("tokyo")),
            "Should mention 'tokyo': {errs:?}"
        );
    }

    #[test]
    fn test_validate_bad_optimization_ranges() {
        let reg = default_registry();
        let mut spec = valid_spec();
        // min >= max
        if let OptimizationPlan::V1(ref mut v1) = spec.optimization_plan {
            v1.parameter_groups[0]
                .ranges
                .insert(
                    "sma_period".to_string(),
                    ParamRange {
                        min: 50.0,
                        max: 5.0,
                        step: 5.0,
                    },
                );
        }
        let result = validate_spec(&spec, &reg, None);
        assert!(result.is_err());
        let errs = result.unwrap_err();
        assert!(
            errs.iter().any(|e| e.reason.contains("min") && e.reason.contains("max")),
            "Should mention min/max: {errs:?}"
        );
    }

    #[test]
    fn test_validate_collects_all_errors() {
        let reg = default_registry();
        let mut spec = valid_spec();
        // Error 1: bad timeframe
        spec.metadata.timeframe = "INVALID".to_string();
        // Error 2: unknown indicator
        spec.entry_rules.conditions[0].indicator = "unknown".to_string();
        // Error 3: bad session
        spec.entry_rules.filters = vec![Filter::Session(SessionFilterParams {
            include: vec!["tokyo".to_string()],
        })];
        // Error 4: bad max_lots
        spec.position_sizing.max_lots = 0.0;
        let result = validate_spec(&spec, &reg, None);
        assert!(result.is_err());
        let errs = result.unwrap_err();
        assert!(
            errs.len() >= 3,
            "Should collect at least 3 errors, got {}: {errs:?}",
            errs.len()
        );
    }

    #[test]
    fn test_validate_cost_model_version_only_no_path() {
        // Without cost_model_path, only version format is validated
        let reg = default_registry();
        let spec = valid_spec();
        let result = validate_spec(&spec, &reg, None);
        assert!(result.is_ok());
    }

    #[test]
    fn test_validate_cost_model_reference_invalid() {
        // With a nonexistent cost_model_path, should produce ValidationError (not panic)
        let reg = default_registry();
        let spec = valid_spec();
        let result = validate_spec(&spec, &reg, Some(Path::new("/nonexistent/path")));
        assert!(result.is_err());
        let errs = result.unwrap_err();
        assert!(
            errs.iter()
                .any(|e| e.section == "cost_model_reference" && e.reason.contains("could not be loaded")),
            "Should flag cost model load failure: {errs:?}"
        );
    }

    // --- Regression tests (review synthesis fixes) ---

    #[test]
    fn test_regression_risk_percent_contract_bounds() {
        // Regression: risk_percent=50.0 was allowed (code used (0,100] but contract says [0.1,10.0])
        let reg = default_registry();
        let mut spec = valid_spec();
        spec.position_sizing.risk_percent = 50.0;
        let result = validate_spec(&spec, &reg, None);
        assert!(result.is_err());
        let errs = result.unwrap_err();
        assert!(
            errs.iter().any(|e| e.field == "risk_percent" && e.reason.contains("[0.1, 10.0]")),
            "Should reject risk_percent=50.0 per contract bounds: {errs:?}"
        );
    }

    #[test]
    fn test_regression_risk_percent_lower_bound() {
        // Regression: risk_percent=0.05 was allowed (below contract min 0.1)
        let reg = default_registry();
        let mut spec = valid_spec();
        spec.position_sizing.risk_percent = 0.05;
        let result = validate_spec(&spec, &reg, None);
        assert!(result.is_err());
        let errs = result.unwrap_err();
        assert!(
            errs.iter().any(|e| e.field == "risk_percent"),
            "Should reject risk_percent=0.05 below contract min: {errs:?}"
        );
    }

    #[test]
    fn test_regression_max_lots_contract_upper_bound() {
        // Regression: max_lots=1000.0 was allowed (code only checked >0, contract says [0.01,100.0])
        let reg = default_registry();
        let mut spec = valid_spec();
        spec.position_sizing.max_lots = 1000.0;
        let result = validate_spec(&spec, &reg, None);
        assert!(result.is_err());
        let errs = result.unwrap_err();
        assert!(
            errs.iter().any(|e| e.field == "max_lots" && e.reason.contains("[0.01, 100.0]")),
            "Should reject max_lots=1000.0 per contract bounds: {errs:?}"
        );
    }

    #[test]
    fn test_regression_max_lots_contract_lower_bound() {
        // Regression: max_lots=0.001 was allowed (below contract min 0.01)
        let reg = default_registry();
        let mut spec = valid_spec();
        spec.position_sizing.max_lots = 0.001;
        let result = validate_spec(&spec, &reg, None);
        assert!(result.is_err());
        let errs = result.unwrap_err();
        assert!(
            errs.iter().any(|e| e.field == "max_lots"),
            "Should reject max_lots=0.001 below contract min: {errs:?}"
        );
    }

    #[test]
    fn test_regression_volatility_min_exceeds_max() {
        // Regression: min_value > max_value was silently accepted
        let reg = default_registry();
        let mut spec = valid_spec();
        spec.entry_rules.filters = vec![Filter::Volatility(VolatilityFilterParams {
            indicator: "atr".to_string(),
            period: 14,
            min_value: Some(100.0),
            max_value: Some(10.0),
        })];
        let result = validate_spec(&spec, &reg, None);
        assert!(result.is_err());
        let errs = result.unwrap_err();
        assert!(
            errs.iter().any(|e| e.reason.contains("min_value") && e.reason.contains("max_value")),
            "Should reject min_value > max_value: {errs:?}"
        );
    }

    #[test]
    fn test_regression_metadata_version_pattern() {
        // Regression: version="abc" was accepted (contract requires v\d{3})
        let reg = default_registry();
        let mut spec = valid_spec();
        spec.metadata.version = "abc".to_string();
        let result = validate_spec(&spec, &reg, None);
        assert!(result.is_err());
        let errs = result.unwrap_err();
        assert!(
            errs.iter().any(|e| e.field == "version" && e.reason.contains("vNNN")),
            "Should reject version='abc': {errs:?}"
        );
    }

    #[test]
    fn test_regression_metadata_pair_constraint() {
        // Regression: unknown pairs must be rejected
        let reg = default_registry();
        let mut spec = valid_spec();
        spec.metadata.pair = "ZARJPY".to_string();
        let result = validate_spec(&spec, &reg, None);
        assert!(result.is_err());
        let errs = result.unwrap_err();
        assert!(
            errs.iter().any(|e| e.field == "pair" && e.reason.contains("invalid pair")),
            "Should reject pair='ZARJPY': {errs:?}"
        );
    }

    #[test]
    fn test_regression_cost_model_version_pattern() {
        // Regression: cost_model version="latest" was accepted (contract requires v\d{3})
        let reg = default_registry();
        let mut spec = valid_spec();
        spec.cost_model_reference.version = "latest".to_string();
        let result = validate_spec(&spec, &reg, None);
        assert!(result.is_err());
        let errs = result.unwrap_err();
        assert!(
            errs.iter().any(|e| e.section == "cost_model_reference" && e.reason.contains("vNNN")),
            "Should reject cost_model version='latest': {errs:?}"
        );
    }

    #[test]
    fn test_regression_optimization_params_ranges_mismatch() {
        // Regression: parameter listed but no range defined was silently accepted
        let reg = default_registry();
        let mut spec = valid_spec();
        if let OptimizationPlan::V1(ref mut v1) = spec.optimization_plan {
            v1.parameter_groups[0].parameters = vec![
                "sma_period".to_string(),
                "missing_param".to_string(),
            ];
        }
        let result = validate_spec(&spec, &reg, None);
        assert!(result.is_err());
        let errs = result.unwrap_err();
        assert!(
            errs.iter().any(|e| e.reason.contains("missing_param") && e.reason.contains("no corresponding range")),
            "Should reject parameter with no matching range: {errs:?}"
        );
    }
}
