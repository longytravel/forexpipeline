#!/usr/bin/env bash
# Step 3a: BMAD Code Review — invoke claude --print with code-review workflow
# Produces findings report only — no auto-fixes. Synthesis step handles fixes.

# Run the BMAD code review step for a story
# Usage: run_review_step "story-key" "/path/to/story.md"
# Returns: 0 on success (findings produced), 1 on crash
# Sets BMAD_REVIEW_LOG to the log file path
run_review_step() {
  local story_key="$1"
  local story_file="$2"
  BMAD_REVIEW_LOG="$LOG_DIR/${story_key}-review-$(date +%H%M%S).log"
  export BMAD_REVIEW_LOG

  log_step "BMAD REVIEW: $story_key"
  log_info "Step log: $BMAD_REVIEW_LOG"

  # Findings-only mode — no auto-fixes, just produce the report
  local review_instruction
  read -r -d '' review_instruction << 'REVIEW_EOF' || true
AUTOMATED REVIEW MODE — FINDINGS ONLY (NO FIXES):

You are running in fully automated mode. There is no user to ask questions to.
NEVER present menus, prompts, or ask the user to choose anything.
NEVER output "Choose [1] or [2]" or any selection prompt.

CRITICAL WORKFLOW OVERRIDES:
- TEAM MODE CHECK: SKIP ENTIRELY. Use Single Reviewer mode. Do NOT output the
  review mode selection prompt. Proceed directly to EXECUTION steps.
- Fix vs Action Items: Always choose Action Items only.
- Do NOT ask which story to review — use the one provided in the prompt.

Your job is to produce a thorough findings report. Do NOT fix any code.
Do NOT edit any files. Only READ and ANALYZE.

For each finding, include:
- Severity: CRITICAL, HIGH, MEDIUM, or LOW
- Description of the issue
- Specific file:line references
- What the correct behavior should be

Also produce an Acceptance Criteria scorecard:
- For each AC in the story, assess: Fully Met, Partially Met, or Not Met
- Include file:line evidence for each assessment

IMPORTANT: Output your final verdict as the LAST LINE of your response in this EXACT format:
VERDICT: APPROVED
or
VERDICT: CHANGES_REQUIRED
or
VERDICT: BLOCKED
REVIEW_EOF

  # Execute claude --print for code review
  local exit_code=0
  claude --print \
    --permission-mode bypassPermissions \
    --allowedTools "Read,Bash,Glob,Grep,Skill" \
    --append-system-prompt "$review_instruction" \
    "/bmad-code-review ${story_file}" \
    > "$BMAD_REVIEW_LOG" 2>&1 || exit_code=$?

  if [[ $exit_code -ne 0 ]]; then
    log_error "BMAD review crashed for $story_key (exit code: $exit_code)"
    return 1
  fi

  # Check we got meaningful output
  local line_count
  line_count=$(wc -l < "$BMAD_REVIEW_LOG" | tr -d ' \r')
  if [[ "$line_count" -lt 10 ]]; then
    log_warn "BMAD review produced very little output ($line_count lines)"
    return 1
  fi

  local verdict
  verdict=$(grep -oP 'VERDICT:\s*\K\w+' "$BMAD_REVIEW_LOG" | tail -1 || true)
  log_success "BMAD review complete for $story_key (verdict: ${verdict:-unknown})"
  return 0
}
