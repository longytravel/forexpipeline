# Lessons Learned

## Story 1-5-data-validation-quality-scoring
- ACCEPTED (Both): timezone_issues computed by _verify_timezone_alignment() but never added to report, scoring, quarantine, or gate — findings fully discarded
  → Rule: If a validation check is called, its results must appear in the output artifact. Never compute-and-discard — either wire the result into the report/gate or don't call the method. Dead results create false confidence that the check influences downstream behavior.

- ACCEPTED (Both): quarantined_periods report summary only included gaps and stale records, not integrity-error quarantines; gap bar_count hardcoded to 0
  → Rule: When building a summary of marked data, account for every marking source. If three mechanisms mark rows, the summary must explain all three. Discrepancies between data state and report text erode operator trust.

- ACCEPTED (Both): config_hash field in quality report always blank — placeholder never populated
  → Rule: Don't ship placeholder fields in production artifacts. An empty field in a report looks like a bug. Either populate it from available data (config hash utility exists) or omit the field entirely.

- ACCEPTED (BMAD): Story spec's gate semantics (score-only) conflicted with architecture's per-check ERROR actions (reject/re-download) — implementation correctly followed spec but left architecture actions unaddressed
  → Rule: When architecture specifies per-check actions beyond scoring (e.g., "reject and re-download"), story specs must explicitly assign those actions to either the checker or the orchestrator. Ambiguity leads to dropped behavior.

## Story 1-6-parquet-storage-arrow-ipc-conversion
- ACCEPTED (Both): converter_cli.py looks for validated data in `raw/.../validated-data.csv` but quality_checker saves to `validated/.../{dataset_id}_validated.csv` — CLI entry point always fails on real pipeline runs
  → Rule: Stage handoff paths must be tested end-to-end at the CLI/persisted-artifact level, not just via in-memory DataFrame passing. Add a CLI-to-CLI chain test that exercises the actual file path contract between stages.

- ACCEPTED (Both): VALID_SESSIONS hardcoded as a frozenset while contracts/arrow_schemas.toml defines the allowed values (including "mixed") — two sources of truth that can drift
  → Rule: If a contract file defines allowed values, runtime code must load from that file, not duplicate it. Hardcoding values the contract already specifies creates drift risk and violates single-source-of-truth.

- ACCEPTED (Both): New config keys ([data_pipeline.storage], [data_pipeline.parquet]) added to base.toml but not covered by schema.toml validation
  → Rule: Every story that adds config keys must add corresponding schema.toml validation entries. Consider a contract test that verifies every key in base.toml has a schema.toml entry.

- ACCEPTED (BMAD): Manifest records quality_score/rating as scalars but doesn't link to upstream quality report path or source dataset manifest — no artifact chain traceability
  → Rule: Each stage's manifest should include a reference to the previous stage's manifest (path + hash), building a linked lineage chain. A `source_manifest` field suffices. Don't just copy scalar values — link to the source artifact.

## Story 1-7-timeframe-conversion
- ACCEPTED (Both): H1 session recomputation used majority-vote on pre-labeled M1 data instead of recomputing from config schedule
  → Rule: When the spec says "recompute from config," always use the config-driven utility function — never rely on pre-existing labels from upstream stages, as they may be incorrect or stale.

- ACCEPTED (Both): target_timeframes array elements had no validation at schema or runtime level
  → Rule: Array config values need element-level validation, not just array-level type checks. Add both schema constraints and runtime guards for defense in depth.

- ACCEPTED (Codex): Partial preexisting output (one of two files) caused the valid artifact to be overwritten
  → Rule: When writing paired artifacts (e.g., Arrow IPC + Parquet), check and skip each file independently. Never assume both are in the same state.

- ACCEPTED (BMAD): Empty aggregation path returned source schema instead of canonical output schema
  → Rule: Empty-result code paths must produce the exact same schema as non-empty paths. Use a single canonical schema definition, not derived copies.

- ACCEPTED (Codex): No guard before calling functions that assume non-empty input (e.g., min/max on empty column)
  → Rule: Always guard against empty tables before operations that assume at least one row. Return early with a clear log message rather than letting PyArrow raise a cryptic error.

## Story 1-8-data-splitting-consistent-sourcing
- ACCEPTED (Codex): Split filenames omitted the data hash, so new downloads for the same pair/date range would silently reuse stale split artifacts from prior downloads
  → Rule: When immutability depends on content identity, embed a content hash in the filename. Never rely solely on existence checks without hash verification — "file exists" does not mean "file is the right version."

- ACCEPTED (Codex): Ratio-mode splitting sliced by row index without sorting by timestamp first, so unsorted input produced non-chronological partitions
  → Rule: Always sort time-series data by timestamp before any positional operation (slice, index-based split). Defensive sorting is cheap; silent misordering is catastrophic for temporal guarantees.

- ACCEPTED (Codex): Date-mode metadata recorded the actual last-train timestamp but lost the user-configured split boundary date
  → Rule: When a user-configured value is transformed into an internal representation, record both the configured value and the actual value in metadata. Traceability requires knowing intent, not just outcome.

## Story 1-9-e2e-pipeline-proof-market-data-flow
- ACCEPTED (Both): Artifact chain verification (AC8) marked complete but only checked for `.partial` files and config hash — no manifest cross-reference, no orphan detection, no hash-chain verification
  → Rule: "Verify artifact chain" means bidirectional: every file on disk must be in the manifest AND every manifest entry must exist on disk. Always implement both directions — one-way checks create false confidence.

- ACCEPTED (Both): Log verifier searched for `python_*.log` but the logging system writes `python_*.jsonl` — the wrong file extension meant verification never found real log files
  → Rule: When one component produces files that another component consumes, derive the filename pattern from the producer's code or config, never hardcode it independently. A single constant or config key should be the source of truth.

- ACCEPTED (Both): Download stage required columns set omitted `bid` and `ask` despite the story spec and `arrow_schemas.toml` both listing them
  → Rule: When a contract file (schema TOML) defines required columns, the validation code should either load from that file or mirror it exactly. Cross-reference verification code against the contract during review.

- ACCEPTED (Both): Quality report verification only checked JSON validity, not that required fields (`gap_count`, `integrity_checks`, `staleness_checks`) were present — an empty `{}` would pass
  → Rule: "Verify artifact is produced" must include content validation, not just existence/format checks. An empty valid-JSON file is not a valid artifact.

- ACCEPTED (Both): Log verification accepted `valid > 0` (at least one valid line) — 50% invalid JSON lines would still pass; no per-line field checks for required schema fields
  → Rule: Verification tolerances must match the claim. If the AC says "each log line contains required fields," the check must be per-line, not aggregate. Weak checks undermine the proof's value.

- ACCEPTED (Codex): `glob("*_manifest.json")[-1]` used in 4 locations to find the manifest — in multi-dataset directories this silently picks the wrong manifest
  → Rule: File lookups in shared directories must be scoped by the current operation's identity (e.g., dataset_id). Never use glob-and-pick-last as a substitute for deterministic lookup.

- ACCEPTED (Codex): Missing train/test split files caused the verification loop to silently skip instead of fail — `if train_files and test_files` guarded the entire check
  → Rule: "File not found" in a verification stage must be an error, not a skip. Guard clauses that skip verification on missing inputs hide failures. Check existence first, then verify contents.

- ACCEPTED (Codex): Reproducibility check only hashed `.arrow` and `.parquet` files, excluding `quality-report.json` — a non-deterministic quality checker would go undetected
  → Rule: Reproducibility verification must cover ALL artifacts the pipeline claims to produce deterministically. Enumerate the full artifact set from the manifest, not just binary formats.

- ACCEPTED (BMAD): Session valid set hardcoded without "mixed" despite `arrow_schemas.toml` including it for aggregated timeframes
  → Rule: (Repeat of Story 1-6 lesson) Runtime code must load allowed values from the contract file, not duplicate them. This is the second time this pattern has caused a bug.

- ACCEPTED (BMAD): `to_pylist()` used to find min/max of 500K+ element timestamp columns, creating unnecessary Python lists
  → Rule: Use PyArrow compute functions (`pc.min()`, `pc.max()`) instead of converting to Python lists for aggregate operations. This is O(1) memory vs O(n).

## Story 1-10-epic1-pir-remediation (synthesis run 2)
- ACCEPTED (Codex): `ParquetArchiver.write_parquet()` reimplemented crash-safe write logic instead of using the shared `safe_write_parquet` utility, violating AC #4's single-utility requirement
  → Rule: When consolidating duplicate implementations into a shared utility, verify that ALL call sites actually delegate to the new utility. Grep for the old pattern (write-to-partial, fsync, os.replace) across the codebase after consolidation.

- ACCEPTED (Codex): Quality reports auto-compute `config_hash` as bare hex while conversion manifests prefix with `sha256:` — cross-artifact string equality fails
  → Rule: When multiple components produce the same semantic value, enforce a canonical format at the point of computation. Prefixed hashes (`sha256:...`) are self-describing and should be the standard. Add a contract test that asserts format consistency across all artifacts that share a field name.

- ACCEPTED (Codex): All integrity-error timestamps collapsed into one synthetic quarantine period from first to last error — disjoint errors at 10:00 and 15:00 imply a 5-hour bad region that never existed
  → Rule: When grouping events into periods for operator display, use a gap threshold to separate disjoint clusters. A single span from min to max is only valid when events are contiguous. Misleading period metadata erodes operator trust even when counts are correct.

## Story 2-1-claudebacktester-strategy-evaluator-review
- ACCEPTED (Codex): Indicator catalogue listed 12 of 18 indicators — supertrend, keltner, williams_r, cci, swing_highs, swing_lows omitted despite having dedicated tests
  → Rule: When cataloguing a module's public API, use AST parsing or automated enumeration to verify completeness. Manual reading of source files misses functions at the bottom of the file. Write a regression test that cross-references the catalogue against the actual source.

- ACCEPTED (Codex): ATR documented as `ema(true_range(...))` but actually uses Wilder's smoothing — a mathematically distinct algorithm
  → Rule: When documenting computation logic, verify the actual formula in source code, not just function call signatures. Wilder's smoothing and EMA have different multipliers; conflating them propagates incorrect parity expectations to downstream Rust ports.

- ACCEPTED (Codex): Donchian documented as returning 2 values (upper, lower) but actually returns 3 (upper, middle, lower)
  → Rule: When documenting function return types, check the actual `return` statement, not just the function name's mathematical definition. Many implementations add convenience outputs (like a middle band) beyond the textbook definition.

- ACCEPTED (Codex): Loading mechanism said `registry.get()` instantiates and "No referential validation" — but `get()` returns the class, `create()` instantiates, and `get()` raises KeyError on unknown names
  → Rule: When documenting runtime behavior, trace the actual call chain (get→class, create→instance) rather than inferring from method names. Also verify validation claims by checking for exception paths — "no validation" is a strong claim that requires proving the negative.

- ACCEPTED (Both): AC3 explicit unknowns section missing from strategy authoring workflow documentation
  → Rule: When an AC requires "explicit unknowns," treat it as a mandatory section even if you believe everything is known. The section forces the author to actively consider what they might have missed, and "none identified" is a valid but explicit answer.

- ACCEPTED (Codex): Price Sources field missing from true_range, rolling_max, and rolling_min indicator entries
  → Rule: When a catalogue has a defined field schema (AC2 lists required fields), every entry must include every field. Missing fields are not "implied" — they must be explicit for downstream consumers (Story 2.8 registry).

- ACCEPTED (BMAD): Verdict count in completion notes said "7 Adapt" but only 6 were listed, and 2+7+1+1=11≠10
  → Rule: When summarizing a table in prose, cross-check the count against the actual table rows. Enumerate items in parentheses and verify the count matches. Arithmetic errors in summaries undermine confidence in the analysis.

- ACCEPTED (Codex): Checkpoint JSON examples used wrong field names (partial_enabled, hours_start, days_bitmask) instead of actual persisted names (partial_close_enabled, allowed_hours_start, allowed_days)
  → Rule: When documenting persisted data schemas, always verify field names against an actual persisted file, not from memory or code-level variable names. Internal encoding transformations (e.g., list→bitmask) mean the persisted format may differ from the runtime representation.

- ACCEPTED (Codex): Signal.entry_price documented as "signal bar close" but all concrete strategies compute it as next-bar open with close as last-bar fallback only
  → Rule: When documenting runtime behavior, verify against concrete implementations (not just base class or dataclass comments). If multiple strategies share a pattern that differs from the abstract description, the concrete behavior is the truth.

- ACCEPTED (Codex): Precompute-once pattern recommended for D10 adoption without mentioning the SignalCausality/REQUIRES_TRAIN_FIT guard that makes it safe
  → Rule: When recommending an optimization pattern for adoption, always document the correctness invariant that makes it safe. An optimization without its safety constraint is a footgun — downstream implementers will adopt the speed without the guard.

- ACCEPTED (Codex): Authoring workflow documented only legacy generate_signals()/filter_signals()/calc_sl_tp() path, omitting generate_signals_vectorized(), management_modules(), optimization_stages()
  → Rule: When documenting an API surface, enumerate all overridable methods in the base class, not just the ones used by the simplest example. Check which methods concrete subclasses actually override — that reveals the real authoring surface.

## Story 2-2-strategy-definition-format-cost-modeling-research
- ACCEPTED (Codex): Weighted comparison matrix totals were arithmetically wrong — TOML stated 8.60 (correct: 8.45), JSON stated 7.80 (correct: 7.90), DSL stated 4.95 (correct: 5.35)
  → Rule: When producing a scored matrix with weighted criteria, always verify the final totals by recomputing weight × score for each row. Add a regression test that extracts raw scores and recomputes totals. Arithmetic errors in decision artifacts propagate incorrect confidence to downstream consumers.

- ACCEPTED (Codex): Commission example used $3.50/side as 0.35 pips, but a round-trip trade pays both sides ($7.00/lot = 0.70 pips). Annual cost omission understated by ~175 pips.
  → Rule: When converting per-side costs to per-trade costs, always multiply by 2 for round-trip. Make the derivation explicit in the text (e.g., "$3.50/side × 2 = $7.00/lot = 0.70 pips"). Financial arithmetic errors compound — a 2x undercount in commission cascades into incorrect strategy viability conclusions.

- ACCEPTED (Both): Decision records in Sections 5 (Constraint Validation) and 7.3 (Cost Model) were missing AC#10 required elements: evidence sources, unresolved assumptions, downstream contract impact, known limitations
  → Rule: When an AC specifies a decision record template with N required elements, use it as a checklist for EVERY decision section, not just the first one. Decision record completeness degrades as authors fatigue through multiple sections — the last section is always the weakest. Consider a structural test that verifies all required elements appear in each decision section.

## Story 2-3-strategy-specification-schema-contracts
- ACCEPTED (Both): MA crossover reference spec used two separate SMA conditions with threshold=0.0 — semantically broken because SMA of FX prices never crosses zero, and the schema had no mechanism for cross-indicator comparison
  → Rule: When a schema must express relationships between two dynamic values (indicator vs indicator), the schema must support that relationship type natively. A numeric threshold field cannot substitute for a cross-indicator reference. Add a dedicated composite indicator type (e.g., sma_crossover) rather than hacking around schema limitations.

- ACCEPTED (Codex): All Pydantic models had `strict=True` but not `extra="forbid"`, so unknown fields in TOML specs were silently ignored instead of rejected
  → Rule: When the AC says "fail loud on non-conforming specs," `strict=True` is necessary but not sufficient — `extra="forbid"` is what catches unknown/extra fields. Always pair both settings for contract enforcement models.

- ACCEPTED (Both): Indicator parameter names were never validated against the registry's `required_params` — a spec could declare `sma` with `{window: 20}` instead of `{period: 20}` and pass validation
  → Rule: When a registry defines required parameters per type, the validator must cross-check actual parameters against the registry at validation time. Type-name checks alone are insufficient — parameter-name checks are equally important.

- ACCEPTED (Both): `entry_indicator_params` set was populated in the loader but never used — optimization parameters could reference non-existent entry condition params
  → Rule: If you write code that collects data for validation, immediately write the validation that uses it. Dead collection code creates false confidence that validation is happening. Treat "populated but unused" as a CI-worthy lint rule.

- ACCEPTED (Both): Volatility filter period, trailing stop distance_pips, and chandelier atr_period/atr_multiplier were checked for presence but not validated as > 0
  → Rule: Presence checks and value checks are different things. When a parameter must be positive, validate both that it exists AND that it's > 0. A present-but-zero parameter is just as broken as a missing one.

- ACCEPTED (Codex): `save_strategy_spec()` incremented the filename to v002 but wrote the original model with `metadata.version = "v001"` — persisted artifact was internally inconsistent
  → Rule: When auto-incrementing an artifact version, update ALL version references — both the filename AND the embedded metadata. Self-consistency of persisted artifacts is a data integrity requirement, not a cosmetic one.

- ACCEPTED (Codex): `group_dependencies` was modeled as free-form strings with no validation that referenced group names actually existed
  → Rule: When a field references other named entities in the same model, add a model-level validator that cross-checks references against the actual set of names. Free-form strings that are semantically constrained must be validated at parse time.

## Story 2-5-strategy-review-confirmation-versioning
- ACCEPTED (Both): VERSION_PATTERN `r"^v\d{3}$"` rejected v1000+ versions, but `increment_version("v999")` produces `"v1000"` — integration failure untested because unit test only tested the incrementer in isolation
  → Rule: When a format constraint (regex) and a producer function (incrementer) operate on the same value space, write an integration test that round-trips the producer's output through the constraint. Boundary values (v999→v1000) are where format assumptions break.

- ACCEPTED (Both): `StrategyMetadata` had no `created_at`/`confirmed_at` fields — confirmer computed timestamps but could never persist them; idempotent path used `hasattr()` that always returned False
  → Rule: If a workflow step must persist a value into a model, the model must have a field for it. Computing a value without a storage destination is a silent no-op. Verify that every "set X" step in a workflow has a corresponding field in the target schema.

- ACCEPTED (BMAD): `_clean_none_values()` duplicated identically in 3 files (storage, confirmer, modifier)
  → Rule: When a utility function is needed by multiple modules, define it once and import it. Before writing a helper, grep for existing implementations. DRY violations in serialization logic are especially dangerous because format changes must be applied consistently.

- ACCEPTED (Codex): `update_manifest_version()` always set `current_version` to the entry being updated — confirming v001 after v002 existed would regress the pointer
  → Rule: When a "current" or "latest" pointer tracks the highest value, compute it from the full dataset (`max()`), not from the last-touched entry. Any write operation that updates a pointer must consider whether the new value is actually higher than the existing one.

- ACCEPTED (Both): `_format_value()` for nested dicts produced `f"{k}: {v}"` where `v` was another dict — output contained raw Python `{'key': 'value'}` syntax in operator-facing text
  → Rule: When formatting values for human display, make the formatter recursive. Any function that formats a value for display must handle all types that value can be, including nested structures. A non-recursive formatter on recursive data always breaks at depth > 1.

- ACCEPTED (Codex): Modifier path operations (`_set_nested`, `_add_to_list`) surfaced raw `TypeError`/`IndexError` instead of controlled `ValueError` with path context
  → Rule: When user-provided paths index into data structures, wrap the traversal in a try/except that re-raises with the path in the error message. Raw Python exceptions from dict/list indexing are unintelligible to operators.

- ACCEPTED (Codex): Skill files called `python -m strategy` from repo root, but `pythonpath` was set inside `src/python/` — module resolution would fail
  → Rule: When a skill or script invokes a Python module, verify the working directory matches the `pythonpath` configuration. Test the exact shell command from the documented location before shipping.

- ACCEPTED (Both): `spec_hash` included lifecycle metadata (status, config_hash, confirmed_at, created_at) — same strategy content produced different hashes before and after confirmation, breaking the "content hash" contract
  → Rule: When a hash is documented as a "content hash," explicitly exclude all lifecycle/administrative fields from the computation. Define a `_LIFECYCLE_FIELDS` exclusion set and strip it before hashing. Test hash stability across status transitions — a content hash that changes when only metadata changes is semantically broken.

## Story 2-6-execution-cost-model-session-aware-artifact
- ACCEPTED (Both): Manifest config_hash and input_hash always null despite AC10 requiring them for reproducibility verification
  → Rule: When an AC requires reproducibility hashes, compute them at the point of artifact creation — never defer to "future work." A null hash in a manifest entry is indistinguishable from a missing implementation. Wire the hash computation into the CLI command that creates the artifact.

- ACCEPTED (Both): calibrated_at field declared `format = "iso8601_utc"` in schema TOML but validate_cost_model() never checked it — malformed timestamps passed validation
  → Rule: Every format constraint declared in a schema contract must have a corresponding runtime check in the validator. Schema declarations without enforcement create false confidence. Add a regression test for each format constraint.

- ACCEPTED (Codex): CLI show/validate used load_latest_cost_model() (raw highest file) instead of manifest's latest_approved_version pointer — violated AC9 and anti-pattern #18
  → Rule: When a manifest defines an "approved" pointer, ALL consumer code paths must resolve through it. Add a dedicated load_approved_*() function and grep for any direct load_latest_*() usage in consumer-facing code. Raw "latest file" is an internal utility, not a consumer API.

- ACCEPTED (BMAD): E2E test ran shutil.rmtree on real artifact directory during regular pytest — not marked @pytest.mark.live
  → Rule: Any test that mutates files outside tmp_path must be marked with a gate marker (@pytest.mark.live or similar). Review all subprocess-based tests that resolve project root internally — they bypass tmp_path isolation by design.

- ACCEPTED (Both): Hardcoded pip multiplier (10000) only correct for non-JPY pairs — from_tick_data silently produced 100x wrong values for JPY crosses
  → Rule: When converting between raw price differences and pips, the multiplier depends on the pair's pip definition. Always parameterize by pair, never hardcode. JPY pairs (0.01 pip) vs standard (0.0001 pip) is the most common source of this class of bug.

- ACCEPTED (Both): Session boundaries hardcoded in _LABEL_BOUNDARIES while story anti-pattern #2 says "load from config" — get_session_for_time() accepted but ignored session_defs parameter
  → Rule: When hardcoded constants duplicate values from a config file, add a startup validation that asserts they match. Unused parameters in function signatures create false confidence that config is being used. Either wire the parameter or remove it.

- ACCEPTED (Codex): SessionProfile(**profile_data) in from_dict() failed when artifact JSON contained optional schema fields (description, data_points, confidence_level)
  → Rule: When deserializing into a strict dataclass, filter the input dict to only known fields. Optional fields in the schema contract that aren't in the dataclass will cause TypeError on construction. Use `dataclasses.fields()` to build the allowlist.

- ACCEPTED (Codex): save_cost_model() only validated when schema_path explicitly passed — callers could persist invalid artifacts by omission
  → Rule: When an AC says "validated before saving," make validation mandatory by auto-discovering the schema path if not provided. Optional validation is no validation — the default must be safe.

- ACCEPTED (Pass 2): save_cost_model() auto-discovery of schema was silent on failure — when _discover_schema_path() returned None, validation was skipped with no log output
  → Rule: When a safety mechanism (auto-discovery, fallback, retry) fails to activate, always log a warning. Silent fallthrough means operators never learn that a defense-in-depth layer is inactive. "No schema found, skipping validation" is a critical operational signal.

## Story 2-4-strategy-intent-capture-dialogue-to-specification
- ACCEPTED (Both): 17 hardcoded `.get("key", fallback)` values across defaults.py and spec_generator.py silently shadowed TOML config — if a config key was missing, Python fallbacks took over without any error
  → Rule: When D7 says "defaults from config, not hardcoded," use direct dict access `["key"]` so missing keys raise KeyError immediately. `.get("key", fallback)` is a D7 violation disguised as defensive coding.

- ACCEPTED (Both): intent_capture.py had no `__main__` block, making the skill's `python -m strategy.intent_capture` invocation path completely broken
  → Rule: If a skill or CLI documents a `python -m module` invocation, the module MUST have a `__main__` block. Test the exact shell command from the skill during development — not just the Python API.

- ACCEPTED (Both): Structured log fields (event, spec_version, spec_hash) passed as top-level `extra` keys were silently dropped because JsonFormatter only serializes the `ctx` field
  → Rule: When using a custom log formatter, pass structured data through the field the formatter actually serializes. Test that logged data survives the formatter — string-matching log messages does not verify structured field serialization.

- ACCEPTED (Both): spec_hash test was a placeholder — only checked `len(hash) == 64` in memory, never saved to disk or verified roundtrip
  → Rule: When an AC says "verify X in saved artifact," the test must exercise the full save→load→verify path. In-memory assertions prove the computation works, not that the artifact contains the result.

- ACCEPTED (Codex): Indicator aliases mapped to wrong registry keys — `keltner` → `keltner_channels` (registry has `keltner_channel`), `donchian channel` → `donchian` (registry has `donchian_channel`)
  → Rule: When alias mappings resolve to registry keys, add a startup or test-time check that every alias target exists in the registry. String typos in lookup tables are invisible until a user hits the wrong alias.

- ACCEPTED (BMAD): normalize_timeframe silently accepted unknown timeframes (e.g., "3h" → "3H"), deferring the error to a confusing downstream Pydantic validation failure
  → Rule: Validate at the earliest possible boundary. When a function normalizes user input, it must reject invalid values with a clear error listing valid options — not pass garbage downstream for another layer to catch.

## Story 2-7-cost-model-rust-crate
- ACCEPTED (Both): `CostModelArtifact` lacked `#[serde(deny_unknown_fields)]` while `CostProfile` had it — unknown top-level JSON fields silently ignored
  → Rule: When applying `deny_unknown_fields` for fail-loud schema enforcement, apply it at EVERY deserialization level, not just leaf types. A fail-loud inner type inside a permissive outer type still leaks schema drift at the outer boundary.

- ACCEPTED (Both): Version validation checked `digits.len() < 3` (accepting 3+ digits) but spec said `v\d{3}` (exactly 3) — test explicitly documented the deviation as intentional
  → Rule: When the spec says "exactly N," enforce exactly N. Forward-compatibility relaxations must go through spec amendment, not silent implementation deviation. Tests that document spec violations as "intentional" are red flags — update the spec or fix the code.

- ACCEPTED (Codex): `test_get_cost_all_sessions` only asserted non-negative values, not correct session-to-profile mapping — swapped sessions would pass
  → Rule: When testing a lookup table, verify that each key maps to its specific expected value, not just that the returned value is structurally valid. Non-negative checks prove type correctness, not mapping correctness. At least one test must pin exact values per key.

- ACCEPTED (Both): `metadata` stored in artifact but no public accessor, CLI `inspect` didn't print it, test didn't verify preservation — AC6 says "printing artifact metadata"
  → Rule: If a field is stored, it must be observable. Every stored field needs: (1) a public accessor, (2) inclusion in CLI/display output if the AC mentions it, (3) a test that verifies round-trip preservation. "Stored but not interpreted" does not mean "stored but not accessible."

## Story 2-8-strategy-engine-crate-specification-parser-indicator-registry
- ACCEPTED (BMAD): `risk_percent` validated as (0.0, 100.0] but contract specifies [0.1, 10.0] — allowed 50% risk per trade in a trading system
  → Rule: When a contract defines numeric bounds (min/max), the validator must enforce exactly those bounds. Never relax contract constraints for "flexibility" — the contract exists to prevent dangerous values. For financial parameters, looser-than-contract bounds are a safety gap.

- ACCEPTED (BMAD): `max_lots` validated only as > 0 but contract specifies [0.01, 100.0] — allowed 1000-lot positions
  → Rule: Same as above — enforce exact contract bounds. Partial bound checks (only lower, not upper) are incomplete validation that creates false confidence.

- ACCEPTED (Both): Volatility filter `min_value` and `max_value` not cross-validated — a filter with min=100, max=10 was silently accepted
  → Rule: When a struct has paired min/max fields, always validate min < max when both are present. This is a universal invariant — add it as a checklist item for any validator that handles range pairs.

- ACCEPTED (Codex): `metadata.version` and `cost_model_reference.version` not validated against contract pattern `v\d{3}` — any non-empty string accepted
  → Rule: When a contract specifies a `pattern` constraint, the validator must enforce it. "Non-empty" is not the same as "matches pattern." Pattern constraints are especially important for version strings that downstream consumers will parse.

- ACCEPTED (Codex): `metadata.pair` not validated against contract's allowed values `["EURUSD"]` — any non-empty pair string accepted
  → Rule: When a contract specifies `values = [...]`, the validator must check membership. V1 constraints exist for a reason — allowing unconstrained values defeats the purpose of having a contract.

- ACCEPTED (Codex): `optimization_plan.parameter_groups.parameters` deserialized but never cross-checked against `ranges` keys — parameters without ranges or ranges without parameters silently accepted
  → Rule: When two fields in a struct are semantically linked (parameters list ↔ ranges map), add bidirectional cross-validation. Deserialized-but-unchecked fields create a false sense of validation coverage.

- ACCEPTED (Both): Parity test task marked [x] in story spec but `parity_test.rs` file does not exist — completion notes acknowledged deferral but checkbox was not updated
  → Rule: When deferring a task, immediately uncheck it in the story spec. A checked box is a claim of completion — false claims erode trust in the completion audit and block accurate status reporting.

- ACCEPTED (Codex): `test_validate_cost_model_reference_valid` passed None for cost_model_path, so it never exercised a successful artifact load — misleading test name
  → Rule: Test names must accurately describe what they test. A test named "valid" that skips the validation path it claims to exercise is worse than no test — it creates false confidence. Name tests by what they actually verify, not what they aspire to.

## Story 2-9-e2e-pipeline-proof-strategy-definition-cost-model
- ACCEPTED (Both): Structured log test only checked message substrings ("intent", "modif"), never verified D6 required fields (stage, strategy_id, timestamp, correlation_id) — any log output would pass
  → Rule: When an AC specifies required structured fields in log output, the test must extract and verify those fields from log records. Substring matching on messages proves log statements exist, not that structured data is emitted. Use log record attributes or parsed JSON, not message grep.

- ACCEPTED (BMAD): Version mismatch error-path test asserted matching versions then checked != "v999" — a tautology that never constructed an actual mismatch
  → Rule: Error-path tests must construct the error condition, not just assert the happy path holds. If testing "mismatch is caught," mutate the input to create a real mismatch and verify it's detected. A test that only confirms correct data is correct is a no-op.

- ACCEPTED (Both): Golden-file fixture `expected_ma_crossover_spec.toml` created but never loaded or compared against in any test — no regression baseline existed
  → Rule: If you create a reference fixture, write a test that loads and compares against it. Unused fixtures are dead code — they create false confidence that a regression check exists. If the fixture isn't needed, delete it.

- ACCEPTED (Both): Reference fixture `reference_ma_crossover_v001.toml` contained confirmed v002 spec — filename and embedded version disagreed
  → Rule: When saving reference artifacts, the filename must reflect the content's identity (version, status). A v001 filename with v002 content is a trap for anyone reading the fixtures directory. Use semantic names (e.g., `_confirmed.toml`) when the content represents a post-mutation state.

- ACCEPTED (Both): spec_generator.py doesn't produce optimization_plan or cost_model_reference — E2E test enriched them post-generation with no xfail marker or tracking
  → Rule: When an E2E proof works around a production code gap, mark the workaround with xfail or a tracked TODO. Undocumented workarounds become permanent — they survive code reviews because nobody knows they were supposed to be temporary.

- ACCEPTED (Codex): Determinism test only compared capture-stage spec_hash — never checked enriched spec hash, manifest hash, or fixture hashes despite AC requiring "identical spec hash, manifest hash, and fixture hashes"
  → Rule: When an AC lists specific hashes to verify, the test must check each one explicitly. Partial determinism checks give partial confidence. If some hashes can't be deterministic (e.g., timestamps), document why and check the ones that can be.

- ACCEPTED (BMAD): cost_model crate used HashMap<String, CostProfile> for sessions despite project convention (Story 2.8) requiring BTreeMap for deterministic iteration
  → Rule: When a project establishes a convention (BTreeMap over HashMap for determinism), enforce it at review time for every new crate. Conventions that aren't checked at boundaries drift immediately. Consider a workspace-level clippy lint or grep check.

## Story 3-1-claudebacktester-backtest-engine-review
- ACCEPTED (Codex): Research artifact misstated that max_spread_pips is enforced "not in Rust; in Python engine" — but lib.rs:319-324 clearly applies the filter inside batch_evaluate()
  → Rule: When documenting where a filter/check is enforced, verify against the actual source at every call site. Research artifacts guide porting decisions — a misstatement about enforcement location can cause the filter to be dropped during migration.

- ACCEPTED (Codex): AC6 required documenting "what state is persisted vs recomputed" but the checkpoint section only described the mechanism without explicitly categorizing each data item
  → Rule: When an AC requires a specific analysis dimension (persisted vs recomputed, hot vs cold, mutable vs immutable), produce an explicit table or list with that dimension as a column. Implicit coverage buried in prose doesn't satisfy structured AC requirements.

- ACCEPTED (Codex): Downstream handoff sections for Stories 3-6 through 3-9 were missing required subsections (V1 port decisions, deferred items, open questions) that Stories 3-2 through 3-5 had
  → Rule: When an AC defines a template (required subsections per downstream story), apply it uniformly to every instance. Later sections tend to get abbreviated as the author fatigues — review should check the last items as carefully as the first.

- ACCEPTED (Both): Research tests used keyword-presence checks that couldn't detect structural gaps or factual errors — this is why the AC6/AC11/max_spread_pips issues went undetected
  → Rule: For research artifact tests, go beyond keyword presence. Test structural completeness (required subsections exist per-section) and cross-reference claims against source where feasible. Keyword tests catch missing topics but not wrong claims or incomplete coverage.

## Story 3-2-python-rust-ipc-deterministic-backtesting-research
- ACCEPTED (Codex): Downstream contract defined bar-level equity curves in CLI output table, but Open Questions section recommended per-trade for V1. Contradictory guidance for Stories 3.5/3.6.
  → Rule: When a downstream contract is defined in one section and discussed as an open question in another, resolve the open question and update the contract before marking the story complete. Contracts must be internally consistent — downstream consumers should never need to reconcile contradictions.

- ACCEPTED (Codex): Executive summary claimed "~2.4GB active" memory but the detailed budget table totaled ~1,065MB heap / ~1,465MB including mmap. Numerical inconsistency between summary and detail.
  → Rule: When an executive summary quotes a number from a detailed section, verify the number matches. Summaries are often written first (as estimates) and not updated after detailed analysis. Add a regression test asserting summary figures are consistent with detail tables.

- ACCEPTED (Codex): Checkpoint recommended strategy said single-backtest state was "not persisted," reading as if single backtests had no crash-resume strategy. The granularity table covered it but the summary didn't connect the dots.
  → Rule: When a recommendation summary follows a detailed options table, the summary must address every use case in the table — not just the primary one. Readers use the summary as the authoritative guidance; if a use case is only in the table, it's effectively undocumented.

- ACCEPTED (BMAD): Appendix cross-reference tables omitted requirements and decisions that were out of scope, instead of marking them N/A. Silent omission looks like an oversight rather than a deliberate scoping decision.
  → Rule: Cross-reference tables must include every item in the specified range, even if marked "N/A — addressed by Story X." Explicit N/A entries distinguish intentional scoping from accidental omission and help reviewers verify completeness at a glance.

## Story 3-3-pipeline-state-machine-checkpoint-infrastructure
- ACCEPTED (Both): `check_preconditions()` only checked artifact file existence but never validated manifest hash via executor — AC #2 explicitly requires "artifact exists and is valid per manifest hash"
  → Rule: When an AC says "valid per manifest hash," existence checks are insufficient. Wire the executor's `validate_artifact()` call into the precondition checker. Existence and integrity are separate properties — always verify both when the spec demands it.

- ACCEPTED (Codex): `resume()` looked up executor for `current_stage` instead of the last completed stage that produced the artifact — at `review-pending`, no executor exists so validation was silently skipped
  → Rule: When verifying an artifact on resume, look up the executor for the stage that *produced* the artifact (last completed stage), not the stage about to run. The producer knows how to validate its own output. A missing executor for the current stage should not silently skip verification of a prior stage's artifact.

- ACCEPTED (Both): `progress_pct` computed from `len(completed_stages)` which is append-only — after refine cycles that re-run stages, duplicate entries cause progress to exceed 100%
  → Rule: When computing progress from a history list that can have duplicate entries (due to retries or re-runs), use the count of *unique* identifiers, not the raw list length. Append-only audit logs and deduplicated progress counters serve different purposes — never conflate them.

- ACCEPTED (Codex + BMAD): Retry loop log message used `attempt/retry_max_attempts` as denominator but total attempts is `max_attempts + 1` — produced misleading `4/3` on the last attempt; final failed attempt also slept the longest backoff before returning failure
  → Rule: When logging retry progress, ensure the denominator reflects total attempts (initial + retries), not just the retry count. Also, skip backoff sleep on the final attempt — sleeping before returning failure wastes the longest delay for no benefit.

- ACCEPTED (BMAD): `GateDecision.stage` field had no validation against `PipelineStage` values — invalid strings like `"foo-bar"` were silently accepted and persisted
  → Rule: When a string field semantically represents an enum value, validate it against the enum's value set in `__post_init__`. Unvalidated string-typed enum fields are a persistence time bomb — invalid values propagate to disk and corrupt state files.

- ACCEPTED (BMAD): Gate status string computed via `decision + "ed"` with special case for "refine" — fragile concatenation that would break for future decision types
  → Rule: When mapping enum-like strings to display forms, use an explicit mapping dict, not string manipulation. Concatenation rules that work for current values silently break for new values added later.

## Story 3-4-python-rust-bridge-batch-evaluation-dispatch
- ACCEPTED (Both): Contract SSOT `contracts/arrow_schemas.toml` only defined `[backtest_trades]` — Rust code invented `equity_curve` and `metrics` schemas with no contract backing
  → Rule: When a contract file is the SSOT for cross-runtime schemas, every schema referenced in code must exist in the contract. Code that defines schemas not in the contract undermines the SSOT guarantee. Add a build-time or test-time check that Rust/Python schema definitions have a corresponding contract entry.

- ACCEPTED (BMAD): Checkpoint file written as `checkpoint.json` but contract specifies `checkpoint-{stage}.json` — Python orchestrator resume would look for the wrong filename
  → Rule: When a contract defines a filename pattern with template variables, code must substitute the variables and use the resulting name exactly. Never simplify a templated filename — the pattern exists so multiple stages can coexist. Add a regression test that verifies the actual filename against the contract pattern.

- ACCEPTED (Both): `output.rs` comment claimed "This allows Python `pyarrow.ipc.open_file()` to open the file" but the stubs were JSON, not Arrow IPC — pyarrow cannot read them
  → Rule: Comments that describe what a consumer can do with the output must be accurate for the current implementation, not aspirational. A false "pyarrow can read this" comment causes downstream developers to write code that immediately fails. If the output is a stub, the comment must say so explicitly.

- ACCEPTED (BMAD): `backtest_executor.py` used deprecated `asyncio.get_event_loop()` which raises DeprecationWarning in Python 3.10+ and will break in 3.12+
  → Rule: Use `asyncio.get_running_loop()` (Python 3.7+) to detect an existing loop, and `asyncio.run()` to create a new one. Never use `asyncio.get_event_loop()` — it has been deprecated since 3.10 and its implicit loop creation behavior is removed in 3.12.

- ACCEPTED (BMAD): Python memory pre-check returned raw available memory but Rust subtracted a 2GB OS reserve — Python could approve a job that Rust immediately rejects
  → Rule: When two runtimes (Python and Rust) independently validate the same resource constraint, they must use identical thresholds. Define the reserve constant in a shared location (contract or config) and reference it from both sides. Inconsistent validation causes confusing "passed preflight but failed at runtime" errors.

- ACCEPTED (BMAD): `verify_output()` docstring claimed it "also verifies per-fold score files via `verify_fold_scores()`" but the function body never called it
  → Rule: When a function's docstring claims it calls another function, verify the claim in the function body. Aspirational docstrings that describe planned-but-unimplemented behavior are worse than no docs — they cause callers to skip verification they think is already happening.

- ACCEPTED (Codex): Subprocess process handle stored by `config_hash` key — two concurrent jobs with identical config_hash silently overwrote the first handle, making cancellation target ambiguous
  → Rule: When tracking concurrent resources (processes, connections, locks) in a dict, use a guaranteed-unique key (UUID or composite key), not a business-domain identifier that could collide. Even if collisions seem unlikely, concurrent dispatch of identical configs is a valid use case (retries, A/B comparison).

## Story 3-5-rust-backtester-crate-trade-simulation-engine
- ACCEPTED (Both): Trade log Arrow output wrote only 12 simplified columns, combining per-leg spread/slippage and dropping raw prices, exit_session, signal_id, holding_duration, exit_reason — all present in the TradeRecord struct but discarded at the output layer
  → Rule: When internal data structures contain richer data than the output serializer writes, treat missing output fields as bugs. Add a compile-time or test-time assertion that the output schema field count matches the struct field count. "Compute then discard" is the most common output-layer defect pattern.

- ACCEPTED (Both): Equity curve computed and stored unrealized_pnl but never wrote it to Arrow output; drawdown column named `drawdown_pips` but contained a percentage value
  → Rule: Every field stored in a result struct must appear in the output schema. Semantic naming errors (pips vs pct) silently mislead downstream consumers. Add a regression test that verifies column names match their units — or include units in the column name.

- ACCEPTED (Both): Metrics struct computed 17 fields (r_squared, max_drawdown_pct, avg_trade_duration, etc.) but output writer serialized only 9 — 8+ fields computed then discarded
  → Rule: When a metrics struct adds a field, the output serializer must also add it. Make the serializer derive from the struct fields rather than maintaining a separate hardcoded list. If the struct and the serializer are defined in different files, add a test that asserts their field counts match.

- ACCEPTED (Codex): Missing pre-computed signal columns silently replaced with bar.close, generating trades from wrong data instead of failing fast
  → Rule: When a D14 contract says data arrives via pre-computed columns, a missing column is a data integrity error, not a fallback case. Only price columns (open/high/low/close) should use direct bar data. All other missing columns must warn and skip, not silently substitute.

- ACCEPTED (Codex): Max drawdown duration measured peak-to-trough instead of peak-to-recovery, and the unit test locked in the wrong behavior
  → Rule: When the spec defines a metric with precise semantics (peak-to-recovery), verify the implementation matches, not just that a test passes. Tests that assert incorrect values with explanatory comments ("but max dd_bars tracks...") are a red flag — the comment explains why the wrong answer is produced instead of questioning whether it's the right answer.

- ACCEPTED (Both): `--param-batch` CLI arg accepted, validated for existence, but never parsed or used — batch evaluation completely unimplemented despite task marked [x]
  → Rule: When a CLI arg is declared and validated, also verify it's consumed. An accepted-but-ignored argument is worse than a missing one — it creates false confidence that the feature works. Add an integration test that exercises the feature end-to-end, not just arg parsing.

- ACCEPTED (Both): Signal evaluation re-implemented in backtester instead of calling strategy_engine::Evaluator — broke the shared-logic guarantee of AC #4
  → Rule: When an AC specifies shared logic across two consumers, the first consumer to implement must create the shared abstraction. Implementing locally "for now" creates duplication that is never cleaned up. If the shared crate isn't ready, block the story rather than duplicate.

- ACCEPTED (BMAD): DayOfWeek and Volatility filters silently accepted and ignored with no warning — users expecting filtering got incorrect results
  → Rule: When a filter type is parsed but not implemented, log a warning at the point of use. Silent pass-through of unimplemented filters is indistinguishable from "filter applied successfully" to the operator. Make unimplemented features noisy, not quiet.

## Story 3-5 Synthesis Round 2 (apply_cost, crossover, schema sync, EOD equity)
- ACCEPTED (Both): trade_simulator.rs manually computed `spread + slippage * PIP_VALUE` instead of calling `cost_model.apply_cost()`, duplicating logic that would drift if cost model changes
  → Rule: When an upstream crate provides a canonical method for a computation (e.g., apply_cost), always call it even if you could reimplement it locally. Keep get_cost() only for component breakdown (trade record attribution), never for the price adjustment itself.

- ACCEPTED (Both): `crosses_above` implemented as `value > threshold` — fires every bar above threshold instead of detecting the actual crossing event
  → Rule: Crossover detection requires tracking the previous bar's value. `crosses_above` means `prev <= threshold AND current > threshold`. Always maintain previous-bar state for crossover comparators. Simplified implementations produce orders of magnitude more false signals.

- ACCEPTED (BMAD): common/arrow_schemas.rs had 12/4/11 columns while output.rs and contracts had 20/5/19 — stale schema definitions from a prior story that would cause validate_column_names() to reject valid output
  → Rule: When updating output schemas in one file, grep for the schema definition in ALL files across the workspace. Stale copies in shared crates are especially dangerous because they look authoritative. Add a test that asserts schema column counts match between the shared definition and the output writer.

- ACCEPTED (Both): DayOfWeek/Volatility filter warnings printed on every bar with no first-encounter gate — 5.26M identical warning lines for a 10-year dataset
  → Rule: When logging warnings for unsupported features in a hot loop, always gate with a boolean flag. Log once, then suppress. Per-bar warnings are a performance and usability catastrophe.

- ACCEPTED (Codex): End-of-data position close happened after the main loop but no equity point was recorded afterward — last equity point showed unrealized P&L instead of final realized state
  → Rule: When force-closing positions at end-of-data, record a final equity point AFTER the close. The equity curve must reflect the final state of all positions. Any post-loop state mutation that affects output must be followed by output recording.

- ACCEPTED (Codex): CLI binary parsed spec with parse_spec_from_file() but never called validate_spec() — invalid specs could reach the evaluation engine
  → Rule: Always validate after parsing. Parsing only checks syntax; validation checks semantics (indicator registry, parameter ranges, cross-field constraints). A parseable-but-invalid spec produces subtle wrong results instead of a clear error.

- ACCEPTED (BMAD): Breakeven trades (pnl == 0.0) counted as losses via `p <= 0.0` filter — inflated loss count and reduced profit factor
  → Rule: Use strict inequality `p < 0.0` for losses and `p > 0.0` for wins. Breakeven trades are a distinct category. This matters for profit factor computation where zero-PnL trades in the denominator artificially reduce the ratio.

## Story 3-5 Synthesis Round 3 (embargo bar exit checks)
- ACCEPTED (BMAD): Fold embargo bars skipped exit checks entirely — open positions had no SL/TP protection during embargo periods at fold boundaries
  → Rule: Any bar-skipping mechanism (quarantine, embargo, data gaps) must still allow exit checks for open positions. "Skip new entries" and "skip everything" are fundamentally different — the former protects positions, the latter abandons them. When adding a new skip path, copy the exit-check pattern from the existing quarantine path.

## Story 3-6-backtest-results-artifact-storage-sqlite-ingest
- ACCEPTED (BMAD): AC #11 said "across formats" but consistency validation only checked Arrow↔Parquet trade_id ordering and entry_time — SQLite was only count-verified, never cross-checked for ordering or timestamps
  → Rule: When an AC says "across formats," it means ALL formats, not just the two most convenient ones. For each cross-format check (counts, ordering, boundary values), build a matrix of all format pairs and verify none are missing.

- ACCEPTED (BMAD): Error handler used `checkpoint if 'checkpoint' in dir() else {}` — `dir()` is unreliable for checking local variable assignment, and the variable was unbound if the exception fired before its assignment
  → Rule: Always initialize variables used in except/finally blocks BEFORE the try block. Never use `dir()` or `locals()` to check variable existence — it's fragile and unclear. A simple `checkpoint = {}` before `try:` eliminates the entire class of bugs.

- ACCEPTED (BMAD): `_validate_schemas` opened a SQLiteManager connection just to instantiate ResultIngester for `validate_schema()`, but that method never touches SQLite — pure Arrow + TOML file reading
  → Rule: When a method only reads files and does no I/O with its parent's resource (DB connection, network socket), make it a @staticmethod or standalone function. Unnecessary resource acquisition wastes connections, risks contention, and obscures the method's actual dependencies.

- ACCEPTED (BMAD): Schema validation checked column names (presence) but not column types — an Arrow file with `entry_time` as Utf8 instead of Int64 would pass validation, then cause silent data corruption during timestamp conversion
  → Rule: Schema validation must check BOTH column presence AND column types. Name-only checks catch missing columns but miss type drift. Type mismatches cause silent data corruption that's much harder to diagnose than a missing column error.

- ACCEPTED (BMAD): Docstring said "direction utf8 → TEXT (already lowercase per contract)" but code correctly called `.lower()` because Rust outputs "Long"/"Short" — the comment contradicted the code
  → Rule: When code transforms a value (e.g., `.lower()`), the comment must describe the transformation, not claim it's unnecessary. Misleading comments cause future maintainers to remove "redundant" transformations, reintroducing the bug the code was fixing.

## Story 3-7-ai-analysis-layer-narrative-anomaly-detection-evidence-packs
- ACCEPTED (BMAD): `_downsample_equity_curve` loaded ALL equity curve rows into a Python list before downsampling — violating anti-pattern #2 (no unbounded memory) with ~125 MB Arrow IPC files
  → Rule: When processing large Arrow IPC files, use a two-pass streaming approach: count total rows first, then extract only the needed rows at stride indices. Never materialize the full dataset into Python objects. Convert Arrow columns to Python lists per-batch (`.to_pylist()`) not per-row (`.as_py()`).

- ACCEPTED (BMAD): `_find_version_dir` had two unsafe fallbacks after failing manifest match — returning any version with `trade-log.arrow` or falling back to latest version — silently assembling evidence packs from wrong version's artifacts
  → Rule: When resolving versioned artifact directories, only fall back to a default if exactly one version exists. With multiple versions, a missing manifest match is an error, not a fallback case. Silent wrong-version selection corrupts provenance chains.

- ACCEPTED (BMAD): `assemble_evidence_pack` opened a third SQLite connection and recomputed `compute_metrics()` independently despite `generate_narrative()` having already computed identical metrics via the same shared function
  → Rule: When multiple analysis steps compute the same metrics via a shared function, reuse the result from the first caller rather than recomputing. Redundant connections and duplicate computation waste resources and create subtle divergence risk if the shared function is ever made non-deterministic.

- ACCEPTED (BMAD): `anomaly_detector._load_run_metadata` returned empty dict `{}` on missing backtest run while `narrative._load_run_metadata` raised `AnalysisError` — inconsistent error handling for the same condition across sibling modules
  → Rule: Sibling modules that handle the same error condition must handle it consistently. When one module raises and another silently returns empty data, a typo in a shared parameter (backtest_id) produces a clear error in one path and silent garbage in the other. Pick one error strategy and apply it uniformly.

- ACCEPTED (BMAD): `__init__.py` docstring listed `generate_narrative`, `detect_anomalies`, `assemble_evidence_pack` as public interfaces but `__all__` only exported data models — inconsistent API surface
  → Rule: If a module docstring declares public interfaces, `__all__` must export them. Consumers reading the docstring will try `from module import function` and get confusing ImportErrors when the function exists but isn't re-exported.

## Story 3-8-operator-pipeline-skills-dialogue-control-stage-management
- ACCEPTED (BMAD): Refine returns to BACKTEST_RUNNING instead of STRATEGY_READY — gate_manager.py hardcoded the wrong re-entry stage, violating AC #6 which explicitly requires STRATEGY_READY
  → Rule: When a story AC specifies a target stage for a state transition, the implementation must match exactly. Cross-story modules (gate_manager from Story 3-3) must be updated when a later story's AC overrides their behavior. Always trace AC stage references back to the code that implements the transition.
- ACCEPTED (BMAD): Dead import — assemble_evidence_pack imported but never called because StageRunner handles evidence pack assembly automatically
  → Rule: When delegating to an orchestrator that already triggers downstream work (e.g., StageRunner auto-generates evidence packs), do not also import the downstream function. Dead imports create false expectations about the call chain.
- ACCEPTED (BMAD): Skill Operation 11 (Review Results) calls load_evidence_pack without state-driven evidence_pack_ref, falling back to filesystem scan instead of using pipeline state
  → Rule: When dev notes specify "state-driven lookup", skill snippets must extract references from pipeline state before calling the backing function. Filesystem fallbacks are for recovery only, not the happy path.
- ACCEPTED (BMAD): Logging test fallback path only checks for "Operator action" string without validating D6 schema fields (run_id, config_hash)
  → Rule: When testing structured log schemas, assert ALL required fields are present and non-empty. A weak fallback that checks only the message string creates false confidence that the schema contract is enforced.
- ACCEPTED (BMAD): Empty run_id in run_backtest error path breaks lineage tracking — when StageRunner raises before producing state, run_id was set to ""
  → Rule: Generate lineage identifiers (run_id, trace_id) before the try block, not after. Error paths need the same lineage tracking as success paths — empty IDs break log correlation and audit trails.

## Story 5-4-validation-gauntlet
- ACCEPTED (Both): CPCV evaluates non-contiguous test groups as a single span from first to last, contaminating OOS with intervening train data
  → Rule: When cross-validation produces non-contiguous test folds, evaluate each segment independently and aggregate. Never span from min to max index — intervening groups may be training data.
- ACCEPTED (Both): IS returns populated with OOS data (`is_returns.append(oos_sharpe)`) — data leak making PBO meaningless
  → Rule: When a function accepts both IS and OOS inputs, verify they come from independent evaluations. A placeholder that copies one to the other is a silent data leak that makes the entire test statistically invalid.
- ACCEPTED (Both): DSR gating computed but never wired back to candidate failures — dead code gate
  → Rule: When implementing a hard gate (pass/fail decision), trace the result all the way to the decision point. A computed-but-unused gate metric is worse than no gate — it creates false confidence that the check is enforced.
- ACCEPTED (BMAD): DSR skew/kurtosis correction applied to expected max Sharpe instead of the SE of the Sharpe ratio estimator
  → Rule: When implementing statistical corrections from papers, map each formula term to the correct variable in code. The non-normality correction adjusts the standard error (denominator), not the benchmark (numerator) or the observed statistic.
- ACCEPTED (Codex): Permutation test shuffles return order and computes mean/std — order-invariant, producing degenerate p-values
  → Rule: When implementing permutation/randomization tests, verify the null distribution actually varies. If the test statistic is invariant to the permutation operation (e.g., mean/std is order-invariant), the test is mathematically degenerate. Sign-flip tests H0: mean=0 correctly.
- ACCEPTED (BMAD): Permutation p-value uses count/N instead of (count+1)/(N+1), allowing impossible p=0
  → Rule: Always use the corrected permutation p-value formula (count+1)/(N+1). This prevents impossible p=0 and is standard practice (Phipson & Smyth 2010).
- ACCEPTED (Both): Checkpoint saves only current candidate's progress; resume() never called from run()
  → Rule: Checkpoint/resume must be tested end-to-end: verify the checkpoint contains ALL accumulated state, and verify the entry point actually checks for and loads existing checkpoints on startup.
- ACCEPTED (Both): Gauntlet fabricates synthetic dummy data when required inputs (trade_results, market_data) are None
  → Rule: Validation stages must fail loudly on missing inputs, not silently fabricate data. Synthetic fallbacks mask upstream pipeline failures and produce meaningless validation results that appear legitimate.
- ACCEPTED (Both): base.toml gated_stages missing validation-complete, overriding code default
  → Rule: When code defines a default list and config overrides it entirely (not merges), the config must include ALL required entries. A config that replaces the default with a subset silently disables entries the code expected.
- ACCEPTED (BMAD): Config from_dict() accepts nonsensical values (0 windows, train_ratio > 1.0, k >= n_groups)
  → Rule: Configuration deserialization must validate value ranges, not just types. Nonsensical configs (zero windows, ratio > 1.0) produce garbage results or runtime errors that are hard to trace back to configuration.
- ACCEPTED (Codex): Suspicious performance flagging only captures Sharpe divergence, not profit factor divergence per AC9
  → Rule: When acceptance criteria specify multiple metrics for a feature (e.g., "Sharpe AND profit factor divergence"), implement all of them. Partial implementation of multi-metric requirements creates blind spots in the exact areas the requirement was designed to cover.

### Pass 2 (second review cycle)
- ACCEPTED (Both): `compute_pbo()` accepts IS returns parameter but never uses it — computes OOS-median fraction instead of IS-vs-OOS ranking
  → Rule: If a function signature accepts a parameter, it must use it meaningfully. An unused parameter that was designed for correctness (IS returns for PBO) is a silent correctness bug. Either use it or remove it from the signature.
- ACCEPTED (Both): Gauntlet manifest stubs out downstream contract fields (`config_hash=""`, `chart_data_refs={}`, `candidate_rank` missing)
  → Rule: When a story spec defines a Downstream Contract table, every field in that table is a deliverable — not a placeholder for the next story. Empty stubs create integration failures that surface late. Populate or raise NotImplementedError.
- ACCEPTED (Both): ValidationExecutor missing `stage` class attribute for pipeline discovery
  → Rule: When implementing a protocol/interface, include ALL required attributes — not just methods. Class-level attributes like `stage = PipelineStage.X` are part of the protocol contract and are needed for registration/discovery.
- ACCEPTED (BMAD): `validate_artifact()` checks 6 of 10 required manifest fields, missing fields that are now populated
  → Rule: When adding new fields to an output artifact, also update the corresponding validation/verification function. Output and validation must evolve together.
- ACCEPTED (BMAD): `regime_analysis._get_pnl()` returns zeros instead of checking alternative column names
  → Rule: When multiple valid column names exist for the same semantic field (pnl_pips, pnl), check all known aliases before falling back to zeros. Silent zero-fill produces plausible-looking but meaningless results.
- ACCEPTED (Codex): UUID-based run_id prevents deterministic reproducibility of serialized outputs
  → Rule: When a spec requires deterministic outputs (AC13), ALL output fields must be deterministic — including metadata like run_id. Derive IDs from deterministic inputs (seed + config hash), not from random sources.
- ACCEPTED (Codex): Walk-forward artifact omits train/test boundaries needed for AC12 visualization
  → Rule: When an AC requires "temporal split timestamps available for visualization," those timestamps must be persisted in the artifact — not just used transiently during computation. If the data exists in memory during processing, persist it.

## Story 5-2b-optimization-search-space-schema-range-proposal
- ACCEPTED (Codex): Engine clamping logic has redundant `min(proposed_max, tf_max)` that defeats the "at least 2x current" guarantee, producing slow_period.max=100 instead of story-required 200
  → Rule: When sequential min/max clamps are applied to the same variable, verify each clamp doesn't defeat the guarantee of a previous line. A common pattern: `x = max(x, floor)` followed by `x = min(x, ceiling)` where ceiling < floor silently undoes the floor.
- ACCEPTED (Codex): Constraint functions rebuild SearchParameter without preserving the `condition` field, silently dropping conditional activation metadata
  → Rule: When reconstructing immutable/frozen data objects to change one field, always pass through ALL other fields — especially optional ones that may be None in test fixtures but present in production data. Use keyword unpacking or copy-with-update patterns to prevent silent field drops.
- ACCEPTED (Both): `_determine_source_layer()` marks dimensionless multiplier params as L3 (ATR-scaled) due to prefix matching on `sl_`/`tp_`/`trailing_`, but those params have hardcoded constant ranges
  → Rule: Provenance/attribution logic must reflect how values were actually computed, not just naming patterns. A parameter named `sl_atr_multiplier` is not ATR-scaled — it multiplies ATR. The distinction matters for audit trails and reproducibility claims.
- ACCEPTED (Codex): `daily_range_median` field computes per-bar high-low range, not daily aggregated range — misleading for non-daily timeframes
  → Rule: Field names in data structures must accurately describe the computation, especially when the structure crosses abstraction boundaries. "daily" means daily aggregation; "bar" means per-bar. Misleading names in reproducibility artifacts undermine trust in the whole provenance chain.
- ACCEPTED (Both): Pipeline skill not updated with required optimization commands (AC #9 entirely missing)
  → Rule: When a story's AC explicitly requires skill/CLI/interface updates, check the interface artifact as a first-class deliverable — not an afterthought. Interface gaps are easy to miss in code-focused reviews but are high-impact for operator workflow.

## Story 5-3-python-optimization-orchestrator
- ACCEPTED (Both): DEInstance._converged never set to True, permanently blocking portfolio convergence detection
  → Rule: When an ABC/protocol defines a `converged()` method, every concrete subclass must have a reachable code path that returns True. Unreachable convergence in one instance type blocks aggregate convergence checks. Test with a portfolio containing all instance types.
- ACCEPTED (BMAD): CMAESInstance pending buffers (_pending_candidates, _pending_scores) not serialized in state_dict/load_state, silently dropped on checkpoint resume
  → Rule: If a class introduces internal buffers as part of a batching/buffering pattern, those buffers are state and MUST be included in checkpoint serialization. Any mutable field that accumulates between external API calls is checkpointable state.
- ACCEPTED (Codex): _read_fold_scores() returned zeros when no score file existed, silently corrupting CV objectives with fabricated data
  → Rule: Missing output from an external process (evaluator, subprocess) must be treated as failure (-inf or exception), never silently filled with a neutral value. Zeros are a valid score; -inf is an unambiguous sentinel for "no data."
- ACCEPTED (Codex): On resume, best_candidates and best_score were reset to defaults instead of restored from checkpoint, discarding prior progress
  → Rule: Every field that tracks cumulative progress across generations must be both saved in the checkpoint AND restored on resume. Audit checkpoint save/load symmetry: for each field in the save path, verify a matching restore in the load path.
- ACCEPTED (Both): Per-candidate instance_type attribution used cyclic repeat of instance type list instead of actual allocation tracking
  → Rule: When provenance metadata (who produced what) is recorded, derive it from the actual allocation data structure, not from a rough approximation. Mislabeled provenance in results artifacts corrupts downstream analysis.
- ACCEPTED (Codex): Strategy spec fallback wrote JSON content to a .toml filename, breaking format contract with Rust consumer
  → Rule: File extensions must match content format. If writing JSON, use .json. Never rely on consumers ignoring the extension — some will parse based on it.
- ACCEPTED (BMAD): generation_count computed via `'gen' in dir()` — fragile Python introspection for scope checking
  → Rule: Never use `dir()` or `locals()` to check if a loop variable was assigned. Initialize a tracking variable before the loop with a sensible default (e.g., `generations_completed = start_gen`).
- ACCEPTED (BMAD): Executor config loading failure silently fell back to empty config with no logging
  → Rule: Silent fallback to defaults on config load failure makes misconfiguration invisible. At minimum, log a warning with the exception. For critical config, consider failing fast.

## Story 5-5-confidence-scoring-evidence-packs
- ACCEPTED (Codex): IS-OOS coherence compared OOS-vs-OOS (two different OOS sources) instead of IS-vs-OOS
  → Rule: When implementing cross-validation coherence checks, verify you're actually comparing in-sample to out-of-sample, not two different OOS estimates. Field naming like `mean_oos_sharpe` can mislead — trace back to what the metric actually represents.
- ACCEPTED (Codex): Layer B anomaly surfacing counted raw flags instead of distinct detector types — single detector with 2 flags falsely triggered "multiple detectors agree"
  → Rule: When a threshold is defined as "N independent sources agree", count distinct source types, not total signals. A single detector emitting multiple flags is corroboration, not independent agreement.
- ACCEPTED (Both): Triage summary omitted 3 of 6 specified headline metrics, substituting unspecified fields
  → Rule: When a spec enumerates exact field names for an operator-facing summary, implement those exact fields. Don't substitute internal metrics for spec-mandated ones — the operator contract is the spec, not what's convenient.
- ACCEPTED (Codex): Narrative overview always cited walk_forward metric ID regardless of which component was strongest/weakest
  → Rule: When a narrative references a dynamic element (strongest/weakest component), the citation must follow the dynamic selection, not be hardcoded to a default stage.
- ACCEPTED (Codex): PBO margin normalization used hardcoded 0.40 instead of config threshold, causing scorer/config desync
  → Rule: Never hardcode values that exist in configuration. If a threshold is configurable for gates, the scoring normalization using that threshold must also read from config.
- ACCEPTED (Both): Operator review overwrote file instead of appending, violating append-only audit trail requirement
  → Rule: When the spec says "append-only artifact", the implementation must read-then-append, not overwrite. This is an audit/compliance pattern — overwriting destroys the decision history.
- ACCEPTED (Codex): Short-circuit interpretation messages said "short-circuit" without naming the specific failing gate
  → Rule: When documenting why a stage was skipped, include the specific cause (gate name, error code) — not just "something failed". Operators need to know which gate to investigate.
- ACCEPTED (BMAD): SCORING_COMPLETE had no outbound transition in STAGE_GRAPH despite spec requiring a gated transition
  → Rule: Every pipeline stage that requires operator action before advancing must have an explicit GATED transition in the state graph, even if the next stage doesn't exist yet. A comment is not a transition.
- ACCEPTED (Codex): ComponentScore.gate_result field existed in model but was never populated by scorer
  → Rule: If a data model has a field, some code path must populate it. An always-None optional field is dead code that misleads consumers into thinking the data is unavailable when it's actually just unwired.

### Pass 2 (second review cycle)
- ACCEPTED (Codex): Short-circuited gates described as "FAILED" in gate evaluator, despite never being evaluated — misleading decision trace
  → Rule: When a gate is not evaluated because a prior gate caused short-circuit, describe it as "SKIPPED", not "FAILED". The distinction matters for decision traces: "FAILED" implies the gate was evaluated and the candidate didn't pass, while "SKIPPED" correctly communicates the gate was never reached. Both result in the same outcome (RED), but the audit trail must be accurate.
- ACCEPTED (Codex): Risk assessment header line in narrative had no [metric:] citation while all other narrative lines did
  → Rule: When a narrative contract requires "every claim cites a metric or chart ID", audit ALL generated strings including headers, summaries, and fallback messages. It's easy to add citations to the main content and forget the framing lines.
- ACCEPTED (Codex): PBO threshold fallback still hardcoded to 0.40 after config parameter was added — the fallback path was never updated
  → Rule: When adding a config parameter to replace a hardcoded value, also update ALL fallback paths that use the old hardcoded value. Extract the default into a named constant in the config module so fallbacks stay synchronized with config defaults.
- ACCEPTED (BMAD): Population tests logged at INFO when triggered but unimplemented, making the silent no-op invisible in normal operation
  → Rule: V1 placeholder functions that are reachable at runtime must log at WARNING level, not INFO. INFO is for normal operations; WARNING signals "this ran but produced no useful output." Operators scanning logs for anomalies will filter on WARNING+, missing the placeholder at INFO.

## Story 5-7-e2e-pipeline-proof-optimization-validation
- ACCEPTED (Both): Operator review tests wrapped API calls in `try/except` blocks that silently fell back to `PipelineState.load()`, making broken APIs invisible
  → Rule: E2E proof tests must NEVER use bare `try/except` to mask API failures. If the API call fails, the test must fail. Fix the call signature — don't swallow the error.
- ACCEPTED (Both): Validation gauntlet test asserted `len(found_stages) > 0` instead of all 5 stages for complete candidates
  → Rule: When testing multi-stage pipelines, assert the EXACT expected set for normal-path items. Use `==` not `>0`. Only relax for explicitly short-circuited items identified from manifests.
- ACCEPTED (Both): Evidence pack and triage summary assertions guarded by `if path.exists()`, silently passing when files were missing
  → Rule: In E2E proof tests, artifact existence is the claim being proved. Use `assert path.exists()` not `if path.exists()`. Conditional guards on proof assertions defeat the purpose of the proof.
- ACCEPTED (Both): `REQUIRED_LOG_FIELDS` defined with 4 fields instead of the 8 required by D6, and was never used in the log verification test
  → Rule: When a constant represents a contract (like D6 log schema), define it once with the FULL spec and use it in assertions. Unused constants are dead code — verify they appear in at least one test assertion.
- ACCEPTED (Both): Manifest chain test used conditional `if field:` checks instead of assertions, and only verified `isinstance(dict)`
  → Rule: Provenance chain tests must use `assert field in manifest` not `if field:`. The chain is the proof — conditional checks make the proof vacuously true when fields are missing.
- ACCEPTED (Both): Determinism test only compared optimization outputs, not validation or scoring
  → Rule: When AC says "identical results across stages X, Y, Z", the determinism test must compare ALL named stages. Testing only one stage and calling the test `full_pipeline` is misleading.
- ACCEPTED (Both): Checkpoint/resume tests never called `resume_pipeline()` and treated checkpoint files as optional
  → Rule: Resume/recovery proof tests must actually call the recovery API, not just check for file existence. If the API exists, exercise it. If checkpoint files are part of the contract, assert they exist.
- ACCEPTED (Codex): Synthetic cost model used `datetime.now()` for `calibrated_at`, introducing non-deterministic inputs that undermine determinism proofs
  → Rule: Test fixtures that feed determinism proofs must use FIXED timestamps and seeds. Any `datetime.now()`, `uuid4()`, or `random()` in fixture creation is a determinism bug.

## Story 5-6-advanced-candidate-selection-clustering-diversity
- ACCEPTED (Codex): Cluster assignments used row positions (0..n-1) as candidate_id instead of actual IDs from the table, causing silent lookup failures after pre-filter/dedup
  → Rule: When a function processes indexed data (distance matrices, arrays), pass actual entity IDs explicitly rather than assuming row position equals identity. After any filtering, sorting, or deduplication, row indices diverge from entity IDs.
- ACCEPTED (Both): Synthetic equity curve fallback `[100.0, 110.0, ...]` used silently for all candidates, making quality metrics identical constants
  → Rule: When a metric computation falls back to synthetic/default data, log a WARNING immediately. Silent fallbacks that produce identical values across entities turn a multi-dimensional analysis into a single dimension without any operator visibility.
- ACCEPTED (Codex): Visualization parallel coordinates received empty parameter dicts, producing axes-less plots
  → Rule: When building visualization data, trace the actual data flow — don't assume a dict will be populated downstream. If you initialize `params[cid] = {}`, verify something fills it before it reaches the renderer.
- ACCEPTED (Both): Gate failure counts computed in funnel Stage 1 then discarded; orchestrator recomputed separately with different logic
  → Rule: If a function computes a useful intermediate result, return it. Never compute-then-discard and recompute externally — the two computations will inevitably diverge.
- ACCEPTED (Codex): `deterministic_ratio=0.0` still produced 1 deterministic pick due to `max(1, int(target * 0.0))`
  → Rule: When a ratio parameter controls a split, test the boundary values 0.0 and 1.0 explicitly. `max(1, ...)` guards against zero but violates the config's semantic intent when zero is a valid setting.
- ACCEPTED (Codex): Diversity selection overwrote `funnel_stage` with "selected", losing original funnel position required by AC #7
  → Rule: When promoting/selecting entities from one stage to another, preserve the original stage as provenance. Overwriting provenance fields breaks audit trails — append to a reason field instead.
- ACCEPTED (Both): Behavior data defaults used without warning, silently degrading diversity archive to proxy-only dimensions
  → Rule: Known limitations must be logged as WARNINGs at runtime, not just documented in code comments. Operators need runtime visibility into degraded-mode operation.

## Story 5-7-e2e-pipeline-proof-optimization-validation
- ACCEPTED (Codex): Determinism hash function (`hash_manifest_deterministic`) stripped only timestamp/ID keys but not path fields (`results_arrow_path`, `promoted_candidates_path`, etc.), causing false-negative determinism failures when re-runs used different output directories
  → Rule: When building a deterministic hash of an artifact manifest, strip ALL environment-dependent fields — not just timestamps and IDs, but also absolute/relative paths that vary by run directory. Maintain a single `VOLATILE_KEYS` set and review it whenever new path fields are added to manifests.

- ACCEPTED (Both): Structured log validation (`verify_structured_logs`) only checked for `component` field, ignoring `stage` and `strategy_id` from the D6 schema `{ts, level, runtime, component, stage, strategy_id, msg, ctx}`
  → Rule: When a spec defines a required field set, the validation function must check ALL fields in the set, not a subset. Partial validation creates false confidence that the schema is enforced. Test the validator itself with records missing each individual field.

- ACCEPTED (Both): Hard gates test verified outcome (failed gates -> RED) but not the required application order (DSR -> PBO -> cost_stress) specified by AC #5
  → Rule: When a spec requires ordered gate application, the test must verify order, not just final outcome. Check gate results keys/indices for correct precedence. Outcome-only checks pass even when gates are applied in the wrong order.

- ACCEPTED (Codex): Triage summary 60-second card assertion used `or` logic (any one of `headline_metrics`, `dominant_edge`, `top_risks`), allowing incomplete cards to pass
  → Rule: When a spec defines a fixed set of required fields for a summary card, require ALL of them. Using `or` logic lets partially-populated artifacts pass as complete. Use a list comprehension to check for missing fields.

- ACCEPTED (Codex): Ranked candidates schema check only verified `candidate_id` and `cv_objective`, missing `fold_scores` required by AC #2 ("per-fold CV-objective scores")
  → Rule: When a spec defines an output schema, the test must check all specified columns, not just the two most obvious ones. Missing schema columns silently degrade downstream consumers that depend on the full contract.

- ACCEPTED (Codex): Gauntlet manifest integrity test conditionally checked artifact existence (`if full_path.exists()`) instead of asserting it, silently passing when manifest referenced non-existent files
  → Rule: Never guard artifact existence checks with `if exists`. A manifest that references a non-existent file is a broken contract — assert existence unconditionally. Conditional checks turn hard failures into silent passes.

- ACCEPTED (Codex): Provenance chain test only required `dataset_hash` and `config_hash`, missing `strategy_spec_hash` specified by AC #12
  → Rule: When a spec lists required provenance fields, the test must check all of them. Missing one field means that field can silently disappear from manifests without any test catching it.

## Story 5-7-e2e-pipeline-proof-optimization-validation (Round 3)
- ACCEPTED (BMAD): `test_structured_logs_cover_all_stages` re-implemented D6 field validation inline instead of calling the existing `verify_structured_logs()` helper — two copies of the same logic that can diverge
  → Rule: When a reusable validation helper exists, call it from tests instead of re-implementing inline. Duplicated assertion logic defeats the purpose of the helper and risks the test and helper diverging silently.

- ACCEPTED (Codex): Optimization candidates schema check included `fold_scores` but omitted `generation` column required by AC #2 spec for optimization provenance
  → Rule: When extending a schema check after a prior review finding, re-read the full spec to catch ALL missing columns — not just the one flagged. Incremental fixes that add one column at a time leave other gaps undetected.

- ACCEPTED (Codex): `load_evidence_pack` was imported in the E2E proof test but never actually called in any test method, leaving the operator evidence pack loading API completely unexercised
  → Rule: Unused imports in test files are a red flag — they indicate planned-but-unwritten test coverage. After writing tests, grep for imported-but-unused names. An imported API that's never called provides zero test coverage despite appearing in the import list.

## Story 5-7-e2e-pipeline-proof-optimization-validation (Round 4)
- ACCEPTED (Both): Checkpoint/resume tests only verified file existence and API callability, never checked checkpoint content structure or that resume preserves completed artifacts. A resume that deletes prior work would pass.
  → Rule: Checkpoint tests must verify the resume *contract*, not just the resume *API*. Assert: (1) checkpoint content has enough state to resume (generation, stage tracking), (2) existing artifacts survive the resume cycle (`original.issubset(post_resume)`). API callability alone proves nothing about data safety.

- ACCEPTED (BMAD): Gauntlet stage verification used `set()` comparison which is order-insensitive. AC #4 requires config-driven cheapest-first execution order, but `{a,b,c} == {c,b,a}` is True.
  → Rule: When a spec requires ordered execution, use ordered comparisons (list ==), not set comparisons. Sets prove presence; lists prove sequence. If ordering info is available in the manifest (key insertion order, explicit `stage_order` field), assert it.

- ACCEPTED (BMAD): Story Dev Agent Record file list omitted files created during review synthesis, and Key Entry Points referenced a renamed function (`recover_from_checkpoint` → `resume_pipeline`).
  → Rule: After review synthesis adds files, update the story spec's file list. After API renames, grep the story spec for stale function names. Story specs are living documents during the review cycle.
