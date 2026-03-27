#!/usr/bin/env bash
set -euo pipefail

# =============================================================================
# Story Writer — Automated BMAD story creation pipeline
# Breakdown → Write → Verify → Codex Review → Synthesis → Post-Verify → Done
#
# Features:
#   --epic N       Process all stories for an epic (runs breakdown if needed)
#   --breakdown N  Break an epic into stories only (no story file creation)
#   --daemon       Run detached from terminal (no timeout)
#   --status       Poll current writer status
#   --follow       Follow writer progress until completion
#   --stop         Stop a running writer
#   Smart skip     Skips write if story file already exists and is valid
# =============================================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ORIGINAL_ARGS=("$@")

source "$SCRIPT_DIR/lib/common.sh"
source "$SCRIPT_DIR/lib/parse-sprint.sh"
source "$SCRIPT_DIR/lib/run-breakdown.sh"
source "$SCRIPT_DIR/lib/run-write.sh"
source "$SCRIPT_DIR/lib/verify-write.sh"
source "$SCRIPT_DIR/lib/run-story-review.sh"
source "$SCRIPT_DIR/lib/run-story-synthesis.sh"
source "$SCRIPT_DIR/lib/update-status.sh"

# Override paths for writer (avoid conflicts with story runner)
LOG_DIR="$PROJECT_ROOT/logs/story-writer"
PID_FILE="$LOG_DIR/writer.pid"
STATUS_FILE="$LOG_DIR/writer-status.json"

# --- Usage ---
usage() {
  cat <<'EOF'
Story Writer — Automated BMAD story creation pipeline

Usage: write-stories.sh [OPTIONS] <story-keys...>
       write-stories.sh --epic <N>
       write-stories.sh --breakdown <N>

Arguments:
  story-keys    Space-separated story keys (e.g., "2-1 2-2 2-3")
                Accepts short keys (2-1) or full keys (2-1-strategy-review)

Options:
  --epic N         Process all stories for epic N (breakdown + write all)
  --breakdown N    Break epic N into stories only (add to epics.md + sprint-status)
  --max-retries N  Max retries per story (default: 2)
  --gap N          Minutes to wait between stories (default: 0, avoids subscription limits)
  --dry-run        Show what would run without executing
  --daemon         Run detached from terminal (no timeout)
  --status         Show status of running writer
  --follow         Follow writer progress until completion (poll every 30s)
  --stop           Stop a running writer
  --help           Show this help

Examples:
  write-stories.sh --epic 2                    Break down + write all Epic 2 stories
  write-stories.sh --breakdown 2               Just break Epic 2 into stories
  write-stories.sh --daemon --epic 2           Run detached (no timeout)
  write-stories.sh --daemon --gap 45 5-3 5-4   45-min gap between stories
  write-stories.sh 2-1 2-2                     Write specific stories (short keys)
  write-stories.sh --status                    Check writer progress
  write-stories.sh --follow                    Follow until completion
EOF
}

# --- Handle --status (early exit, no args needed) ---
if [[ "${1:-}" == "--status" ]]; then
  mkdir -p "$LOG_DIR"
  if [[ ! -f "$PID_FILE" ]]; then
    echo "No writer active (no PID file)"
    exit 0
  fi
  pid=$(cat "$PID_FILE")
  if kill -0 "$pid" 2>/dev/null; then
    echo "Writer ACTIVE (PID $pid)"
    if [[ -f "$STATUS_FILE" ]]; then
      cat "$STATUS_FILE"
    fi
  else
    echo "Writer NOT running (stale PID $pid)"
    rm -f "$PID_FILE" "$STATUS_FILE"
  fi
  exit 0
fi

# --- Handle --follow (poll until completion) ---
if [[ "${1:-}" == "--follow" ]]; then
  mkdir -p "$LOG_DIR"
  POLL_INTERVAL="${2:-30}"
  if [[ ! -f "$PID_FILE" ]]; then
    echo "No writer active (no PID file)"
    exit 0
  fi
  last_step=""
  last_detail=""
  echo "Following writer progress (poll every ${POLL_INTERVAL}s) — Ctrl+C to detach"
  echo ""
  while true; do
    pid=$(cat "$PID_FILE" 2>/dev/null || true)
    if [[ -z "$pid" ]] || ! kill -0 "$pid" 2>/dev/null; then
      # Writer finished — show final status
      if [[ -f "$STATUS_FILE" ]]; then
        final_step=$(grep -oP '"step":"[^"]*"' "$STATUS_FILE" | cut -d'"' -f4)
        final_story=$(grep -oP '"story_key":"[^"]*"' "$STATUS_FILE" | cut -d'"' -f4)
        if [[ "$final_step" == "done" ]]; then
          echo -e "\033[0;32m[DONE]\033[0m $(date +%H:%M:%S) Story $final_story written successfully!"
        elif [[ "$final_step" == "failed" ]]; then
          echo -e "\033[0;31m[FAIL]\033[0m $(date +%H:%M:%S) Story $final_story failed"
        else
          echo -e "\033[1;33m[EXIT]\033[0m $(date +%H:%M:%S) Writer exited (last step: $final_step)"
        fi
      fi
      rm -f "$PID_FILE" "$STATUS_FILE"
      echo ""
      echo "Writer finished."
      exit 0
    fi
    # Read current status
    if [[ -f "$STATUS_FILE" ]]; then
      cur_step=$(grep -oP '"step":"[^"]*"' "$STATUS_FILE" | cut -d'"' -f4)
      cur_detail=$(grep -oP '"detail":"[^"]*"' "$STATUS_FILE" | cut -d'"' -f4)
      cur_story=$(grep -oP '"story_key":"[^"]*"' "$STATUS_FILE" | cut -d'"' -f4)
      cur_time=$(grep -oP '"timestamp":"[^"]*"' "$STATUS_FILE" | cut -d'"' -f4)
      # Only print on step/detail change
      if [[ "$cur_step" != "$last_step" || "$cur_detail" != "$last_detail" ]]; then
        detail_suffix=""
        [[ -n "$cur_detail" ]] && detail_suffix=" ($cur_detail)"
        echo -e "\033[0;34m[INFO]\033[0m $cur_time  $cur_story → \033[1m$cur_step\033[0m$detail_suffix"
        last_step="$cur_step"
        last_detail="$cur_detail"
      fi
    fi
    sleep "$POLL_INTERVAL"
  done
fi

# --- Handle --stop (early exit) ---
if [[ "${1:-}" == "--stop" ]]; then
  mkdir -p "$LOG_DIR"
  if [[ ! -f "$PID_FILE" ]]; then
    echo "No writer active"
    exit 0
  fi
  pid=$(cat "$PID_FILE")
  if kill -0 "$pid" 2>/dev/null; then
    kill "$pid" 2>/dev/null || true
    echo "Sent SIGTERM to PID $pid"
    sleep 2
    if kill -0 "$pid" 2>/dev/null; then
      kill -9 "$pid" 2>/dev/null || true
      echo "Force killed PID $pid"
    fi
  fi
  rm -f "$PID_FILE" "$STATUS_FILE"
  echo "Writer stopped"
  exit 0
fi

# --- Argument parsing ---
STORY_KEYS=()
EPIC_NUM=""
BREAKDOWN_ONLY=""
DRY_RUN=false
DAEMON_MODE=false
GAP_MINUTES=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --epic)           EPIC_NUM="$2"; shift 2 ;;
    --breakdown)      BREAKDOWN_ONLY="$2"; shift 2 ;;
    --max-retries)    MAX_RETRIES_PER_STORY="$2"; shift 2 ;;
    --gap)            GAP_MINUTES="$2"; shift 2 ;;
    --dry-run)        DRY_RUN=true; shift ;;
    --daemon)         DAEMON_MODE=true; shift ;;
    --help|-h)        usage; exit 0 ;;
    -*)               echo "Unknown option: $1"; usage; exit 1 ;;
    *)                STORY_KEYS+=("$1"); shift ;;
  esac
done

# Validate arguments
if [[ -z "$EPIC_NUM" && -z "$BREAKDOWN_ONLY" && ${#STORY_KEYS[@]} -eq 0 ]]; then
  echo "Error: Provide --epic N, --breakdown N, or story keys"
  usage
  exit 1
fi

# --- Daemon mode: re-exec detached ---
if [[ "$DAEMON_MODE" == "true" && "${_WRITER_DAEMONIZED:-}" != "1" ]]; then
  mkdir -p "$LOG_DIR"
  # Check for existing writer
  if [[ -f "$PID_FILE" ]] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
    echo "ERROR: Writer already active (PID $(cat "$PID_FILE"))"
    echo "Use --stop to kill it first, or --status to check progress"
    exit 1
  fi
  # Re-exec as detached process
  export _WRITER_DAEMONIZED=1
  FG_LOG="$LOG_DIR/daemon-$(date +%Y%m%d-%H%M%S).log"
  # Strip --daemon from args for the re-exec
  REEXEC_ARGS=()
  for arg in "${ORIGINAL_ARGS[@]}"; do
    [[ "$arg" != "--daemon" ]] && REEXEC_ARGS+=("$arg")
  done
  nohup bash "$SCRIPT_DIR/write-stories.sh" "${REEXEC_ARGS[@]}" > "$FG_LOG" 2>&1 &
  DAEMON_PID=$!
  echo "$DAEMON_PID" > "$PID_FILE"
  echo ""
  echo "Writer daemonized (PID $DAEMON_PID)"
  echo "  Follow:  bash scripts/write-stories.sh --follow"
  echo "  Status:  bash scripts/write-stories.sh --status"
  echo "  Stop:    bash scripts/write-stories.sh --stop"
  echo "  Log:     $FG_LOG"
  echo ""
  exit 0
fi

# --- Initialize ---
init_logging

# PID/status cleanup on exit (daemon or foreground)
if [[ "${_WRITER_DAEMONIZED:-}" == "1" ]]; then
  echo $$ > "$PID_FILE"
  trap 'write_runner_status "" "exited" ""; rm -f "$PID_FILE"' EXIT
fi

echo ""
echo -e "${BOLD}=========================================${NC}"
echo -e "${BOLD}  Story Writer — Forex Pipeline${NC}"
echo -e "${BOLD}=========================================${NC}"
echo ""
log_info "Max retries per story: $MAX_RETRIES_PER_STORY"

# --- Handle --breakdown only ---
if [[ -n "$BREAKDOWN_ONLY" ]]; then
  write_runner_status "" "breakdown" "epic $BREAKDOWN_ONLY"
  if [[ "$DRY_RUN" == "true" ]]; then
    log_info "DRY RUN — would break Epic $BREAKDOWN_ONLY into stories"
    exit 0
  fi
  if ! run_breakdown_step "$BREAKDOWN_ONLY"; then
    log_error "Breakdown failed for Epic $BREAKDOWN_ONLY"
    exit 1
  fi
  log_success "Breakdown complete for Epic $BREAKDOWN_ONLY"
  echo ""
  log_info "Stories registered:"
  get_epic_story_keys "$BREAKDOWN_ONLY" | while IFS= read -r key; do
    key="${key%$'\r'}"
    [[ -n "$key" ]] && log_info "  - $key"
  done
  echo ""
  log_info "Next: bash scripts/write-stories.sh --epic $BREAKDOWN_ONLY"
  exit 0
fi

# --- Resolve stories for --epic mode ---
if [[ -n "$EPIC_NUM" ]]; then
  log_info "Epic mode: processing Epic $EPIC_NUM"

  # Run breakdown if stories don't exist yet
  if ! epic_has_stories "$EPIC_NUM"; then
    log_info "No stories found for Epic $EPIC_NUM — running breakdown..."
    write_runner_status "" "breakdown" "epic $EPIC_NUM"
    if [[ "$DRY_RUN" == "true" ]]; then
      log_info "DRY RUN — would break Epic $EPIC_NUM into stories, then write each"
      exit 0
    fi
    if ! run_breakdown_step "$EPIC_NUM"; then
      log_error "Breakdown failed for Epic $EPIC_NUM"
      exit 1
    fi
  else
    log_info "Epic $EPIC_NUM already has stories in sprint-status.yaml"
  fi

  # Collect all story keys for the epic
  while IFS= read -r key; do
    key="${key%$'\r'}"
    [[ -n "$key" ]] && STORY_KEYS+=("$key")
  done < <(get_epic_story_keys "$EPIC_NUM")

  if [[ ${#STORY_KEYS[@]} -eq 0 ]]; then
    log_error "No stories found for Epic $EPIC_NUM after breakdown"
    exit 1
  fi

  log_info "Found ${#STORY_KEYS[@]} stories for Epic $EPIC_NUM"
fi

# --- Resolve short keys to full keys ---
RESOLVED_KEYS=()
for key in "${STORY_KEYS[@]}"; do
  # Full key: has 3+ dash-separated parts starting with digit-digit-alpha
  if [[ "$key" =~ ^[0-9]+-[0-9]+-[a-z] ]]; then
    RESOLVED_KEYS+=("$key")
    log_info "Story: $key"
  else
    # Short key (e.g., "2-1") — resolve from sprint-status
    full_key=$(get_full_story_key "$key")
    if [[ -z "$full_key" ]]; then
      log_error "Could not resolve story key: $key"
      log_error "Check sprint-status.yaml for valid story keys"
      exit 1
    fi
    RESOLVED_KEYS+=("$full_key")
    log_info "Resolved: $key -> $full_key"
  fi
done

# --- Pre-flight checks ---
echo ""
log_step "PRE-FLIGHT CHECKS"

runnable_keys=()

for story_key in "${RESOLVED_KEYS[@]}"; do
  cur_status=$(get_story_status "$story_key")

  # Skip stories already written (ready-for-dev or beyond) IF file exists
  if [[ "$cur_status" == "ready-for-dev" || "$cur_status" == "in-progress" || "$cur_status" == "done" ]]; then
    existing_file=$(get_story_file "$story_key")
    if [[ -n "$existing_file" && -f "$existing_file" ]]; then
      log_info "SKIP: $story_key already written (status: $cur_status, file exists)"
      continue
    else
      log_info "Story $story_key has status '$cur_status' but no file — will write"
    fi
  fi

  log_success "Pre-flight OK: $story_key ($cur_status)"
  runnable_keys+=("$story_key")
done

if [[ ${#runnable_keys[@]} -eq 0 ]]; then
  log_info "No stories to write (all already written or skipped)"
  exit 0
fi

log_info "Stories to write: ${#runnable_keys[@]}"

# --- Dry run exit ---
if [[ "$DRY_RUN" == "true" ]]; then
  echo ""
  log_info "DRY RUN — would write ${#runnable_keys[@]} stories:"
  for key in "${runnable_keys[@]}"; do
    log_info "  - $key"
  done
  exit 0
fi

# --- Main execution loop ---
echo ""
log_step "EXECUTION"

completed_count=0
failed_count=0
consecutive_failures=0

for i in "${!runnable_keys[@]}"; do
  story_key="${runnable_keys[$i]}"
  retry_count=0
  story_success=false
  failure_context=""

  echo ""
  echo -e "${BOLD}===========================================${NC}"
  echo -e "${BOLD}  WRITE: $story_key${NC}"
  echo -e "${BOLD}  ($(($i + 1)) of ${#runnable_keys[@]})${NC}"
  echo -e "${BOLD}===========================================${NC}"

  while [[ $retry_count -le $MAX_RETRIES_PER_STORY ]]; do
    if [[ $retry_count -gt 0 ]]; then
      echo ""
      log_warn "--- RETRY $retry_count/$MAX_RETRIES_PER_STORY for $story_key ---"
    fi

    # --- Smart skip: check if story file already exists and is valid ---
    write_runner_status "$story_key" "pre-check"
    existing_file=$(get_story_file "$story_key")
    if [[ -n "$existing_file" && -f "$existing_file" ]]; then
      existing_lines=$(wc -l < "$existing_file" | tr -d ' \r')
      if [[ $existing_lines -ge $MIN_STORY_LINES ]]; then
        log_info "Smart skip: story file exists ($existing_lines lines) — verifying..."
        if verify_write_step "$story_key"; then
          log_success "Smart skip: story file valid — skipping write"
          story_success=true
          break
        else
          log_info "Smart skip: file exists but failed verify — re-writing"
          failure_context="$WRITE_VERIFY_FAILURE_CONTEXT"
        fi
      fi
    fi

    # --- STEP 1: Write story ---
    write_runner_status "$story_key" "write" "attempt $((retry_count + 1))"
    if ! run_write_step "$story_key" "$failure_context"; then
      failure_context="Write step failed for $story_key. Check logs in $LOG_DIR."
      retry_count=$((retry_count + 1))
      continue
    fi

    # --- STEP 2: Verify story ---
    write_runner_status "$story_key" "verify"
    if ! verify_write_step "$story_key"; then
      failure_context="$WRITE_VERIFY_FAILURE_CONTEXT"
      retry_count=$((retry_count + 1))
      continue
    fi

    # --- STEP 3: Codex Holistic Review ---
    # System alignment review — challenges PRD/architecture fit, not just story quality
    write_runner_status "$story_key" "review"
    story_file_path=$(get_story_file "$story_key")
    run_story_review_step "$story_key" "$story_file_path"
    # Review failure is non-blocking (Codex may be unavailable)

    # --- STEP 4: Synthesis — Claude applies accepted improvements ---
    if [[ -n "$STORY_REVIEW_LOG" && -f "$STORY_REVIEW_LOG" ]]; then
      write_runner_status "$story_key" "synthesis"
      if ! run_story_synthesis_step "$story_key" "$story_file_path" "$STORY_REVIEW_LOG"; then
        failure_context="$STORY_SYNTHESIS_FAILURE_CONTEXT"
        retry_count=$((retry_count + 1))
        continue
      fi

      # --- STEP 5: Post-synthesis verify (catch regressions from synthesis edits) ---
      write_runner_status "$story_key" "post-verify"
      if ! verify_write_step "$story_key"; then
        failure_context="POST-SYNTHESIS REGRESSION: Synthesis edits broke story quality.
$WRITE_VERIFY_FAILURE_CONTEXT
Fix the story file while preserving the synthesis improvements' intent."
        retry_count=$((retry_count + 1))
        continue
      fi
    else
      log_info "No Codex review produced — skipping synthesis"
    fi

    # --- STEP 6: Done ---
    write_runner_status "$story_key" "done"
    story_success=true
    break
  done

  if [[ "$story_success" == "true" ]]; then
    completed_count=$((completed_count + 1))
    consecutive_failures=0
    echo ""
    log_success "STORY WRITTEN: $story_key"
  else
    failed_count=$((failed_count + 1))
    consecutive_failures=$((consecutive_failures + 1))
    echo ""
    log_error "STORY FAILED: $story_key (exhausted retries)"
    write_runner_status "$story_key" "failed" "exhausted retries"

    # Circuit breaker
    if [[ $consecutive_failures -ge $MAX_CONSECUTIVE_FAILURES ]]; then
      log_error "CIRCUIT BREAKER: $consecutive_failures consecutive failures — aborting"
      break
    fi
  fi

  # Inter-story gap (subscription rate-limit protection)
  if [[ $GAP_MINUTES -gt 0 && $((i + 1)) -lt ${#runnable_keys[@]} ]]; then
    gap_seconds=$((GAP_MINUTES * 60))
    resume_time=$(date -d "+${GAP_MINUTES} minutes" +%H:%M 2>/dev/null || date -v+${GAP_MINUTES}M +%H:%M 2>/dev/null || echo "~${GAP_MINUTES}m")
    log_info "Waiting ${GAP_MINUTES}m before next story (resume ~${resume_time})..."
    write_runner_status "${runnable_keys[$((i + 1))]}" "waiting" "gap ${GAP_MINUTES}m until ~${resume_time}"
    sleep "$gap_seconds"
  fi
done

# --- Summary ---
echo ""
echo -e "${BOLD}===========================================${NC}"
echo -e "${BOLD}  WRITE COMPLETE${NC}"
echo -e "${BOLD}===========================================${NC}"
log_info "Written: $completed_count | Failed: $failed_count"
log_info "Log file: $RUN_LOG"
echo ""

if [[ $completed_count -gt 0 ]]; then
  log_info "Stories are now ready-for-dev. Run them with:"
  if [[ -n "$EPIC_NUM" ]]; then
    log_info "  bash scripts/run-stories.sh --daemon --skip-deps ${RESOLVED_KEYS[*]%%-*}-1"
  fi
  log_info "  bash scripts/run-stories.sh --daemon <story-keys>"
fi
echo ""

if [[ $failed_count -gt 0 ]]; then
  exit 1
fi
exit 0
