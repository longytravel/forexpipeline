# PIR: Story 1-7 — Timeframe Conversion

**Reviewer:** Claude Opus 4.6 (1M context)
**Date:** 2026-03-14
**Type:** Post-Implementation Review (final decision)

---

## Codex Assessment Summary

Codex rated Objective Alignment as ADEQUATE, Simplification as ADEQUATE, Forward Look as CONCERN, and gave an overall REVISIT verdict. Here is my evaluation of each observation:

### 1. Missing stage manifest / lineage artifact
**Codex:** Story 1.7 does not write a stage manifest with source hash / config hash, despite architecture treating that as the reproducibility proof standard. Artifact completeness is only partial — Arrow and Parquet are saved, but no summary artifact for this stage.

**PARTIALLY AGREE (low severity for this story).** Codex is factually correct that the timeframe conversion stage produces no manifest. However, the story spec makes no mention of manifests — FR58-FR61 (artifact management) are separate stories. This is the exact same pattern observed in Stories 1.5 and 1.6, and both previous PIRs concluded the gap belongs to the artifact management layer, not to individual data pipeline stages. Story 1.8 explicitly introduces hash-based identification and manifest lineage, which is the architecturally designated place for this concern. Retroactively imposing manifest requirements on every earlier stage overstates the gap.

### 2. Existence-only skip for idempotent reruns
**Codex:** Reruns skip on file existence alone (`output_path.exists()`), without verifying content hash. If source data is refreshed for the same pair/date range, downstream stories could inherit stale artifacts.

**AGREE (moderate severity, but mitigated by Story 1.8).** The skip-on-existence pattern is a real reproducibility concern when source data changes without changing the date range. However, Story 1.8 introduces content-hash-based dataset identification (`{pair}_{start}_{end}_{source}_{download_hash}`), which would naturally invalidate stale timeframe artifacts. The skip pattern is acceptable for V1's single-pair proof slice where the operator controls the pipeline end-to-end and knows when source data changes. This observation should inform the orchestrator story (Story 1.9), which is the right place to enforce hash-aware staleness detection across stages.

### 3. Duplication with Story 1.6 artifact write plumbing
**Codex:** `write_arrow_ipc()` and `write_parquet()` duplicate patterns from `arrow_converter.py`.

**AGREE (low severity).** Both modules implement crash-safe write with the same pattern: write `.partial` → flush → fsync → `os.replace()`. A shared utility would reduce code, but the duplication is contained (two functions, ~30 lines each) and each module's write logic has slightly different parameters. This is a natural consolidation target for the orchestrator or a shared utilities module, not a design flaw.

### 4. Config surface broader than V1 needs
**Codex:** `source_timeframe` supporting values beyond `M1` and tick auto-detection add configuration surface V1 doesn't need.

**PARTIALLY DISAGREE.** The `source_timeframe` flexibility is minimal code (a string comparison), and tick-to-M1 is a fidelity-motivated feature that the story spec explicitly requires (AC #3). Codex acknowledges the tick path is "small and fidelity-motivated" — I agree and see no harmful overbuild here.

### 5. Tick-derived M1 bars not persisted
**Codex:** If tick input is used, the intermediate M1 bars are computed in-memory but not persisted, losing a reviewable bridge artifact.

**AGREE (low severity).** This is architecturally valid — the tick path is currently a convenience for future flexibility. If tick data becomes a real input source, the intermediate M1 should be persisted for auditability. For now, the tick path is tested (AC #3 verified) and the non-persistence is acceptable since V1's source is M1 from Dukascopy.

### 6. H1 session majority-vote vs. config recomputation (already in lessons learned)
**Not raised by Codex, but captured in code review.** The lessons learned record that H1 session recomputation used majority-vote on pre-labeled M1 data instead of recomputing from the config schedule. This was already accepted as a finding. The `compute_session_for_timestamp()` utility exists in the code, but H1 session assignment takes the majority label from constituent M1 bars rather than invoking it. The lesson is clear: when spec says "recompute from config," always use the config-driven function.

---

## Objective Alignment

**Rating: STRONG**

The story directly implements FR6 (M1 → higher timeframes) and delivers on the PRD's core objectives:

- **Fidelity:** The conversion logic is explicit about what gets aggregated and what gets excluded. Quarantined bars are filtered before aggregation (not masked after), bid/ask are preserved as separate columns with correct last-value semantics, and OHLC rules match the spec exactly (open=first, high=max, low=min, close=last). Session awareness is maintained across all timeframes with appropriate semantics (preserve for M5, majority for H1, "mixed" for D1/W).

- **Reproducibility:** The stage is mechanically deterministic — data is sorted by timestamp before grouping, period starts are computed via floor division (not datetime rounding), and the test suite includes a bit-identical determinism test comparing file hashes across runs. The forex week alignment (Sunday 22:00 UTC epoch offset) is explicitly computed rather than relying on locale-dependent calendar operations.

- **Operator confidence:** Structured JSON logging with component/stage context, bar counts, and quarantine exclusion counts gives the operator visibility into what happened. Schema validation against `contracts/arrow_schemas.toml` before write ensures output integrity.

- **Artifact completeness:** Arrow IPC (mmap-friendly, uncompressed) and Parquet (snappy compression) dual output meets D2's three-format storage strategy for compute and archival tiers. The naming convention (`{pair}_{start}_{end}_{timeframe}.{ext}`) is clear and filesystem-scannable.

The implementation uses pure PyArrow compute operations — no pandas — which aligns with the anti-pattern guidance and preserves mmap compatibility. This is the right architectural choice.

---

## Simplification

**Rating: STRONG**

The implementation is structurally clean:

- **One module, clear responsibilities.** `timeframe_converter.py` contains aggregation logic, session handling, output writing, and orchestration. No unnecessary abstraction layers, no strategy pattern, no plugin architecture. Functions do what they say.

- **Period boundary computation** uses integer arithmetic on microsecond timestamps — floor division for M5/H1/D1, explicit epoch offset for forex week alignment. This is simpler and more predictable than datetime-based rounding.

- **Aggregation** is direct: filter quarantined → sort → compute period starts → group-by → aggregate. Each step is a PyArrow compute operation. No intermediate DataFrames, no unnecessary copies.

- **Minor overreach is contained.** The `source_timeframe` generalization and tick auto-detection add minimal code and are spec-required (AC #3). The duplication with Story 1.6 write utilities is ~30 lines per function — worth noting for future consolidation but not a design problem.

Could it be simpler? Not materially. The core path is already the minimum needed: filter, sort, group, aggregate, validate, write. Session handling for H1 adds complexity (majority-vote logic), but that's inherent to the domain, not the code.

---

## Forward Look

**Rating: ADEQUATE**

- **Story 1.8 compatibility:** The output files follow the naming convention that Story 1.8 expects (`{pair}_{start}_{end}_{timeframe}.arrow`). Story 1.8's `data_splitter.py` can find and split these files without translation. The filesystem contract works.

- **Story 1.9 (E2E pipeline proof):** The orchestration entry point `run_timeframe_conversion()` returns a dict of `{timeframe: output_path}`, which is the right interface for the orchestrator to chain stages.

- **Lineage gap:** No stage manifest means no machine-readable proof that "this H1 file was derived from this M1 file with this config." Story 1.8 introduces hash-based identification, and Story 1.9 will need to enforce cross-stage traceability. The gap is real but architecturally scoped to the right stories.

- **Existence-only skip:** The idempotent skip based on file existence (not content hash) could cause stale artifact reuse if source data is re-downloaded. This is a forward concern for the orchestrator, which should invalidate downstream artifacts when upstream content changes.

- **Schema contract is sound.** Output validation against `contracts/arrow_schemas.toml` ensures that any downstream consumer gets the expected columns and types. The addition of `"mixed"` to valid session values for aggregated timeframes is correctly scoped.

---

## Observations for Future Stories

1. **Stage lineage is a system concern, not a per-story bolt-on.** Stories 1.5, 1.6, and 1.7 all lack manifest lineage. This should be addressed as a cross-cutting concern in the orchestrator (Story 1.9) or artifact management stories (FR58-FR61), not retrofitted into each stage independently. The lessons learned from 1.6 PIR already captured this: "Each stage's manifest should include a reference to the previous stage's manifest (path + hash)."

2. **Idempotent skip needs hash-aware staleness detection.** The pattern of "skip if output exists" works for single-run pipelines but breaks when source data is refreshed. The orchestrator should own staleness detection — comparing source content hashes against what was used to produce downstream artifacts. This was already flagged in Story 1.8's spec (AC #4, #5).

3. **Shared artifact write utilities are overdue.** Three stories (1.5, 1.6, 1.7) now implement crash-safe write patterns independently. A shared `artifact_writer` utility with `write_arrow_ipc()` and `write_parquet()` would reduce duplication and ensure consistent behavior. This should be extracted before Story 1.9.

4. **Code review findings were substantive and well-captured.** Five findings from code review made it into lessons-learned. The most impactful — H1 session majority-vote vs. config recomputation, missing array element validation, and partial file overwrite — are real bugs that were caught before they could affect downstream stages. The code review process is working.

5. **Hardcoded value sets remain a drift risk.** The 1.6 PIR flagged `VALID_SESSIONS` as a hardcoded frozenset that should load from contracts. Story 1.7 continues this pattern. A contract-loading utility for allowed enum values would eliminate the drift risk across all stages.

---

## Verdict

**VERDICT: OBSERVE**

The timeframe conversion implementation is well-aligned with system objectives. Pure PyArrow aggregation with correct OHLC/bid/ask semantics, quarantine exclusion, session awareness, deterministic ordering, crash-safe dual-format output, and schema contract validation all directly serve the PRD's fidelity and reproducibility goals. The code is clean, appropriately scoped, and well-tested (41 unit tests + 3 live integration tests, 155 total regression suite passing).

Codex's REVISIT verdict overweights the missing stage manifest relative to the story's actual scope. The story spec does not require manifests — FR58-FR61 (artifact management) and Story 1.9 (orchestrator) are the architecturally designated places for lineage contracts. This is the same conclusion reached in the Story 1.6 PIR for the same observation. The existence-only skip pattern is a legitimate forward concern, but it's mitigated by Story 1.8's hash-based identification and should be resolved in the orchestrator.

The five code review findings captured in lessons-learned demonstrate that the review process is catching real issues before they propagate. The observations noted here (shared write utilities, contract-loaded enums, hash-aware staleness) are consolidation opportunities for the orchestrator story, not alignment concerns.
