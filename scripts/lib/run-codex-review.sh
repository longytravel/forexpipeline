#!/usr/bin/env bash
# Step 3b: Codex Review — independent second-opinion code review via OpenAI Codex CLI
# Non-blocking: runs alongside BMAD review, output saved to reviews/codex/
# Does NOT gate the pipeline — informational only

# Run the Codex review step for a story
# Usage: run_codex_review_step "story-key" "/path/to/story.md"
# Returns: 0 always (non-blocking), logs warnings on failure
run_codex_review_step() {
  local story_key="$1"
  local story_file="$2"
  local review_dir="$PROJECT_ROOT/reviews/codex"
  local output_file="$review_dir/story-${story_key}-codex-review.md"
  local step_log="$LOG_DIR/${story_key}-codex-review-$(date +%H%M%S).log"

  log_step "CODEX REVIEW: $story_key"
  log_info "Output: $output_file"
  log_info "Step log: $step_log"

  # Check codex is available
  if ! command -v codex &>/dev/null; then
    log_warn "Codex CLI not installed — skipping Codex review"
    return 0
  fi

  # Check codex auth
  local auth_status
  auth_status=$(codex login status 2>&1 | tr -d '\r')
  if [[ "$auth_status" != *"Logged in"* ]]; then
    log_warn "Codex not authenticated — skipping Codex review"
    return 0
  fi

  mkdir -p "$review_dir"

  # Read the story file to extract title and key info for the prompt
  local story_title
  story_title=$(grep -m1 "^# " "$story_file" 2>/dev/null | sed 's/^# //' | tr -d '\r')
  if [[ -z "$story_title" ]]; then
    story_title="Story $story_key"
  fi

  # Build the manifest path to find source/test files
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
    file_context="Main source files: ${source_files}. Test files: ${test_files}."
  fi

  # Build the Codex prompt
  local codex_prompt
  codex_prompt="Perform a thorough code review of Story ${story_key}: ${story_title}.

The story specification is at: ${story_file}
${file_context}

Review against the story's acceptance criteria. For each criterion, assess: Fully Met, Partially Met, or Not Met.

Focus on:
1. Acceptance criteria compliance — does the code actually satisfy each AC?
2. Logic bugs — off-by-one errors, edge cases, incorrect thresholds
3. Data integrity — are computed values used or silently discarded?
4. Test coverage gaps — what important paths are untested?

Output format:
- HIGH findings (bugs, AC violations) with specific file:line references
- MEDIUM findings (quality, correctness concerns)
- Acceptance Criteria Scorecard table
- Test Coverage Gaps section
- Summary with counts: X of Y criteria fully met, Z partially, W not met"

  # Execute codex in read-only sandbox
  log_info "Running Codex review (this may take a few minutes)..."
  local codex_output
  codex_output=$(codex exec --skip-git-repo-check \
    -m gpt-5.4 \
    --config model_reasoning_effort="high" \
    --sandbox read-only \
    "$codex_prompt" \
    2>/dev/null) || true

  # Check if we got meaningful output
  if [[ -z "$codex_output" || ${#codex_output} -lt 100 ]]; then
    log_warn "Codex review returned empty or minimal output for $story_key"
    echo "Codex review failed or returned empty output at $(date)" > "$step_log"
    return 0
  fi

  # Write the review file with header
  {
    echo "# Story ${story_key}: ${story_title} — Codex Review"
    echo ""
    echo "**Reviewer:** Codex GPT-5.4 (high effort, read-only sandbox)"
    echo "**Date:** $(date +%Y-%m-%d)"
    echo "**Method:** Static analysis (no pytest execution — sandbox policy)"
    echo "**Pipeline Stage:** Automated (non-blocking second opinion)"
    echo ""
    echo "---"
    echo ""
    echo "$codex_output"
  } > "$output_file"

  # Also save raw output to step log
  echo "$codex_output" > "$step_log"

  local finding_count
  finding_count=$(echo "$codex_output" | grep -ci "high\|critical" 2>/dev/null || echo "0")

  log_success "Codex review complete for $story_key — saved to $output_file"
  if [[ "$finding_count" -gt 0 ]]; then
    log_info "Codex found ~$finding_count HIGH/CRITICAL references (review saved, non-blocking)"
  fi

  return 0
}
