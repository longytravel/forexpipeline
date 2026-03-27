//! Forex backtester CLI binary — thin subprocess wrapper (D1).
//!
//! Python `BatchRunner` spawns this binary via `asyncio.create_subprocess_exec`.
//! All data exchange is via Arrow IPC files and CLI arguments.
//! Core trade simulation logic lives in the library crate.

use std::collections::BTreeMap;
use std::path::{Path, PathBuf};
use std::process;
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::Arc;

use clap::Parser;
use serde::Deserialize;

use backtester::engine;
use backtester::fold::FoldConfig;
use backtester::memory::MemoryBudget;
use backtester::output;
use backtester::progress::{write_progress, now_iso, ProgressReport};
use common::error_types::{install_panic_hook, BacktesterError};
use strategy_engine::StrategySpec;

/// Forex Pipeline batch backtester binary.
///
/// CLI contract consumed by Python BatchRunner (Story 3-4).
#[derive(Parser, Debug)]
#[command(name = "forex_backtester", about = "Batch backtest evaluation engine")]
struct Args {
    /// Strategy specification TOML file path (required unless --manifest is used)
    #[arg(long)]
    spec: Option<PathBuf>,

    /// Arrow IPC market data file path (mmap-ready, required unless --manifest)
    #[arg(long)]
    data: Option<PathBuf>,

    /// Cost model JSON file path (required unless --manifest)
    #[arg(long)]
    cost_model: Option<PathBuf>,

    /// Output directory for results (required unless --manifest)
    #[arg(long)]
    output: Option<PathBuf>,

    /// Config hash for artifact tracing (required unless --manifest)
    #[arg(long)]
    config_hash: Option<String>,

    /// Memory budget in MB for pre-allocation
    #[arg(long)]
    memory_budget: u64,

    /// Resume from checkpoint file (optional)
    #[arg(long)]
    checkpoint: Option<PathBuf>,

    /// Fold boundaries as JSON array: [[start, end], ...] (optional)
    #[arg(long)]
    fold_boundaries: Option<String>,

    /// Embargo size at fold boundaries (optional)
    #[arg(long)]
    embargo_bars: Option<u64>,

    /// Windowed evaluation start bar index (optional)
    #[arg(long)]
    window_start: Option<u64>,

    /// Windowed evaluation end bar index (optional)
    #[arg(long)]
    window_end: Option<u64>,

    /// Path to JSON file with parameter batch for batch evaluation (optional)
    #[arg(long)]
    param_batch: Option<PathBuf>,

    /// When true, write only scores.arrow and skip the best-candidate re-run.
    /// Used during optimization to avoid redundant full backtests.
    #[arg(long, default_value_t = false)]
    scores_only: bool,

    /// Path to manifest JSON for multi-group batch evaluation.
    /// Mutually exclusive with --spec/--param-batch.
    #[arg(long)]
    manifest: Option<PathBuf>,
}

/// Multi-group manifest for batch evaluation across signal groups.
/// One process handles ALL groups for a fold, sharing market data.
#[derive(Debug, Deserialize)]
struct ManifestSpec {
    groups: Vec<ManifestGroup>,
    market_data_path: PathBuf,
    cost_model_path: PathBuf,
    #[serde(default)]
    fold_boundaries: Option<Vec<[u64; 2]>>,
    window_start: Option<u64>,
    window_end: Option<u64>,
    #[serde(default)]
    scores_only: bool,
}

/// A single signal group within a manifest.
#[derive(Debug, Deserialize)]
struct ManifestGroup {
    group_id: String,
    spec_path: PathBuf,
    data_path: PathBuf,
    candidates: Vec<BTreeMap<String, f64>>,
    output_dir: PathBuf,
}

fn main() {
    install_panic_hook();

    let args = Args::parse();

    if let Err(e) = run(args) {
        e.to_structured().write_to_stderr();
        process::exit(1);
    }
}

fn run(args: Args) -> Result<(), BacktesterError> {
    // ------------------------------------------------------------------
    // Memory budget enforcement (AC #10, NFR4)
    // ------------------------------------------------------------------
    let budget = MemoryBudget::new(args.memory_budget);
    budget.check_system_memory()?;

    eprintln!(
        "{{\"level\":\"info\",\"msg\":\"Memory budget: {}MB\"}}",
        args.memory_budget
    );

    // ------------------------------------------------------------------
    // Setup cancellation signal handler
    // ------------------------------------------------------------------
    let cancelled = Arc::new(AtomicBool::new(false));
    let cancelled_clone = cancelled.clone();
    if let Err(e) = ctrlc::set_handler(move || {
        cancelled_clone.store(true, Ordering::SeqCst);
    }) {
        eprintln!(
            "{{\"level\":\"warn\",\"msg\":\"Signal handler registration failed: {e}\"}}",
        );
    }

    // ------------------------------------------------------------------
    // Dispatch: manifest mode vs legacy single/batch mode
    // ------------------------------------------------------------------
    if let Some(ref manifest_path) = args.manifest {
        return run_manifest_mode(manifest_path, &args, cancelled);
    }

    // Legacy mode: require --spec, --data, --cost-model, --output, --config-hash
    let spec_path = args.spec.as_ref().ok_or_else(|| {
        BacktesterError::Validation("--spec is required unless --manifest is used".into())
    })?;
    let data_path = args.data.as_ref().ok_or_else(|| {
        BacktesterError::Validation("--data is required unless --manifest is used".into())
    })?;
    let cost_model_path = args.cost_model.as_ref().ok_or_else(|| {
        BacktesterError::Validation("--cost-model is required unless --manifest is used".into())
    })?;
    let output_dir = args.output.as_ref().ok_or_else(|| {
        BacktesterError::Validation("--output is required unless --manifest is used".into())
    })?;
    let config_hash = args.config_hash.as_ref().ok_or_else(|| {
        BacktesterError::Validation("--config-hash is required unless --manifest is used".into())
    })?;

    // Validate paths
    if !spec_path.exists() {
        return Err(BacktesterError::Validation(format!(
            "Strategy spec not found: {}", spec_path.display()
        )));
    }
    if !data_path.exists() {
        return Err(BacktesterError::Validation(format!(
            "Market data file not found: {}", data_path.display()
        )));
    }
    if !cost_model_path.exists() {
        return Err(BacktesterError::Validation(format!(
            "Cost model file not found: {}", cost_model_path.display()
        )));
    }
    if let Some(ref cp) = args.checkpoint {
        if !cp.exists() {
            return Err(BacktesterError::Validation(format!(
                "Checkpoint file not found: {}", cp.display()
            )));
        }
    }
    if let Some(ref pb) = args.param_batch {
        if !pb.exists() {
            return Err(BacktesterError::Validation(format!(
                "Parameter batch file not found: {}", pb.display()
            )));
        }
    }

    // Create output directory
    std::fs::create_dir_all(output_dir)?;

    // Load inputs
    let spec = strategy_engine::parse_spec_from_file(spec_path)
        .map_err(|e| BacktesterError::StrategySpec(e.to_string()))?;

    let registry = strategy_engine::default_registry();
    let _validated = strategy_engine::validate_spec(&spec, &registry, Some(cost_model_path))
        .map_err(|errors| BacktesterError::StrategySpec(
            errors.iter().map(|e| e.to_string()).collect::<Vec<_>>().join("; ")
        ))?;

    let cost_model = cost_model::load_from_file(cost_model_path)
        .map_err(|e| BacktesterError::CostModel(e.to_string()))?;

    let fold_config = FoldConfig::from_args(
        args.fold_boundaries.as_deref(),
        args.embargo_bars,
    ).map_err(|e| BacktesterError::Validation(e))?;

    let checkpoint = if let Some(ref cp_path) = args.checkpoint {
        let cp_json = std::fs::read_to_string(cp_path)?;
        let cp: engine::Checkpoint = serde_json::from_str(&cp_json)
            .map_err(|e| BacktesterError::Validation(format!("Invalid checkpoint: {e}")))?;
        Some(cp)
    } else {
        None
    };

    eprintln!(
        "{{\"level\":\"info\",\"msg\":\"Loaded spec '{}', cost model '{}', data '{}'\"}}",
        spec.metadata.name,
        cost_model.version(),
        data_path.display()
    );

    // Write initial progress
    write_progress(
        output_dir,
        &ProgressReport {
            bars_processed: 0,
            total_bars: 0,
            estimated_seconds_remaining: 0.0,
            memory_used_mb: args.memory_budget,
            updated_at: now_iso(),
        },
    )?;

    // Run evaluation (single or batch mode)
    if let Some(ref batch_path) = args.param_batch {
        run_batch_mode(
            &spec, data_path, output_dir, config_hash, &cost_model,
            fold_config, cancelled, batch_path, args.scores_only,
            args.window_start, args.window_end,
        )
    } else {
        run_single_mode(
            &spec, data_path, output_dir, config_hash, &cost_model,
            fold_config, checkpoint, cancelled,
            args.window_start, args.window_end, args.memory_budget,
        )
    }
}

/// Single-run mode: one backtest with the spec's default parameters.
fn run_single_mode(
    spec: &StrategySpec,
    data_path: &Path,
    output_dir: &Path,
    config_hash: &str,
    cost_model: &cost_model::CostModel,
    fold_config: Option<FoldConfig>,
    checkpoint: Option<engine::Checkpoint>,
    cancelled: Arc<AtomicBool>,
    window_start: Option<u64>,
    window_end: Option<u64>,
    memory_budget: u64,
) -> Result<(), BacktesterError> {
    let result = engine::run_backtest(
        spec,
        data_path,
        cost_model,
        output_dir,
        config_hash,
        cancelled,
        fold_config,
        checkpoint,
        window_start,
        window_end,
    )?;

    output::write_results(
        output_dir,
        &result,
        config_hash,
        &spec.metadata.name,
    )?;

    write_progress(
        output_dir,
        &ProgressReport {
            bars_processed: result.total_bars,
            total_bars: result.total_bars,
            estimated_seconds_remaining: 0.0,
            memory_used_mb: memory_budget,
            updated_at: now_iso(),
        },
    )?;

    eprintln!(
        "{{\"level\":\"info\",\"msg\":\"Backtest complete: {} trades, net PnL {:.1} pips\"}}",
        result.metrics.total_trades, result.metrics.net_pnl_pips
    );

    Ok(())
}

/// Batch evaluation mode: vectorized single-pass evaluator (primary) with
/// per-candidate Rayon fallback.
///
/// Entry indicator params are fixed (baked into enriched Arrow signals).
/// Only exit/trade-management params are varied per candidate:
///   sl_atr_multiplier  → spec.exit_rules.stop_loss.value
///   tp_rr_ratio        → spec.exit_rules.take_profit.value
///   trailing_atr_multiplier → spec.exit_rules.trailing.chandelier.atr_multiplier
fn run_batch_mode(
    base_spec: &StrategySpec,
    data_path: &Path,
    output_dir: &Path,
    config_hash: &str,
    cost_model: &cost_model::CostModel,
    fold_config: Option<FoldConfig>,
    cancelled: Arc<AtomicBool>,
    batch_path: &Path,
    scores_only: bool,
    window_start: Option<u64>,
    window_end: Option<u64>,
) -> Result<(), BacktesterError> {
    // Parse parameter batch JSON
    let batch_json = std::fs::read_to_string(batch_path)?;
    let candidates: Vec<BTreeMap<String, f64>> = serde_json::from_str(&batch_json)
        .map_err(|e| BacktesterError::Validation(format!(
            "Invalid param batch JSON: {e}"
        )))?;

    let n_candidates = candidates.len();

    // Load data ONCE — shared across vectorized pass or Rayon threads.
    let data = engine::load_market_data(data_path)?;

    // --- Primary path: vectorized single-pass evaluator ---
    // All candidates share entry signals; only exit params differ.
    // Fold config is not used in vectorized path (window_start/end handle folds).
    let scores = backtester::batch_eval::run_batch_vectorized(
        &data,
        &candidates,
        base_spec,
        cost_model,
        cancelled.clone(),
        window_start,
        window_end,
    )?;

    // Write scores.arrow — per-candidate objective values
    write_scores_arrow(output_dir, &scores)?;

    // In scores-only mode, skip the expensive best-candidate re-run.
    // This is the optimization hot path — we only need the numeric scores.
    if scores_only {
        eprintln!(
            "{{\"level\":\"info\",\"msg\":\"Batch complete (scores-only): {n_candidates} candidates\"}}",
        );
        return Ok(());
    }

    // Re-run best candidate with full output writing (detailed trades/equity)
    if let Some((best_idx, _)) = scores.iter().enumerate()
        .filter(|(_, s)| s.is_finite() && **s != 0.0)
        .max_by(|(_, a), (_, b)| a.partial_cmp(b).unwrap_or(std::cmp::Ordering::Equal))
    {
        let mut best_spec = base_spec.clone();
        apply_candidate_params(&mut best_spec, &candidates[best_idx]);

        let best_result = engine::run_backtest(
            &best_spec,
            data_path,
            cost_model,
            output_dir,
            config_hash,
            cancelled,
            fold_config,
            None,
            window_start,
            window_end,
        )?;

        output::write_results(
            output_dir,
            &best_result,
            config_hash,
            &base_spec.metadata.name,
        )?;

        eprintln!(
            "{{\"level\":\"info\",\"msg\":\"Batch complete: {n_candidates} candidates, best sharpe={:.4} ({} trades)\"}}",
            best_result.metrics.sharpe_ratio, best_result.metrics.total_trades
        );
    } else {
        eprintln!(
            "{{\"level\":\"warn\",\"msg\":\"Batch complete: {n_candidates} candidates, no finite scores\"}}",
        );
    }

    Ok(())
}

/// Manifest mode: process multiple signal groups in one process, sharing
/// market data across all groups. Collapses N group spawns into 1 process.
fn run_manifest_mode(
    manifest_path: &Path,
    args: &Args,
    cancelled: Arc<AtomicBool>,
) -> Result<(), BacktesterError> {
    // Parse manifest JSON
    let manifest_json = std::fs::read_to_string(manifest_path).map_err(|e| {
        BacktesterError::Validation(format!(
            "Failed to read manifest '{}': {e}", manifest_path.display()
        ))
    })?;
    let manifest: ManifestSpec = serde_json::from_str(&manifest_json).map_err(|e| {
        BacktesterError::Validation(format!("Invalid manifest JSON: {e}"))
    })?;

    // Validate manifest paths
    if !manifest.market_data_path.exists() {
        return Err(BacktesterError::Validation(format!(
            "Manifest market data not found: {}", manifest.market_data_path.display()
        )));
    }
    if !manifest.cost_model_path.exists() {
        return Err(BacktesterError::Validation(format!(
            "Manifest cost model not found: {}", manifest.cost_model_path.display()
        )));
    }
    if manifest.groups.is_empty() {
        return Err(BacktesterError::Validation("Manifest contains no groups".into()));
    }

    let n_groups = manifest.groups.len();
    let total_candidates: usize = manifest.groups.iter().map(|g| g.candidates.len()).sum();

    eprintln!(
        "{{\"level\":\"info\",\"msg\":\"Manifest mode: {} groups, {} total candidates\"}}",
        n_groups, total_candidates
    );

    // Load cost model ONCE — shared across all groups.
    // NOTE: market_data_path is reserved in ManifestSpec for future use (merging
    // base OHLC with signal-only files). Currently each group's data_path already
    // contains OHLC + signal columns, so we don't load market_data here.
    let cost_model = cost_model::load_from_file(&manifest.cost_model_path)
        .map_err(|e| BacktesterError::CostModel(e.to_string()))?;

    eprintln!(
        "{{\"level\":\"info\",\"msg\":\"Loaded cost model '{}'\"}}",
        cost_model.version()
    );

    // Process each group sequentially
    for (gi, group) in manifest.groups.iter().enumerate() {
        if cancelled.load(Ordering::SeqCst) {
            return Err(BacktesterError::Validation("Cancelled by signal".into()));
        }

        // Validate group paths
        if !group.spec_path.exists() {
            return Err(BacktesterError::Validation(format!(
                "Group '{}' spec not found: {}", group.group_id, group.spec_path.display()
            )));
        }
        if !group.data_path.exists() {
            return Err(BacktesterError::Validation(format!(
                "Group '{}' data not found: {}", group.group_id, group.data_path.display()
            )));
        }

        let n_candidates = group.candidates.len();
        eprintln!(
            "{{\"level\":\"info\",\"msg\":\"Processing group {}/{}: '{}' ({} candidates)\"}}",
            gi + 1, n_groups, group.group_id, n_candidates
        );

        // Load per-group enriched signal data
        let group_data = engine::load_market_data(&group.data_path)?;

        // Load per-group strategy spec
        let base_spec = strategy_engine::parse_spec_from_file(&group.spec_path)
            .map_err(|e| BacktesterError::StrategySpec(format!(
                "Group '{}': {e}", group.group_id
            )))?;

        // Create output directory for this group
        std::fs::create_dir_all(&group.output_dir)?;

        // Run vectorized batch evaluation
        let scores = backtester::batch_eval::run_batch_vectorized(
            &group_data,
            &group.candidates,
            &base_spec,
            &cost_model,
            cancelled.clone(),
            manifest.window_start,
            manifest.window_end,
        )?;

        // Write scores.arrow to group's output directory
        write_scores_arrow(&group.output_dir, &scores)?;

        // In scores-only mode (optimization), skip best-candidate re-run
        if !manifest.scores_only {
            if let Some((best_idx, _)) = scores.iter().enumerate()
                .filter(|(_, s)| s.is_finite() && **s != 0.0)
                .max_by(|(_, a), (_, b)| a.partial_cmp(b).unwrap_or(std::cmp::Ordering::Equal))
            {
                let mut best_spec = base_spec.clone();
                apply_candidate_params(&mut best_spec, &group.candidates[best_idx]);

                let fold_config = if let Some(ref boundaries) = manifest.fold_boundaries {
                    let json = serde_json::to_string(boundaries).unwrap();
                    FoldConfig::from_args(Some(&json), args.embargo_bars)
                        .map_err(|e| BacktesterError::Validation(e))?
                } else {
                    None
                };

                let best_result = engine::run_backtest(
                    &best_spec,
                    &group.data_path,
                    &cost_model,
                    &group.output_dir,
                    &group.group_id,
                    cancelled.clone(),
                    fold_config,
                    None,
                    manifest.window_start,
                    manifest.window_end,
                )?;

                output::write_results(
                    &group.output_dir,
                    &best_result,
                    &group.group_id,
                    &base_spec.metadata.name,
                )?;
            }
        }

        eprintln!(
            "{{\"level\":\"info\",\"msg\":\"Group '{}' complete: {} candidates scored\"}}",
            group.group_id, n_candidates
        );
    }

    eprintln!(
        "{{\"level\":\"info\",\"msg\":\"Manifest complete: {} groups, {} total candidates\"}}",
        n_groups, total_candidates
    );

    Ok(())
}

/// Apply flat parameter dict to strategy spec's exit rules.
fn apply_candidate_params(spec: &mut StrategySpec, params: &std::collections::BTreeMap<String, f64>) {
    if let Some(&val) = params.get("sl_atr_multiplier") {
        spec.exit_rules.stop_loss.value = val;
    }
    if let Some(&val) = params.get("tp_rr_ratio") {
        if let Some(ref mut tp) = spec.exit_rules.take_profit {
            tp.value = val;
        }
    }
    if let Some(&val) = params.get("trailing_atr_multiplier") {
        if let Some(ref mut trailing) = spec.exit_rules.trailing {
            match trailing {
                strategy_engine::TrailingConfig::Chandelier(ref mut p) => {
                    p.atr_multiplier = val;
                }
                strategy_engine::TrailingConfig::TrailingStop(ref mut p) => {
                    p.distance_pips = val;
                }
            }
        }
    }
    if let Some(&val) = params.get("trailing_atr_period") {
        if let Some(ref mut trailing) = spec.exit_rules.trailing {
            match trailing {
                strategy_engine::TrailingConfig::Chandelier(ref mut p) => {
                    p.atr_period = val as u32;
                }
                strategy_engine::TrailingConfig::TrailingStop(_) => {}
            }
        }
    }
    // Entry indicator params (swing_bars, atr_period, etc.) are applied via
    // per-group signal precompute + spec override, not here.
}

/// Write per-candidate scores as Arrow IPC.
fn write_scores_arrow(output_dir: &std::path::Path, scores: &[f64]) -> Result<(), BacktesterError> {
    use arrow::array::Float64Array;
    use arrow::datatypes::{DataType, Field, Schema};
    use arrow::record_batch::RecordBatch;
    use arrow::ipc::writer::FileWriter;

    let schema = Schema::new(vec![
        Field::new("score", DataType::Float64, false),
    ]);

    let score_array = Float64Array::from(scores.to_vec());
    let batch = RecordBatch::try_new(
        std::sync::Arc::new(schema.clone()),
        vec![std::sync::Arc::new(score_array)],
    ).map_err(|e| BacktesterError::Validation(format!("Failed to create scores batch: {e}")))?;

    let scores_path = output_dir.join("scores.arrow");
    let file = std::fs::File::create(&scores_path)?;
    let mut writer = FileWriter::try_new(file, &schema)
        .map_err(|e| BacktesterError::Validation(format!("Failed to create scores writer: {e}")))?;

    writer.write(&batch)
        .map_err(|e| BacktesterError::Validation(format!("Failed to write scores: {e}")))?;

    writer.finish()
        .map_err(|e| BacktesterError::Validation(format!("Failed to finish scores: {e}")))?;

    eprintln!(
        "{{\"level\":\"info\",\"msg\":\"Wrote scores.arrow with {} entries\"}}",
        scores.len()
    );

    Ok(())
}
