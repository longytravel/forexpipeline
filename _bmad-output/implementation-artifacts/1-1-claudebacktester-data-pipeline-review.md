# Story 1.1: ClaudeBackTester Data Pipeline Review

Status: done

## Story

As the **operator**,
I want the system's data pipeline design validated against ClaudeBackTester's actual implementation,
So that I know which components to keep, adapt, or replace before writing any code.

## Acceptance Criteria

1. **Given** the ClaudeBackTester codebase is accessible
   **When** the data pipeline modules are reviewed (acquisition, validation, splitting, timeframe conversion, storage)
   **Then** a component verdict table is produced with keep/adapt/replace per component, with rationale

2. **And** any capabilities found in baseline that are missing from our PRD/Architecture are documented

3. **And** any baseline patterns that are better than our planned approach are flagged with a recommendation to adopt

4. **And** any baseline weaknesses or technical debt that should not be carried forward are documented

5. **And** the Architecture document is updated if findings warrant changes

## Tasks / Subtasks

This is a **research story** — the deliverable is a research artifact document, not code.

- [x] Task 1: Locate and inventory ClaudeBackTester data pipeline modules (AC: #1)
  - [x] 1.1: Identify the ClaudeBackTester project root directory (expected: a sibling project or documented path)
  - [x] 1.2: Inventory all files related to data acquisition (Dukascopy download logic — look for `dukascopy`, `download`, `fetch`, `acquire` in filenames and code)
  - [x] 1.3: Inventory all files related to data validation (gap detection, price integrity, timezone checks — look for `validate`, `quality`, `check`, `gap`)
  - [x] 1.4: Inventory all files related to data splitting (train/test chronological split — look for `split`, `partition`)
  - [x] 1.5: Inventory all files related to timeframe conversion (M1 to H1/D1/W — look for `timeframe`, `resample`, `aggregate`, `convert`)
  - [x] 1.6: Inventory all files related to data storage (Parquet, Arrow, CSV — look for `parquet`, `arrow`, `storage`, `persist`)
  - [x] 1.7: Document the file list with brief description of each module's purpose

- [x] Task 2: Deep-read each data pipeline module and document behavior (AC: #1, #2, #3, #4)
  - [x] 2.1: **Acquisition module** — document: download source (Dukascopy API endpoint/method), data format received, rate limiting, error handling, incremental update support, progress reporting, timeout handling
  - [x] 2.2: **Validation module** — document: which checks are implemented (gap detection thresholds, price integrity rules, timezone validation, stale quote detection, completeness checks), quality scoring formula if any, quarantine behavior if any
  - [x] 2.3: **Splitting module** — document: split method (chronological?), configurable split point, data leakage prevention, how split datasets are identified/versioned
  - [x] 2.4: **Timeframe conversion module** — document: aggregation logic (OHLC from M1 bars), which timeframes supported, handling of session boundaries, handling of quarantined/missing bars, bid/ask aggregation approach
  - [x] 2.5: **Storage module** — document: file format(s) used (Parquet? CSV? Arrow?), compression, schema definition approach, crash-safe write patterns if any, versioning scheme
  - [x] 2.6: For each module, note the libraries and versions used (e.g., `pandas`, `pyarrow`, `requests`, `polars`)

- [x] Task 3: Produce the component verdict table (AC: #1)
  - [x] 3.1: For each component (acquisition, validation, splitting, timeframe conversion, storage), produce a row with:
    - Component name
    - Baseline status (what exists, how mature)
    - Verdict: **keep** (use as-is), **adapt** (modify to fit new architecture), or **replace** (build new)
    - Rationale for the verdict
    - Effort estimate (low/medium/high) for the required work
  - [x] 3.2: For "adapt" verdicts, specify what needs to change (e.g., "add quality scoring", "switch from CSV to Arrow IPC", "add crash-safe writes")
  - [x] 3.3: For "replace" verdicts, specify why the baseline isn't salvageable and what the new implementation needs

- [x] Task 4: Document undiscovered capabilities (AC: #2)
  - [x] 4.1: List any data pipeline capabilities found in ClaudeBackTester that are NOT mentioned in the PRD (FR1-FR8) or Architecture
  - [x] 4.2: For each, assess: should this be added to the Forex Pipeline architecture? If yes, where does it fit?
  - [x] 4.3: Examples to look for: tick data handling, multi-pair batch download, data caching strategies, download resume after interruption, data format migration tooling

- [x] Task 5: Document superior baseline patterns (AC: #3)
  - [x] 5.1: Identify any patterns in the baseline that are better than what the Architecture specifies
  - [x] 5.2: For each, document: what the baseline does, what the Architecture specifies, why the baseline approach is better, and a recommendation
  - [x] 5.3: Pay special attention to: error handling patterns, data format choices, configuration approaches, logging patterns, directory organization

- [x] Task 6: Document baseline weaknesses and technical debt (AC: #4)
  - [x] 6.1: Identify code quality issues (no error handling, silent failures, hardcoded values, no tests)
  - [x] 6.2: Identify architectural issues (tight coupling, missing abstractions, non-deterministic behavior)
  - [x] 6.3: Identify operational issues (poor logging, no progress reporting, no crash recovery)
  - [x] 6.4: For each weakness, note: "DO NOT carry forward" with explanation of what the new system should do instead

- [x] Task 7: Architecture update assessment (AC: #5)
  - [x] 7.1: Based on findings from Tasks 4-6, determine if the Architecture document (`_bmad-output/planning-artifacts/architecture.md`) needs updates
  - [x] 7.2: If updates are warranted, produce a specific list of proposed changes with section references (e.g., "Update Data Quality Gate Specifications section to add X check found in baseline")
  - [x] 7.3: Do NOT modify the Architecture document directly — produce the proposed changes as a section in the research artifact for operator review

- [x] Task 8: Write the research artifact (AC: all)
  - [x] 8.1: Save the complete research artifact to `_bmad-output/planning-artifacts/research/data-pipeline-baseline-review.md`
  - [x] 8.2: Structure the artifact with these sections:
    1. Executive Summary (1-2 paragraphs)
    2. Module Inventory (file list with descriptions)
    3. Component Verdict Table
    4. Detailed Component Analysis (one subsection per component)
    5. Undiscovered Capabilities
    6. Superior Baseline Patterns
    7. Weaknesses and Technical Debt
    8. Proposed Architecture Updates
    9. Impact on Stories 1.3-1.9 (which stories are porting baseline code vs building new)

## Dev Notes

### Architecture Constraints

The following architecture decisions define what "good" looks like for the data pipeline — the review must assess the baseline against these standards:

- **D2 (Artifact Schema & Storage):** "Three-format storage strategy — Arrow IPC (compute), SQLite (query), Parquet (archival)." The baseline likely uses CSV or Parquet only. The review must assess how much work is needed to add Arrow IPC conversion with mmap-friendly output. [Source: architecture.md, Decision 2]

- **D6 (Logging):** "Each runtime writes structured JSON log lines to logs/, one file per runtime per day." Review whether baseline has structured logging or ad-hoc print statements. [Source: architecture.md, Decision 6]

- **D7 (Configuration):** "Layered TOML configs validated at startup. Environment variables for secrets only." Review whether baseline config is hardcoded, uses .env, uses JSON, etc. [Source: architecture.md, Decision 7]

- **D8 (Error Handling):** "Each runtime catches errors at component boundaries, wraps in structured error type, propagates to orchestrator." Review whether baseline swallows errors silently. [Source: architecture.md, Decision 8]

- **Data Quality Gate Specifications:** The Architecture defines specific quality checks (gap detection > 5 consecutive M1 bars, price integrity bid > 0 / ask > bid, timezone UTC verification, stale quote detection), a quality scoring formula (`1.0 - (gap_penalty + integrity_penalty + staleness_penalty)`), and quarantine behavior. The review must assess which of these the baseline already implements. [Source: architecture.md, Data Quality Gate Specifications section]

- **Crash-Safe Write Pattern:** "Write to {filename}.partial → flush/fsync → atomic rename to {filename}." Review whether baseline has any crash safety. [Source: architecture.md, Process Patterns section]

- **Consistent Data Sourcing (FR8):** "Every dataset identified by {pair}_{start_date}_{end_date}_{source}_{download_hash}." Review whether baseline has any data versioning/hashing. [Source: architecture.md, Data Quality Gate Specifications]

### Technical Requirements

- The research artifact must be Markdown format
- Output path: `_bmad-output/planning-artifacts/research/data-pipeline-baseline-review.md`
- The ClaudeBackTester codebase location must be discovered (check `C:\Users\ROG\Projects\ClaudeBackTester` or similar)
- If the ClaudeBackTester codebase is not accessible, document this as a blocker and produce the artifact based on the gap assessment document instead

### What to Reuse from ClaudeBackTester

From the baseline-to-architecture mapping:

| Component | Mapping Direction | Notes |
|---|---|---|
| `data_pipeline/` (acquisition, quality, Arrow conversion) | **Keep and adapt** | "Documented as mature. Add quality scoring/quarantine (new). Core download/validation reusable" |
| `config_loader/` | **Build new** | "Config exists but not schema-validated" |
| `logging_setup/` | **Adapt** | "Logging exists. Switch to structured JSON, per-runtime files" |

[Source: baseline-to-architecture-mapping.md, Orchestration Tier table]

The gap assessment states data pipeline is "Mature — acquisition, validation, splitting, timeframe conversion." This story validates that claim by reading the actual code.

### Anti-Patterns to Avoid

1. **DO NOT skim the code** — read every data pipeline module thoroughly. The gap assessment says "mature" but that needs verification against the Architecture's specific requirements.
2. **DO NOT assume the baseline is correct** — it may have bugs, silent failures, or incorrect logic that was never caught because there were no tests.
3. **DO NOT modify any ClaudeBackTester code** — this is a read-only review.
4. **DO NOT modify the Architecture document directly** — proposed changes go in the research artifact for operator review.
5. **DO NOT write any Forex Pipeline code** — this story produces a research artifact only.
6. **DO NOT skip the "Impact on Stories 1.3-1.9" section** — downstream stories depend on this verdict to know whether they're porting code or building new.

### Project Structure Notes

- Research artifact output: `C:\Users\ROG\Projects\Forex Pipeline\_bmad-output\planning-artifacts\research\data-pipeline-baseline-review.md`
- Ensure the `research/` subdirectory exists before writing
- The Architecture's Phase 0 research process (architecture.md) specifies research artifacts go to `_bmad-output/planning-artifacts/research/`

### References

- [Source: planning-artifacts/epics.md#Story 1.1 — lines 451-465]
- [Source: planning-artifacts/architecture.md#Data Quality Gate Specifications — lines 224-260]
- [Source: planning-artifacts/architecture.md#Decision 2 — lines 332-388]
- [Source: planning-artifacts/architecture.md#Decision 6 — lines 473-497]
- [Source: planning-artifacts/architecture.md#Decision 7 — lines 499-526]
- [Source: planning-artifacts/architecture.md#Decision 8 — lines 528-565]
- [Source: planning-artifacts/architecture.md#Crash-Safe Write Pattern — lines 1258-1265]
- [Source: planning-artifacts/architecture.md#Contracts Directory Content — lines 1367-1477]
- [Source: planning-artifacts/baseline-to-architecture-mapping.md — Orchestration Tier table, lines 52-66]
- [Source: planning-artifacts/prd.md#FR1-FR8 — lines 461-468]
- [Source: planning-artifacts/prd.md#Market Data Integrity — lines 217-222]
- [Source: planning-artifacts/prd.md#MVP Strategy — lines 352-360]

## Dev Agent Record

### Agent Model Used
Claude Opus 4.6 (1M context)

### Completion Notes List
- Reviewed all 5 data pipeline modules in `ClaudeBackTester/backtester/data/` (downloader.py, validation.py, splitting.py, timeframes.py, __init__.py)
- Also reviewed: tests/test_data.py, scripts/download_all.py, pipeline/checkpoint.py, core/dtypes.py, pyproject.toml
- Inspected the `dukascopy-python` library source to understand download mechanism (REST API via freeserv.dukascopy.com, NOT raw bi5 binary)
- All 5 components assessed as "Adapt" — core logic is reusable but every module needs Architecture compliance wrapping
- No component can be used as-is (no "Keep" verdicts)
- Key finding: baseline uses `dukascopy-python` library (REST API) not raw bi5 — Story 1.4 approach should be reconsidered
- Key finding: baseline quality scoring (0-100 point deduction) is fundamentally different from Architecture's formula (1.0 - penalties) — cannot reuse scoring logic
- 3 proposed Architecture updates documented for operator review
- 6 undiscovered capabilities identified, 4 recommended for adoption
- 11 weaknesses/technical debt items documented as "DO NOT carry forward"
- Impact assessment produced for all Stories 1.3-1.9

### Change Log
- 2026-03-14: Story completed. Research artifact written to `_bmad-output/planning-artifacts/research/data-pipeline-baseline-review.md`

### File List
- `_bmad-output/planning-artifacts/research/data-pipeline-baseline-review.md` (NEW — research artifact, 350+ lines)
