#!/usr/bin/env bash
# Run retroactive PIRs on completed stories
#
# Usage:
#   ./scripts/run-retroactive-pir.sh                  # All completed stories
#   ./scripts/run-retroactive-pir.sh 1-5 1-6          # Specific stories
#   ./scripts/run-retroactive-pir.sh --skip-codex     # Claude-only (no Codex phase)
#
# Runs each story's PIR sequentially. Results saved to reviews/pir/

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/lib/common.sh"
source "$SCRIPT_DIR/lib/run-pir.sh"

# Initialize logging
mkdir -p "$LOG_DIR"
RUN_LOG="$LOG_DIR/retroactive-pir-$(date +%Y%m%d-%H%M%S).log"
export RUN_LOG

echo ""
echo "========================================="
echo "  Retroactive PIR Runner"
echo "  $(date +%Y-%m-%d\ %H:%M:%S)"
echo "========================================="
echo ""

# Parse args
SKIP_CODEX=false
STORY_KEYS=()
for arg in "$@"; do
  if [[ "$arg" == "--skip-codex" ]]; then
    SKIP_CODEX=true
  else
    STORY_KEYS+=("$arg")
  fi
done

# If no stories specified, find all completed stories
if [[ ${#STORY_KEYS[@]} -eq 0 ]]; then
  log_info "Finding completed stories from sprint status..."
  while IFS= read -r line; do
    line=$(echo "$line" | tr -d '\r')
    if [[ "$line" =~ status:\ *done ]]; then
      # Extract the story key from the previous context
      true  # handled below
    fi
  done < "$SPRINT_STATUS"

  # Parse sprint-status.yaml for done stories
  STORY_KEYS=()
  current_key=""
  while IFS= read -r line; do
    line=$(echo "$line" | tr -d '\r')
    # Match story key lines (indented, ending with colon)
    if [[ "$line" =~ ^[[:space:]]+([0-9]+-[0-9]+-[a-z0-9-]+): ]]; then
      current_key="${BASH_REMATCH[1]}"
    fi
    # Match status: done
    if [[ -n "$current_key" && "$line" =~ status:\ *done ]]; then
      STORY_KEYS+=("$current_key")
      current_key=""
    fi
    # Reset on next story key
    if [[ "$line" =~ ^[[:space:]]+[0-9]+-[0-9]+-[a-z] && -n "$current_key" && ! "$line" =~ status ]]; then
      current_key=""
    fi
  done < "$SPRINT_STATUS"
fi

if [[ ${#STORY_KEYS[@]} -eq 0 ]]; then
  log_error "No stories found to PIR"
  exit 1
fi

log_info "Stories to PIR: ${STORY_KEYS[*]}"
log_info "Codex phase: $(if [[ "$SKIP_CODEX" == "true" ]]; then echo "SKIPPED"; else echo "ENABLED"; fi)"
echo ""

# Track results
declare -A PIR_RESULTS
total=0
aligned=0
observe=0
revisit=0
failed=0

for story_key in "${STORY_KEYS[@]}"; do
  total=$((total + 1))

  # Resolve full story key if short key given (e.g., "1-5" -> "1-5-data-validation-quality-scoring")
  local_story_key="$story_key"
  story_file=$(get_story_file "$story_key")
  if [[ -z "$story_file" ]]; then
    # Try as short key
    full_key=$(get_full_story_key "$story_key")
    if [[ -n "$full_key" ]]; then
      local_story_key="$full_key"
      story_file=$(get_story_file "$full_key")
    fi
  fi

  if [[ -z "$story_file" ]]; then
    log_error "Story file not found for $story_key — skipping"
    PIR_RESULTS[$story_key]="SKIPPED"
    failed=$((failed + 1))
    continue
  fi

  echo ""
  echo "-----------------------------------------"
  log_step "PIR $total/${#STORY_KEYS[@]}: $local_story_key"
  echo "-----------------------------------------"

  # Check if PIR already exists
  pir_report="$PIR_DIR/story-${local_story_key}-pir.md"
  if [[ -f "$pir_report" ]]; then
    log_info "PIR report already exists — re-running (previous report will be overwritten)"
  fi

  # Run the PIR
  exit_code=0
  run_pir_step "$local_story_key" "$story_file" || exit_code=$?

  if [[ $exit_code -eq 0 ]]; then
    # Parse verdict from report
    verdict=""
    if [[ -f "$PIR_DIR/story-${local_story_key}-pir.md" ]]; then
      verdict=$(grep -oP 'VERDICT:\s*\K\w+' "$PIR_DIR/story-${local_story_key}-pir.md" | tail -1 || true)
    fi
    case "$verdict" in
      ALIGNED) aligned=$((aligned + 1)); PIR_RESULTS[$story_key]="ALIGNED" ;;
      OBSERVE) observe=$((observe + 1)); PIR_RESULTS[$story_key]="OBSERVE" ;;
      *)       observe=$((observe + 1)); PIR_RESULTS[$story_key]="OBSERVE" ;;
    esac
  else
    # Check if REVISIT vs actual failure
    verdict=""
    if [[ -f "$PIR_DIR/story-${local_story_key}-pir.md" ]]; then
      verdict=$(grep -oP 'VERDICT:\s*\K\w+' "$PIR_DIR/story-${local_story_key}-pir.md" | tail -1 || true)
    fi
    if [[ "$verdict" == "REVISIT" ]]; then
      revisit=$((revisit + 1))
      PIR_RESULTS[$story_key]="REVISIT"
    else
      failed=$((failed + 1))
      PIR_RESULTS[$story_key]="FAILED"
    fi
  fi

  echo ""
done

# ===================================================================
# Summary
# ===================================================================

echo ""
echo "========================================="
echo "  PIR Summary"
echo "========================================="
echo ""
echo "  Total stories:  $total"
echo "  ALIGNED:        $aligned"
echo "  OBSERVE:        $observe"
echo "  REVISIT:        $revisit"
echo "  FAILED:         $failed"
echo ""
echo "  Results:"
for key in "${!PIR_RESULTS[@]}"; do
  printf "    %-45s %s\n" "$key" "${PIR_RESULTS[$key]}"
done
echo ""
echo "  Reports: $PIR_DIR/"
echo "========================================="
echo ""

# Exit with error if any REVISIT
if [[ $revisit -gt 0 ]]; then
  log_warn "$revisit story/stories flagged REVISIT — review the PIR reports"
  exit 1
fi

exit 0
