#!/usr/bin/env bash
# Sprint status parsing utilities

# Get current status of a story from sprint-status.yaml
get_story_status() {
  local story_key="$1"
  grep -P "^\s+${story_key}:" "$SPRINT_STATUS" | sed 's/.*:\s*//' | tr -d ' \r' || true
}

# Check if a story can be started (ready-for-dev, in-progress for resume, or review for review pipeline)
can_start_story() {
  local status
  status=$(get_story_status "$1")
  [[ "$status" == "ready-for-dev" || "$status" == "in-progress" || "$status" == "review" ]]
}

# Check if a story is already done
is_story_done() {
  local status
  status=$(get_story_status "$1")
  [[ "$status" == "done" ]]
}

# Validate dependencies: story X.N requires X.(N-1) to be at least review/done
check_dependencies() {
  local story_key="$1"
  local epic_num story_num story_num_base story_num_suffix
  epic_num=$(echo "$story_key" | cut -d'-' -f1)
  story_num=$(echo "$story_key" | cut -d'-' -f2)
  story_num_base=$(echo "$story_num" | sed 's/[^0-9]//g')
  story_num_suffix=$(echo "$story_num" | sed 's/[0-9]//g')

  # Sub-stories (e.g., 5-2b) depend on the base story (e.g., 5-2)
  if [[ -n "$story_num_suffix" ]]; then
    local prev_key
    prev_key=$(get_full_story_key "${epic_num}-${story_num_base}")
  else
    # First few stories in an epic have no intra-epic dependencies
    if [[ "$story_num_base" -le 3 ]]; then
      return 0
    fi

    local prev_key
    prev_key=$(get_full_story_key "${epic_num}-$((story_num_base - 1))")
  fi

  if [[ -z "$prev_key" ]]; then
    log_warn "Could not find predecessor story ${epic_num}-${prev_num} in sprint-status.yaml"
    return 1
  fi

  local prev_status
  prev_status=$(get_story_status "$prev_key")

  if [[ "$prev_status" == "done" || "$prev_status" == "review" ]]; then
    return 0
  else
    log_error "Dependency not met: $prev_key is '$prev_status' (needs 'review' or 'done')"
    return 1
  fi
}

# List all stories with a given status
list_stories_by_status() {
  local target_status="$1"
  grep -oP '^\s+\d+-\d+-[a-z0-9-]+(?=:\s+'"$target_status"')' "$SPRINT_STATUS" | tr -d ' ' || true
}
