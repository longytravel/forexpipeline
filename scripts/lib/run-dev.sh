#!/usr/bin/env bash
# Step 1: Dev Story — invoke claude --print with dev-story workflow
# Dev agent implements the story AND writes a verify-manifest.json for the verify step.

# Run the dev step for a story
# Usage: run_dev_step "story-key" "/path/to/story.md" [retry_context]
# Returns: 0 on success, 1 on failure
run_dev_step() {
  local story_key="$1"
  local story_file="$2"
  local retry_context="${3:-}"
  local step_log="$LOG_DIR/${story_key}-dev-$(date +%H%M%S).log"
  local manifest_path="$LOG_DIR/${story_key}-verify-manifest.json"

  log_step "DEV: $story_key"
  log_info "Story file: $story_file"
  log_info "Step log: $step_log"
  log_info "Verify manifest: $manifest_path"

  # Build the prompt
  local prompt
  if [[ -n "$retry_context" ]]; then
    prompt="RETRY: Fix issues from previous attempt. Failure context:
${retry_context}

Now re-run: /bmad-dev-story ${story_file}"
  else
    prompt="/bmad-dev-story ${story_file}"
  fi

  # Instructions appended to system prompt — live tests + verify manifest
  local dev_instruction
  read -r -d '' dev_instruction << INST_EOF || true
CRITICAL ADDITIONAL REQUIREMENTS — READ CAREFULLY:

== REQUIREMENT 1: LIVE INTEGRATION TESTS ==

After implementing all story tasks, you MUST also write @pytest.mark.live integration tests.
These tests:
1. MUST be marked with @pytest.mark.live decorator
2. MUST exercise REAL system behavior — download real data, write real files, verify real outputs
3. MUST NOT use mocks for the system under test (mocks only for true external deps if needed)
4. MUST be placed in the appropriate test file in src/python/tests/
5. MUST verify actual output files exist on disk after the operation
6. MUST validate data content, not just that code ran without errors

If the story already specifies live/integration tests in its Tasks, ensure they use @pytest.mark.live.
If the story does NOT specify live tests, ADD them as additional test methods.

The pipeline automation WILL run 'pytest -m live' after your implementation and WILL fail the story
if no live tests exist or if they fail.

== REQUIREMENT 2: VERIFICATION MANIFEST ==

As your FINAL action, you MUST write a verify-manifest.json file that tells the automated
verification step exactly what to check. This is critical — you know what you built, what
tests you wrote, and what artifacts should exist.

Write this file to: ${manifest_path}

The file MUST be valid JSON with this structure:

{
  "story_key": "${story_key}",
  "story_type": "code",
  "source_files": [
    "src/python/data_pipeline/example_module.py"
  ],
  "test_files": [
    "src/python/tests/test_data_pipeline/test_example_module.py"
  ],
  "unit_test_count": 15,
  "live_test_count": 3,
  "live_test_names": [
    "test_live_full_validation",
    "test_live_quality_report_output",
    "test_live_crash_safe_write"
  ],
  "expected_artifacts": [
    "artifacts/raw/*/quality-report.json"
  ],
  "verify_commands": [],
  "notes": "Brief description of what was implemented and any caveats"
}

Field descriptions:
- story_type: "code" (normal), "research" (no code output), "e2e" (end-to-end integration)
- source_files: All source files you created or modified (relative to project root)
- test_files: All test files you created or modified (relative to project root)
- unit_test_count: Exact number of unit test methods you wrote (not marked @pytest.mark.live)
- live_test_count: Exact number of @pytest.mark.live test methods you wrote
- live_test_names: Names of all @pytest.mark.live test methods
- expected_artifacts: Glob patterns for artifacts that live tests should produce (can be empty)
- verify_commands: Optional extra shell commands to run during verification (can be empty)
- notes: What you built and any verification caveats

DO NOT skip writing this manifest. The verify step depends on it.

== LESSONS FROM PRIOR REVIEWS ==

Before starting implementation, check if this file exists:
  ${PROJECT_ROOT}/reviews/lessons-learned.md

If it exists, READ it. It contains rules derived from accepted review findings
on prior stories — patterns and mistakes to avoid. Let these lessons inform your
implementation so the same issues don't recur.
INST_EOF

  # Execute claude --print
  local exit_code=0
  claude --print \
    --permission-mode bypassPermissions \
    --allowedTools "Read,Edit,Write,Bash,Glob,Grep,Skill" \
    --append-system-prompt "$dev_instruction" \
    "$prompt" \
    > "$step_log" 2>&1 || exit_code=$?

  if [[ $exit_code -ne 0 ]]; then
    log_error "Dev step failed for $story_key (exit code: $exit_code)"
    log_info "Check log: $step_log"
    return 1
  fi

  # Verify live tests were actually created
  local live_test_count
  live_test_count=$(grep -rl "@pytest.mark.live" "$TESTS_DIR" 2>/dev/null | wc -l || true)

  if [[ "$live_test_count" -eq 0 ]]; then
    log_error "Dev completed but NO @pytest.mark.live tests found anywhere in $TESTS_DIR"
    return 1
  fi

  # Check verify manifest was written
  if [[ -f "$manifest_path" ]]; then
    log_success "Verify manifest written: $manifest_path"
  else
    log_warn "Dev did not write verify manifest — verify step will fall back to story file parsing"
  fi

  log_success "Dev step completed for $story_key (live tests found: $live_test_count files)"
  return 0
}
