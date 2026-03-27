#!/usr/bin/env bash
# Monitor the story writer daemon — logs status, detects failures
set -uo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOG_DIR="$PROJECT_ROOT/logs/story-writer"
PID_FILE="$LOG_DIR/writer.pid"
STATUS_FILE="$LOG_DIR/writer-status.json"
MONITOR_LOG="$LOG_DIR/monitor.log"

log() { echo "[$(date +%H:%M:%S)] $*" | tee -a "$MONITOR_LOG"; }

if [[ ! -f "$PID_FILE" ]]; then
  log "MONITOR: No PID file — writer not running or already finished"
  # Check if stories were completed
  if [[ -f "$STATUS_FILE" ]]; then
    cat "$STATUS_FILE"
  fi
  exit 0
fi

pid=$(cat "$PID_FILE")
if ! kill -0 "$pid" 2>/dev/null; then
  # Writer exited — check how
  if [[ -f "$STATUS_FILE" ]]; then
    step=$(grep -oP '"step":"[^"]*"' "$STATUS_FILE" | cut -d'"' -f4)
    story=$(grep -oP '"story_key":"[^"]*"' "$STATUS_FILE" | cut -d'"' -f4)
    detail=$(grep -oP '"detail":"[^"]*"' "$STATUS_FILE" | cut -d'"' -f4)
    if [[ "$step" == "done" || "$step" == "exited" ]]; then
      log "MONITOR: Writer finished normally (last: $story → $step)"
      echo "STATUS:FINISHED"
    else
      log "MONITOR: ⚠️ Writer CRASHED — $story stuck at '$step' ($detail)"
      echo "STATUS:CRASHED:$story:$step"
      # Show last 20 lines of run log for diagnosis
      run_log=$(ls -t "$LOG_DIR"/run-*.log 2>/dev/null | head -1)
      if [[ -n "$run_log" ]]; then
        log "Last log lines:"
        tail -20 "$run_log" | tee -a "$MONITOR_LOG"
      fi
    fi
  else
    log "MONITOR: Writer exited with no status file"
    echo "STATUS:UNKNOWN"
  fi
  exit 1
fi

# Writer is alive — report status
if [[ -f "$STATUS_FILE" ]]; then
  step=$(grep -oP '"step":"[^"]*"' "$STATUS_FILE" | cut -d'"' -f4)
  story=$(grep -oP '"story_key":"[^"]*"' "$STATUS_FILE" | cut -d'"' -f4)
  detail=$(grep -oP '"detail":"[^"]*"' "$STATUS_FILE" | cut -d'"' -f4)
  log "MONITOR: ALIVE (PID $pid) — $story → $step ($detail)"
  echo "STATUS:ALIVE:$story:$step"
else
  log "MONITOR: ALIVE (PID $pid) — no status yet"
  echo "STATUS:ALIVE"
fi
exit 0
