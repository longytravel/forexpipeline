#!/usr/bin/env bash
# Step 2: Verify Write — check story file quality and completeness

WRITE_VERIFY_FAILURE_CONTEXT=""

# Required sections in a story file (grep patterns)
REQUIRED_WRITE_SECTIONS=(
  "## Story"
  "## Acceptance Criteria"
  "## Tasks"
  "## Dev Notes"
)

# Minimum line count for a proper story file
MIN_STORY_LINES=50

# Verify a written story file
# Usage: verify_write_step "2-1-strategy-evaluator-review"
# Returns: 0 on success, 1 on failure
# Sets WRITE_VERIFY_FAILURE_CONTEXT on failure
verify_write_step() {
  local story_key="$1"
  WRITE_VERIFY_FAILURE_CONTEXT=""

  log_step "VERIFY-WRITE: $story_key"

  # Find the story file
  local story_file
  story_file=$(get_story_file "$story_key")

  if [[ -z "$story_file" || ! -f "$story_file" ]]; then
    WRITE_VERIFY_FAILURE_CONTEXT="Story file not found for $story_key in $STORY_DIR.
The write step must create a file matching pattern: ${STORY_DIR}/${story_key}*.md"
    export WRITE_VERIFY_FAILURE_CONTEXT
    log_error "Story file not found for $story_key"
    return 1
  fi

  log_info "Checking: $story_file"

  # --- Check required sections ---
  local missing_sections=()
  for section in "${REQUIRED_WRITE_SECTIONS[@]}"; do
    if ! grep -q "$section" "$story_file" 2>/dev/null; then
      missing_sections+=("$section")
    fi
  done

  if [[ ${#missing_sections[@]} -gt 0 ]]; then
    WRITE_VERIFY_FAILURE_CONTEXT="Story file missing required sections: ${missing_sections[*]}
File: $story_file
The story MUST include all of: ${REQUIRED_WRITE_SECTIONS[*]}"
    export WRITE_VERIFY_FAILURE_CONTEXT
    log_error "Missing sections: ${missing_sections[*]}"
    return 1
  fi
  log_success "All required sections present"

  # --- Check minimum content length ---
  local line_count
  line_count=$(wc -l < "$story_file" | tr -d ' \r')
  if [[ $line_count -lt $MIN_STORY_LINES ]]; then
    WRITE_VERIFY_FAILURE_CONTEXT="Story file too short: $line_count lines (minimum: $MIN_STORY_LINES).
File: $story_file
The story needs comprehensive developer context — acceptance criteria, tasks, dev notes, references."
    export WRITE_VERIFY_FAILURE_CONTEXT
    log_error "Too short: $line_count lines (need $MIN_STORY_LINES)"
    return 1
  fi
  log_success "Content length OK ($line_count lines)"

  # --- Check acceptance criteria count ---
  # Match numbered items like "1. **Given**" or "1. Given" or just "1. "
  local ac_count
  ac_count=$(grep -cP '^\d+\.\s+' "$story_file" 2>/dev/null || true)
  if [[ ${ac_count:-0} -lt 3 ]]; then
    WRITE_VERIFY_FAILURE_CONTEXT="Too few acceptance criteria: found ${ac_count:-0} (minimum: 3).
File: $story_file
Stories need at least 3 numbered acceptance criteria in Gherkin format."
    export WRITE_VERIFY_FAILURE_CONTEXT
    log_error "Too few acceptance criteria: ${ac_count:-0}"
    return 1
  fi
  log_success "Acceptance criteria OK ($ac_count)"

  # --- Check tasks exist (checkbox format) ---
  local task_count
  task_count=$(grep -cP '^\s*-\s+\[[ x]\]' "$story_file" 2>/dev/null || true)
  if [[ ${task_count:-0} -lt 2 ]]; then
    WRITE_VERIFY_FAILURE_CONTEXT="Too few tasks: found ${task_count:-0} (minimum: 2).
File: $story_file
Stories need a detailed task breakdown with subtasks in checkbox format."
    export WRITE_VERIFY_FAILURE_CONTEXT
    log_error "Too few tasks: ${task_count:-0}"
    return 1
  fi
  log_success "Task count OK ($task_count)"

  # --- Ensure sprint-status is ready-for-dev ---
  local status
  status=$(get_story_status "$story_key")
  if [[ "$status" != "ready-for-dev" ]]; then
    log_warn "Sprint status is '$status', not 'ready-for-dev' — updating now"
    update_story_status "$story_key" "ready-for-dev"
  fi

  log_success "Verify-write passed for $story_key"
  return 0
}
