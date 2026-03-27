# Story 1-8: Story 1.8: Data Splitting & Consistent Sourcing — Codex PIR

**Reviewer:** Codex GPT-5.4 (high effort, read-only sandbox)
**Date:** 2026-03-14
**Type:** Post-Implementation Review (alignment analysis)

---

**1. Objective Alignment**

Assessment: `CONCERN`

Specific evidence:
- The story clearly advances reproducibility and artifact completeness. It enforces chronological splitting and a hard temporal guard in [`data_splitter.py#L104`](/C:/Users/ROG/Projects/Forex Pipeline/src/python/data_pipeline/data_splitter.py#L104), [`data_splitter.py#L197`](/C:/Users/ROG/Projects/Forex Pipeline/src/python/data_pipeline/data_splitter.py#L197), reuses the M1 split boundary across timeframes in [`data_splitter.py#L419`](/C:/Users/ROG/Projects/Forex Pipeline/src/python/data_pipeline/data_splitter.py#L419) and [`data_splitter.py#L453`](/C:/Users/ROG/Projects/Forex Pipeline/src/python/data_pipeline/data_splitter.py#L453), and persists dataset/data/config identity in the manifest in [`data_manifest.py#L51`](/C:/Users/ROG/Projects/Forex Pipeline/src/python/data_pipeline/data_manifest.py#L51) and [`data_manifest.py#L58`](/C:/Users/ROG/Projects/Forex Pipeline/src/python/data_pipeline/data_manifest.py#L58). Crash-safe writes are present in [`storage.py#L10`](/C:/Users/ROG/Projects/Forex Pipeline/src/python/artifacts/storage.py#L10) and [`data_manifest.py#L78`](/C:/Users/ROG/Projects/Forex Pipeline/src/python/data_pipeline/data_manifest.py#L78).
- The biggest misalignment is that reuse is keyed only by `dataset_id`, not by `config_hash`. `compute_dataset_id()` excludes config in [`dataset_hasher.py#L20`](/C:/Users/ROG/Projects/Forex Pipeline/src/python/data_pipeline/dataset_hasher.py#L20), and `run_data_splitting()` returns an existing manifest immediately in [`data_splitter.py#L409`](/C:/Users/ROG/Projects/Forex Pipeline/src/python/data_pipeline/data_splitter.py#L409) and [`data_splitter.py#L417`](/C:/Users/ROG/Projects/Forex Pipeline/src/python/data_pipeline/data_splitter.py#L417). That conflicts with the system invariant that same dataset + same config = same output in [`architecture.md#L1310`](/C:/Users/ROG/Projects/Forex Pipeline/_bmad-output/planning-artifacts/architecture.md#L1310) and with the PRD’s “no implicit drift” requirement in [`prd.md#L191`](/C:/Users/ROG/Projects/Forex Pipeline/_bmad-output/planning-artifacts/prd.md#L191) and [`prd.md#L551`](/C:/Users/ROG/Projects/Forex Pipeline/_bmad-output/planning-artifacts/prd.md#L551).
- Operator confidence is only partially served. The stage emits a manifest and structured logs in [`data_splitter.py#L394`](/C:/Users/ROG/Projects/Forex Pipeline/src/python/data_pipeline/data_splitter.py#L394), [`data_splitter.py#L424`](/C:/Users/ROG/Projects/Forex Pipeline/src/python/data_pipeline/data_splitter.py#L424), and [`data_splitter.py#L525`](/C:/Users/ROG/Projects/Forex Pipeline/src/python/data_pipeline/data_splitter.py#L525), but not an operator-ready evidence summary. Also, config validation is weaker than advertised: `schema.toml` declares `split_date` semantics in [`schema.toml#L224`](/C:/Users/ROG/Projects/Forex Pipeline/config/schema.toml#L224), but the validator only supports required/type/allowed/min/max in [`validator.py#L63`](/C:/Users/ROG/Projects/Forex Pipeline/src/python/config_loader/validator.py#L63) and [`validator.py#L99`](/C:/Users/ROG/Projects/Forex Pipeline/src/python/config_loader/validator.py#L99), so bad date-mode config is caught only at runtime in [`data_splitter.py#L96`](/C:/Users/ROG/Projects/Forex Pipeline/src/python/data_pipeline/data_splitter.py#L96).

Concrete observations:
- This story strongly supports reproducibility, artifact persistence, and temporal fidelity.
- It works against reproducibility if split config changes, because stale split artifacts can be silently reused.
- It fits V1 scope. Multi-timeframe splits and dual Arrow/Parquet outputs are justified by the architecture and by the next proof stage, not obvious over-engineering.

**2. Simplification**

Assessment: `ADEQUATE`

Specific evidence:
- The core implementation is not abstraction-heavy: split logic, dataset identity, and manifest writing are separated cleanly in [`data_splitter.py#L53`](/C:/Users/ROG/Projects/Forex Pipeline/src/python/data_pipeline/data_splitter.py#L53), [`dataset_hasher.py#L20`](/C:/Users/ROG/Projects/Forex Pipeline/src/python/data_pipeline/dataset_hasher.py#L20), and [`data_manifest.py#L22`](/C:/Users/ROG/Projects/Forex Pipeline/src/python/data_pipeline/data_manifest.py#L22).
- The unnecessary complexity is in idempotency. There is manifest-level reuse in [`data_splitter.py#L409`](/C:/Users/ROG/Projects/Forex Pipeline/src/python/data_pipeline/data_splitter.py#L409) plus file-level overwrite checks in [`data_splitter.py#L470`](/C:/Users/ROG/Projects/Forex Pipeline/src/python/data_pipeline/data_splitter.py#L470), but those checks are called without expected hashes, so they do not validate content and just skip existing files per [`dataset_hasher.py#L119`](/C:/Users/ROG/Projects/Forex Pipeline/src/python/data_pipeline/dataset_hasher.py#L119).
- A simpler and safer design would be: reuse only when both `dataset_id` and `config_hash` match, or make split artifacts derive from a split-specific ID. That would remove the current overlap between “manifest cache” and “never overwrite” logic.

Concrete observations:
- I do not see broad over-engineering.
- The main simplification opportunity is not “less functionality”; it is “one correct identity rule instead of two partial ones.”
- `split_mode="date"` is not gratuitous. The story explicitly asked for it.

**3. Forward Look**

Assessment: `CONCERN`

Specific evidence:
- The output contract is thinner than the next story wants. Story 1.9 expects per-file hash-chain verification from the manifest in [`1-9-e2e-pipeline-proof-market-data-flow.md#L140`](/C:/Users/ROG/Projects/Forex Pipeline/_bmad-output/implementation-artifacts/1-9-e2e-pipeline-proof-market-data-flow.md#L140), but Story 1.8’s manifest stores only the source `data_hash`, `config_hash`, and filenames in [`data_manifest.py#L57`](/C:/Users/ROG/Projects/Forex Pipeline/src/python/data_pipeline/data_manifest.py#L57) and [`data_manifest.py#L71`](/C:/Users/ROG/Projects/Forex Pipeline/src/python/data_pipeline/data_manifest.py#L71). The current proof code has to compensate by hashing files directly in [`pipeline_proof.py#L626`](/C:/Users/ROG/Projects/Forex Pipeline/src/python/data_pipeline/pipeline_proof.py#L626) and [`pipeline_proof.py#L727`](/C:/Users/ROG/Projects/Forex Pipeline/src/python/data_pipeline/pipeline_proof.py#L727).
- Date-mode attribution is not fully preserved. `split_train_test()` captures `configured_split_date` in [`data_splitter.py#L119`](/C:/Users/ROG/Projects/Forex Pipeline/src/python/data_pipeline/data_splitter.py#L119), but `create_data_manifest()` drops it in [`data_manifest.py#L62`](/C:/Users/ROG/Projects/Forex Pipeline/src/python/data_pipeline/data_manifest.py#L62). That weakens future auditability.
- Two promised guarantees are missing for downstream consumers: minimum non-trivial split sizes and schema validation before writing. The story spec calls them out in [`1-8-data-splitting-consistent-sourcing.md#L217`](/C:/Users/ROG/Projects/Forex Pipeline/_bmad-output/implementation-artifacts/1-8-data-splitting-consistent-sourcing.md#L217) and [`1-8-data-splitting-consistent-sourcing.md#L236`](/C:/Users/ROG/Projects/Forex Pipeline/_bmad-output/implementation-artifacts/1-8-data-splitting-consistent-sourcing.md#L236), but the code only rejects empty partitions in [`data_splitter.py#L147`](/C:/Users/ROG/Projects/Forex Pipeline/src/python/data_pipeline/data_splitter.py#L147) and [`data_splitter.py#L184`](/C:/Users/ROG/Projects/Forex Pipeline/src/python/data_pipeline/data_splitter.py#L184), and then writes directly in [`data_splitter.py#L447`](/C:/Users/ROG/Projects/Forex Pipeline/src/python/data_pipeline/data_splitter.py#L447).

Concrete observations:
- The biggest baked-in assumption is that one dataset implies one valid split artifact set. That will not hold once split policies vary.
- The filename parser is deliberately V1/FX-specific in [`data_splitter.py#L220`](/C:/Users/ROG/Projects/Forex Pipeline/src/python/data_pipeline/data_splitter.py#L220). That is fine for now, but it is a scope assumption, not a durable contract.
- Downstream stories can use this output, but they already need workarounds.

**OVERALL**

`REVISIT`

The story is directionally aligned and adds real value, but the config-blind reuse path is a significant conflict with the system’s primary objective: deterministic, explainable reproducibility without implicit drift.
