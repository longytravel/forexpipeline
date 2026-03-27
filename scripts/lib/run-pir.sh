#!/usr/bin/env bash
# Step 7: Post-Implementation Review (PIR)
#
# Asks "did we build the right thing?" — not "is the code right?" (that's the
# dual review's job) but "does this story's output actually serve the system's
# objectives?"
#
# Two-phase process:
#   1. Codex (sparring partner) — adversarial alignment analysis
#   2. Claude (decision-maker) — weighs Codex's assessment, produces verdict
#
# Verdicts:
#   ALIGNED  — story serves system objectives, no concerns
#   OBSERVE  — proceed, but observations noted for future stories
#   REVISIT  — flag to operator with evidence, pause for human decision

# Planning artifacts
PRD_FILE="$PROJECT_ROOT/_bmad-output/planning-artifacts/prd.md"
ARCH_FILE="$PROJECT_ROOT/_bmad-output/planning-artifacts/architecture.md"
EPICS_FILE="$PROJECT_ROOT/_bmad-output/planning-artifacts/epics.md"
PIR_DIR="$PROJECT_ROOT/reviews/pir"

# Run the PIR step for a story
# Usage: run_pir_step "story-key" "/path/to/story.md"
# Returns: 0 on ALIGNED/OBSERVE, 1 on REVISIT
run_pir_step() {
  local story_key="$1"
  local story_file="$2"
  local step_log="$LOG_DIR/${story_key}-pir-$(date +%H%M%S).log"
  local codex_pir_file="$PIR_DIR/story-${story_key}-codex-pir.md"
  local pir_report="$PIR_DIR/story-${story_key}-pir.md"

  log_step "PIR: $story_key"
  log_info "Step log: $step_log"

  mkdir -p "$PIR_DIR"

  # --- Gather context ---

  local story_title
  story_title=$(grep -m1 "^# " "$story_file" 2>/dev/null | sed 's/^# //' | tr -d '\r')
  if [[ -z "$story_title" ]]; then
    story_title="Story $story_key"
  fi

  # Find the synthesis report (evidence of what was actually built + reviewed)
  local synthesis_report="$PROJECT_ROOT/reviews/synthesis/${story_key}-synthesis-report.md"
  local synthesis_context=""
  if [[ -f "$synthesis_report" ]]; then
    synthesis_context="
SYNTHESIS REPORT (what was reviewed and fixed during implementation):
  File: ${synthesis_report}"
  fi

  # Find the codex code review (what Codex already found about the code)
  local codex_review="$PROJECT_ROOT/reviews/codex/story-${story_key}-codex-review.md"
  local codex_review_context=""
  if [[ -f "$codex_review" ]]; then
    codex_review_context="
CODEX CODE REVIEW (Codex's prior analysis of code quality — for reference):
  File: ${codex_review}"
  fi

  # Find source/test files from verify manifest
  local manifest_path="$LOG_DIR/${story_key}-verify-manifest.json"
  local file_context=""
  if [[ -f "$manifest_path" ]]; then
    local source_files test_files
    source_files=$("$PYTHON_BIN" -c "
import json, sys
m = json.load(open(sys.argv[1]))
print(' '.join(m.get('source_files', [])))
" "$(to_win_path "$manifest_path")" 2>/dev/null | tr -d '\r')
    test_files=$("$PYTHON_BIN" -c "
import json, sys
m = json.load(open(sys.argv[1]))
print(' '.join(m.get('test_files', [])))
" "$(to_win_path "$manifest_path")" 2>/dev/null | tr -d '\r')
    file_context="Source files: ${source_files}. Test files: ${test_files}."
  fi

  # Find prior PIR reports (so the review can see the trajectory)
  local prior_pirs=""
  local pir_file
  for pir_file in "$PIR_DIR"/story-*-pir.md; do
    [[ -f "$pir_file" ]] || continue
    [[ "$pir_file" == "$pir_report" ]] && continue
    prior_pirs="${prior_pirs}
  - ${pir_file}"
  done
  local prior_pir_context=""
  if [[ -n "$prior_pirs" ]]; then
    prior_pir_context="
PRIOR PIR REPORTS (alignment trajectory across earlier stories):${prior_pirs}"
  fi

  # Lessons learned
  local lessons_file="$PROJECT_ROOT/reviews/lessons-learned.md"
  local lessons_context=""
  if [[ -f "$lessons_file" ]]; then
    lessons_context="
LESSONS LEARNED (accumulated review findings):
  File: ${lessons_file}"
  fi

  # ===================================================================
  # PHASE 1: Codex — Adversarial Alignment Analysis
  # ===================================================================

  log_info "Phase 1: Codex alignment analysis..."

  local codex_available=true
  if ! command -v codex &>/dev/null; then
    log_warn "Codex CLI not installed — skipping Codex phase, Claude-only PIR"
    codex_available=false
  else
    local auth_status
    auth_status=$(codex login status 2>&1 | tr -d '\r')
    if [[ "$auth_status" != *"Logged in"* ]]; then
      log_warn "Codex not authenticated — skipping Codex phase, Claude-only PIR"
      codex_available=false
    fi
  fi

  if [[ "$codex_available" == "true" ]]; then
    local codex_prompt
    codex_prompt="You are conducting a Post-Implementation Review (PIR) for Story ${story_key}: ${story_title}.

This is NOT a code review. The code has already been reviewed and approved. Your job is to assess
whether what was built ACTUALLY SERVES THE SYSTEM'S OBJECTIVES.

== SYSTEM CONTEXT ==

The system is BMAD Backtester — a trading-system operating platform. Its core objectives are:
1. REPRODUCIBILITY — every run produces the same results given the same inputs
2. OPERATOR CONFIDENCE — a non-coder can drive the workflow with clear evidence at every stage
3. ARTIFACT COMPLETENESS — every stage emits saved, reviewable artifacts
4. FIDELITY — explicit tolerances and attribution for any divergence

V1 scope: one strategy family, one pair/timeframe, full path from hypothesis to go/no-go decision.
V1 is NOT gated on profitability — it's gated on reproducibility, evidence quality, and operator confidence.

== FILES TO READ ==

Story specification: ${story_file}
PRD (system objectives): ${PRD_FILE}
Architecture decisions: ${ARCH_FILE}
${file_context}${synthesis_context}${codex_review_context}

== YOUR THREE QUESTIONS ==

Answer these thoroughly, with specific evidence from the code and docs:

1. OBJECTIVE ALIGNMENT: Does what this story built advance the system's stated objectives
   (reproducibility, operator confidence, artifact completeness, fidelity)?
   - What specific objectives does it serve?
   - Is anything here that works AGAINST an objective (e.g., adds operator complexity)?
   - Does it fit V1 scope or is it over-engineered beyond V1 needs?

2. SIMPLIFICATION: Is there a simpler way to achieve the same outcome?
   - Are there unnecessary abstractions, over-engineering, or redundant mechanisms?
   - Could the same goal be achieved with less code or fewer moving parts?
   - Is anything built that isn't actually needed by any downstream consumer?

3. FORWARD LOOK: Does this story set up the next stories correctly?
   - Does the output contract give downstream stories what they actually need?
   - Is anything missing that downstream stories will need?
   - Are there assumptions baked in that might not hold as the pipeline grows?

== OUTPUT FORMAT ==

For each question, provide:
- Your assessment (STRONG / ADEQUATE / CONCERN)
- Specific evidence (file:line references or doc references)
- Concrete observations (not vague — specific things you noticed)

End with an OVERALL assessment: ALIGNED, OBSERVE (minor observations), or REVISIT (significant concerns)."

    local codex_output
    codex_output=$(codex exec --skip-git-repo-check \
      -m gpt-5.4 \
      --config model_reasoning_effort="high" \
      --sandbox read-only \
      "$codex_prompt" \
      2>/dev/null) || true

    if [[ -n "$codex_output" && ${#codex_output} -gt 100 ]]; then
      {
        echo "# Story ${story_key}: ${story_title} — Codex PIR"
        echo ""
        echo "**Reviewer:** Codex GPT-5.4 (high effort, read-only sandbox)"
        echo "**Date:** $(date +%Y-%m-%d)"
        echo "**Type:** Post-Implementation Review (alignment analysis)"
        echo ""
        echo "---"
        echo ""
        echo "$codex_output"
      } > "$codex_pir_file"
      log_success "Codex PIR complete — saved to $codex_pir_file"
    else
      log_warn "Codex PIR returned empty or minimal output"
      codex_available=false
    fi
  fi

  # ===================================================================
  # PHASE 2: Claude — Final PIR Judgment
  # ===================================================================

  log_info "Phase 2: Claude PIR synthesis..."

  local codex_pir_source=""
  if [[ "$codex_available" == "true" && -f "$codex_pir_file" ]]; then
    codex_pir_source="
CODEX PIR ASSESSMENT (Codex's alignment analysis — read this first):
  File: ${codex_pir_file}

IMPORTANT: Codex is a sparring partner, not an authority. You may agree or disagree
with any of Codex's observations. Evaluate each one independently against the PRD
and architecture. Do not blindly accept or reject — weigh the evidence."
  fi

  local pir_instruction
  read -r -d '' pir_instruction << PIR_EOF || true
AUTOMATED POST-IMPLEMENTATION REVIEW (PIR) — NO USER INTERACTION:

You are the final decision-maker for the PIR of Story ${story_key}: ${story_title}.

This is NOT a code review. The code works and tests pass. Your job is to assess whether
what was built actually serves the SYSTEM'S OBJECTIVES.

== CONTEXT FILES TO READ ==${codex_pir_source}

Story specification: ${story_file}
PRD (system objectives): ${PRD_FILE}
Architecture decisions: ${ARCH_FILE}${synthesis_context}${lessons_context}${prior_pir_context}
${file_context}

== YOUR PROCESS ==

1. READ the Codex PIR assessment (if available)
2. READ the story spec, PRD, and architecture doc
3. READ the actual source code for this story
4. For each of Codex's observations:
   a. If you AGREE: note it with your own supporting evidence
   b. If you DISAGREE: explain why with specific references
   c. Add any observations Codex missed
5. Assess the three PIR questions yourself:
   - OBJECTIVE ALIGNMENT: Does this serve reproducibility, operator confidence,
     artifact completeness, fidelity?
   - SIMPLIFICATION: Is there a simpler way?
   - FORWARD LOOK: Does this set up downstream stories correctly?

== PIR REPORT FORMAT ==

Write the report to: ${pir_report}

# PIR: Story ${story_key} — ${story_title}

## Codex Assessment Summary
[If available: key observations from Codex, with your agree/disagree for each]

## Objective Alignment
**Rating:** STRONG / ADEQUATE / CONCERN
[Which objectives does this story serve? Does anything work against an objective?]

## Simplification
**Rating:** STRONG / ADEQUATE / CONCERN
[Could this be simpler? Is anything over-engineered or unused?]

## Forward Look
**Rating:** STRONG / ADEQUATE / CONCERN
[Does the output contract serve downstream? Anything missing or assumed?]

## Observations for Future Stories
[Specific, actionable observations that should inform how future stories are written]

## Verdict
VERDICT: ALIGNED / OBSERVE / REVISIT

Criteria:
- ALIGNED: Story clearly serves system objectives, no significant concerns
- OBSERVE: Story serves objectives but has minor observations worth noting for future stories
- REVISIT: Significant concerns about alignment — flag to operator with evidence
PIR_EOF

  local exit_code=0
  claude --print \
    --permission-mode bypassPermissions \
    --allowedTools "Read,Bash,Glob,Grep" \
    --append-system-prompt "$pir_instruction" \
    "Conduct the Post-Implementation Review for Story ${story_key}. Read the Codex PIR (if available), the story spec, PRD, architecture, and source code. Write your PIR report." \
    > "$step_log" 2>&1 || exit_code=$?

  if [[ $exit_code -ne 0 ]]; then
    log_error "PIR step crashed for $story_key (exit code: $exit_code)"
    return 1
  fi

  # Parse the verdict
  local verdict
  verdict=$(grep -oP 'VERDICT:\s*\K\w+' "$step_log" | tail -1 || true)

  # Also try the report file if log didn't have it
  if [[ -z "$verdict" && -f "$pir_report" ]]; then
    verdict=$(grep -oP 'VERDICT:\s*\K\w+' "$pir_report" | tail -1 || true)
  fi

  case "$verdict" in
    ALIGNED)
      log_success "PIR ALIGNED for $story_key — story serves system objectives"
      return 0
      ;;
    OBSERVE)
      log_success "PIR OBSERVE for $story_key — aligned with minor observations"
      if [[ -f "$pir_report" ]]; then
        local observations
        observations=$(grep -A3 "## Observations" "$pir_report" | tail -3 || true)
        if [[ -n "$observations" ]]; then
          log_info "Observations: $observations"
        fi
      fi
      return 0
      ;;
    REVISIT)
      log_warn "PIR REVISIT for $story_key — significant alignment concerns flagged"
      log_warn "Review the PIR report: $pir_report"
      return 1
      ;;
    *)
      log_warn "Could not parse PIR verdict (got: '$verdict') — treating as OBSERVE"
      return 0
      ;;
  esac
}
