# PIR: Story 1-8 — Data Splitting & Consistent Sourcing

**Reviewer:** Claude Opus 4.6 (1M context)
**Date:** 2026-03-14
**Type:** Post-Implementation Review (final decision)

---

## Codex Assessment Summary

Codex rated Objective Alignment as CONCERN, Simplification as ADEQUATE, Forward Look as CONCERN, and gave an overall REVISIT verdict. The central thesis: config-blind reuse (dataset_id excludes config_hash) creates a significant conflict with deterministic reproducibility.

### 1. Config-blind reuse path
**Codex:** `compute_dataset_id()` excludes `config_hash`, so `run_data_splitting()` returns an existing manifest immediately when dataset_id matches, even if split config has changed. This conflicts with the "same dataset + same config = same output" invariant and the "no implicit drift" requirement.

**PARTIALLY AGREE (lower severity than Codex rates).** Codex is factually correct that `dataset_id` does not include `config_hash` and that `check_existing_dataset()` at `data_splitter.py:409` returns early based on `dataset_id` alone. However, Codex overweights this concern for V1:

- The story spec (AC #3) explicitly defines `dataset_id` as `{pair}_{start_date}_{end_date}_{source}_{download_hash}` — it identifies the **data**, not the **transformation**. The spec is intentional.
- In V1, the pipeline operates on a single pair with a fixed config. There is no operational path where an operator changes split_ratio between runs without understanding they need to clear old artifacts.
- The `dataset_id` includes `download_hash`, so different source data produces different IDs. The concern is limited to same-data-different-config scenarios.
- The manifest records `config_hash` (`data_manifest.py:58`), making any config mismatch detectable by inspection or by downstream verification (Story 1.9 does verify this).
- The architecture invariant "same inputs -> same outputs" is **preserved** in practice: identical inputs produce identical outputs. The gap is only that *changed* configs don't invalidate cached outputs — a cache-invalidation concern, not a reproducibility violation.

This is a legitimate forward concern for multi-config scenarios but not a V1 alignment problem.

### 2. `ensure_no_overwrite` called without expected_hash
**Codex:** File-level overwrite checks at `data_splitter.py:470` are called without `expected_hash`, so they only check existence, not content.

**AGREE (low severity).** The code at `dataset_hasher.py:119-126` confirms: when `expected_hash is None`, it returns `False` (skip) without verifying content. However, severity is low because:
- Filenames now embed `data_hash8` (lines 458-461), so different downloads produce different filenames — the primary identity guarantee.
- For the same download, deterministic splitting means the content should be identical.
- The manifest-level check at line 409 provides the first gate; file-level checks are defense-in-depth.
- Passing `expected_hash` would require computing the hash of what *would* be written before writing, which adds complexity for marginal benefit.

### 3. Config validation gap — split_date semantics
**Codex:** `schema.toml` declares `split_date` semantics but the validator only supports basic type/min/max checks, so bad date-mode config is caught at runtime, not at config validation.

**AGREE (low severity).** The validator cannot enforce "if split_mode='date' then split_date must be a valid ISO date" — that cross-field validation happens at runtime in `data_splitter.py:96-98`. This is consistent with every prior story's validation approach and is an accepted limitation of the simple schema validator. Not a regression.

### 4. Manifest missing `configured_split_date`
**Codex:** `split_train_test()` captures `configured_split_date` in metadata (line 119-120) but `create_data_manifest()` drops it (doesn't include it in the `split` section).

**AGREE (low severity).** This was accepted in lessons-learned. The `split_metadata` dict includes `configured_split_date` when `split_mode="date"`, but `create_data_manifest()` at lines 62-70 copies only specific fields and omits it. The actual split timestamp (`split_date_iso`) is recorded, so the *outcome* is preserved — only the *intent* (user-configured boundary) is lost. For ratio-mode (the V1 default), there is no configured date to lose. Fix is trivial: add one `.get()` line to `create_data_manifest()`.

### 5. Missing per-file output hashes in manifest
**Codex:** Story 1.9 expects per-file hash-chain verification but the manifest stores only filenames, not per-file hashes. Story 1.9's `pipeline_proof.py` compensates by hashing files directly.

**PARTIALLY AGREE (scope issue, not a Story 1.8 gap).** The story spec's manifest structure (lines 78-112 of the spec) shows filenames, not hashes, in the `files` and `timeframes` sections. The implementation matches the spec. Per-file output hashes would strengthen the artifact chain, but the spec didn't require them and Story 1.9 successfully works around it. This is a future enhancement, not a misalignment.

### 6. Missing minimum split size validation
**Codex:** The spec says "at least 1000 M1 bars" (anti-pattern #8) but the code only rejects empty partitions.

**AGREE (low severity for V1).** The code guards against empty splits (`data_splitter.py:147-154`, `184-191`) but does not enforce a configurable minimum. With V1's ~525K bars and 0.7 ratio, the smallest partition is ~158K bars. This is a defensive guard against misconfiguration that would only fire on pathologically small datasets or extreme ratios — neither is possible in V1's operational envelope.

### Observations Codex missed

**Sorting is correct.** The lessons-learned records that ratio-mode splitting was fixed to sort by timestamp before slicing. Verified at `data_splitter.py:141-143` — `_split_by_ratio()` sorts ascending before `table.slice()`. The fix is in place and tested.

**Filenames embed data hash.** The lessons-learned records that split filenames were fixed to include `data_hash8`. Verified at `data_splitter.py:458-461` — `_build_split_filename()` includes the hash. This significantly mitigates the overwrite concern: new downloads produce new filenames, old artifacts are preserved.

**M1 split re-execution.** In `run_data_splitting()`, the M1 table is split twice: once at line 421 to determine `split_timestamp_us`, and again at line 451 in the `for tf` loop. This is harmless (deterministic, same result) but redundant. A minor inefficiency, not a correctness issue.

---

## Objective Alignment

**Rating: ADEQUATE**

This story directly serves the system's core objectives:

- **Reproducibility:** Hash-based dataset identification ensures the same data always maps to the same dataset_id. Deterministic splitting (sorted, no shuffle) produces identical outputs for identical inputs. Manifest records `config_hash` and `data_hash` for full traceability.
- **Artifact completeness:** Dual-format output (Arrow IPC + Parquet) for every timeframe and every partition. Crash-safe writes for all files and manifest. Manifest links all artifacts together.
- **Operator confidence:** Structured JSON logging at every step. Manifest is human-readable JSON. Strict temporal guarantee verified and enforced (`_verify_temporal_guarantee`).
- **Fidelity:** No shuffle, no random sampling, strict chronological order. Zero-copy PyArrow slicing for ratio mode. Filter-based splitting for date mode.

The config-blind reuse path is a real gap but does not work *against* objectives in V1's single-config operational envelope. The manifest records the config_hash, so drift is detectable even if not automatically prevented.

---

## Simplification

**Rating: ADEQUATE**

The implementation is well-factored across three modules with clear responsibilities:
- `data_splitter.py`: Splitting logic + orchestration
- `dataset_hasher.py`: Identity + hashing + overwrite guards
- `data_manifest.py`: Manifest creation + crash-safe writing

No over-engineering observed:
- `split_mode="date"` is explicitly required by the spec, not gratuitous.
- Multi-timeframe splitting is required (all Story 1.7 outputs must be split at the same boundary).
- Dual Arrow/Parquet output matches the architecture's D2 decision.

The dual idempotency mechanism (manifest-level reuse + file-level existence check) adds slight complexity, but each serves a distinct purpose: manifest check handles the happy re-run path; file check handles crash-recovery where manifest wasn't written but some files were. This is correct for crash-safe design.

One simplification opportunity: the M1 table is split redundantly (once to get the split timestamp, once in the loop). Could be avoided by saving the M1 train/test tables from the first split. Not worth changing — it's a performance micro-optimization on an already-fast zero-copy operation.

---

## Forward Look

**Rating: ADEQUATE**

- **Story 1.9 compatibility:** Story 1.9 is already implemented and working on top of Story 1.8's output. The `pipeline_proof.py` successfully exercises the full artifact chain including splitting, manifest verification, and reproducibility checks. Any contract gaps were successfully bridged.

- **Lineage chain:** The manifest includes `data_hash` (source identity) and `config_hash` (transform identity), which together form the reproducibility proof that D7 requires. Per-file output hashes would strengthen this, but the current contract is sufficient for the pipeline proof to verify artifact integrity by hashing files at verification time.

- **Downstream consumers:** The file naming convention (`{pair}_{start}_{end}_{TF}_{split}_{hash8}.arrow`) is clear, deterministic, and content-addressed. Any downstream story can locate and identify split artifacts by name.

- **Multi-config future:** When the pipeline supports multiple split configurations (e.g., walk-forward analysis), the reuse path will need to incorporate config_hash into the cache key. This is a known limitation documented in lessons-learned and addressable with a one-line change to `check_existing_dataset()`. The current design does not preclude this fix.

- **FX-specific filename parser:** The `_FILENAME_RE` at `data_splitter.py:220` assumes 6-letter pair codes. This is a deliberate V1 scope choice, not a forward problem — the system only targets FX pairs in V1.

---

## Observations for Future Stories

1. **Config-aware cache invalidation:** When any story introduces multiple config variants (e.g., walk-forward, different split ratios per experiment), the reuse check in `run_data_splitting()` must be extended to verify `config_hash` matches the existing manifest's `config_hash` before returning cached results. This is a one-line fix but must not be forgotten.

2. **Manifest should preserve user intent:** When a user specifies `split_mode="date"` with a `split_date`, both the configured boundary and the actual boundary should appear in the manifest. Currently `configured_split_date` is computed but dropped by `create_data_manifest()`. Future stories that add audit trails or operator review of split decisions will need this.

3. **Per-file output hashes in manifests:** As the artifact chain grows deeper (strategy -> backtest -> optimization), manifests should include hashes of their output files, not just filenames. This enables chain-of-custody verification without re-reading files. Consider adding this to the manifest schema when the artifact management layer matures.

4. **Minimum split size guard:** The spec calls for "at least 1000 M1 bars" but only empty-partition guards are implemented. If future stories add operator-configurable datasets (smaller pairs, shorter date ranges), add a configurable minimum bar count to prevent trivially small test sets.

---

## Verdict

**VERDICT: OBSERVE**

Story 1.8 clearly serves the system's primary objectives — reproducibility, artifact completeness, and temporal fidelity. The implementation is well-structured, correctly applies lessons from prior stories (sorted splitting, hash-embedded filenames, independent paired-artifact checks), and provides a working foundation that Story 1.9 successfully builds upon.

The config-blind reuse path is a real observation but is appropriately scoped as an OBSERVE rather than REVISIT:
- It matches the spec's definition of dataset identity (data-based, not config-based)
- It is inert in V1's fixed-config operational envelope
- It is detectable via manifest inspection (config_hash is recorded)
- It is fixable with a minimal change when multi-config scenarios arise
- Story 1.9 is already working successfully on top of this output

Codex's REVISIT verdict overweights a theoretical concern that has no practical impact in V1. The four items in lessons-learned (filenames, sorting, configured_split_date) demonstrate that the implementation was actively refined during development. Three of four were fully addressed in code; the fourth (configured_split_date in manifest) is trivial.
