#!/usr/bin/env bash
# Sprint status update utilities

# Update a story's status in sprint-status.yaml
update_story_status() {
  local story_key="$1"
  local new_status="$2"

  if [[ ! -f "$SPRINT_STATUS" ]]; then
    log_error "sprint-status.yaml not found at $SPRINT_STATUS"
    return 1
  fi

  sed -i "s/\(${story_key}:\s*\).*/\1${new_status}/" "$SPRINT_STATUS"

  local today
  today=$(date +%Y-%m-%d)
  sed -i "s/\(last_updated:\s*\).*/\1${today}/" "$SPRINT_STATUS"

  log_info "Sprint status updated: $story_key -> $new_status"
}

# Mark a story as done
mark_story_done() {
  local story_key="$1"
  update_story_status "$story_key" "done"
  log_success "Story $story_key marked DONE"
}

# Check if all stories in an epic are done; if so mark epic done
check_epic_completion() {
  local epic_num="$1"
  local all_done=true

  local story_keys
  story_keys=$(grep -oP "^\s+${epic_num}-\d+-[a-z0-9-]+(?=:)" "$SPRINT_STATUS" | tr -d ' ' || true)

  for key in $story_keys; do
    local status
    status=$(get_story_status "$key")
    if [[ "$status" != "done" ]]; then
      all_done=false
      break
    fi
  done

  if [[ "$all_done" == "true" ]]; then
    update_story_status "epic-${epic_num}" "done"
    log_success "Epic $epic_num completed! All stories done."
  fi
}
