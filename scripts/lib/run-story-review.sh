#!/usr/bin/env bash
# Step 3: Story Review — Codex holistic system alignment review
#
# NOT a code review. This is a SYSTEM THINKING review:
#   - Does this story serve the system's goals holistically?
#   - Is the PRD/architecture right for what we're trying to achieve?
#   - Are we over/under-engineering?
#   - Does the story set up downstream correctly?
#   - Are there systemic gaps or misalignments?
#
# Codex (GPT-5.4) acts as an independent sparring partner who has read
# the full system context (PRD, architecture, all epics) and challenges
# whether we're building the right thing.

STORY_REVIEW_DIR="$PROJECT_ROOT/reviews/story-reviews"
STORY_REVIEW_LOG=""

# Run the Codex story review step
# Usage: run_story_review_step "2-1-strategy-evaluator-review" "/path/to/story.md"
# Returns: 0 on success (review produced), 1 on failure
run_story_review_step() {
  local story_key="$1"
  local story_file="$2"
  local step_log="$LOG_DIR/${story_key}-story-review-$(date +%H%M%S).log"
  local review_file="$STORY_REVIEW_DIR/story-${story_key}-codex-review.md"

  STORY_REVIEW_LOG="$review_file"

  log_step "STORY REVIEW (Codex): $story_key"
  log_info "Step log: $step_log"

  mkdir -p "$STORY_REVIEW_DIR"

  # Check Codex availability
  if ! command -v codex &>/dev/null; then
    log_warn "Codex CLI not installed — skipping story review"
    STORY_REVIEW_LOG=""
    return 0
  fi

  local auth_status
  auth_status=$(codex login status 2>&1 | tr -d '\r')
  if [[ "$auth_status" != *"Logged in"* ]]; then
    log_warn "Codex not authenticated — skipping story review"
    STORY_REVIEW_LOG=""
    return 0
  fi

  # Get story title
  local story_title
  story_title=$(grep -m1 "^# " "$story_file" 2>/dev/null | sed 's/^# //' | tr -d '\r')
  if [[ -z "$story_title" ]]; then
    story_title="Story $story_key"
  fi

  local codex_prompt
  codex_prompt="You are conducting a HOLISTIC SYSTEM REVIEW of a story specification for a trading system pipeline.

This is NOT a line-by-line review. You are the system architect's sparring partner. Your job is to
think about the SYSTEM AS A WHOLE and challenge whether we're building the right thing.

== THE SYSTEM ==

BMAD Backtester is a one-person trading-system operating platform. Core objectives:
1. REPRODUCIBILITY — every run produces the same results given the same inputs
2. OPERATOR CONFIDENCE — a non-coder operator can drive the workflow with clear evidence
3. ARTIFACT COMPLETENESS — every stage emits saved, reviewable artifacts
4. FIDELITY — explicit tolerances and attribution for any divergence

V1 scope: one strategy family, one pair/timeframe, full path from hypothesis to go/no-go decision.
V1 is NOT gated on profitability — it's gated on reproducibility, evidence quality, and operator confidence.

== FILES TO READ (READ ALL OF THESE) ==

Story being reviewed: ${story_file}
PRD (system objectives and requirements): ${PRD_FILE}
Architecture (decisions and constraints): ${ARCH_FILE}
Epics (full epic breakdown and all stories): ${EPICS_FILE}

== YOUR FIVE QUESTIONS ==

Think deeply about each. Give specific, evidence-backed answers.

1. SYSTEM ALIGNMENT: Does this story actually serve the system's stated objectives?
   - Which of the 4 objectives does it advance? Which does it NOT touch?
   - Is anything in this story working AGAINST a system objective?
   - Does this story fit V1 scope or is it over-reaching?
   - Is there a simpler way to achieve the same system-level outcome?

2. PRD CHALLENGE: Is the PRD asking for the right thing here?
   - Do the functional requirements (FRs) this story maps to actually serve the system goals?
   - Are any FRs over-specified, under-specified, or misaligned with the operator's real needs?
   - Would a different decomposition of requirements serve the system better?
   - Are we solving real problems or imagined ones?

3. ARCHITECTURE CHALLENGE: Are the architecture decisions right for this?
   - Do the referenced architecture decisions (Ds) actually serve the implementation well?
   - Is the technology stack appropriate for what this story needs?
   - Are there simpler architectural approaches that would work just as well?
   - Are any architecture decisions creating unnecessary complexity?

4. STORY DESIGN: Is this story well-designed for implementation?
   - Are the acceptance criteria actually testable and verifiable?
   - Does the task breakdown cover everything needed, or are there gaps?
   - Are the anti-patterns and dev notes sufficient to prevent real mistakes?
   - Would a different story boundary (splitting or merging) work better?

5. DOWNSTREAM IMPACT: Does this set up the rest of the system correctly?
   - What does this story's output need to provide for downstream stories?
   - Are there assumptions that might not hold as the pipeline grows?
   - Are we creating technical debt that will hurt later epics?
   - Is there anything missing that will force a rewrite later?

== OUTPUT FORMAT ==

For each question, provide:
- **Assessment:** STRONG / ADEQUATE / CONCERN / CRITICAL
- **Evidence:** Specific references to PRD, architecture, or story content
- **Observations:** Concrete, actionable observations (not vague)
- **Recommendation:** What to change, keep, or investigate further

End with:

## Overall Verdict
VERDICT: ALIGNED / REFINE / RETHINK

- ALIGNED: Story is well-designed and serves the system's goals
- REFINE: Story is mostly right but has specific improvements needed
- RETHINK: Significant concerns about approach — story may need substantial revision

## Recommended Changes
[Numbered list of specific, actionable changes to the story file]"

  local codex_output
  codex_output=$(codex exec --skip-git-repo-check \
    -m gpt-5.4 \
    --config model_reasoning_effort="high" \
    --sandbox read-only \
    "$codex_prompt" \
    2>/dev/null) || true

  if [[ -n "$codex_output" && ${#codex_output} -gt 200 ]]; then
    {
      echo "# Story ${story_key}: ${story_title} — Holistic System Review"
      echo ""
      echo "**Reviewer:** Codex GPT-5.4 (high effort, read-only sandbox)"
      echo "**Date:** $(date +%Y-%m-%d)"
      echo "**Type:** Holistic System Alignment Review"
      echo ""
      echo "---"
      echo ""
      echo "$codex_output"
    } > "$review_file"
    log_success "Codex story review complete — saved to $review_file"
    return 0
  else
    log_warn "Codex review returned empty or minimal output"
    STORY_REVIEW_LOG=""
    return 0
  fi
}
