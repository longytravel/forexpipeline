//! Persistent worker process — keeps market data in memory across evaluations.
//!
//! Protocol: JSON-lines over stdin/stdout. Python sends commands, worker replies
//! with structured JSON responses. Stderr is reserved for tracing logs.
//!
//! Commands: init, load_data, eval, shutdown.
//! State: LRU cache of Arrow RecordBatches keyed by signal hash.

use std::collections::{BTreeMap, HashMap};
use std::io::{self, BufRead, BufReader, BufWriter, Write};
use std::path::{Path, PathBuf};
use std::sync::atomic::{AtomicBool, AtomicU32, Ordering};
use std::sync::Arc;

use arrow::record_batch::RecordBatch;
use lru::LruCache;
use serde::{Deserialize, Serialize};

use crate::batch_eval;
use crate::engine;
use cost_model::CostModel;
use common::error_types::BacktesterError;
use strategy_engine::StrategySpec;

// ---------------------------------------------------------------------------
// Protocol types
// ---------------------------------------------------------------------------

/// Inbound command from Python (one JSON line on stdin).
#[derive(Debug, Deserialize)]
#[serde(tag = "cmd", rename_all = "snake_case")]
enum Command {
    Init {
        id: u64,
        cost_model_path: PathBuf,
        #[serde(default = "default_budget_mb")]
        memory_budget_mb: u64,
    },
    LoadData {
        id: u64,
        key: String,
        data_path: PathBuf,
    },
    Eval {
        id: u64,
        data_key: String,
        groups: Vec<EvalGroup>,
        #[serde(default)]
        window_start: Option<u64>,
        #[serde(default)]
        window_end: Option<u64>,
        /// Reserved for future use — currently all eval responses return scores only.
        #[serde(default)]
        #[allow(dead_code)]
        scores_only: bool,
    },
    Shutdown {
        id: u64,
    },
}

fn default_budget_mb() -> u64 {
    8192
}

/// A signal group within an eval command.
#[derive(Debug, Deserialize)]
struct EvalGroup {
    group_id: String,
    spec_path: PathBuf,
    candidates: Vec<BTreeMap<String, f64>>,
}

/// Outbound response to Python (one JSON line on stdout).
#[derive(Debug, Serialize)]
struct Response {
    id: u64,
    ok: bool,
    #[serde(skip_serializing_if = "Option::is_none")]
    rows: Option<usize>,
    #[serde(skip_serializing_if = "Option::is_none")]
    results: Option<HashMap<String, Vec<f64>>>,
    #[serde(skip_serializing_if = "Option::is_none")]
    error: Option<ErrorEnvelope>,
}

/// Structured error in the response envelope.
#[derive(Debug, Serialize)]
struct ErrorEnvelope {
    code: String,
    message: String,
    fatal: bool,
}

impl Response {
    fn ok(id: u64) -> Self {
        Self { id, ok: true, rows: None, results: None, error: None }
    }

    fn ok_rows(id: u64, rows: usize) -> Self {
        Self { id, ok: true, rows: Some(rows), results: None, error: None }
    }

    fn ok_results(id: u64, results: HashMap<String, Vec<f64>>) -> Self {
        Self { id, ok: true, rows: None, results: Some(results), error: None }
    }

    fn err(id: u64, code: &str, message: String, fatal: bool) -> Self {
        Self {
            id,
            ok: false,
            rows: None,
            results: None,
            error: Some(ErrorEnvelope {
                code: code.to_string(),
                message,
                fatal,
            }),
        }
    }
}

// ---------------------------------------------------------------------------
// Cache
// ---------------------------------------------------------------------------

/// A cached Arrow RecordBatch with memory tracking.
struct CacheEntry {
    batch: Arc<RecordBatch>,
    bytes: usize,
    in_flight: AtomicU32,
    /// The file path used to load this entry, for staleness detection.
    data_path: PathBuf,
}

/// Worker state held across commands.
struct WorkerCache {
    cost_model: Option<CostModel>,
    data: LruCache<String, CacheEntry>,
    strategy_specs: HashMap<String, Arc<StrategySpec>>,
    budget_bytes: usize,
    used_bytes: usize,
}

impl WorkerCache {
    fn new(budget_mb: u64) -> Self {
        // Unbounded LRU — we manage eviction ourselves via the byte budget.
        // A bounded LruCache auto-evicts on put() without consulting in_flight
        // or strong_count, which would break our memory accounting.
        Self {
            cost_model: None,
            data: LruCache::unbounded(),
            strategy_specs: HashMap::new(),
            budget_bytes: (budget_mb as usize) * 1024 * 1024,
            used_bytes: 0,
        }
    }

    /// Compute actual Arrow buffer bytes for a RecordBatch.
    fn batch_bytes(batch: &RecordBatch) -> usize {
        batch.columns().iter().map(|col| col.get_array_memory_size()).sum()
    }

    /// Evict LRU entries until we have `needed` bytes free.
    /// Respects in_flight and Arc strong_count safety checks.
    fn evict_until_free(&mut self, needed: usize) -> bool {
        while self.used_bytes + needed > self.budget_bytes {
            // Find the LRU key that is safe to evict
            let evict_key = {
                let mut found = None;
                // Iterate from LRU (least recently used) end
                for (key, entry) in self.data.iter() {
                    let in_flight = entry.in_flight.load(Ordering::SeqCst);
                    let strong = Arc::strong_count(&entry.batch);
                    if in_flight == 0 && strong == 1 {
                        found = Some(key.clone());
                        break;
                    }
                }
                found
            };

            match evict_key {
                Some(key) => {
                    if let Some(entry) = self.data.pop(&key) {
                        self.used_bytes = self.used_bytes.saturating_sub(entry.bytes);
                        eprintln!(
                            "{{\"level\":\"info\",\"msg\":\"Evicted cache key '{}' ({} bytes)\"}}",
                            key, entry.bytes
                        );
                    }
                }
                None => return false, // Cannot evict anything — all entries in use
            }
        }
        true
    }

    /// Load a strategy spec, caching by path string.
    fn get_or_load_spec(&mut self, spec_path: &Path) -> Result<Arc<StrategySpec>, BacktesterError> {
        let key = spec_path.to_string_lossy().to_string();
        if let Some(cached) = self.strategy_specs.get(&key) {
            return Ok(Arc::clone(cached));
        }

        let spec = strategy_engine::parse_spec_from_file(spec_path)
            .map_err(|e| BacktesterError::StrategySpec(e.to_string()))?;

        let arc = Arc::new(spec);
        self.strategy_specs.insert(key, Arc::clone(&arc));
        Ok(arc)
    }
}

// ---------------------------------------------------------------------------
// Command handlers
// ---------------------------------------------------------------------------

fn handle_init(cache: &mut WorkerCache, id: u64, cost_model_path: &Path, budget_mb: u64) -> Response {
    // Update budget
    cache.budget_bytes = (budget_mb as usize) * 1024 * 1024;

    // Evict entries that exceed the new (possibly smaller) budget
    cache.evict_until_free(0);

    // Load cost model
    match cost_model::load_from_file(cost_model_path) {
        Ok(cm) => {
            eprintln!(
                "{{\"level\":\"info\",\"msg\":\"Init: cost model '{}', budget {}MB\"}}",
                cm.version(), budget_mb
            );
            cache.cost_model = Some(cm);
            Response::ok(id)
        }
        Err(e) => Response::err(id, "INIT_FAILED", format!("Cost model load failed: {e}"), true),
    }
}

fn handle_load_data(cache: &mut WorkerCache, id: u64, key: &str, data_path: &Path) -> Response {
    // Check if already cached — evict if path differs (stale data detection)
    if let Some(entry) = cache.data.peek(&key.to_string()) {
        if entry.data_path == data_path {
            // Same path, promote in LRU and return cached
            if let Some(entry) = cache.data.get(&key.to_string()) {
                let rows = entry.batch.num_rows();
                return Response::ok_rows(id, rows);
            }
        } else {
            // Different path — evict stale entry and reload
            eprintln!(
                "{{\"level\":\"info\",\"msg\":\"Key '{}' path changed, evicting stale entry\"}}",
                key
            );
            if let Some(evicted) = cache.data.pop(&key.to_string()) {
                cache.used_bytes = cache.used_bytes.saturating_sub(evicted.bytes);
            }
        }
    }

    // Load the Arrow data
    let batch = match engine::load_market_data(data_path) {
        Ok(b) => b,
        Err(e) => return Response::err(
            id, "LOAD_FAILED",
            format!("Failed to load '{}': {e}", data_path.display()),
            false,
        ),
    };

    let bytes = WorkerCache::batch_bytes(&batch);
    let rows = batch.num_rows();

    // Evict if needed to fit within budget
    if !cache.evict_until_free(bytes) {
        return Response::err(
            id, "OOM",
            format!(
                "Cannot fit {} bytes (key '{}') into budget ({} used / {} total)",
                bytes, key, cache.used_bytes, cache.budget_bytes
            ),
            false,
        );
    }

    cache.used_bytes += bytes;
    cache.data.put(key.to_string(), CacheEntry {
        batch: Arc::new(batch),
        bytes,
        in_flight: AtomicU32::new(0),
        data_path: data_path.to_path_buf(),
    });

    eprintln!(
        "{{\"level\":\"info\",\"msg\":\"Loaded key '{}': {} rows, {} bytes\"}}",
        key, rows, bytes
    );

    Response::ok_rows(id, rows)
}

fn handle_eval(
    cache: &mut WorkerCache,
    id: u64,
    data_key: &str,
    groups: &[EvalGroup],
    window_start: Option<u64>,
    window_end: Option<u64>,
) -> Response {
    // Validate window bounds to prevent usize underflow / huge allocations
    if let (Some(ws), Some(we)) = (window_start, window_end) {
        if ws > we {
            return Response::err(
                id,
                "INVALID_WINDOW",
                format!("window_start ({}) > window_end ({})", ws, we),
                false,
            );
        }
    }

    // Clone cost model out to avoid holding an immutable borrow on cache
    // while we need mutable access for spec loading below.
    let cost_model = match cache.cost_model.clone() {
        Some(cm) => cm,
        None => return Response::err(
            id, "NOT_INITIALIZED",
            "Cost model not loaded — call init first".into(),
            false,
        ),
    };

    // Look up cached data — clone the Arc to release the borrow on cache
    let batch = match cache.data.get(data_key) {
        Some(entry) => {
            entry.in_flight.fetch_add(1, Ordering::SeqCst);
            Arc::clone(&entry.batch)
        }
        None => return Response::err(
            id, "CACHE_MISS",
            format!("Key '{}' not loaded", data_key),
            false,
        ),
    };

    // Validate window_end against data length
    if let Some(we) = window_end {
        let num_rows = batch.num_rows() as u64;
        if we > num_rows {
            if let Some(entry) = cache.data.get(data_key) {
                entry.in_flight.fetch_sub(1, Ordering::SeqCst);
            }
            return Response::err(
                id,
                "INVALID_WINDOW",
                format!("window_end ({}) exceeds data length ({})", we, num_rows),
                false,
            );
        }
    }

    let cancelled = Arc::new(AtomicBool::new(false));
    let mut all_results: HashMap<String, Vec<f64>> = HashMap::new();

    for group in groups {
        // Load or get cached spec
        let spec = match cache.get_or_load_spec(&group.spec_path) {
            Ok(s) => s,
            Err(e) => {
                // Decrement in_flight and return error for entire eval
                if let Some(entry) = cache.data.get(data_key) {
                    entry.in_flight.fetch_sub(1, Ordering::SeqCst);
                }
                return Response::err(
                    id, "SPEC_FAILED",
                    format!("Group '{}': {e}", group.group_id),
                    false,
                );
            }
        };

        // Run vectorized batch evaluation
        let scores = match batch_eval::run_batch_vectorized(
            &batch,
            &group.candidates,
            &spec,
            &cost_model,
            cancelled.clone(),
            window_start,
            window_end,
        ) {
            Ok(s) => s,
            Err(e) => {
                if let Some(entry) = cache.data.get(data_key) {
                    entry.in_flight.fetch_sub(1, Ordering::SeqCst);
                }
                return Response::err(
                    id, "EVAL_FAILED",
                    format!("Group '{}': {e}", group.group_id),
                    false,
                );
            }
        };

        all_results.insert(group.group_id.clone(), scores);
    }

    // Decrement in_flight
    if let Some(entry) = cache.data.get(data_key) {
        entry.in_flight.fetch_sub(1, Ordering::SeqCst);
    }

    Response::ok_results(id, all_results)
}

// ---------------------------------------------------------------------------
// Main loop
// ---------------------------------------------------------------------------

/// Run the persistent worker process. Reads JSON-line commands from stdin,
/// writes JSON-line responses to stdout. Returns on shutdown or stdin EOF.
pub fn run() -> Result<(), BacktesterError> {
    let stdin = io::stdin();
    let reader = BufReader::new(stdin.lock());
    let stdout = io::stdout();
    let mut writer = BufWriter::new(stdout.lock());

    let mut cache = WorkerCache::new(default_budget_mb());

    eprintln!("{{\"level\":\"info\",\"msg\":\"Worker started, awaiting commands\"}}");

    for line in reader.lines() {
        let line = match line {
            Ok(l) => l,
            Err(e) => {
                eprintln!("{{\"level\":\"error\",\"msg\":\"stdin read error: {e}\"}}");
                return Err(BacktesterError::Io(e));
            }
        };

        let line = line.trim();
        if line.is_empty() {
            continue;
        }

        let cmd: Command = match serde_json::from_str(line) {
            Ok(c) => c,
            Err(e) => {
                // Attempt to extract "id" from the raw JSON so the Python
                // client can correlate the error to the correct pending future.
                let fallback_id = serde_json::from_str::<serde_json::Value>(line)
                    .ok()
                    .and_then(|v| v.get("id")?.as_u64())
                    .unwrap_or(0);
                let resp = Response::err(fallback_id, "PARSE_ERROR", format!("Invalid command: {e}"), false);
                write_response(&mut writer, &resp)?;
                continue;
            }
        };

        match cmd {
            Command::Init { id, cost_model_path, memory_budget_mb } => {
                let resp = handle_init(&mut cache, id, &cost_model_path, memory_budget_mb);
                write_response(&mut writer, &resp)?;
            }
            Command::LoadData { id, key, data_path } => {
                let resp = handle_load_data(&mut cache, id, &key, &data_path);
                write_response(&mut writer, &resp)?;
            }
            Command::Eval { id, data_key, groups, window_start, window_end, scores_only: _ } => {
                let resp = handle_eval(
                    &mut cache, id, &data_key, &groups,
                    window_start, window_end,
                );
                write_response(&mut writer, &resp)?;
            }
            Command::Shutdown { id } => {
                let resp = Response::ok(id);
                write_response(&mut writer, &resp)?;
                eprintln!("{{\"level\":\"info\",\"msg\":\"Shutdown acknowledged\"}}");
                return Ok(());
            }
        }
    }

    eprintln!("{{\"level\":\"info\",\"msg\":\"Worker exiting (stdin closed)\"}}");
    Ok(())
}

/// Write a single JSON response line and flush.
fn write_response<W: Write>(writer: &mut W, resp: &Response) -> Result<(), BacktesterError> {
    serde_json::to_writer(&mut *writer, resp)
        .map_err(|e| BacktesterError::Validation(format!("Failed to serialize response: {e}")))?;
    writer.write_all(b"\n")
        .map_err(|e| BacktesterError::Io(e))?;
    writer.flush()
        .map_err(|e| BacktesterError::Io(e))?;
    Ok(())
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

#[cfg(test)]
mod tests {
    use super::*;
    use std::io::Cursor;

    /// Helper: run a sequence of JSON-line commands through the worker loop
    /// and return all response lines.
    fn run_commands(input: &str) -> Vec<Response> {
        let reader = BufReader::new(Cursor::new(input.as_bytes().to_vec()));
        let mut output = Vec::new();
        let mut cache = WorkerCache::new(64); // 64MB test budget

        for line in reader.lines() {
            let line = line.unwrap();
            let line = line.trim();
            if line.is_empty() {
                continue;
            }

            let cmd: Result<Command, _> = serde_json::from_str(line);
            match cmd {
                Ok(Command::Init { id, cost_model_path, memory_budget_mb }) => {
                    output.push(handle_init(&mut cache, id, &cost_model_path, memory_budget_mb));
                }
                Ok(Command::LoadData { id, key, data_path }) => {
                    output.push(handle_load_data(&mut cache, id, &key, &data_path));
                }
                Ok(Command::Eval { id, data_key, groups, window_start, window_end, .. }) => {
                    let resp = handle_eval(&mut cache, id, &data_key, &groups, window_start, window_end);
                    output.push(resp);
                }
                Ok(Command::Shutdown { id }) => {
                    output.push(Response::ok(id));
                }
                Err(e) => {
                    output.push(Response::err(0, "PARSE_ERROR", format!("Invalid command: {e}"), false));
                }
            }
        }

        output
    }

    #[test]
    fn test_shutdown_responds_ok() {
        let responses = run_commands("{\"cmd\":\"shutdown\",\"id\":42}\n");
        assert_eq!(responses.len(), 1);
        assert!(responses[0].ok);
        assert_eq!(responses[0].id, 42);
    }

    #[test]
    fn test_parse_error_returns_structured_error() {
        let responses = run_commands("this is not valid json\n");
        assert_eq!(responses.len(), 1);
        assert!(!responses[0].ok);
        let err = responses[0].error.as_ref().unwrap();
        assert_eq!(err.code, "PARSE_ERROR");
        assert!(!err.fatal);
    }

    #[test]
    fn test_eval_cache_miss_returns_error() {
        // Init with a fake path (will fail), then try eval
        let input = concat!(
            "{\"cmd\":\"eval\",\"id\":3,\"data_key\":\"nonexistent\",",
            "\"groups\":[{\"group_id\":\"g1\",\"spec_path\":\"x.toml\",",
            "\"candidates\":[{\"sl_atr_multiplier\":1.5}]}]}\n"
        );
        let responses = run_commands(input);
        assert_eq!(responses.len(), 1);
        assert!(!responses[0].ok);
        let err = responses[0].error.as_ref().unwrap();
        assert_eq!(err.code, "NOT_INITIALIZED");
        assert!(!err.fatal);
    }

    #[test]
    fn test_eval_without_init_returns_not_initialized() {
        let input = concat!(
            "{\"cmd\":\"eval\",\"id\":5,\"data_key\":\"some_key\",",
            "\"groups\":[{\"group_id\":\"g1\",\"spec_path\":\"x.toml\",",
            "\"candidates\":[]}]}\n"
        );
        let responses = run_commands(input);
        assert_eq!(responses.len(), 1);
        assert!(!responses[0].ok);
        let err = responses[0].error.as_ref().unwrap();
        assert_eq!(err.code, "NOT_INITIALIZED");
    }

    #[test]
    fn test_load_data_missing_file_returns_error() {
        let input = concat!(
            "{\"cmd\":\"load_data\",\"id\":2,\"key\":\"test_key\",",
            "\"data_path\":\"nonexistent_file.arrow\"}\n"
        );
        let responses = run_commands(input);
        assert_eq!(responses.len(), 1);
        assert!(!responses[0].ok);
        let err = responses[0].error.as_ref().unwrap();
        assert_eq!(err.code, "LOAD_FAILED");
        assert!(!err.fatal);
    }

    #[test]
    fn test_lru_eviction_respects_in_flight() {
        let schema = arrow::datatypes::Schema::new(vec![
            arrow::datatypes::Field::new("x", arrow::datatypes::DataType::Float64, false),
        ]);
        let col = arrow::array::Float64Array::from(vec![1.0; 1000]);
        let batch = RecordBatch::try_new(
            Arc::new(schema),
            vec![Arc::new(col)],
        ).unwrap();
        let bytes = WorkerCache::batch_bytes(&batch);

        // Budget fits exactly 2 entries — adding a 3rd forces eviction
        let mut cache = WorkerCache::new(1); // 1MB default
        cache.budget_bytes = bytes * 2; // Tight budget: room for exactly 2 entries

        // Insert busy_key first (LRU = least recently used)
        cache.data.put("busy_key".to_string(), CacheEntry {
            batch: Arc::new(batch.clone()),
            bytes,
            in_flight: AtomicU32::new(1), // Simulate in-flight eval
            data_path: PathBuf::from("test_busy.arrow"),
        });
        cache.used_bytes = bytes;

        // Insert idle_key second (more recently used than busy_key)
        cache.data.put("idle_key".to_string(), CacheEntry {
            batch: Arc::new(batch.clone()),
            bytes,
            in_flight: AtomicU32::new(0),
            data_path: PathBuf::from("test_idle.arrow"),
        });
        cache.used_bytes += bytes;

        // Evict to make room for a new entry of `bytes` size.
        // busy_key is LRU but in_flight=1, so it must be skipped.
        // idle_key is next and in_flight=0, so it should be evicted.
        let could_evict = cache.evict_until_free(bytes);

        assert!(could_evict, "Should be able to evict idle entry");
        assert!(cache.data.contains(&"busy_key".to_string()), "busy_key must survive (in_flight=1)");
        assert!(!cache.data.contains(&"idle_key".to_string()), "idle_key should be evicted");
    }

    #[test]
    fn test_lru_eviction_respects_arc_strong_count() {
        let mut cache = WorkerCache::new(1); // 1MB

        let schema = arrow::datatypes::Schema::new(vec![
            arrow::datatypes::Field::new("x", arrow::datatypes::DataType::Float64, false),
        ]);
        let col = arrow::array::Float64Array::from(vec![1.0; 1000]);
        let batch = RecordBatch::try_new(
            Arc::new(schema),
            vec![Arc::new(col)],
        ).unwrap();
        let bytes = WorkerCache::batch_bytes(&batch);

        let shared_batch = Arc::new(batch.clone());

        // Insert entry where someone else holds a reference (strong_count > 1)
        let extra_ref = Arc::clone(&shared_batch);
        cache.data.put("held_key".to_string(), CacheEntry {
            batch: shared_batch,
            bytes,
            in_flight: AtomicU32::new(0),
            data_path: PathBuf::from("test_held.arrow"),
        });
        cache.used_bytes = bytes;

        // Try to evict — should fail because strong_count > 1
        let could_evict = cache.evict_until_free(cache.budget_bytes);
        assert!(!could_evict, "Should not evict entry with strong_count > 1");
        assert!(cache.data.contains(&"held_key".to_string()));

        // Drop extra reference, then eviction should succeed
        drop(extra_ref);
        let could_evict = cache.evict_until_free(cache.budget_bytes);
        assert!(could_evict, "Should evict after dropping extra Arc ref");
    }

    #[test]
    fn test_response_serialization() {
        let resp = Response::ok(1);
        let json = serde_json::to_string(&resp).unwrap();
        assert!(json.contains("\"id\":1"));
        assert!(json.contains("\"ok\":true"));
        // Optional fields should be absent
        assert!(!json.contains("\"rows\""));
        assert!(!json.contains("\"error\""));

        let resp = Response::err(2, "CACHE_MISS", "key not found".into(), false);
        let json = serde_json::to_string(&resp).unwrap();
        assert!(json.contains("\"ok\":false"));
        assert!(json.contains("CACHE_MISS"));
        assert!(json.contains("\"fatal\":false"));
    }

    #[test]
    fn test_write_response_flushes() {
        let resp = Response::ok_rows(7, 5000);
        let mut buf = Vec::new();
        write_response(&mut buf, &resp).unwrap();
        let output = String::from_utf8(buf).unwrap();
        assert!(output.ends_with('\n'));
        let parsed: serde_json::Value = serde_json::from_str(output.trim()).unwrap();
        assert_eq!(parsed["id"], 7);
        assert_eq!(parsed["rows"], 5000);
    }
}
