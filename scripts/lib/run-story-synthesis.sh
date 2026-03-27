#!/usr/bin/env bash
# Step 4: Story Synthesis — Claude reads Codex review and improves the story
#
# Claude is the final decision-maker. Reads Codex's holistic review,
# agrees or disagrees with each observation, and applies accepted
# improvements directly to the story file.
#
# Key principle: Codex challenges, Claude decides. Not everything Codex
# flags needs to change — some observations may be wrong or out of scope.

STORY_SYNTHESIS_DIR="$PROJECT_ROOT/reviews/story-reviews"
STORY_SYNTHESIS_FAILURE_CONTEXT=""

# Run the story synthesis step
# Usage: run_story_synthesis_step "2-1-strategy-evaluator-review" "/path/to/story.md" "/path/to/codex-review.md"
# Returns: 0 on success, 1 on failure
run_story_synthesis_step() {
  local story_key="$1"
  local story_file="$2"
  local codex_review="${3:-}"
  local step_log="$LOG_DIR/${story_key}-story-synthesis-$(date +%H%M%S).log"
  local synthesis_report="$STORY_SYNTHESIS_DIR/${story_key}-synthesis-report.md"

  STORY_SYNTHESIS_FAILURE_CONTEXT=""

  log_step "STORY SYNTHESIS: $story_key"
  log_info "Step log: $step_log"

  mkdir -p "$STORY_SYNTHESIS_DIR"

  # If no Codex review available, skip synthesis
  if [[ -z "$codex_review" || ! -f "$codex_review" ]]; then
    log_info "No Codex review available — skipping synthesis"
    return 0
  fi

  local synthesis_instruction
  read -r -d '' synthesis_instruction << 'SYNTH_EOF' || true
AUTOMATED STORY SYNTHESIS — NO USER INTERACTION:

You are the final decision-maker for story quality. Codex (GPT-5.4) has reviewed the story
holistically and produced observations. Your job:

1. READ the Codex review thoroughly
2. READ the story file, PRD, architecture, and epics for full context
3. For EACH Codex observation:
   a. AGREE — the observation is valid, apply the improvement
   b. DISAGREE — explain why (Codex may be wrong, out of scope, or overreaching)
   c. DEFER — valid concern but not actionable at the story level (note for future)
4. Apply accepted improvements DIRECTLY to the story file via Edit tool
5. Write a synthesis report documenting every decision

== DECISION PRINCIPLES ==

- V1 is NOT gated on profitability — it's gated on reproducibility and evidence quality
- Do NOT add enterprise complexity for a one-person operator
- Do NOT over-engineer beyond V1 scope (one strategy, one pair/timeframe)
- DO accept observations about missing acceptance criteria or testability gaps
- DO accept observations about downstream contract gaps
- DO accept observations about architecture misalignment with stated goals
- REJECT observations that add scope creep or premature optimization
- REJECT observations that second-guess deliberate architecture decisions without strong evidence

== WHAT TO IMPROVE IN THE STORY ==

When applying improvements, you may:
- Add missing acceptance criteria
- Strengthen task breakdowns with missing steps
- Add dev notes about architecture constraints Codex identified
- Add anti-patterns Codex flagged
- Clarify ambiguous requirements
- Add references Codex found relevant

Do NOT:
- Rewrite the story from scratch
- Change the fundamental scope or approach without strong justification
- Remove existing content unless it's demonstrably wrong
- Add content that makes the story too long to be useful (stay under 400 lines)

== SYNTHESIS REPORT ==

Write to the synthesis report file. Format:

# Story Synthesis: {story_key}

## Codex Observations & Decisions

### 1. [Observation title]
**Codex said:** [brief summary]
**Decision:** AGREE / DISAGREE / DEFER
**Reasoning:** [why]
**Action:** [what was changed, or "none"]

[repeat for each observation]

## Changes Applied
- [list of specific changes made to the story file]

## Deferred Items
- [items noted for future consideration]

## Verdict
VERDICT: IMPROVED / UNCHANGED / BLOCKED
SYNTH_EOF

  local prompt
  prompt="Review and improve Story ${story_key} based on Codex's holistic system review.

Files to read:
- Story file: ${story_file}
- Codex review: ${codex_review}
- PRD: ${PRD_FILE}
- Architecture: ${ARCH_FILE}
- Epics: ${EPICS_FILE}

Write the synthesis report to: ${synthesis_report}
Apply accepted improvements directly to: ${story_file}"

  local exit_code=0
  claude --print \
    --permission-mode bypassPermissions \
    --allowedTools "Read,Edit,Write,Bash,Glob,Grep" \
    --append-system-prompt "$synthesis_instruction" \
    "$prompt" \
    > "$step_log" 2>&1 || exit_code=$?

  if [[ $exit_code -ne 0 ]]; then
    log_error "Story synthesis failed for $story_key (exit code: $exit_code)"
    log_info "Check log: $step_log"
    STORY_SYNTHESIS_FAILURE_CONTEXT="Synthesis step crashed. Check log: $step_log"
    export STORY_SYNTHESIS_FAILURE_CONTEXT
    return 1
  fi

  # Check if synthesis report was written
  if [[ -f "$synthesis_report" ]]; then
    log_success "Synthesis report: $synthesis_report"

    # Parse verdict
    local verdict
    verdict=$(grep -oP 'VERDICT:\s*\K\w+' "$synthesis_report" | tail -1 || true)
    case "$verdict" in
      IMPROVED)
        log_success "Story improved based on Codex observations"
        ;;
      UNCHANGED)
        log_info "Story unchanged — Codex observations rejected or deferred"
        ;;
      BLOCKED)
        log_warn "Synthesis flagged BLOCKED — significant issues found"
        STORY_SYNTHESIS_FAILURE_CONTEXT="Synthesis verdict is BLOCKED. Review: $synthesis_report"
        export STORY_SYNTHESIS_FAILURE_CONTEXT
        return 1
        ;;
      *)
        log_info "Synthesis complete (verdict: ${verdict:-unknown})"
        ;;
    esac
  else
    log_warn "No synthesis report written — synthesis may have only made minor changes"
  fi

  return 0
}
