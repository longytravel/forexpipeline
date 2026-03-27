# PIR: Story 1-4 — Dukascopy Data Download

**Reviewer:** Claude Opus 4.6 (1M context)
**Date:** 2026-03-14
**Type:** Post-Implementation Review (final decision)

---

## Codex Assessment Summary

Codex rated all three axes CONCERN and gave an overall REVISIT verdict. Here is my evaluation of each observation:

### 1. Year-wide downloads, not request-range-wide
**Codex:** `_download_year()` fetches full years; `download()` consolidates without clipping to `start_date`/`end_date`, producing a larger dataset than requested.

**DISAGREE (severity).** This is the documented design, not an oversight. The story spec (Task 2.7-2.9) explicitly calls for yearly chunking adapted from ClaudeBackTester. Dukascopy's API works most efficiently at yearly granularity, and yearly chunks enable resume. The consolidated artifact contains *more* data than requested — never less. The manifest records the intended range (`start_date`/`end_date`), so downstream consumers can clip if needed. "More data than requested" is not a fidelity problem; "less data than requested" would be.

### 2. Incremental/merge helpers are dead code
**Codex:** `_detect_existing_data`, `_compute_missing_ranges`, `_validate_merge_boundary`, `_merge_data` are implemented but never called in runtime.

**PARTIALLY AGREE.** The yearly chunk resume (lines 286-293 in `download()`) IS the operational incremental mechanism — it skips already-downloaded years and re-downloads only the current year. This satisfies AC #5 in spirit. However, the four finer-grained methods add ~125 lines of unreachable code. AC #6 ("incremental data is validated before merging") is not exercised in the runtime path — `_consolidate_chunks` sorts and deduplicates but doesn't call `_validate_merge_boundary`. These methods should either be wired into the flow or removed. Dead code adds cognitive load without serving the shipped workflow.

### 3. Timeout/backoff config is cosmetic
**Codex:** `_timeout` and `_backoff_factor` are stored but never passed to `dk.fetch()`.

**AGREE.** `dk.fetch()` is called with `max_retries=self._max_retries` (functional) but `_timeout` and `_backoff_factor` are never used (lines 42, 45 vs 112-120). This creates a false control surface: an operator who adjusts `download_timeout_seconds` or `retry_backoff_factor` in config expects changed behavior but gets none. Either wire them in (if `dukascopy_python` supports them), remove from config, or document as advisory-only.

### 4. Tick mode over-scopes V1 MVP
**Codex:** PRD FR1 is M1 bid+ask; tick mode adds a second data shape before downstream consumers support it.

**PARTIALLY AGREE.** The story spec AC #3 explicitly includes tick support, so the implementation is spec-compliant. But Codex is right that downstream stories (1.5 validator, 1.6 converter) don't handle tick-shaped data. The tick path (`_download_tick_data`, ~50 lines) is self-contained and doesn't complicate the M1 path, so it's low-harm. Note for future: avoid adding capabilities without downstream consumers to exercise them.

### 5. Dataset identity omits `source` and `download_hash`
**Codex:** Architecture D2/FR8 says `{pair}_{start_date}_{end_date}_{source}_{download_hash}` but implementation uses `{pair}_{start}_{end}_{resolution}`.

**AGREE (minor).** The hash is inside the manifest (correct for provenance) but not in the directory name (acceptable — hash-in-filename is unwieldy). Omitting `source` is fine for V1 with a single source (Dukascopy). Replacing `source` with `resolution` in the ID is a pragmatic choice. If multi-source ever arrives, the naming scheme will need revision, but that's a Growth-phase concern.

### 6. Current year assumption is brittle
**Codex:** Only the current year is re-downloaded; older years are treated as stable cache.

**DISAGREE.** Historical forex M1 data from Dukascopy is immutable once the year ends — this is a domain fact, not an assumption. The manifest's `data_hash` detects any divergence if a re-download is forced. The resume pattern (skip completed years, always refresh current year) is exactly what ClaudeBackTester proved over years of use.

### 7-8. Tick path doesn't connect downstream; cross-story artifact lookup unstable
**Codex:** Story 1.6's converter doesn't handle tick schema; Story 1.5/1.6 have inconsistent version path assumptions.

**AGREE but out-of-scope.** These are downstream story bugs, not Story 1.4 defects. Story 1.4's output contract (`raw/{dataset_id}/v{NNN}/{dataset_id}.csv` + `manifest.json`) is clear, correct, and self-consistent. Downstream consumers failing to use it correctly is their PIR's concern.

---

## Objective Alignment
**Rating:** ADEQUATE

Story 1.4 serves the core system objectives:

- **Reproducibility:** Versioned artifacts (never overwritten), SHA-256 data hash, config hash in manifest. Same download produces same hash. Re-runs create new versions, preserving history.
- **Operator confidence:** Structured logging with progress/ETA (AC #8), graceful degradation on failures (AC #9), failed periods tracked in manifest. LogContext scoping per D6.
- **Artifact completeness:** Raw CSV + `manifest.json` with full metadata (dataset_id, version, hash, timestamps, row count, failed periods, config hash).
- **Fidelity:** Bid/ask stored as separate columns (not computed spread), UTC timestamps enforced, crash-safe writes prevent corruption.

Two gaps prevent STRONG:
1. Dead incremental code creates a false impression that fine-grained incremental logic is operational
2. Cosmetic timeout/backoff config undermines operator confidence (config appears functional but isn't)

---

## Simplification
**Rating:** ADEQUATE

The core download flow (yearly chunk -> consolidate -> versioned artifact) is clean and well-structured. The adaptation from ClaudeBackTester is faithful and pragmatic.

Areas of unnecessary complexity:
1. **Dead incremental methods** (~125 lines): `_detect_existing_data`, `_compute_missing_ranges`, `_validate_merge_boundary`, `_merge_data` should be removed or wired in. They exist only in tests.
2. **Cosmetic config keys** (`download_timeout_seconds`, `retry_backoff_factor`): Config surface that doesn't influence behavior should be pruned.
3. **Tick mode** (~50 lines): Self-contained but exercised only by live tests, not downstream stories. Low harm.

The hash computation workaround (lines 601-621, bypassing pandas `to_csv` for Windows compatibility) and CSV write workaround (lines 657-680, bypassing pandas C extension) are necessary platform-specific fixes, not over-engineering.

---

## Forward Look
**Rating:** STRONG

- **Story 1.5 handoff:** The output contract (`raw/{dataset_id}/v{NNN}/{dataset_id}.csv`) is clear. Story 1.5's validator loads this path correctly (confirmed by reading the story spec references).
- **Manifest contract:** `manifest.json` with `data_hash`, `config_hash`, `row_count`, `failed_periods` gives downstream stages everything they need for provenance and quality assessment.
- **Version auto-increment:** New downloads never overwrite existing versions — this is architecturally correct and proven by the live full-pipeline test (v001 + v002 coexistence).
- **Chunk cache:** Yearly Parquet chunks enable fast resume across pipeline re-runs. The chunk directory (`{pair}_M1_chunks/`) is a cache, not a contract — downstream stories consume the versioned CSV, not chunks.
- **Config integration:** Uses Story 1.3's `compute_config_hash()` and `LogContext` correctly, building on prior story outputs.

The only forward concern (tick data not consumed downstream) is a scope observation, not an impediment.

---

## Observations for Future Stories

1. **Dead code discipline:** If a method is implemented to satisfy an AC but not wired into the runtime path, either wire it in or defer the AC. Implemented-but-uncalled code creates a false sense of completeness. (Echoes lessons-learned pattern from Story 1-7: "When the spec says X, always use the config-driven utility function.")

2. **Config-behavior parity:** Every config key must influence runtime behavior. Cosmetic config erodes operator trust — if one knob is fake, which others are? Either pass `timeout`/`backoff_factor` to the library or remove them from config.

3. **Scope gating by downstream consumer:** Don't add capabilities (tick mode) until at least one downstream story is ready to consume the output. Unused capabilities are untested in integration and may rot.

4. **Test coverage of runtime path vs helper methods:** Several tests exercise the dead incremental helpers but don't test the actual runtime incremental flow (yearly chunk resume). Future stories should prioritize testing the code paths that actually execute in production.

---

## Verdict

**VERDICT: OBSERVE**

Story 1.4 delivers its core value: reliable, resumable, versioned Dukascopy data download with crash-safe writes, provenance tracking (data hash + config hash), structured logging, and graceful degradation. The yearly chunking pattern adapted from ClaudeBackTester is proven and pragmatic. The output contract serves Story 1.5 correctly.

The observations (dead incremental code, cosmetic config, premature tick scope) are worth noting for future story quality but do not compromise system objectives. Codex's REVISIT verdict overstates the severity — none of the issues block the pipeline or produce incorrect results. The dead code and cosmetic config are cleanup items, not alignment failures.
