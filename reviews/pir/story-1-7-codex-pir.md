# Story 1-7: Story 1.7: Timeframe Conversion — Codex PIR

**Reviewer:** Codex GPT-5.4 (high effort, read-only sandbox)
**Date:** 2026-03-14
**Type:** Post-Implementation Review (alignment analysis)

---

**1. Objective Alignment**  
Assessment: `ADEQUATE`

Specific evidence:
- The story directly implements FR6 and supports the platform’s reproducibility/persistence goals in the docs: [prd.md#L99](/c/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/planning-artifacts/prd.md#L99), [prd.md#L466](/c/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/planning-artifacts/prd.md#L466), [prd.md#L551](/c/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/planning-artifacts/prd.md#L551), [architecture.md#L80](/c/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/planning-artifacts/architecture.md#L80), [architecture.md#L334](/c/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/planning-artifacts/architecture.md#L334).
- Determinism is built into the conversion path: quarantined bars are removed first, rows are sorted by timestamp, period starts are computed explicitly, and outputs are schema-validated before write in [timeframe_converter.py#L111](/c/Users/ROG/Projects/Forex%20Pipeline/src/python/data_pipeline/timeframe_converter.py#L111), [timeframe_converter.py#L120](/c/Users/ROG/Projects/Forex%20Pipeline/src/python/data_pipeline/timeframe_converter.py#L120), [timeframe_converter.py#L125](/c/Users/ROG/Projects/Forex%20Pipeline/src/python/data_pipeline/timeframe_converter.py#L125), [timeframe_converter.py#L555](/c/Users/ROG/Projects/Forex%20Pipeline/src/python/data_pipeline/timeframe_converter.py#L555).
- Fidelity is materially improved by preserving bid/ask, recomputing H1 sessions from config, marking D1/W as `mixed`, and excluding quarantined periods in [timeframe_converter.py#L202](/c/Users/ROG/Projects/Forex%20Pipeline/src/python/data_pipeline/timeframe_converter.py#L202), [timeframe_converter.py#L249](/c/Users/ROG/Projects/Forex%20Pipeline/src/python/data_pipeline/timeframe_converter.py#L249), [timeframe_converter.py#L291](/c/Users/ROG/Projects/Forex%20Pipeline/src/python/data_pipeline/timeframe_converter.py#L291), [contracts/arrow_schemas.toml#L1](/c/Users/ROG/Projects/Forex%20Pipeline/contracts/arrow_schemas.toml#L1).
- Crash-safe dual-format output and bit-identical determinism are covered in [timeframe_converter.py#L499](/c/Users/ROG/Projects/Forex%20Pipeline/src/python/data_pipeline/timeframe_converter.py#L499), [timeframe_converter.py#L526](/c/Users/ROG/Projects/Forex%20Pipeline/src/python/data_pipeline/timeframe_converter.py#L526), [test_timeframe_converter.py#L437](/c/Users/ROG/Projects/Forex%20Pipeline/src/python/tests/test_data_pipeline/test_timeframe_converter.py#L437), [test_timeframe_converter.py#L453](/c/Users/ROG/Projects/Forex%20Pipeline/src/python/tests/test_data_pipeline/test_timeframe_converter.py#L453), [test_timeframe_converter.py#L837](/c/Users/ROG/Projects/Forex%20Pipeline/src/python/tests/test_data_pipeline/test_timeframe_converter.py#L837).

Concrete observations:
- This strongly advances `fidelity`. The conversion logic is explicit about what gets aggregated and what gets excluded.
- This advances `reproducibility` mechanically, but not evidentially. The stage is deterministic, but it does not write a stage manifest with source hash/config hash, despite architecture treating that as the reproducibility proof standard [architecture.md#L523](/c/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/planning-artifacts/architecture.md#L523), [architecture.md#L1318](/c/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/planning-artifacts/architecture.md#L1318).
- `Artifact completeness` is only partial. Arrow and Parquet are saved, but there is no saved summary artifact for this stage; by contrast Story 1.6 already writes a manifest with hashes and quality context in [arrow_converter.py#L299](/c/Users/ROG/Projects/Forex%20Pipeline/src/python/data_pipeline/arrow_converter.py#L299), [arrow_converter.py#L351](/c/Users/ROG/Projects/Forex%20Pipeline/src/python/data_pipeline/arrow_converter.py#L351), [arrow_converter.py#L443](/c/Users/ROG/Projects/Forex%20Pipeline/src/python/data_pipeline/arrow_converter.py#L443).
- `Operator confidence` is helped by structured logs with counts and quarantined exclusions [timeframe_converter.py#L778](/c/Users/ROG/Projects/Forex%20Pipeline/src/python/data_pipeline/timeframe_converter.py#L778), but a non-coder still gets raw files plus logs, not a reviewable stage artifact.
- It fits V1 scope. Producing M5/H1/D1/W is exactly FR6 and is explicitly required downstream [1-9-e2e-pipeline-proof-market-data-flow.md#L103](/c/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/implementation-artifacts/1-9-e2e-pipeline-proof-market-data-flow.md#L103). The only mild overreach is generalized `source_timeframe` plus auto tick support.

**2. Simplification**  
Assessment: `ADEQUATE`

Specific evidence:
- The implementation is structurally simple: one module, direct helpers, one orchestration function in [timeframe_converter.py#L83](/c/Users/ROG/Projects/Forex%20Pipeline/src/python/data_pipeline/timeframe_converter.py#L83), [timeframe_converter.py#L376](/c/Users/ROG/Projects/Forex%20Pipeline/src/python/data_pipeline/timeframe_converter.py#L376), [timeframe_converter.py#L620](/c/Users/ROG/Projects/Forex%20Pipeline/src/python/data_pipeline/timeframe_converter.py#L620).
- There is duplication with existing artifact plumbing from Story 1.6 in [timeframe_converter.py#L499](/c/Users/ROG/Projects/Forex%20Pipeline/src/python/data_pipeline/timeframe_converter.py#L499), [timeframe_converter.py#L555](/c/Users/ROG/Projects/Forex%20Pipeline/src/python/data_pipeline/timeframe_converter.py#L555), versus [arrow_converter.py#L213](/c/Users/ROG/Projects/Forex%20Pipeline/src/python/data_pipeline/arrow_converter.py#L213), [arrow_converter.py#L299](/c/Users/ROG/Projects/Forex%20Pipeline/src/python/data_pipeline/arrow_converter.py#L299).
- The config surface is broader than the immediate story need in [schema.toml#L205](/c/Users/ROG/Projects/Forex%20Pipeline/config/schema.toml#L205), [timeframe_converter.py#L726](/c/Users/ROG/Projects/Forex%20Pipeline/src/python/data_pipeline/timeframe_converter.py#L726).

Concrete observations:
- The core aggregation path is not over-engineered. There is no unnecessary abstraction stack.
- The simpler path would be shared artifact machinery, not less conversion logic. Reusing common manifest/hash/write behavior would reduce moving parts and align better with platform standards.
- Allowing `source_timeframe` values beyond `M1` adds configuration surface that V1 does not really need.
- Tick-to-M1 is extra relative to the immediate M1 happy path, but it is small and fidelity-motivated, so I would not count it as harmful overbuild.

**3. Forward Look**  
Assessment: `CONCERN`

Specific evidence:
- Immediate downstream stories want exactly these files and naming conventions: [1-8-data-splitting-consistent-sourcing.md#L13](/c/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/implementation-artifacts/1-8-data-splitting-consistent-sourcing.md#L13), [1-8-data-splitting-consistent-sourcing.md#L135](/c/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/implementation-artifacts/1-8-data-splitting-consistent-sourcing.md#L135), [1-9-e2e-pipeline-proof-market-data-flow.md#L103](/c/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/implementation-artifacts/1-9-e2e-pipeline-proof-market-data-flow.md#L103), [timeframe_converter.py#L755](/c/Users/ROG/Projects/Forex%20Pipeline/src/python/data_pipeline/timeframe_converter.py#L755).
- Story 1.8 has to introduce the real lineage contract itself: dataset hash, config hash, manifest, and multi-timeframe file registry in [1-8-data-splitting-consistent-sourcing.md#L25](/c/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/implementation-artifacts/1-8-data-splitting-consistent-sourcing.md#L25), [1-8-data-splitting-consistent-sourcing.md#L74](/c/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/implementation-artifacts/1-8-data-splitting-consistent-sourcing.md#L74), [data_splitter.py#L381](/c/Users/ROG/Projects/Forex%20Pipeline/src/python/data_pipeline/data_splitter.py#L381), [data_splitter.py#L509](/c/Users/ROG/Projects/Forex%20Pipeline/src/python/data_pipeline/data_splitter.py#L509).
- Story 1.7 filenames omit source identity, and reruns skip on existence alone in [timeframe_converter.py#L599](/c/Users/ROG/Projects/Forex%20Pipeline/src/python/data_pipeline/timeframe_converter.py#L599), [timeframe_converter.py#L721](/c/Users/ROG/Projects/Forex%20Pipeline/src/python/data_pipeline/timeframe_converter.py#L721), [timeframe_converter.py#L761](/c/Users/ROG/Projects/Forex%20Pipeline/src/python/data_pipeline/timeframe_converter.py#L761).

Concrete observations:
- The filesystem contract is good enough for the next story. Story 1.8 can find and split M1/M5/H1/D1/W without translation.
- The missing piece is lineage. This stage assumes `pair + date range + timeframe` uniquely identify converted artifacts. That will not hold once source files are refreshed or corrected without changing dates.
- Because existence alone can cause reuse, downstream stories can inherit stale timeframe artifacts while believing they are current. That works against reproducibility and operator confidence.
- If tick input becomes real rather than optional, the intermediate derived M1 bars are not persisted; the pipeline loses a reviewable bridge artifact on that path [timeframe_converter.py#L689](/c/Users/ROG/Projects/Forex%20Pipeline/src/python/data_pipeline/timeframe_converter.py#L689), [timeframe_converter.py#L695](/c/Users/ROG/Projects/Forex%20Pipeline/src/python/data_pipeline/timeframe_converter.py#L695).

**Overall**  
`REVISIT`

Functionally, the story improves fidelity and gives the next stages the data shapes they need. The reason for `REVISIT` is stage-level lineage and evidence: Story 1.7 does not yet meet the platform’s own bar for self-describing, reviewable, versioned artifacts, and that gap sits directly on the core objectives rather than on code quality.
