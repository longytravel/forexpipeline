#!/usr/bin/env bash
# Step 4: Review Synthesis — Claude reads both BMAD and Codex reviews, decides what to fix
#
# This is where the actual code fixes happen. Claude acts as the final decision-maker:
# - Reads both review reports (BMAD + Codex)
# - Identifies findings it agrees with
# - Discards findings it disagrees with (with reasoning)
# - Fixes agreed-upon CRITICAL/HIGH issues in the code
# - Re-runs tests to verify fixes
# - Produces a synthesis report and final verdict

# Run the review synthesis step
# Usage: run_synthesis_step "story-key" "/path/to/story.md" "bmad-review.log" "codex-review.md"
# Returns: 0 on approved, 1 on changes required, 2 on blocked
# Sets SYNTHESIS_FAILURE_CONTEXT on failure
run_synthesis_step() {
  local story_key="$1"
  local story_file="$2"
  local bmad_log="$3"
  local codex_file="$4"
  local step_log="$LOG_DIR/${story_key}-synthesis-$(date +%H%M%S).log"
  local synthesis_report="$PROJECT_ROOT/reviews/synthesis/${story_key}-synthesis-report.md"
  SYNTHESIS_FAILURE_CONTEXT=""

  log_step "REVIEW SYNTHESIS: $story_key"
  log_info "BMAD review: $bmad_log"
  log_info "Codex review: $codex_file"
  log_info "Step log: $step_log"

  # Determine which reviews are available
  local has_bmad=false
  local has_codex=false

  if [[ -f "$bmad_log" ]] && [[ $(wc -l < "$bmad_log" | tr -d ' \r') -gt 10 ]]; then
    has_bmad=true
  fi
  if [[ -f "$codex_file" ]] && [[ $(wc -l < "$codex_file" | tr -d ' \r') -gt 10 ]]; then
    has_codex=true
  fi

  if [[ "$has_bmad" == "false" && "$has_codex" == "false" ]]; then
    log_error "No review data available for synthesis"
    SYNTHESIS_FAILURE_CONTEXT="Neither BMAD nor Codex review produced usable output. Re-run reviews."
    export SYNTHESIS_FAILURE_CONTEXT
    return 1
  fi

  # Build the synthesis prompt with paths to both reviews
  local review_sources=""
  if [[ "$has_bmad" == "true" ]]; then
    review_sources="${review_sources}
BMAD REVIEW (Claude code-review workflow):
  File: ${bmad_log}
  Read this file to see BMAD's findings, severity ratings, and AC scorecard."
  fi
  if [[ "$has_codex" == "true" ]]; then
    review_sources="${review_sources}

CODEX REVIEW (OpenAI GPT-5.4, independent read-only analysis):
  File: ${codex_file}
  Read this file to see Codex's findings, severity ratings, and AC scorecard."
  fi

  local synthesis_instruction
  read -r -d '' synthesis_instruction << SYNTH_EOF || true
AUTOMATED REVIEW SYNTHESIS — NO USER INTERACTION:

You are the final decision-maker. Two independent code reviewers have analyzed Story ${story_key}.
Your job is to read both reviews, synthesize them, and fix what needs fixing.

== REVIEW SOURCES ==${review_sources}

== YOUR PROCESS ==

1. READ both review reports (use the Read tool on the file paths above)
2. READ the story spec: ${story_file}
3. For each finding from either reviewer:
   a. If you AGREE it's a real issue: note it as ACCEPTED and fix it
   b. If you DISAGREE: note it as REJECTED with your reasoning
   c. If both reviewers flag the same issue: strong signal — prioritize it
   d. If only one reviewer flags it: evaluate independently
4. For ACCEPTED findings:
   - CRITICAL/HIGH: Fix automatically in the code
   - MEDIUM: Fix if straightforward, otherwise note as action item
   - LOW: Note as action item only
5. After all fixes, run the test suite: pytest tests/ -x
6. If tests fail after your fixes, fix the regression
7. Write a synthesis report to: ${synthesis_report}

== SYNTHESIS REPORT FORMAT ==

Write the report with these sections:
# Review Synthesis: Story ${story_key}
## Reviews Analyzed
- BMAD: [available/unavailable]
- Codex: [available/unavailable]

## Accepted Findings (fixes applied)
[For each: source (BMAD/Codex/Both), severity, description, what you fixed]

## Rejected Findings (disagreed)
[For each: source, severity, description, why you rejected it]

## Action Items (deferred)
[MEDIUM/LOW items not fixed now]

## Test Results
[paste pytest summary after fixes]

## Verdict
[APPROVED/CHANGES_REQUIRED/BLOCKED with reasoning]

== VERDICT ==

Output your final verdict as the LAST LINE:
VERDICT: APPROVED
or
VERDICT: CHANGES_REQUIRED
or
VERDICT: BLOCKED

== REQUIREMENT: REGRESSION TESTS ==

For each ACCEPTED finding that you fix, also write a regression test that would
have caught the original bug. Place it in the appropriate test file with the
marker @pytest.mark.regression. These tests ensure the same class of bug never
recurs.

Example: If you fix "gap_severity computed then discarded", write
test_gap_severity_affects_report() that asserts gap_severity appears in the
quality report and affects can_proceed.

== REQUIREMENT: LESSONS LEARNED ==

After writing your synthesis report, append a summary of ACCEPTED findings to:
  ${PROJECT_ROOT}/reviews/lessons-learned.md

Format each entry as:

## Story ${story_key}
- ACCEPTED (source): description of finding
  → Rule: the generalized lesson/rule derived from this finding

Create the file if it doesn't exist (with a "# Lessons Learned" header).
Append to it if it does — never overwrite existing content.
SYNTH_EOF

  # Execute claude --print for synthesis
  local exit_code=0
  claude --print \
    --permission-mode bypassPermissions \
    --allowedTools "Read,Edit,Write,Bash,Glob,Grep" \
    --append-system-prompt "$synthesis_instruction" \
    "Synthesize the code reviews for Story ${story_key} and fix accepted findings. Start by reading both review files and the story spec." \
    > "$step_log" 2>&1 || exit_code=$?

  if [[ $exit_code -ne 0 ]]; then
    log_error "Synthesis step crashed for $story_key (exit code: $exit_code)"
    SYNTHESIS_FAILURE_CONTEXT="Review synthesis crashed (exit $exit_code). Check $step_log."
    export SYNTHESIS_FAILURE_CONTEXT
    return 1
  fi

  # Guard: detect empty/trivial output (claude session produced nothing useful)
  local log_size
  log_size=$(wc -c < "$step_log" | tr -d ' \r')
  if [[ "$log_size" -lt 200 ]]; then
    log_warn "Synthesis session produced minimal output (${log_size} bytes) — treating as transient failure"
    SYNTHESIS_FAILURE_CONTEXT="Claude synthesis session produced empty/minimal output (${log_size} bytes). Likely transient — retry with backoff."
    export SYNTHESIS_FAILURE_CONTEXT
    return 1
  fi

  # Parse the verdict
  local verdict
  verdict=$(grep -oP 'VERDICT:\s*\*{0,2}\K\w+' "$step_log" | tail -1 || true)

  case "$verdict" in
    APPROVED)
      log_success "Review synthesis APPROVED for $story_key"
      # Check if synthesis report was written
      if [[ -f "$synthesis_report" ]]; then
        log_info "Synthesis report: $synthesis_report"
      fi
      return 0
      ;;
    CHANGES_REQUIRED)
      log_warn "Synthesis requires more changes for $story_key"
      local findings
      # Use -m to limit matches — avoids grep|tail pipe which causes SIGPIPE daemon kills on MSYS2
      findings=$(grep -A2 -i -m 10 "critical\|high\|accepted" "$step_log" 2>/dev/null || true)
      SYNTHESIS_FAILURE_CONTEXT="REVIEW SYNTHESIS — CHANGES STILL REQUIRED:

Key remaining issues:
$findings

Fix these issues, ensure all tests pass, and ensure live tests cover the fixes."
      export SYNTHESIS_FAILURE_CONTEXT
      return 1
      ;;
    BLOCKED)
      log_error "Synthesis BLOCKED for $story_key"
      SYNTHESIS_FAILURE_CONTEXT="REVIEW SYNTHESIS BLOCKED: Issues require manual intervention. Check $step_log."
      export SYNTHESIS_FAILURE_CONTEXT
      return 2
      ;;
    *)
      # Fallback: check story status
      local current_status
      current_status=$(get_story_status "$story_key" 2>/dev/null)
      if [[ "$current_status" == "done" ]]; then
        log_success "Story status is 'done' — treating as APPROVED"
        return 0
      fi
      log_warn "Could not parse synthesis verdict (got: '$verdict') — treating as changes required"
      SYNTHESIS_FAILURE_CONTEXT="Review synthesis completed but verdict unclear. Re-review needed."
      export SYNTHESIS_FAILURE_CONTEXT
      return 1
      ;;
  esac
}
