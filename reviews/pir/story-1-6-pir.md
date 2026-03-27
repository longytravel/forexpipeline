# PIR: Story 1-6 — Parquet Storage & Arrow IPC Conversion

**Reviewer:** Claude Opus 4.6 (1M context)
**Date:** 2026-03-14
**Type:** Post-Implementation Review (final decision)

---

## Codex Assessment Summary

Codex rated Objective Alignment as ADEQUATE, Simplification as ADEQUATE, Forward Look as CONCERN, and gave an overall REVISIT verdict. Here is my evaluation of each observation:

### 1. CLI handoff from Story 1.5 — mismatched output path
**Codex:** `converter_cli.py` looks for validated data in `raw/.../validated-data.csv` then falls back to a raw CSV name, but `quality_checker.py` saves to `validated/.../{dataset_id}_validated.csv`.

**AGREE (moderate severity).** Confirmed in the code. `quality_checker._save_validated_data()` (line 766-771) writes to `storage_path / "validated" / dataset_id / version / f"{dataset_id}_validated.csv"`. But `converter_cli.run_conversion()` (line 42-47) looks in `storage_path / "raw" / dataset_id / version / "validated-data.csv"`, with a fallback to `{pair}_{resolution}_raw.csv`. Neither path matches the actual output from Story 1.5.

This means the CLI entry point will **always fail** on real pipeline runs. The `ArrowConverter.convert()` method itself is fine — it accepts a DataFrame parameter — so any caller that passes the correct DataFrame succeeds. The problem is isolated to the CLI integration point. This is a real gap in the persisted stage-to-stage contract, but it's a CLI-level wiring bug, not a core logic issue. The programmatic API (which integration tests use) works correctly.

### 2. Config keys not schema-validated
**Codex:** `[data_pipeline.storage]` and `[data_pipeline.parquet]` exist in `base.toml` but aren't covered by `schema.toml` validation.

**AGREE (low severity).** Confirmed: `schema.toml` has no entries for `data_pipeline.storage.arrow_ipc_path`, `data_pipeline.storage.parquet_path`, or `data_pipeline.parquet.compression`. The code has its own fallback chain (`__init__` lines 60-73), so it works at runtime. But per D7 ("Config hash embedded in every artifact manifest — reproducibility is verifiable"), unvalidated config keys undercut the "explicit, traceable" intent. This is a pattern we've seen before — Story 1.5 PIR noted placeholder config_hash fields. Adding schema entries is trivial and should be done.

### 3. Multiple storage path resolution sources
**Codex:** Storage can come from `[data].storage_path`, `[data_pipeline].storage_path`, or `[data_pipeline.storage].*`, creating implicit fallback complexity.

**AGREE (low severity).** The `__init__` method resolves paths through a multi-level fallback chain. This is a pragmatic accommodation of the config structure evolving across stories (Story 1.4 used `[data].storage_path`, Story 1.6 added `[data_pipeline.storage]`). For V1 with a single operator, this works fine. But it creates a maintenance burden — if someone changes `[data].storage_path` but not `[data_pipeline.storage]`, behavior depends on which takes precedence. A single canonical source would be cleaner, but this is not blocking.

### 4. `_find_contracts_path()` walks CWD
**Codex:** Contract discovery walks `cwd()` and parents, which is operationally fragile.

**PARTIALLY AGREE.** The walk-up-from-cwd pattern is common in Python projects (pytest, setuptools all do it). For a single-operator system where the pipeline is always run from the project root or a known subdirectory, this is acceptable. However, Codex is right that an explicit config-resolved contracts path would be more reproducible. A config entry like `project.contracts_path` would eliminate the CWD dependency. Minor concern for V1.

### 5. `validate_dataframe_against_schema()` imported but redundant
**Codex:** The import exists but conversion relies on `pa.Table.from_pandas(schema=...)` plus a post-build schema equality check.

**DISAGREE.** The import is used in `_prepare_arrow_table()` as a pre-check before the `pa.Table.from_pandas()` call. Having both a DataFrame-level check (readable error messages) and a Table-level check (exact Arrow schema match) is defense in depth, not redundancy. The DataFrame validator catches column-level mismatches early with clear error messages; the `from_pandas(schema=...)` call catches type casting failures. Different failure modes, different error messages, both useful for an operator diagnosing schema drift.

### 6. Manifest doesn't link to upstream quality report
**Codex:** The manifest records `quality_score` and `quality_rating` but doesn't reference the upstream quality report path, validated CSV path, or source dataset manifest.

**AGREE (moderate severity).** The manifest at lines 328-359 includes quality score/rating as scalar values but has no `upstream_artifacts` or `source_manifest` field linking back to the quality report at `{storage_path}/raw/{dataset_id}/{version}/quality-report.json` or the download manifest. The PRD (Section 2.3 artifact chain: "stage artifacts be versioned, linked, and reviewable") and architecture (D2 directory structure, D7 config hash embedding) imply a full lineage chain. Currently, an operator reviewing this manifest cannot trace back to the specific quality report or download manifest that produced this data. For V1's single-pair proof slice this is workable — the operator knows the pipeline order — but it weakens reproducibility verification.

### 7. data_hash computed from IPC stream, not file bytes
**Codex:** `_compute_data_hash()` serializes the table to an IPC stream (line 283: `pa.ipc.new_stream()`) and hashes that, while the actual `.arrow` file is written using IPC file format (`pa.ipc.new_file()`). This proves logical table identity, not file identity.

**PARTIALLY AGREE (low severity).** The hash proves the *data content* is identical — same schema, same record batches, same values. This is actually more useful than file-byte hashing for reproducibility: the data hash is stable across different PyArrow versions that might produce slightly different IPC file headers/footers. If you re-run conversion with the same input, the data hash will match even if PyArrow internals changed the file layout. The architecture says "same dataset (identical Arrow IPC file)" but the meaningful invariant is "same data content," which the stream hash captures. However, if downstream Rust code needs to verify the exact `.arrow` file integrity (e.g., for security), a separate file checksum would be needed. Not a V1 concern.

### 8. Session validation hardcodes 5-value set; contract allows "mixed"
**Codex:** `VALID_SESSIONS` at line 40 is `frozenset(["asian", "london", "new_york", "london_ny_overlap", "off_hours"])`, but `arrow_schemas.toml` includes `"mixed"` in the market_data session values. Timeframe conversion (Story 1.7) emits `"mixed"` for D1/W bars.

**AGREE (low severity for V1, important for future).** For the V1 proof slice (M1 only), `"mixed"` never appears, so this doesn't break anything. But the contract (`arrow_schemas.toml`) explicitly includes `"mixed"` in the `market_data.session.values` list. Story 1.6's hardcoded set is stricter than the contract it claims to enforce. When/if Story 1.6 is ever called on aggregated timeframe data, it would incorrectly reject valid `"mixed"` sessions. The `VALID_SESSIONS` set should be loaded from the contract or from `session_schema.toml` rather than hardcoded. This echoes the anti-pattern the story spec itself warns about: "Do NOT hardcode the Arrow schema."

### 9. CLI hardcodes dataset_id and version
**Codex:** `converter_cli.py` constructs `dataset_id = f"{pair}_{start_str}_{end_str}_{resolution}"` and `version = "v001"`.

**PARTIALLY AGREE (low severity).** The dataset_id format matches the convention used by Story 1.4 (`downloader.py`) and Story 1.5 (`quality_checker.py`), so it's consistent across the pipeline. The `version = "v001"` is indeed hardcoded, but V1 only has one version. When Story 1.8 (data splitting / consistent sourcing) needs hash-identified versioning, the CLI should accept version as a parameter. For now, this is consistent with the other CLIs.

---

## Objective Alignment
**Rating:** ADEQUATE

The core storage conversion work directly serves the system's key objectives:

- **Reproducibility:** Data hash (SHA-256 of IPC stream), config hash, and session schedule hash are all embedded in the manifest. Same input + same config = same hash = reproducibility verified (FR8). Deterministic hash tests confirm this (`test_data_hash_determinism`).
- **Artifact completeness:** Both Arrow IPC and Parquet outputs are produced, verified, and manifested. The schema is loaded from `contracts/arrow_schemas.toml` (not hardcoded), enforcing the single-source-of-truth principle. mmap verification proves Rust compatibility.
- **Fidelity:** Exact schema enforcement via `pa.Table.from_pandas(schema=...)` plus post-build equality check. Timestamps correctly converted to int64 epoch microseconds. Session column stamped via the shared `session_labeler.py` utility. Crash-safe write pattern applied to all three artifacts (Arrow IPC, Parquet, manifest).
- **Operator confidence:** Conversion logging at INFO level with sizes and compression ratios. Manifest includes session distribution and quarantined bar count for quick sanity checking.

What works against objectives:
- The CLI path mismatch (observation #1) means an operator running the CLI directly hits a failure. This directly undermines operator confidence at the integration boundary. The programmatic API is fine, but the CLI is the operator-facing entry point.
- Missing upstream lineage links (observation #6) weaken the "reviewable artifact chain" goal.

---

## Simplification
**Rating:** ADEQUATE

The implementation is appropriately scoped:

- **Core mechanism is not over-engineered.** Dual-format output (Arrow IPC + Parquet) is the architecture, not invention. mmap verification, crash-safe writes, and hash computation are all explicit requirements.
- **Sensible reuse.** `crash_safe_write` from `artifacts.storage`, `compute_config_hash` from `config_loader.hasher`, and `assign_sessions_bulk` from Story 1.5's `session_labeler.py` are all reused rather than reimplemented.
- **ParquetArchiver is lean.** ~60 lines, does exactly one thing (crash-safe Parquet write + verify), no unnecessary abstractions.
- **Test coverage is comprehensive without being bloated.** 36 tests across 3 files plus 3 live tests. Each test targets a specific AC or edge case.

Minor complexity concerns:
1. **Config fallback chain** (3 potential sources for storage path) adds implicit resolution logic. A single canonical path would be simpler.
2. **`_find_contracts_path()`** walk-up logic adds ~10 lines that a config entry would eliminate.

Neither is blocking. The implementation follows YAGNI — no speculative features, no unused abstractions.

---

## Forward Look
**Rating:** ADEQUATE

### Downstream compatibility
- **Story 1.7 (timeframe conversion):** Contract tests (`test_pipeline_contracts.py` line 187) verify Story 1.6 output can be consumed by timeframe conversion. The Arrow IPC schema and column set are compatible.
- **Story 1.8 (data splitting):** The `convert()` method accepts `dataset_id` and `version` as parameters, so Story 1.8 can pass hash-identified versions. The CLI hardcodes these, but the API doesn't.
- **Rust compute layer:** mmap verification (`_verify_arrow_ipc` using `pa.memory_map()`) directly proves the file format works for Rust's zero-copy access. IPC file format (not stream) is correctly used.

### Items that need attention
1. **CLI path mismatch must be fixed** before the pipeline orchestrator (Story 2.x) wires stages together. Currently the CLI is broken for real pipeline runs.
2. **`VALID_SESSIONS` should load from contract** before any story calls this on aggregated timeframes. Currently safe for M1-only V1.
3. **Manifest lineage linking** should be addressed when the orchestrator or evidence pack stories need full artifact chain traceability.

### What's set up well
- The `ArrowConverter.convert()` API is clean and parameterized — easy for an orchestrator to call with the right arguments.
- Hash computation (data + config + session schedule) provides the foundation for Story 1.8's consistent sourcing and reproducibility verification.
- Schema loaded from contracts means Rust and Python share a single source of truth for the data format.

---

## Observations for Future Stories

1. **Stage handoff paths must be tested end-to-end at the CLI level.** The programmatic API (`convert(validated_df=...)`) works correctly, but the CLI (`converter_cli.py`) constructs the wrong input path. Integration tests should include a CLI-to-CLI chain test that exercises the persisted artifact handoff, not just the in-memory DataFrame handoff. This is a recurring theme: Story 1.5 PIR noted that `can_proceed` gates are score-only — the pattern of "core logic works, integration wiring has gaps" should be caught by stage-boundary tests.

2. **Hardcoded value sets should load from contracts.** `VALID_SESSIONS` is hardcoded as a frozenset when the contract (`arrow_schemas.toml`) already defines the allowed values. This creates two sources of truth that can drift. Rule: if a contract file defines allowed values, runtime code should load from that file, not duplicate it.

3. **New config keys need schema.toml entries.** Every story that adds config keys should add corresponding `schema.toml` validation entries in the same PR. This has been missed in Stories 1.5 and 1.6. Consider adding a contract test that verifies every key in `base.toml` has a corresponding `schema.toml` entry.

4. **Manifest lineage should be cumulative.** Each stage's manifest should include a reference to the previous stage's manifest (path + hash), building a linked chain. This doesn't need to be complex — a `source_manifest: "sha256:..."` field would suffice. Story 1.8 or the orchestrator story should formalize this pattern.

---

## Verdict

**VERDICT: OBSERVE**

The core storage conversion work is well-aligned with system objectives. Arrow IPC with mmap verification, Parquet archival, crash-safe writes, contract schema enforcement, and hash-based reproducibility all directly serve the PRD's goals of fidelity, reproducibility, and artifact completeness. The implementation is clean, well-tested (36+ tests, zero regressions), and appropriately scoped.

The concerns Codex raised are real but not severe enough to warrant REVISIT:
- The **CLI path mismatch** (observation #1) is a wiring bug, not a design flaw. The core `ArrowConverter.convert()` API works correctly. The fix is a one-line path correction in `converter_cli.py`.
- **Missing schema.toml entries** (observation #2) and **hardcoded VALID_SESSIONS** (observation #8) are cleanup items that should be addressed before the orchestrator story, not blockers.
- **Missing manifest lineage** (observation #6) is a valid concern for the full artifact chain story, but V1's single-pair proof slice doesn't depend on automated lineage traversal.
- The **data_hash stream-vs-file** distinction (observation #7) is actually a reasonable design choice for content identity.

Codex's REVISIT verdict overweights the CLI integration gap relative to the core value delivered. The programmatic API, schema enforcement, hash computation, mmap verification, and crash-safe writes are all correct and well-tested. The observations noted here should be tracked as cleanup for pre-orchestrator hardening.
