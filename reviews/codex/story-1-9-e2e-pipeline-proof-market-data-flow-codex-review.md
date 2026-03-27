# Story 1-9-e2e-pipeline-proof-market-data-flow: Story 1.9: E2E Pipeline Proof — Market Data Flow — Codex Review

**Reviewer:** Codex GPT-5.4 (high effort, read-only sandbox)
**Date:** 2026-03-14
**Method:** Static analysis (no pytest execution — sandbox policy)
**Pipeline Stage:** Automated (non-blocking second opinion)

---

**High Findings**
- AC10 is not reliably verifiable because the proof looks for `python_*.log` in [`pipeline_proof.py:778`](C:/Users/ROG/Projects/Forex Pipeline/src/python/data_pipeline/pipeline_proof.py), but the logging system writes `python_{date}.jsonl` in [`setup.py:65`](C:/Users/ROG/Projects/Forex Pipeline/src/python/logging_setup/setup.py). Even if a file is found, missing stages and `ERROR` lines only produce warnings in [`pipeline_proof.py:822`](C:/Users/ROG/Projects/Forex Pipeline/src/python/data_pipeline/pipeline_proof.py) and [`pipeline_proof.py:825`](C:/Users/ROG/Projects/Forex Pipeline/src/python/data_pipeline/pipeline_proof.py), so AC10 can pass with incomplete or bad logs.
- AC9 is not met as written because reproducibility only hashes `.arrow` and `.parquet` files in [`pipeline_proof.py:629`](C:/Users/ROG/Projects/Forex Pipeline/src/python/data_pipeline/pipeline_proof.py) and [`pipeline_proof.py:728`](C:/Users/ROG/Projects/Forex Pipeline/src/python/data_pipeline/pipeline_proof.py). The stage-2 quality report is a required artifact but is written to [`quality_checker.py:752`](C:/Users/ROG/Projects/Forex Pipeline/src/python/data_pipeline/quality_checker.py) and never compared across runs.
- AC8 is not actually verified. Artifact-chain validation only checks for `.partial` files and config-hash equality in [`pipeline_proof.py:610`](C:/Users/ROG/Projects/Forex Pipeline/src/python/data_pipeline/pipeline_proof.py) and [`pipeline_proof.py:619`](C:/Users/ROG/Projects/Forex Pipeline/src/python/data_pipeline/pipeline_proof.py); it never proves every produced file is referenced by the manifest or that the manifest/hash chain covers the artifact set described in [`data_manifest.py:71`](C:/Users/ROG/Projects/Forex Pipeline/src/python/data_pipeline/data_manifest.py) and [`data_manifest.py:72`](C:/Users/ROG/Projects/Forex Pipeline/src/python/data_pipeline/data_manifest.py).
- AC7 can false-pass when split outputs are missing. Verification only runs inside `if train_files and test_files` in [`pipeline_proof.py:556`](C:/Users/ROG/Projects/Forex Pipeline/src/python/data_pipeline/pipeline_proof.py), so absent train/test files do not fail the stage; ratio drift is also downgraded to a warning in [`pipeline_proof.py:571`](C:/Users/ROG/Projects/Forex Pipeline/src/python/data_pipeline/pipeline_proof.py).
- AC1 is only partially enforced because the download stage does not require persisted raw output. `save_raw_artifact()` failures are warnings in [`pipeline_proof.py:252`](C:/Users/ROG/Projects/Forex Pipeline/src/python/data_pipeline/pipeline_proof.py) and [`pipeline_proof.py:260`](C:/Users/ROG/Projects/Forex Pipeline/src/python/data_pipeline/pipeline_proof.py), and the required-column check omits `bid` and `ask` in [`pipeline_proof.py:224`](C:/Users/ROG/Projects/Forex Pipeline/src/python/data_pipeline/pipeline_proof.py).
- AC11 has a correctness bug in multi-dataset directories: several paths pick `glob("*_manifest.json")[-1]` rather than the current dataset’s manifest in [`pipeline_proof.py:575`](C:/Users/ROG/Projects/Forex Pipeline/src/python/data_pipeline/pipeline_proof.py), [`pipeline_proof.py:614`](C:/Users/ROG/Projects/Forex Pipeline/src/python/data_pipeline/pipeline_proof.py), [`pipeline_proof.py:743`](C:/Users/ROG/Projects/Forex Pipeline/src/python/data_pipeline/pipeline_proof.py), and [`pipeline_proof.py:846`](C:/Users/ROG/Projects/Forex Pipeline/src/python/data_pipeline/pipeline_proof.py). `reference_dataset.json` can therefore point at the wrong manifest.

**Medium Findings**
- AC3 verification is shallow. The proof only JSON-loads the report in [`pipeline_proof.py:302`](C:/Users/ROG/Projects/Forex Pipeline/src/python/data_pipeline/pipeline_proof.py) and [`pipeline_proof.py:303`](C:/Users/ROG/Projects/Forex Pipeline/src/python/data_pipeline/pipeline_proof.py); it does not assert required report content even though the report structure is available in [`quality_checker.py:694`](C:/Users/ROG/Projects/Forex Pipeline/src/python/data_pipeline/quality_checker.py), [`quality_checker.py:706`](C:/Users/ROG/Projects/Forex Pipeline/src/python/data_pipeline/quality_checker.py), [`quality_checker.py:715`](C:/Users/ROG/Projects/Forex Pipeline/src/python/data_pipeline/quality_checker.py), and [`quality_checker.py:724`](C:/Users/ROG/Projects/Forex Pipeline/src/python/data_pipeline/quality_checker.py).
- AC4/AC5 checks are looser than the story requires. The proof only checks column names in [`pipeline_proof.py:365`](C:/Users/ROG/Projects/Forex Pipeline/src/python/data_pipeline/pipeline_proof.py) and [`pipeline_proof.py:367`](C:/Users/ROG/Projects/Forex Pipeline/src/python/data_pipeline/pipeline_proof.py), plus non-empty sessions in [`pipeline_proof.py:384`](C:/Users/ROG/Projects/Forex Pipeline/src/python/data_pipeline/pipeline_proof.py); it does not validate exact schema types/compression against the contract, and it hardcodes session values instead of reading the contract that includes `"mixed"` at [`arrow_schemas.toml:11`](C:/Users/ROG/Projects/Forex Pipeline/contracts/arrow_schemas.toml).
- Timeframe-count validation is too weak to catch major aggregation errors. The expected counts are approximate in [`pipeline_proof.py:467`](C:/Users/ROG/Projects/Forex Pipeline/src/python/data_pipeline/pipeline_proof.py), and deviations up to 35% only warn in [`pipeline_proof.py:478`](C:/Users/ROG/Projects/Forex Pipeline/src/python/data_pipeline/pipeline_proof.py).

**Acceptance Criteria Scorecard**

| AC | Status | Notes |
| --- | --- | --- |
| 1 | Partially Met | Download is invoked, but persisted raw artifact and `bid`/`ask` presence are not enforced. |
| 2 | Fully Met | Validation runs, score is captured, and GREEN/YELLOW/RED thresholds are checked. |
| 3 | Partially Met | Report existence is checked, but content/location requirements are not fully verified. |
| 4 | Partially Met | Arrow/Parquet are produced, but exact schema/compression verification is incomplete. |
| 5 | Partially Met | Non-empty sessions and spot checks exist, but correctness is not proven on every bar. |
| 6 | Partially Met | H1 OHLC is sampled once; broader timeframe correctness mostly degrades to warnings. |
| 7 | Partially Met | Temporal boundary is checked when files exist, but missing split outputs do not fail. |
| 8 | Not Met | Manifest linkage, orphan detection, and hash-chain verification are not implemented. |
| 9 | Not Met | Reproducibility ignores non-Arrow/Parquet artifacts such as `quality-report.json`. |
| 10 | Not Met | Log verifier targets the wrong filename and weakly enforces the required schema. |
| 11 | Partially Met | `reference_dataset.json` is written, but manifest selection is not dataset-scoped. |

**Test Coverage Gaps**
- No test actually runs `run_pipeline_proof()` end-to-end with synthetic data. It is imported in [`test_pipeline_proof.py:28`](C:/Users/ROG/Projects/Forex Pipeline/src/python/tests/test_data_pipeline/test_pipeline_proof.py), but the file only exercises isolated stages/helpers such as download, validate, convert, logs, artifacts, and JSON writers in [`test_pipeline_proof.py:298`](C:/Users/ROG/Projects/Forex Pipeline/src/python/tests/test_data_pipeline/test_pipeline_proof.py), [`test_pipeline_proof.py:324`](C:/Users/ROG/Projects/Forex Pipeline/src/python/tests/test_data_pipeline/test_pipeline_proof.py), [`test_pipeline_proof.py:358`](C:/Users/ROG/Projects/Forex Pipeline/src/python/tests/test_data_pipeline/test_pipeline_proof.py), [`test_pipeline_proof.py:403`](C:/Users/ROG/Projects/Forex Pipeline/src/python/tests/test_data_pipeline/test_pipeline_proof.py), and [`test_pipeline_proof.py:542`](C:/Users/ROG/Projects/Forex Pipeline/src/python/tests/test_data_pipeline/test_pipeline_proof.py).
- There are no tests for `_stage_timeframe()` or `_stage_split()` verification behavior, so the missing-file false-pass and loose warning thresholds are untested.
- The log test hardcodes a `.log` filename in [`test_pipeline_proof.py:408`](C:/Users/ROG/Projects/Forex Pipeline/src/python/tests/test_data_pipeline/test_pipeline_proof.py), which matches the bug instead of the real logger output in [`setup.py:65`](C:/Users/ROG/Projects/Forex Pipeline/src/python/logging_setup/setup.py).
- Reproducibility tests only cover the skip path and the “no first-run hashes” failure in [`test_pipeline_proof.py:581`](C:/Users/ROG/Projects/Forex Pipeline/src/python/tests/test_data_pipeline/test_pipeline_proof.py) and [`test_pipeline_proof.py:591`](C:/Users/ROG/Projects/Forex Pipeline/src/python/tests/test_data_pipeline/test_pipeline_proof.py); they do not cover a successful two-run comparison.
- No test covers multiple manifests/datasets in `data-pipeline/`, so the `glob(...)[-1]` manifest-selection bug is unexercised.

**Summary**
1 of 11 criteria are fully met, 7 are partially met, and 3 are not met. The main blockers are AC8, AC9, and AC10, with additional correctness gaps in download persistence, split verification, and manifest selection.
