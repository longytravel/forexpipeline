#!/usr/bin/env bash
# Shared constants and utilities for story runner

# Ignore SIGPIPE — MSYS2/Git Bash propagates SIGPIPE from grep|tail pipes to the
# parent shell, killing the daemon. Pipefail still detects pipe failures via exit codes.
trap '' PIPE 2>/dev/null || true

# --- Paths (relative to PROJECT_ROOT) ---
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
SPRINT_STATUS="$PROJECT_ROOT/_bmad-output/implementation-artifacts/sprint-status.yaml"
STORY_DIR="$PROJECT_ROOT/_bmad-output/implementation-artifacts"
LOG_DIR="$PROJECT_ROOT/logs/story-runner"
PYTHON_SRC="$PROJECT_ROOT/src/python"
TESTS_DIR="$PYTHON_SRC/tests"

# --- Python binary (use venv if available, else system) ---
if [[ -f "$PROJECT_ROOT/.venv/Scripts/python.exe" ]]; then
  PYTHON_BIN="$PROJECT_ROOT/.venv/Scripts/python.exe"
elif [[ -f "$PROJECT_ROOT/.venv/bin/python" ]]; then
  PYTHON_BIN="$PROJECT_ROOT/.venv/bin/python"
else
  PYTHON_BIN="python"
fi
export PYTHON_BIN

# --- Convert Git Bash path to Windows path for Python ---
# /c/Users/ROG/... → C:/Users/ROG/...
to_win_path() {
  local p="$1"
  if [[ "$p" =~ ^/([a-zA-Z])/ ]]; then
    echo "${BASH_REMATCH[1]^}:/${p:3}"
  else
    echo "$p"
  fi
}

# --- Circuit breaker defaults ---
MAX_RETRIES_PER_STORY="${MAX_RETRIES_PER_STORY:-2}"
MAX_CONSECUTIVE_FAILURES="${MAX_CONSECUTIVE_FAILURES:-3}"

# --- Terminal colors ---
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'

# --- Logging ---
log_info()    { echo -e "${BLUE}[INFO]${NC} $(date +%H:%M:%S) $*" | tee -a "$RUN_LOG" 2>/dev/null; }
log_success() { echo -e "${GREEN}[PASS]${NC} $(date +%H:%M:%S) $*" | tee -a "$RUN_LOG" 2>/dev/null; }
log_warn()    { echo -e "${YELLOW}[WARN]${NC} $(date +%H:%M:%S) $*" | tee -a "$RUN_LOG" 2>/dev/null; }
log_error()   { echo -e "${RED}[FAIL]${NC} $(date +%H:%M:%S) $*" | tee -a "$RUN_LOG" 2>/dev/null; }
log_step()    { echo -e "${CYAN}${BOLD}[STEP]${NC} $(date +%H:%M:%S) $*" | tee -a "$RUN_LOG" 2>/dev/null; }

# Initialize run log for this session
init_logging() {
  mkdir -p "$LOG_DIR"
  RUN_LOG="$LOG_DIR/run-$(date +%Y%m%d-%H%M%S).log"
  export RUN_LOG
  log_info "Story runner started. Log: $RUN_LOG"
}

# Get story file path from story key (e.g., "1-5-data-validation" -> matching file)
get_story_file() {
  local story_key="$1"
  ls "$STORY_DIR"/${story_key}*.md 2>/dev/null | head -1 || true
}

# Get the full story key from sprint-status.yaml for a short key like "1-5"
get_full_story_key() {
  local short_key="$1"
  grep -oP "^\s+${short_key}-[a-z0-9-]+(?=:)" "$SPRINT_STATUS" | tr -d ' ' | head -1 || true
}

# Get the epic number from a story key
get_epic_number() {
  echo "$1" | cut -d'-' -f1
}

# --- Runner status file (for daemon mode polling) ---
PID_FILE="$LOG_DIR/runner.pid"
STATUS_FILE="$LOG_DIR/runner-status.json"

write_runner_status() {
  local story_key="$1" step="$2" detail="${3:-}"
  cat > "$STATUS_FILE" <<SJEOF
{"pid":$$,"story_key":"$story_key","step":"$step","detail":"$detail","timestamp":"$(date +%Y-%m-%dT%H:%M:%S)","log_file":"$RUN_LOG"}
SJEOF
}

# --- Rate limit detection and backoff ---
# Check if a log file contains rate limit errors from claude --print.
# If found, parse the reset time and sleep until then.
# Returns: 0 if rate limited (and waited), 1 if not rate limited.
RATE_LIMITED=false

check_and_wait_rate_limit() {
  local log_file="$1"
  local story_key="${2:-}"
  RATE_LIMITED=false

  [[ ! -f "$log_file" ]] && return 1

  # Check for common rate limit patterns in the log
  local limit_line
  limit_line=$(grep -iE 'rate.?limit|usage.?limit|too many requests|quota|capacity|try again|429|overloaded' "$log_file" | tail -1 || true)

  if [[ -z "$limit_line" ]]; then
    return 1
  fi

  RATE_LIMITED=true
  log_warn "Rate limit detected: $limit_line"

  # Try to parse wait time from the message
  local wait_minutes=0

  # Pattern: "try again in X minutes" or "wait X minutes"
  local parsed_mins
  parsed_mins=$(echo "$limit_line" | grep -oP '(\d+)\s*minute' | grep -oP '\d+' | head -1 || true)
  if [[ -n "$parsed_mins" && "$parsed_mins" -gt 0 ]]; then
    wait_minutes="$parsed_mins"
  fi

  # Pattern: "try again in X seconds" or "wait X seconds"
  if [[ $wait_minutes -eq 0 ]]; then
    local parsed_secs
    parsed_secs=$(echo "$limit_line" | grep -oP '(\d+)\s*second' | grep -oP '\d+' | head -1 || true)
    if [[ -n "$parsed_secs" && "$parsed_secs" -gt 0 ]]; then
      wait_minutes=$(( (parsed_secs + 59) / 60 ))  # round up to minutes
    fi
  fi

  # Pattern: "resets at HH:MM" or timestamp
  if [[ $wait_minutes -eq 0 ]]; then
    local reset_time
    reset_time=$(echo "$limit_line" | grep -oP '\d{1,2}:\d{2}' | head -1 || true)
    if [[ -n "$reset_time" ]]; then
      local now_epoch reset_epoch
      now_epoch=$(date +%s)
      reset_epoch=$(date -d "$reset_time" +%s 2>/dev/null || true)
      if [[ -n "$reset_epoch" && "$reset_epoch" -gt "$now_epoch" ]]; then
        wait_minutes=$(( (reset_epoch - now_epoch + 59) / 60 ))
      fi
    fi
  fi

  # Fallback: if we detected a limit but couldn't parse time, wait 15 minutes
  if [[ $wait_minutes -eq 0 ]]; then
    wait_minutes=15
    log_warn "Could not parse reset time — defaulting to ${wait_minutes}m"
  fi

  # Cap at 120 minutes (sanity check)
  if [[ $wait_minutes -gt 120 ]]; then
    wait_minutes=120
  fi

  # Add 2 minutes buffer
  wait_minutes=$((wait_minutes + 2))

  local resume_time
  resume_time=$(date -d "+${wait_minutes} minutes" +%H:%M 2>/dev/null || echo "~${wait_minutes}m from now")
  log_warn "Rate limited — waiting ${wait_minutes}m (resume ~${resume_time})"
  write_runner_status "$story_key" "rate-limited" "waiting ${wait_minutes}m, resume ~${resume_time}"
  sleep $((wait_minutes * 60))
  log_info "Rate limit wait complete — resuming"
  return 0
}
