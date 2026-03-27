# Story 1.2: External Data Quality & Acquisition Research

Status: done

## Story

As the **operator**,
I want data quality scoring and acquisition best practices researched,
So that the data pipeline uses proven approaches rather than guesses.

## Acceptance Criteria

1. **Given** Story 1.1's verdict table identifies what needs research
   **When** external research is conducted on data quality scoring, quarantine patterns, and Dukascopy-specific handling
   **Then** a research artifact is produced covering: quality scoring methodologies, quarantine best practices, gap handling approaches, and Dukascopy API/data format specifics

2. **And** recommendations are compared against our Architecture's data quality gate specifications (D2, quality scoring formula)

3. **And** the Architecture document is updated if research shows a better approach

4. **And** a final build plan for Stories 1.3-1.9 is confirmed — each story knows whether it's porting baseline code or building new

## Tasks / Subtasks

This is a **research story** — the deliverable is a research artifact document, not code. This story depends on Story 1.1's verdict table but can begin independent research in parallel on topics that do not depend on the verdict.

- [x] Task 1: Research data quality scoring methodologies for financial time series (AC: #1, #2)
  - [x] 1.1: Research established quality scoring frameworks for M1 forex data — what do quant shops and data vendors use?
  - [x] 1.2: Research gap detection best practices — what gap thresholds are standard for M1 forex data? How do professionals handle expected gaps (weekends, holidays) vs unexpected gaps?
  - [x] 1.3: Research price integrity validation — beyond bid > 0 / ask > bid, what checks do professionals apply? (e.g., price deviation from rolling median, abnormal spread detection during news events, flash crash filtering)
  - [x] 1.4: Research stale quote detection methods — what constitutes "stale" in M1 data? Are there session-specific thresholds (Asian session may have naturally wider/staler quotes)?
  - [x] 1.5: Compare findings against the Architecture's quality scoring formula: `1.0 - (gap_penalty + integrity_penalty + staleness_penalty)` with the specific penalty calculations. Assess: is this formula reasonable? Are the weights balanced? Are there better approaches?
  - [x] 1.6: Compare findings against the Architecture's score thresholds: GREEN >= 0.95, YELLOW 0.80-0.95, RED < 0.80. Assess: are these thresholds appropriate for M1 forex data?

- [x] Task 2: Research data quarantine patterns (AC: #1)
  - [x] 2.1: Research how trading systems handle quarantined data — mark-and-skip vs exclude-and-interpolate vs separate-partition
  - [x] 2.2: Research the Architecture's chosen approach: quarantined bars marked with a `quarantined: bool` column in Arrow IPC, backtester skips quarantined bars. Assess: is this the right approach? What are the tradeoffs?
  - [x] 2.3: Research edge cases: what happens at quarantine boundaries? If bars 100-110 are quarantined, how should indicators that depend on lookback periods handle the gap? (e.g., a 20-period MA at bar 111 would normally include bars 91-110, but bars 100-110 are quarantined)
  - [x] 2.4: Document a recommended quarantine handling strategy that addresses boundary effects

- [x] Task 3: Research gap handling approaches for M1 forex data (AC: #1)
  - [x] 3.1: Research types of gaps in Dukascopy M1 data: weekend gaps, holiday gaps, server maintenance gaps, data feed interruptions, low-liquidity gaps (Asian session, holiday periods)
  - [x] 3.2: Research professional approaches to gap handling: forward-fill vs interpolation vs leave-as-is vs mark-and-exclude
  - [x] 3.3: The Architecture explicitly states "interpolation NOT allowed" for gap handling. Research whether this is the right call — what do professionals do?
  - [x] 3.4: Research gap thresholds: the Architecture uses "> 5 consecutive M1 bars" as the gap detection threshold. Is this appropriate? What's normal for Dukascopy M1 data?

- [x] Task 4: Research Dukascopy API and data format specifics (AC: #1)
  - [x] 4.1: Document the Dukascopy data download mechanism — is it a REST API, FTP, web scraping, or a client library? What authentication is required?
  - [x] 4.2: Document the raw data format received from Dukascopy — CSV, binary, compressed? What columns are provided? What timezone are timestamps in?
  - [x] 4.3: Research Dukascopy-specific data quirks — known issues with their M1 data (duplicate bars, timezone shifts, missing weekend boundary bars, inconsistent formats across date ranges)
  - [x] 4.4: Research rate limiting and download best practices — how fast can you download without being blocked? What retry strategies work?
  - [x] 4.5: Research Dukascopy tick data availability and format — the Architecture mentions optional tick data for scalping strategies. What's the format, size implications, and download mechanism for ticks vs M1 bars?
  - [x] 4.6: Document any Python libraries that wrap Dukascopy access (e.g., `dukascopy-node`, Python equivalents) — assess quality, maintenance status, and whether they're suitable for production use vs building a direct integration

- [x] Task 5: Compare research findings against Architecture specifications (AC: #2)
  - [x] 5.1: Create a comparison table with columns: Topic | Architecture Specification | Research Finding | Verdict (confirm/improve/replace) | Recommendation
  - [x] 5.2: Topics to compare:
    - Quality scoring formula and penalty weights
    - Score thresholds (GREEN/YELLOW/RED)
    - Gap detection threshold (> 5 consecutive M1 bars)
    - Gap severity levels (WARNING < 10 gaps/year, ERROR > 50 gaps/year or > 30 min)
    - Price integrity checks (bid > 0, ask > bid, spread within 10x median)
    - Stale quote detection (bid=ask or spread=0 for > 5 consecutive bars)
    - Quarantine approach (bool column, backtester skips)
    - Consistent data sourcing (hash-based identification)
  - [x] 5.3: For any "improve" or "replace" verdicts, provide a specific alternative with rationale

- [x] Task 6: Produce Architecture update recommendations (AC: #3)
  - [x] 6.1: Based on Task 5, compile a list of proposed Architecture changes
  - [x] 6.2: For each proposed change, specify: the Architecture section to update, the current text, the proposed replacement text, and the research evidence supporting the change
  - [x] 6.3: Do NOT modify the Architecture document directly — proposed changes go in the research artifact for operator review
  - [x] 6.4: If no changes are warranted, explicitly state "Architecture data quality specifications confirmed by research — no changes needed"

- [x] Task 7: Produce the build plan for Stories 1.3-1.9 (AC: #4)
  - [x] 7.1: Using Story 1.1's verdict table (keep/adapt/replace per component) combined with this research, produce a definitive build plan for each downstream story:

    | Story | Title | Build Approach | Key Dependencies |
    |---|---|---|---|
    | 1.3 | Project Structure, Config & Logging | Build new (per Architecture) | None |
    | 1.4 | Dukascopy Data Download | Keep/Adapt/Replace (from 1.1 verdict) | 1.3 |
    | 1.5 | Data Validation & Quality Scoring | Keep/Adapt/Replace (from 1.1 verdict + this research) | 1.4 |
    | 1.6 | Parquet Storage & Arrow IPC Conversion | Likely adapt (add Arrow IPC) | 1.5 |
    | 1.7 | Timeframe Conversion | Keep/Adapt/Replace (from 1.1 verdict) | 1.6 |
    | 1.8 | Data Splitting & Consistent Sourcing | Keep/Adapt/Replace (from 1.1 verdict) | 1.7 |
    | 1.9 | E2E Pipeline Proof | Integration test — build new | 1.3-1.8 |

  - [x] 7.2: For each "adapt" story, list specifically what needs to change from the baseline
  - [x] 7.3: For each "build new" story, note what the baseline provides as reference (even if not directly reusable)

- [x] Task 8: Write the research artifact (AC: all)
  - [x] 8.1: Save the complete research artifact to `_bmad-output/planning-artifacts/research/data-quality-acquisition-research.md`
  - [x] 8.2: Structure the artifact with these sections:
    1. Executive Summary
    2. Data Quality Scoring Methodologies (findings + recommendation)
    3. Quarantine Patterns (findings + recommendation)
    4. Gap Handling Approaches (findings + recommendation)
    5. Dukascopy API & Data Format (technical reference)
    6. Architecture Comparison Table
    7. Proposed Architecture Updates
    8. Build Plan for Stories 1.3-1.9

## Dev Notes

### Architecture Constraints

The research must be evaluated against these specific Architecture specifications:

- **D2 (Artifact Schema & Storage):** The data pipeline outputs must ultimately land in Arrow IPC (for compute), SQLite (for query), and Parquet (for archival). Research must confirm that the data quality approach works across all three formats — particularly that the `quarantined: bool` column is representable and queryable in each. [Source: architecture.md, Decision 2]

- **Data Quality Gate Specifications:** The Architecture defines specific quality checks and a scoring formula. The full specification is:

  ```
  Quality checks: gap detection (> 5 consecutive M1 bars), price integrity (bid > 0, ask > bid, spread within 10x median), timezone alignment (UTC, monotonically increasing), stale quotes (bid=ask or spread=0 for > 5 bars), completeness (no unexpected missing weekday data)

  Scoring formula: quality_score = 1.0 - (gap_penalty + integrity_penalty + staleness_penalty)
    gap_penalty = min(1.0, total_gap_minutes / total_expected_minutes * 10)
    integrity_penalty = min(1.0, bad_price_bars / total_bars * 100)
    staleness_penalty = min(1.0, stale_bars / total_bars * 50)

  Thresholds: GREEN >= 0.95, YELLOW 0.80-0.95, RED < 0.80

  Gap severity: WARNING < 10 gaps/year, ERROR > 50 gaps/year or any gap > 30 min

  Quarantine: marked in Arrow IPC with quarantined:bool column. Backtester skips. Quality report lists all quarantined periods with reasons.

  Interpolation NOT allowed.
  ```
  [Source: architecture.md, Data Quality Gate Specifications section]

- **Session-Awareness:** Quality checks should be session-aware — spread thresholds during Asian session are naturally wider than during London/NY overlap. The Architecture defines sessions in `config/base.toml` with Asian (00:00-08:00 UTC), London (08:00-16:00), New York (13:00-21:00), London/NY Overlap (13:00-16:00), Off Hours (21:00-00:00). [Source: architecture.md, Session-Awareness Architecture section]

- **Arrow IPC market_data schema:** The contract defines columns: timestamp (int64, epoch microseconds), open/high/low/close/bid/ask (float64), session (utf8), quarantined (bool). Research must confirm this schema is sufficient or recommend additions. [Source: architecture.md, Contracts Directory Content]

### Technical Requirements

- The research artifact must be Markdown format
- Output path: `_bmad-output/planning-artifacts/research/data-quality-acquisition-research.md`
- Research sources should be cited (academic papers, industry documentation, library documentation, established quant references)
- If Story 1.1 is not yet complete when this story begins, the Dukascopy research (Task 4) and quality scoring methodology research (Tasks 1-3) can proceed independently — only Task 7 (build plan) requires Story 1.1's verdict table

### What to Reuse from ClaudeBackTester

From the baseline-to-architecture mapping:

| Component | Mapping Direction | Notes |
|---|---|---|
| `data_pipeline/` | **Keep and adapt** | "Add quality scoring/quarantine (new). Core download/validation reusable." |

[Source: baseline-to-architecture-mapping.md, Orchestration Tier table]

The gap assessment says quality scoring and quarantine are **new capabilities** that don't exist in the baseline. This research story defines what those new capabilities should look like. The baseline provides download and basic validation — this research determines the quality scoring layer that sits on top.

### Anti-Patterns to Avoid

1. **DO NOT use generic data quality approaches** — this is specifically M1 forex data from Dukascopy. General "data quality framework" recommendations are not useful. Research must be specific to forex M1 bar data characteristics.
2. **DO NOT recommend overly complex scoring** — the operator is a single person, not a data quality team. The scoring system must be simple, interpretable, and actionable (GREEN/YELLOW/RED).
3. **DO NOT ignore session-awareness** — quality thresholds that don't account for session differences will produce false positives (flagging normal Asian session behavior as anomalous).
4. **DO NOT modify the Architecture document directly** — proposed changes go in the research artifact.
5. **DO NOT write any Forex Pipeline code** — this story produces a research artifact only.
6. **DO NOT skip the Dukascopy-specific research** — generic "how to download forex data" is not sufficient. The specifics of Dukascopy's data format, API quirks, and known issues are critical for Stories 1.4 and 1.5.
7. **DO NOT recommend interpolation** — the Architecture explicitly forbids it. If research supports interpolation, present the argument but note the Architecture constraint.

### Project Structure Notes

- Research artifact output: `C:\Users\ROG\Projects\Forex Pipeline\_bmad-output\planning-artifacts\research\data-quality-acquisition-research.md`
- Ensure the `research/` subdirectory exists before writing
- This research feeds directly into Stories 1.4 (Dukascopy download), 1.5 (validation & quality scoring), and the overall build plan for Epic 1

### References

- [Source: planning-artifacts/epics.md#Story 1.2 — lines 467-480]
- [Source: planning-artifacts/architecture.md#Data Quality Gate Specifications — lines 224-260]
- [Source: planning-artifacts/architecture.md#Session-Awareness Architecture — lines 146-222]
- [Source: planning-artifacts/architecture.md#Decision 2 — lines 332-388]
- [Source: planning-artifacts/architecture.md#Contracts Directory Content, arrow_schemas.toml market_data — lines 1371-1385]
- [Source: planning-artifacts/baseline-to-architecture-mapping.md — Orchestration Tier, data_pipeline row]
- [Source: planning-artifacts/prd.md#FR1-FR8 — lines 461-468]
- [Source: planning-artifacts/prd.md#Market Data Integrity — lines 217-222]
- [Source: planning-artifacts/prd.md#Data source — Dukascopy M1 bid+ask — line 280]
- [Source: planning-artifacts/prd.md#Research-Dependent Design Requirements — lines 330-348]

## Dev Agent Record

### Agent Model Used
Claude Opus 4.6 (1M context)

### Completion Notes List
- Researched data quality scoring methodologies for M1 forex data — Architecture's formula confirmed as well-designed
- Researched quarantine patterns — mark-and-skip confirmed as correct approach, documented boundary effects
- Researched gap handling — 5-bar threshold confirmed, "no interpolation" rule confirmed by professional consensus
- Researched Dukascopy API — documented two approaches (dukascopy-python REST vs raw bi5), recommended dukascopy-python as primary
- Documented dukascopy-python v4.0.1 capabilities: supports INTERVAL_TICK, both bid/ask sides, MIT license, Python 3.10+
- Documented 5 known Dukascopy data quirks: historical revisions, session opening spreads, gaps/spikes, zero-volume bars, UTC timestamps
- Compared Architecture specifications against research findings — all confirmed, 3 minor improvements proposed
- Produced definitive build plan for Stories 1.3-1.9 with build approach, key dependencies, and implementation notes
- Key decision: dukascopy-python library is recommended over building raw bi5 decoder for M1 bars
- Key decision: Architecture's quality scoring formula is confirmed — replace baseline's 0-100 model entirely

### Change Log
- 2026-03-14: Story completed. Research artifact written to `_bmad-output/planning-artifacts/research/data-quality-acquisition-research.md`

### File List
- `_bmad-output/planning-artifacts/research/data-quality-acquisition-research.md` (NEW — research artifact, ~350 lines)
