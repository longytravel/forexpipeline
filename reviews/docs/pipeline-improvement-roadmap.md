# Pipeline Improvement Roadmap

**Created:** 2026-03-14
**Status:** Active
**Owner:** ROG + Claude + Codex

---

## Current Pipeline (as of today)

```
Smart Skip → Dev → Verify (8-phase) → Dual Review (BMAD + Codex) → Synthesis → Post-Verify → PIR → Done
```

### Current Testing Gaps (the problem)

The verify step runs both unit and live tests, but live tests are **isolated per story**. Each story's live test exercises its own module in isolation. Nobody tests the chain:

```
Download (1-4) → Validate (1-5) → Store (1-6) → Convert (1-7) → Split (1-8)
   ↓                ↓                 ↓              ↓              ↓
  raw CSV     quality report      .parquet       M5/H1/D1/W      train/test
              + validated CSV     + .arrow        Arrow IPC       datasets
```

**What breaks in practice:** Story 1-5 computes gap_severity then discards it. Story 1-5 silently localizes tz-naive timestamps instead of rejecting them. These passed unit tests AND story-level live tests because each story's tests only check its own contract — not whether the data flowing into the next story is actually correct.

---

## Phase 1: Live Testing Overhaul (HIGH PRIORITY)

The biggest bang for the buck. Every issue found so far was catchable by better integration testing.

### 1.1 Cross-Story Integration Test Suite
**What:** A new test module `test_pipeline_integration.py` with `@pytest.mark.live` tests that chain story outputs into story inputs.
**Tests:**
- `test_download_to_validation`: 1-4 downloads real data → feeds directly into 1-5 validator → asserts quality report is complete and correct
- `test_validation_to_storage`: 1-5 validated CSV → feeds into 1-6 Arrow/Parquet converter → asserts all columns survive, quarantine column preserved
- `test_storage_to_timeframe`: 1-6 Arrow IPC output → feeds into 1-7 timeframe converter → asserts session column propagated, row counts make sense
- `test_timeframe_to_split`: 1-7 converted timeframes → feeds into 1-8 splitter → asserts train/test sets are disjoint and complete
- `test_full_chain_eurusd_1_week`: Downloads 1 week EURUSD M1, runs through ALL stages, validates final output

**Why it matters:** Catches interface mismatches between stories. The Codex review of 1-5 found 3 HIGH findings that would have been caught if validated CSV was actually fed into the next stage.

**When:** Before running stories 1-8 and 1-9. Can be built independently or as part of story 1-9.

### 1.2 Pipeline Contract Tests
**What:** Lightweight non-live tests that validate the data contracts between stages without downloading real data.
**Tests:**
- Validator output schema matches storage input schema
- Storage output schema matches timeframe converter input schema
- Quality report JSON schema is complete (no silently discarded fields)
- Manifest chain: each stage's output manifest links to the previous stage's input manifest

**Why:** Fast (no network), catches schema drift immediately in unit tests.

### 1.3 Regression Test Generation from Reviews
**What:** When synthesis accepts a finding, automatically generate a regression test for it.
**Example:** Codex found "gap_severity computed then discarded" → generate `test_gap_severity_affects_report()` that asserts gap_severity appears in the quality report and affects can_proceed.

**Implementation:** Add to synthesis step's system prompt:
```
For each ACCEPTED finding that you fix, also write a regression test that would
have caught the original bug. Place it in the appropriate test file with the
marker @pytest.mark.regression.
```

**When:** Can be added to run-synthesis.sh immediately — just a prompt change.

### 1.4 Cumulative Live Test Gate
**What:** After each story completes, run ALL prior stories' live tests — not just the current story's.
**Current behavior:** Phase 6 runs `pytest -m live` which runs all live tests. This is already correct!
**Gap:** When synthesis fixes code in story 1-5, the post-synthesis verify runs all live tests — but if 1-5's fix broke 1-4's live test expectations, this only catches it if 1-4's live tests check 1-5's output. That's the cross-story gap from 1.1.

**Fix:** Integration tests from 1.1 automatically get included in `pytest -m live` runs, closing this gap for free.

---

## Phase 2: Review Intelligence (MEDIUM PRIORITY)

Make the review system learn and improve over time.

### 2.1 Review Memory / Lessons Learned
**What:** After synthesis, append accepted findings to `reviews/lessons-learned.md`. Feed this into the dev step's system prompt for future stories.
**Format:**
```markdown
## Story 1-5: Data Validation
- ACCEPTED (Codex): gap_severity computed but never used in scoring or reporting
  → Rule: Never compute a value without using it in the output contract
- ACCEPTED (BMAD): timezone validation silently localizes instead of rejecting
  → Rule: Validation must reject or flag, never silently fix
```
**How it feeds forward:** Dev step system prompt gets:
```
LESSONS FROM PRIOR REVIEWS (avoid repeating these mistakes):
<contents of lessons-learned.md>
```

**Effort:** ~30 min. Add to run-synthesis.sh prompt + modify run-dev.sh to read the file.

### 2.2 Smart Review Skip
**What:** On retry, if smart-skip determined dev didn't need to re-run (code unchanged), skip re-running both reviews. Use previous review outputs and go straight to synthesis.
**Logic:**
```bash
if [[ "$dev_needed" == "false" ]]; then
  # Check if previous review outputs exist
  if [[ -f "$bmad_log" && -f "$codex_file" ]]; then
    log_info "Skipping re-review — using previous review outputs"
    # Jump to synthesis
  fi
fi
```
**Saves:** 10-20 min per retry (both review steps skipped).

### 2.3 Review Metrics
**What:** Track per-reviewer acceptance rates in `reviews/metrics.json`.
**Data:**
```json
{
  "stories_reviewed": 5,
  "bmad": { "findings": 12, "accepted": 8, "rejected": 4, "acceptance_rate": 0.67 },
  "codex": { "findings": 9, "accepted": 7, "rejected": 2, "acceptance_rate": 0.78 },
  "both_flagged": { "findings": 3, "accepted": 3, "acceptance_rate": 1.0 }
}
```
**Value:** Data-driven prompt tuning. If one reviewer has low acceptance, adjust its prompt. If "both flagged" is always 100% accepted, weight dual-flagged findings higher.

**Implementation:** Synthesis step parses its own report and appends to metrics.json.

---

### 2.4 Story PIR (Post-Implementation Review)
**What:** After post-verify passes, run a mini review that asks "did we build the right thing?" — not "is the code right?" (that's the dual review's job) but "does this story's output actually serve the system's objectives?"
**Flow:**
```
Post-Verify passes
        ↓
   Codex gets: implemented code + PRD + architecture doc + test output
   Codex answers: alignment, simplification, forward-look
        ↓
   Claude gets: Codex's PIR assessment
   Claude weighs it against own understanding of system objectives
   Claude produces PIR verdict:
     ALIGNED   → proceed to Done, no concerns
     OBSERVE   → proceed, but note observations for future stories
     REVISIT   → flag to operator with evidence, pause for human decision
        ↓
   PIR report saved to reviews/pir/story-{key}-pir.md
        ↓
   Done
```
**Three questions Codex answers:**
1. Does what this story built advance the system's stated objectives (reproducibility, operator confidence, artifact completeness)?
2. Is there a simpler way to achieve the same outcome?
3. Is anything here that the next story doesn't actually need, or missing something it will?

**Key design principle:** Codex is the sparring partner, not the authority. Claude evaluates Codex's assessment, may disagree, and makes the final judgment. The PIR should not blindly accept or implement Codex's suggestions.

**What it feeds forward:** PIR observations become input to future story creation — when BMAD creates the next story, it gets prior PIR observations so alignment drift is caught early.

**Pipeline position:**
```
Dev → Verify → Dual Review → Synthesis → Post-Verify → PIR → Done
```

**Runs on:** Every story. ~5 min overhead per story.
**Implementation:** One script (`run-pir.sh`) mirroring existing `run-codex-review.sh` pattern.

---

## Phase 3: Multi-Reviewer Expansion (MEDIUM PRIORITY)

### 3.1 Third Reviewer: Gemini via NotebookLM
**What:** Add Gemini as a third independent reviewer. Already have NLM skills installed.
**Architecture:** Same pattern as Codex — parallel, read-only, non-blocking. Output to `reviews/gemini/`.
**Value:** Three different AI architectures (Claude, GPT, Gemini) with different training data and blind spots.
**Implementation:** New `run-gemini-review.sh` following the same pattern as `run-codex-review.sh`. Uses NLM CLI or Gemini API.

### 3.2 Codex as Adversarial Tester
**What:** Second Codex call in `workspace-write` sandbox that writes edge-case tests based on its review findings.
**Flow:**
```
Codex Review (read-only) → findings
Codex Test Gen (workspace-write) → additional test file
                                    ↓
                            Merged into verify step
```
**Example from story 1-5:** Codex found timezone silently localized → writes `test_timezone_naive_rejected()` that asserts tz-naive input raises an error.
**Output:** `tests/test_data_pipeline/test_codex_edge_cases_{story_key}.py`

### 3.3 Confidence-Gated Automation
**What:** Fast path when reviews are clean, escalation when they disagree.
**Logic:**
- Both reviewers APPROVED + zero HIGH findings → skip synthesis, go straight to post-verify (fast path)
- One reviewer APPROVED, one CHANGES_REQUIRED → normal synthesis
- Both CHANGES_REQUIRED with overlapping findings → synthesis with elevated attention
- Either BLOCKED → flag for human review, don't auto-synthesize
**Saves:** Synthesis step (~5-10 min) skipped on clean stories.

---

## Phase 4: Self-Improving Pipeline (LOWER PRIORITY)

### 4.1 Self-Healing Dev Prompts
**What:** Automatically update the dev step's system prompt with anti-patterns from accepted findings.
**Mechanism:** After synthesis, extract patterns and append to `_bmad-output/dev-anti-patterns.md`. Dev step reads this file.
**Example patterns:**
- "Never compute a value without including it in the output report"
- "Validation must reject or flag invalid data, never silently fix it"
- "All new columns added in one pipeline stage must be tested for presence in the next stage"

**Difference from 2.1:** Lessons-learned is a log of specific findings. Anti-patterns is a distilled, generalized ruleset.

### 4.2 Epic-Level Integration Review
**What:** After all stories in an epic complete, run a cross-story review.
**Trigger:** When `check_epic_completion` fires in the orchestrator.
**Scope:** Review interactions between all stories in the epic — data contracts, error propagation, config consistency.
**Output:** `reviews/epic/epic-{N}-integration-review.md`

### 4.3 Parallel Story Execution
**What:** Stories with no dependency (different epics, or non-sequential within an epic) run in parallel using git worktrees.
**Architecture:**
```bash
# Story 1-8 and 2-1 have no dependency
git worktree add /tmp/story-1-8 -b story/1-8
git worktree add /tmp/story-2-1 -b story/2-1
# Run both in parallel, merge results
```
**Complexity:** High — need to handle merge conflicts, shared test infrastructure, concurrent pytest runs.
**When:** After epic 1 is complete and epic 2 starts.

---

## Implementation Order (recommended)

```
DONE:
├── 1.3 Regression test generation (prompt change to synthesis) ✅ (2026-03-14)
├── 2.1 Review memory / lessons learned ✅ (2026-03-14)
├── 2.2 Smart review skip ✅ (2026-03-14)
├── 1.1 Cross-story integration test suite ✅
├── 1.2 Pipeline contract tests ✅
└── 1.4 Cumulative live test gate ✅ (free — 1.1 tests included in pytest -m live)

NEXT:
├── 2.4 Story PIR (retroactive on stories 1-4 through 1-8, then on every story going forward)
└── 2.3 Review metrics

AFTER EPIC 1:
├── 3.1 Gemini third reviewer
├── 3.2 Codex adversarial tester
├── 3.3 Confidence-gated automation
└── 4.2 Epic-level integration review

ONGOING:
├── 4.1 Self-healing dev prompts
└── 4.3 Parallel story execution (when epic 2 starts)
```

---

## Review Folder Structure

```
reviews/
├── codex/                              ← Codex review outputs (automated)
│   ├── story-1-5-codex-review.md
│   ├── story-1-6-codex-review.md
│   └── ...
├── synthesis/                          ← Synthesis reports (automated)
│   ├── 1-5-synthesis-report.md
│   └── ...
├── gemini/                             ← Gemini reviews (future, Phase 3.1)
│   └── ...
├── pir/                                ← Story PIR reports (Phase 2.4)
│   ├── story-1-4-pir.md
│   └── ...
├── epic/                               ← Epic-level integration reviews (future, Phase 4.2)
│   └── ...
├── docs/                               ← Reference documentation
│   ├── codex-setup-guide.md
│   ├── handover-story-runner.md
│   └── pipeline-improvement-roadmap.md ← This file
├── lessons-learned.md                  ← Accumulated review learnings (Phase 2.1)
└── metrics.json                        ← Review acceptance metrics (Phase 2.3)
```

---

## Cost Model

All automated — no per-token API billing:
- **Claude** (`claude --print`): Max/Pro subscription
- **Codex** (`codex exec`): ChatGPT subscription
- **Gemini** (future): Free tier or Workspace subscription
- **Pipeline runs**: Electricity + time. Typical story: ~30 min total (dev 10m + verify 2m + reviews 10m parallel + synthesis 5m + post-verify 2m)
