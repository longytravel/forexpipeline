#!/usr/bin/env bash
set -euo pipefail

# =============================================================================
# Story Runner — Automated BMAD story pipeline
# Dev → Live Verify → Dual Review (BMAD+Codex) → Synthesis → Post-Verify → Done
#
# Features:
#   --daemon      Run detached from terminal (no timeout)
#   --status      Poll current runner status
#   --stop        Stop a running daemon
#   Smart skip    Skips dev step if verify already passes (code on disk)
# =============================================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ORIGINAL_ARGS=("$@")

source "$SCRIPT_DIR/lib/common.sh"
source "$SCRIPT_DIR/lib/parse-sprint.sh"
source "$SCRIPT_DIR/lib/run-dev.sh"
source "$SCRIPT_DIR/lib/run-verify.sh"
source "$SCRIPT_DIR/lib/run-review.sh"
source "$SCRIPT_DIR/lib/run-codex-review.sh"
source "$SCRIPT_DIR/lib/run-synthesis.sh"
source "$SCRIPT_DIR/lib/run-pir.sh"
source "$SCRIPT_DIR/lib/update-status.sh"

# --- Usage ---
usage() {
  cat <<'EOF'
Story Runner — Automated BMAD story pipeline

Usage: run-stories.sh [OPTIONS] <story-keys...>

Arguments:
  story-keys    Space-separated short story keys (e.g., "1-5 1-6 1-7")

Options:
  --max-retries N    Max retries per story (default: 2)
  --delay N          Wait N minutes between stories (subscription pacing)
  --dry-run          Show what would run without executing
  --skip-deps        Skip dependency checking
  --no-smart-skip    Always run dev step (don't pre-check verify)
  --daemon           Run detached from terminal (no timeout)
  --status           Show status of running daemon
  --follow           Follow daemon progress until completion (poll every 30s)
  --stop             Stop a running daemon
  --help             Show this help

Examples:
  run-stories.sh 1-5 1-6 1-7        Run stories sequentially
  run-stories.sh --daemon 1-5 1-6   Run detached (no timeout)
  run-stories.sh --daemon --delay 45 2-1 2-2 2-3   Pace stories 45min apart
  run-stories.sh --status            Check daemon progress
  run-stories.sh --follow            Follow daemon until completion
  run-stories.sh --stop              Stop daemon
EOF
}

# --- Handle --status (early exit, no args needed) ---
if [[ "${1:-}" == "--status" ]]; then
  mkdir -p "$LOG_DIR"
  if [[ ! -f "$PID_FILE" ]]; then
    echo "No runner active (no PID file)"
    exit 0
  fi
  pid=$(cat "$PID_FILE")
  if kill -0 "$pid" 2>/dev/null; then
    echo "Runner ACTIVE (PID $pid)"
    if [[ -f "$STATUS_FILE" ]]; then
      cat "$STATUS_FILE"
    fi
  else
    echo "Runner NOT running (stale PID $pid)"
    rm -f "$PID_FILE" "$STATUS_FILE"
  fi
  exit 0
fi

# --- Handle --follow (poll until completion) ---
if [[ "${1:-}" == "--follow" ]]; then
  mkdir -p "$LOG_DIR"
  POLL_INTERVAL="${2:-30}"
  if [[ ! -f "$PID_FILE" ]]; then
    echo "No runner active (no PID file)"
    exit 0
  fi
  last_step=""
  last_detail=""
  echo "Following runner progress (poll every ${POLL_INTERVAL}s) — Ctrl+C to detach"
  echo ""
  while true; do
    pid=$(cat "$PID_FILE" 2>/dev/null || true)
    if [[ -z "$pid" ]] || ! kill -0 "$pid" 2>/dev/null; then
      # Runner finished — show final status
      if [[ -f "$STATUS_FILE" ]]; then
        final_step=$(grep -oP '"step":"[^"]*"' "$STATUS_FILE" | cut -d'"' -f4)
        final_story=$(grep -oP '"story_key":"[^"]*"' "$STATUS_FILE" | cut -d'"' -f4)
        if [[ "$final_step" == "done" ]]; then
          echo -e "\033[0;32m[DONE]\033[0m $(date +%H:%M:%S) Story $final_story completed successfully!"
        elif [[ "$final_step" == "failed" ]]; then
          echo -e "\033[0;31m[FAIL]\033[0m $(date +%H:%M:%S) Story $final_story failed"
        else
          echo -e "\033[1;33m[EXIT]\033[0m $(date +%H:%M:%S) Runner exited (last step: $final_step)"
        fi
      fi
      rm -f "$PID_FILE" "$STATUS_FILE"
      echo ""
      echo "Runner finished."
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
    echo "No runner active"
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
  echo "Runner stopped"
  exit 0
fi

# --- Argument parsing ---
STORY_KEYS=()
DRY_RUN=false
SKIP_DEPS=false
SMART_SKIP=true
DAEMON_MODE=false
DELAY_MINUTES=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --max-retries)    MAX_RETRIES_PER_STORY="$2"; shift 2 ;;
    --dry-run)        DRY_RUN=true; shift ;;
    --skip-deps)      SKIP_DEPS=true; shift ;;
    --no-smart-skip)  SMART_SKIP=false; shift ;;
    --daemon)         DAEMON_MODE=true; shift ;;
    --delay)          DELAY_MINUTES="$2"; shift 2 ;;
    --help|-h)        usage; exit 0 ;;
    -*)               echo "Unknown option: $1"; usage; exit 1 ;;
    *)                STORY_KEYS+=("$1"); shift ;;
  esac
done

if [[ ${#STORY_KEYS[@]} -eq 0 ]]; then
  echo "Error: No story keys provided"
  usage
  exit 1
fi

# --- Daemon mode: re-exec detached ---
if [[ "$DAEMON_MODE" == "true" && "${_RUNNER_DAEMONIZED:-}" != "1" ]]; then
  mkdir -p "$LOG_DIR"
  # Check for existing runner
  if [[ -f "$PID_FILE" ]] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
    echo "ERROR: Runner already active (PID $(cat "$PID_FILE"))"
    echo "Use --stop to kill it first, or --status to check progress"
    exit 1
  fi
  # Re-exec as detached process
  export _RUNNER_DAEMONIZED=1
  FG_LOG="$LOG_DIR/daemon-$(date +%Y%m%d-%H%M%S).log"
  # Strip --daemon from args for the re-exec
  REEXEC_ARGS=()
  for arg in "${ORIGINAL_ARGS[@]}"; do
    [[ "$arg" != "--daemon" ]] && REEXEC_ARGS+=("$arg")
  done
  nohup bash "$SCRIPT_DIR/run-stories.sh" "${REEXEC_ARGS[@]}" > "$FG_LOG" 2>&1 &
  DAEMON_PID=$!
  echo "$DAEMON_PID" > "$PID_FILE"
  echo ""
  echo "Runner daemonized (PID $DAEMON_PID)"
  echo "  Follow:  bash scripts/run-stories.sh --follow"
  echo "  Status:  bash scripts/run-stories.sh --status"
  echo "  Stop:    bash scripts/run-stories.sh --stop"
  echo "  Log:     $FG_LOG"
  echo ""
  exit 0
fi

# --- Initialize ---
init_logging

# PID/status cleanup on exit (daemon or foreground)
if [[ "${_RUNNER_DAEMONIZED:-}" == "1" ]]; then
  echo $$ > "$PID_FILE"
  trap 'write_runner_status "" "exited" ""; rm -f "$PID_FILE"' EXIT
fi

echo ""
echo -e "${BOLD}=========================================${NC}"
echo -e "${BOLD}  Story Runner — Forex Pipeline${NC}"
echo -e "${BOLD}=========================================${NC}"
echo ""
log_info "Stories requested: ${STORY_KEYS[*]}"
log_info "Max retries per story: $MAX_RETRIES_PER_STORY"
log_info "Smart skip: $SMART_SKIP"
if [[ $DELAY_MINUTES -gt 0 ]]; then
  log_info "Delay between stories: ${DELAY_MINUTES}m"
fi

# --- Resolve short keys to full keys ---
RESOLVED_KEYS=()
RESOLVED_FILES=()

for short_key in "${STORY_KEYS[@]}"; do
  full_key=$(get_full_story_key "$short_key")
  if [[ -z "$full_key" ]]; then
    log_error "Could not resolve story key: $short_key"
    log_error "Check sprint-status.yaml for valid story keys"
    exit 1
  fi

  story_file=$(get_story_file "$full_key")
  if [[ -z "$story_file" || ! -f "$story_file" ]]; then
    log_error "Story file not found for $full_key in $STORY_DIR"
    exit 1
  fi

  RESOLVED_KEYS+=("$full_key")
  RESOLVED_FILES+=("$story_file")
  log_info "Resolved: $short_key -> $full_key"
done

# --- Pre-flight checks ---
echo ""
log_step "PRE-FLIGHT CHECKS"

if [[ ! -f "$SPRINT_STATUS" ]]; then
  log_error "sprint-status.yaml not found at $SPRINT_STATUS"
  exit 1
fi

runnable_keys=()
runnable_files=()

for i in "${!RESOLVED_KEYS[@]}"; do
  story_key="${RESOLVED_KEYS[$i]}"
  story_file="${RESOLVED_FILES[$i]}"

  # Skip already-done stories
  if is_story_done "$story_key"; then
    log_info "SKIP: $story_key is already 'done'"
    continue
  fi

  # Check status is valid
  if ! can_start_story "$story_key"; then
    local_status=$(get_story_status "$story_key")
    log_error "Cannot start $story_key — status is '$local_status' (need 'ready-for-dev' or 'in-progress')"
    exit 1
  fi

  # Check dependencies (only for stories whose predecessor is NOT in this batch)
  if [[ "$SKIP_DEPS" == "false" ]]; then
    epic_num=$(echo "$story_key" | cut -d'-' -f1)
    story_num=$(echo "$story_key" | cut -d'-' -f2)
    # Extract numeric base and optional suffix (e.g., "2b" -> base=2, suffix="b")
    story_num_base=$(echo "$story_num" | sed 's/[^0-9]//g')
    story_num_suffix=$(echo "$story_num" | sed 's/[0-9]//g')
    if [[ -n "$story_num_suffix" ]]; then
      # Sub-story (e.g., 5-2b) — predecessor is the base story (e.g., 5-2)
      prev_num="${story_num_base}"
    else
      prev_num=$((story_num_base - 1))
    fi
    prev_in_batch=false

    # Check if the predecessor is in our batch (will be done before we get to this one)
    for batch_key in "${STORY_KEYS[@]}"; do
      if [[ "$batch_key" == "${epic_num}-${prev_num}" ]]; then
        prev_in_batch=true
        break
      fi
    done

    if [[ "$prev_in_batch" == "false" ]]; then
      if ! check_dependencies "$story_key"; then
        log_error "Dependency check failed for $story_key (use --skip-deps to override)"
        exit 1
      fi
    else
      log_info "Dependency for $story_key satisfied by batch predecessor ${epic_num}-${prev_num}"
    fi
  fi

  local_status=$(get_story_status "$story_key")
  log_success "Pre-flight OK: $story_key ($local_status)"
  runnable_keys+=("$story_key")
  runnable_files+=("$story_file")
done

if [[ ${#runnable_keys[@]} -eq 0 ]]; then
  log_info "No stories to run (all done or skipped)"
  exit 0
fi

# --- Dry run exit ---
if [[ "$DRY_RUN" == "true" ]]; then
  echo ""
  log_info "DRY RUN — would execute ${#runnable_keys[@]} stories:"
  for key in "${runnable_keys[@]}"; do
    log_info "  - $key"
  done
  exit 0
fi

# --- Main execution loop ---
echo ""
log_step "EXECUTION"

consecutive_failures=0
completed_count=0
failed_count=0

for i in "${!runnable_keys[@]}"; do
  story_key="${runnable_keys[$i]}"
  story_file="${runnable_files[$i]}"
  retry_count=0
  story_success=false
  failure_context=""

  echo ""
  echo -e "${BOLD}===========================================${NC}"
  echo -e "${BOLD}  STORY: $story_key${NC}"
  echo -e "${BOLD}  ($(($i + 1)) of ${#runnable_keys[@]})${NC}"
  echo -e "${BOLD}===========================================${NC}"

  # Just-in-time dependency check (predecessor should be done by now)
  if [[ "$SKIP_DEPS" == "false" ]]; then
    if ! check_dependencies "$story_key"; then
      log_error "Dependency not met at runtime for $story_key — predecessor did not complete"
      failed_count=$((failed_count + 1))
      consecutive_failures=$((consecutive_failures + 1))
      if [[ $consecutive_failures -ge $MAX_CONSECUTIVE_FAILURES ]]; then
        log_error "CIRCUIT BREAKER: $consecutive_failures consecutive failures — aborting run"
        break
      fi
      continue
    fi
  fi

  # Update status to in-progress
  update_story_status "$story_key" "in-progress"

  while [[ $retry_count -le $MAX_RETRIES_PER_STORY ]]; do
    if [[ $retry_count -gt 0 ]]; then
      echo ""
      log_warn "--- RETRY $retry_count/$MAX_RETRIES_PER_STORY for $story_key ---"
    fi

    # --- Smart skip: check if dev already ran for this story ---
    # Requires: 1) verify manifest exists (proof dev ran), 2) unit tests pass
    dev_needed=true
    manifest_path="$LOG_DIR/${story_key}-verify-manifest.json"
    if [[ "$SMART_SKIP" == "true" ]]; then
      write_runner_status "$story_key" "pre-check"
      if [[ ! -f "$manifest_path" ]]; then
        log_info "Smart skip: no verify manifest — dev has not run yet"
      else
        log_info "Smart skip: manifest exists, checking unit tests..."
        precheck_exit=0
        precheck_output=$(cd "$PYTHON_SRC" && "$PYTHON_BIN" -m pytest tests/ -x --tb=short -q 2>&1 | tr -d '\r') || precheck_exit=$?
        if [[ $precheck_exit -eq 0 ]]; then
          log_success "Smart skip: manifest + unit tests pass — skipping dev"
          dev_needed=false
        else
          log_info "Smart skip: unit tests failed — dev needed to fix"
          if [[ -z "$failure_context" ]]; then
            failure_context="PRE-CHECK FAILED (code on disk but tests fail):
$(echo "$precheck_output" | tail -15)

Fix the existing implementation so all tests pass. Do NOT rewrite from scratch."
          fi
        fi
      fi
    fi

    # --- STEP 1: Dev ---
    if [[ "$dev_needed" == "true" ]]; then
      write_runner_status "$story_key" "dev" "attempt $((retry_count + 1))"
      if ! run_dev_step "$story_key" "$story_file" "$failure_context"; then
        # Check if failure was due to rate limiting
        latest_dev_log=$(ls -t "$LOG_DIR"/${story_key}-dev-*.log 2>/dev/null | head -1 || true)
        if [[ -n "$latest_dev_log" ]] && check_and_wait_rate_limit "$latest_dev_log" "$story_key"; then
          log_info "Retrying dev step after rate limit wait..."
          continue  # retry without incrementing counter
        fi
        failure_context="Dev step failed. Check logs in $LOG_DIR."
        retry_count=$((retry_count + 1))
        continue
      fi
    fi

    # --- STEP 2: Live Verify ---
    write_runner_status "$story_key" "verify"
    if ! run_verify_step "$story_key" "$story_file"; then
      failure_context="$VERIFY_FAILURE_CONTEXT"
      retry_count=$((retry_count + 1))
      continue
    fi

    # --- STEP 3: Dual Code Review (BMAD + Codex in parallel) ---
    # Both produce findings reports. Neither modifies code.
    write_runner_status "$story_key" "review"

    bmad_log=""
    codex_file="$PROJECT_ROOT/reviews/codex/story-${story_key}-codex-review.md"
    skip_reviews=false

    # Smart review skip: if dev was skipped (code unchanged), reuse previous reviews
    if [[ "$dev_needed" == "false" ]]; then
      prev_bmad=$(ls -t "$LOG_DIR"/${story_key}-review-*.log 2>/dev/null | head -1 || true)
      if [[ -n "${prev_bmad:-}" && -f "$prev_bmad" && -f "$codex_file" ]]; then
        log_success "Smart review skip: code unchanged + previous reviews exist — reusing"
        bmad_log="$prev_bmad"
        skip_reviews=true
      fi
    fi

    if [[ "$skip_reviews" == "false" ]]; then
      # Launch Codex review in background
      run_codex_review_step "$story_key" "$story_file" &
      codex_pid=$!

      # Run BMAD review in foreground (findings only, no fixes)
      run_review_step "$story_key" "$story_file"
      bmad_exit=$?

      # Wait for Codex to finish
      wait "$codex_pid" 2>/dev/null || true

      if [[ $bmad_exit -ne 0 ]]; then
        # Check if BMAD review failed due to rate limiting
        latest_review_log=$(ls -t "$LOG_DIR"/${story_key}-review-*.log 2>/dev/null | head -1 || true)
        if [[ -n "$latest_review_log" ]] && check_and_wait_rate_limit "$latest_review_log" "$story_key"; then
          log_info "Retrying BMAD review after rate limit wait..."
          run_review_step "$story_key" "$story_file"
          bmad_exit=$?
        fi
        if [[ $bmad_exit -ne 0 ]]; then
          log_warn "BMAD review failed — synthesis will proceed with Codex review only (if available)"
        fi
      fi

      # Locate review outputs
      bmad_log="${BMAD_REVIEW_LOG:-}"
    fi

    # --- STEP 4: Review Synthesis ---
    # Claude reads both reviews, decides what to fix, applies fixes, runs tests
    write_runner_status "$story_key" "synthesis"
    run_synthesis_step "$story_key" "$story_file" "$bmad_log" "$codex_file"
    synthesis_exit=$?

    if [[ $synthesis_exit -eq 2 ]]; then
      # BLOCKED — skip story entirely
      log_error "Story $story_key BLOCKED by synthesis — skipping"
      break
    elif [[ $synthesis_exit -ne 0 ]]; then
      # Check if failure was due to rate limiting
      latest_synth_log=$(ls -t "$LOG_DIR"/${story_key}-synthesis-*.log 2>/dev/null | head -1 || true)
      if [[ -n "$latest_synth_log" ]] && check_and_wait_rate_limit "$latest_synth_log" "$story_key"; then
        log_info "Retrying synthesis step after rate limit wait..."
        continue  # retry without incrementing counter
      fi
      failure_context="$SYNTHESIS_FAILURE_CONTEXT"
      retry_count=$((retry_count + 1))
      log_info "Waiting 60s before synthesis retry (backoff)..."
      sleep 60
      continue
    fi

    # --- STEP 5: Post-synthesis verify (catch regressions from synthesis fixes) ---
    write_runner_status "$story_key" "post-review-verify"
    log_step "POST-SYNTHESIS VERIFY: $story_key"
    if ! run_verify_step "$story_key" "$story_file"; then
      failure_context="POST-SYNTHESIS REGRESSION: Review synthesis fixes broke tests.
$VERIFY_FAILURE_CONTEXT

The synthesis step made changes that introduced test failures. Fix the regression
while preserving the review fixes' intent."
      retry_count=$((retry_count + 1))
      continue
    fi

    # --- STEP 6: Post-Implementation Review (PIR) ---
    # "Did we build the right thing?" — alignment check against system objectives
    write_runner_status "$story_key" "pir"
    pir_exit=0
    run_pir_step "$story_key" "$story_file" || pir_exit=$?

    if [[ $pir_exit -ne 0 ]]; then
      # REVISIT verdict — log but don't block (operator reviews later)
      log_warn "PIR flagged REVISIT for $story_key — see reviews/pir/ for details"
      log_warn "Story will still be marked done. Review the PIR report before starting dependent stories."
    fi

    # --- STEP 7: Done ---
    write_runner_status "$story_key" "done"
    current_status=$(get_story_status "$story_key")
    if [[ "$current_status" != "done" ]]; then
      mark_story_done "$story_key"
    fi

    epic_num=$(get_epic_number "$story_key")
    check_epic_completion "$epic_num"

    story_success=true
    break
  done

  if [[ "$story_success" == "true" ]]; then
    completed_count=$((completed_count + 1))
    consecutive_failures=0
    echo ""
    log_success "STORY COMPLETE: $story_key"

    # Delay between stories (subscription pacing)
    remaining=$((${#runnable_keys[@]} - i - 1))
    if [[ $DELAY_MINUTES -gt 0 && $remaining -gt 0 ]]; then
      delay_secs=$((DELAY_MINUTES * 60))
      resume_time=$(date -d "+${DELAY_MINUTES} minutes" +%H:%M 2>/dev/null || date -v+${DELAY_MINUTES}M +%H:%M 2>/dev/null || echo "~${DELAY_MINUTES}m")
      log_info "Pacing delay: waiting ${DELAY_MINUTES}m before next story ($remaining remaining, resuming ~${resume_time})"
      write_runner_status "$story_key" "delay" "${DELAY_MINUTES}m until next story (${remaining} remaining)"
      sleep "$delay_secs"
    fi
  else
    failed_count=$((failed_count + 1))
    consecutive_failures=$((consecutive_failures + 1))
    echo ""
    log_error "STORY FAILED: $story_key (exhausted retries)"
    write_runner_status "$story_key" "failed" "exhausted retries"

    # Circuit breaker
    if [[ $consecutive_failures -ge $MAX_CONSECUTIVE_FAILURES ]]; then
      log_error "CIRCUIT BREAKER: $consecutive_failures consecutive failures — aborting run"
      break
    fi
  fi
done

# --- Summary ---
echo ""
echo -e "${BOLD}===========================================${NC}"
echo -e "${BOLD}  RUN COMPLETE${NC}"
echo -e "${BOLD}===========================================${NC}"
log_info "Completed: $completed_count | Failed: $failed_count"
log_info "Log file: $RUN_LOG"
echo ""

if [[ $failed_count -gt 0 ]]; then
  exit 1
fi
exit 0
