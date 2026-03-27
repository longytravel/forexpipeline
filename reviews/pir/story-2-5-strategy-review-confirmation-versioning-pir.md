# PIR: Story 2-5-strategy-review-confirmation-versioning — Story 2.5: Strategy Review, Confirmation & Versioning

**Reviewer:** Claude Opus 4.6 (1M context)
**Date:** 2026-03-16
**Type:** Post-Implementation Review (final alignment assessment)

---

## Codex Assessment Summary

Codex rated Objective Alignment ADEQUATE, Simplification ADEQUATE, Forward Look CONCERN, with an overall **REVISIT** verdict. Key observations and my evaluation:

### 1. PIPELINE_ENV vs FOREX_PIPELINE_ENV mismatch
**AGREE — but lower severity than implied.** Confirmed: `confirmer.py:71` uses `os.environ.get("PIPELINE_ENV", "local")` while `config_loader/loader.py:50` uses `os.environ.get("FOREX_PIPELINE_ENV", "local")`. This is a genuine bug — if an operator sets `FOREX_PIPELINE_ENV=production` but not `PIPELINE_ENV`, the confirmer would hash the "local" config while the rest of the system uses "production" config, producing a misleading `config_hash`. However, the severity is bounded: V1 targets a single operator on a single machine, both default to "local", and the mismatch only triggers when one env var is set without the other. The root cause is that `confirmer.py` has its own `_load_config_as_dict()` instead of reusing `config_loader.loader.load_config()`. **Should be fixed before Epic 3, but not a V1 blocker.**

### 2. Missing spec_hash verification on load
**AGREE — deferred appropriately.** `verify_spec_hash()` is implemented in `hasher.py` and exported from `__init__.py`, but neither `confirmer.py` nor `modifier.py` call it when loading specs. The story spec's anti-pattern #15 explicitly says "Do NOT skip hash verification." The synthesis report tracks this as Action Item #1 (deferred). For V1's single-operator scenario where only the operator touches files, the risk of undetected tampering is minimal. **Should be wired in before any multi-user or remote access scenario.**

### 3. Approximate timestamps in manifest bootstrap
**AGREE — edge case, well-documented.** `modifier.py:413` sets the old version's `created_at` to the new version's timestamp with an explicit `# approximate — original timestamp unknown` comment when no manifest exists. This only occurs once per strategy on the first modification when no manifest has been created. The code is honest about the approximation. **Acceptable for V1.**

### 4. No encapsulated "load pipeline-approved spec" helper
**PARTIALLY AGREE.** The `latest_confirmed_version` pointer is present in the manifest, tested in `test_versioner.py:283` and `test_review_e2e.py:338`, and documented in the story spec's Downstream Contract section. But Codex is right that the contract is "documented but not encapsulated" — there's no single `load_approved_spec(slug, artifacts_dir)` helper that downstream consumers can call. Epic 3 will need to either build this or replicate the manifest-reading logic. **Recommend creating a helper in the Epic 3 story spec, not retrofitting here.**

### 5. Diff output for complex nested types
**DISAGREE with Codex's severity.** Codex rated this HIGH; the synthesis rejected it with evidence that `_format_value()` is recursive and produces readable output for the spec structures actually used in V1 (e.g., `type: session, params: include: london`). For one strategy family on one pair/timeframe, the output is adequate. Polish is a cosmetic enhancement.

### 6. Module separation and consolidation opportunities
**AGREE with Codex and synthesis.** The reviewer/versioner/confirmer/modifier split maps cleanly to distinct responsibilities. The synthesis identified three consolidation opportunities (reuse shared config loader, unify `find_latest_version`, extract shared TOML save helper) and deferred them. These are cleanup items, not architectural flaws.

## Objective Alignment
**Rating:** STRONG

This story directly serves the system's four core objectives:

- **Operator confidence (FR11, FR12):** The reviewer generates plain English summaries with clear section headers — no TOML/JSON/dict syntax exposed. The confirm/modify workflow gives the operator explicit control over what enters the pipeline. Tests (`test_summary_no_raw_spec_format`) verify the "no code visibility" requirement.

- **Reproducibility (FR59, FR61):** `config_hash` links each confirmed spec to the pipeline infrastructure state at confirmation time. `spec_hash` (now correctly excluding lifecycle metadata after the synthesis fix) provides content-level integrity. Immutable versions (FR12) with collision guards (`modifier.py:374-379`) prevent silent overwrites.

- **Artifact completeness (FR39, FR58):** Review summaries persist to `reviews/{version}_summary.txt`, diffs persist to `diffs/{old}_{new}_diff.txt`, and the manifest records full version history with timestamps, hashes, and the `latest_confirmed_version` pointer. E2E tests verify artifact presence on disk.

- **Fidelity:** Idempotent confirmation (confirming an already-confirmed spec returns existing result), version collision guards, and crash-safe writes via `safe_write()` / `crash_safe_write()` prevent data corruption.

The env var mismatch (PIPELINE_ENV vs FOREX_PIPELINE_ENV) is the only item that works against an objective (reproducibility), but it defaults safely in V1's single-operator local scenario.

## Simplification
**Rating:** STRONG

The implementation hits the right level of complexity for V1:

- **Four modules, four responsibilities:** reviewer (spec → English), versioner (version management + manifest), confirmer (draft → confirmed), modifier (apply changes → new version). No module does more than one thing.

- **No over-engineering:** The manifest/pointer model (`current_version` vs `latest_confirmed_version`) is justified — "highest file wins" would break operator confidence when a newer draft exists alongside an older confirmed spec. The natural-language modification skill is a thin wrapper around deterministic Python primitives, not a full NL orchestration system.

- **Pure text transformation:** `generate_summary()` and `format_summary_text()` are deterministic template-based transformations with no LLM calls from Python, exactly as the architecture (D10) requires.

- **Minor consolidation opportunities:** The synthesis identified three DRY improvements (shared config loader, unified version finder, shared TOML save helper). These are cleanup items tracked as deferred action items, not signs of over-engineering.

## Forward Look
**Rating:** ADEQUATE

The output contract serves downstream well, with two caveats:

**What works:**
- `latest_confirmed_version` in the manifest is the explicit approved-spec pointer that Epic 3 backtesting needs. It's tested and documented.
- Immutable versioned artifacts with `spec_hash` and `config_hash` give downstream stages a complete provenance record.
- The manifest JSON schema is stable and well-defined (strategy_slug, versions array, current_version, latest_confirmed_version).
- The `verify_spec_hash()` function exists and is exported — downstream can call it even though the confirmer/modifier don't yet.

**What needs attention:**
- **Env var alignment:** The `PIPELINE_ENV` / `FOREX_PIPELINE_ENV` mismatch should be fixed before Epic 3 to ensure config_hash integrity. The fix is trivial: replace `_load_config_as_dict()` in confirmer.py with a call to `config_loader.loader.load_config()`.
- **Approved-spec helper:** Epic 3's story spec should include a `load_approved_spec()` helper rather than requiring downstream consumers to understand manifest internals. This encapsulates the "read `latest_confirmed_version`, load that file" pattern.
- **spec_hash verification on load:** Should be wired into the load path before any story that assumes loaded specs are untampered. The function exists; it just needs to be called.

## Observations for Future Stories

1. **Fix the env var mismatch in the next story that touches confirmer.py or as a prerequisite for Epic 3.** Replace `_load_config_as_dict()` with `config_loader.loader.load_config()`. This is a 5-line fix that eliminates a class of provenance bugs.

2. **Create `load_approved_spec(slug, artifacts_dir)` in the Epic 3 story spec.** This helper reads the manifest, extracts `latest_confirmed_version`, loads and optionally verifies the spec. Encapsulating this prevents downstream consumers from reimplementing manifest reading.

3. **Wire `verify_spec_hash()` into load paths before any multi-consumer scenario.** The function exists and is tested. The confirmer and modifier load paths should call it. This should be an explicit task in the next story that adds a new spec consumer.

4. **Pattern: when a module needs pipeline config, import the shared loader.** The confirmer's `_load_config_as_dict()` duplicating config_loader logic caused the env var mismatch. Future stories should treat `config_loader.loader.load_config()` as the single entry point for config access.

5. **Lesson validated from Story 2.3 PIR:** That PIR noted "reproducibility proof is not complete until later stories attach config_hash and manifest records." Story 2.5 delivers exactly that — config_hash attached at confirmation, manifest tracking version history. The chain is now complete for the specification layer.

## Verdict

**VERDICT: OBSERVE**

Story 2.5 clearly serves all four system objectives — operator confidence, reproducibility, artifact completeness, and fidelity. The implementation is well-structured, appropriately scoped for V1, and thoroughly tested (144 passed, 0 failures). The env var mismatch and missing spec_hash verification on load are real gaps, but both are bounded in V1's single-operator local scenario, documented in the synthesis report, and trivially fixable.

I disagree with Codex's REVISIT verdict. REVISIT implies "significant concerns about alignment" requiring operator escalation. The concerns raised are valid observations for future stories, not alignment blockers. The story delivers what the PRD requires: an operator can review a human-readable summary, confirm a spec for pipeline use, modify it to create new versions, and rely on a complete artifact trail with hashes and timestamps. The downstream contract (`latest_confirmed_version`) is tested and documented. The three deferred items (env var fix, spec_hash verification, approved-spec helper) are tracked and should be addressed as prerequisites for Epic 3, not as reasons to revisit Story 2.5.
