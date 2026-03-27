# Story 3-1-claudebacktester-backtest-engine-review: Story 3.1: ClaudeBackTester Backtest Engine Review — Holistic System Review

**Reviewer:** Codex GPT-5.4 (high effort, read-only sandbox)
**Date:** 2026-03-17
**Type:** Holistic System Alignment Review

---

**1. System Alignment**
- **Assessment:** CONCERN
- **Evidence:** [3-1 story](/c/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/implementation-artifacts/3-1-claudebacktester-backtest-engine-review.md#L10), [epics.md](/c/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/planning-artifacts/epics.md#L869), [prd.md](/c/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/planning-artifacts/prd.md#L93)
- **Observations:** This story advances reproducibility, artifact completeness, and fidelity by reviewing D1/D2/D3/D13/D14 seams. It barely advances operator confidence: there is no explicit AC for FR16, FR17, or FR39, even though the PRD makes evidence quality and operator review central. It also overreaches V1 by expanding from a backtest-engine review into optimizer, validator, checkpoint, storage, and architecture-governance work. That drift is visible against the much narrower epic-level Story 3.1.
- **Recommendation:** Either narrow the story back to backtester core + Python/Rust boundary + checkpoint/storage seams, or formally rename/re-scope it as an Epic 3 baseline systems review. Do not leave it in between.

**2. PRD Challenge**
- **Assessment:** CONCERN
- **Evidence:** [prd.md](/c/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/planning-artifacts/prd.md#L480), [prd.md](/c/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/planning-artifacts/prd.md#L495), [prd.md](/c/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/planning-artifacts/prd.md#L504), [prd.md](/c/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/planning-artifacts/prd.md#L411)
- **Observations:** FR14/15/18/42/58 are the right things to test here. But this story spends major effort mapping baseline code against FR25-FR28 and FR36-FR37, which are partly visualization/candidate-selection concerns and partly post-MVP research areas. Meanwhile the real V1 gate from the PRD is pipeline proof, evidence quality, and confidence, and the story under-specifies those operator-facing outcomes.
- **Recommendation:** Recompose the requirement mapping into three buckets: MVP-critical compute fidelity, operator evidence/reviewability, and later optimization-selection sophistication. For this story, go deep only on the first bucket and note the others at gap-analysis level.

**3. Architecture Challenge**
- **Assessment:** CONCERN
- **Evidence:** [architecture.md](/c/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/planning-artifacts/architecture.md#L316), [architecture.md](/c/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/planning-artifacts/architecture.md#L394), [architecture.md](/c/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/planning-artifacts/architecture.md#L903), [architecture.md](/c/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/planning-artifacts/architecture.md#L939), [3-1 story](/c/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/implementation-artifacts/3-1-claudebacktester-backtest-engine-review.md#L272)
- **Observations:** D3, D13, and D14 are directionally strong. D1 is plausible, but the current story already admits the baseline is Python-first with a small PyO3 Rust core, which weakens the architecture’s implied continuity with a Rust-binary-first design. The story should explicitly test whether V1 should port only the backtester core to Rust and keep optimizer/validator in Python behind artifact boundaries. It also misframes NFR9: the story treats it as “multiple concurrent backtests from same Rust process,” but the PRD’s NFR9 is about resource-management strategy, not same-process concurrency.
- **Recommendation:** Add an explicit “V1 port boundary” outcome: what must move to Rust now, what stays Python for V1, and what should not be ported until later research closes. Correct the NFR9 mapping.

**4. Story Design**
- **Assessment:** CRITICAL
- **Evidence:** [epics.md](/c/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/planning-artifacts/epics.md#L869), [3-1 story](/c/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/implementation-artifacts/3-1-claudebacktester-backtest-engine-review.md#L30), [3-1 story](/c/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/implementation-artifacts/3-1-claudebacktester-backtest-engine-review.md#L95), [3-1 story](/c/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/implementation-artifacts/3-1-claudebacktester-backtest-engine-review.md#L177)
- **Observations:** The story is too big and too soft. It asks one research story to deeply analyze a very large Python-first optimizer/validator/pipeline stack, decide reuse against five architecture decisions, and feed Stories 3.2-3.9. Yet most ACs are phrased as “a document describes...”, which is not a crisp done condition. There is also a governance inconsistency: the epic says architecture gets updated directly, while this story says proposals go only into the research artifact.
- **Recommendation:** Split the story or hard-bound it. Convert ACs into verifiable artifact outputs: required tables, decision records, migration seams, risk register, and downstream handoff sections. Align the architecture-update mechanism with the epic.

**5. Downstream Impact**
- **Assessment:** ADEQUATE
- **Evidence:** [3-1 story](/c/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/implementation-artifacts/3-1-claudebacktester-backtest-engine-review.md#L276), [architecture.md](/c/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/planning-artifacts/architecture.md#L2089), [architecture.md](/c/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/planning-artifacts/architecture.md#L2127)
- **Observations:** The story is downstream-aware and names the right consumers. The gap is output precision: later stories need extracted contracts, migration boundaries, and “do not port yet” decisions, not just prose. Without that, Stories 3.3-3.6 will re-litigate D1/D2/D3/D14 and the team may accidentally treat baseline structures like the 64-slot PL layout or five-stage optimizer as architectural truth.
- **Recommendation:** Make downstream handoff artifacts mandatory: interface candidates for 3.4, decomposition boundary for 3.5, storage/schema mapping for 3.6, operator-evidence implications for 3.7/3.8, and a defer/no-port list.

## Overall Verdict
VERDICT: REFINE

## Recommended Changes
1. Re-scope Story 3.1 to match one of two explicit boundaries: narrow backtest-engine review, or broad Epic 3 baseline systems review.
2. If the broad boundary is kept, rename the story so its title and narrative match the actual work.
3. Add explicit acceptance criteria for FR16, FR17, and FR39 implications, or explicitly defer them to Story 3.7 with a required handoff section.
4. Replace “a document describes” wording with required outputs: module matrix, migration matrix, risk register, contract candidates, and decision log.
5. Correct the NFR9 reference throughout the story; it currently does not match the PRD.
6. Add a “V1 critical path vs later/growth” filter so FR25-FR28 and FR36-FR37 are assessed lightly unless they directly unblock V1.
7. Add a mandatory “V1 port boundary” section: port now, wrap for now, defer, and do-not-port-yet.
8. Reduce emphasis on raw file inventories and line counts; prioritize capability seams, fidelity risks, and migration effort.
9. Align governance with the epic: either research artifacts propose architecture updates, or the story updates architecture directly, but not both.
10. Require downstream handoff tables for Stories 3.2-3.9 so later work does not re-open the same architectural questions.
