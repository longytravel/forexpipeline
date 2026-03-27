#!/usr/bin/env bash
# Step 2: Live Verify — per-story intelligent verification
#
# 7-phase verification:
#   Phase 0: Parse story metadata for expectations
#   Phase 1: Check expected source files exist
#   Phase 2: Check expected test files exist
#   Phase 3: Collect test counts (enforce minimums)
#   Phase 4: Run full unit suite (regression check)
#   Phase 5: Run story-specific tests (targeted)
#   Phase 6: Run live integration tests
#   Phase 7: Artifact sanity checks

VERIFY_LIB_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# --- Load verification expectations ---
# Priority: 1) Dev's verify-manifest.json  2) Story file parsing  3) Defaults
# Sets: STORY_TYPE, TEST_FILES (full paths), SOURCE_FILES (full paths),
#       MIN_UNIT_TESTS, MIN_LIVE_TESTS, LIVE_TEST_NAMES, EXPECTED_ARTIFACTS, VERIFY_COMMANDS
load_verify_expectations() {
  local story_key="$1"
  local story_file="$2"
  local manifest_path="$LOG_DIR/${story_key}-verify-manifest.json"

  # Defaults
  STORY_TYPE="code"
  TEST_FILES=()
  SOURCE_FILES=()
  MIN_UNIT_TESTS=3
  MIN_LIVE_TESTS=1
  LIVE_TEST_NAMES=()
  EXPECTED_ARTIFACTS=()
  VERIFY_COMMANDS=()
  EXPECTATIONS_SOURCE="defaults"

  # --- Try manifest first (written by dev agent) ---
  if [[ -f "$manifest_path" ]]; then
    log_info "Loading verify manifest from dev agent..."

    # Convert Git Bash path to Windows path for Python
    local win_manifest_path
    win_manifest_path=$(to_win_path "$manifest_path")

    # Validate it's parseable JSON
    if ! "$PYTHON_BIN" -c "import json; json.load(open(r'$win_manifest_path'))" 2>/dev/null; then
      log_warn "Verify manifest exists but is invalid JSON — falling back to story parsing"
      log_warn "Manifest path tried: $win_manifest_path"
    else
      EXPECTATIONS_SOURCE="manifest"

      STORY_TYPE=$("$PYTHON_BIN" -c "import json; d=json.load(open(r'$win_manifest_path')); print(d.get('story_type','code'))")
      MIN_UNIT_TESTS=$("$PYTHON_BIN" -c "import json; d=json.load(open(r'$win_manifest_path')); print(max(3, d.get('unit_test_count',3)))")
      MIN_LIVE_TESTS=$("$PYTHON_BIN" -c "import json; d=json.load(open(r'$win_manifest_path')); print(max(1, d.get('live_test_count',1)))")

      # Test files (manifest has full relative paths)
      # NOTE: Python on Windows emits \r\n; strip \r so paths resolve correctly
      while IFS= read -r line; do
        line="${line%$'\r'}"
        [[ -n "$line" ]] && TEST_FILES+=("$PROJECT_ROOT/$line")
      done < <("$PYTHON_BIN" -c "import json; [print(f) for f in json.load(open(r'$win_manifest_path')).get('test_files',[])]")

      # Source files
      while IFS= read -r line; do
        line="${line%$'\r'}"
        [[ -n "$line" ]] && SOURCE_FILES+=("$PROJECT_ROOT/$line")
      done < <("$PYTHON_BIN" -c "import json; [print(f) for f in json.load(open(r'$win_manifest_path')).get('source_files',[])]")

      # Live test names (for targeted verification)
      while IFS= read -r line; do
        line="${line%$'\r'}"
        [[ -n "$line" ]] && LIVE_TEST_NAMES+=("$line")
      done < <("$PYTHON_BIN" -c "import json; [print(f) for f in json.load(open(r'$win_manifest_path')).get('live_test_names',[])]")

      # Expected artifacts (glob patterns)
      while IFS= read -r line; do
        line="${line%$'\r'}"
        [[ -n "$line" ]] && EXPECTED_ARTIFACTS+=("$line")
      done < <("$PYTHON_BIN" -c "import json; [print(f) for f in json.load(open(r'$win_manifest_path')).get('expected_artifacts',[])]")

      # Custom verify commands
      while IFS= read -r line; do
        line="${line%$'\r'}"
        [[ -n "$line" ]] && VERIFY_COMMANDS+=("$line")
      done < <("$PYTHON_BIN" -c "import json; [print(f) for f in json.load(open(r'$win_manifest_path')).get('verify_commands',[])]")

      local notes
      notes=$("$PYTHON_BIN" -c "import json; print(json.load(open(r'$win_manifest_path')).get('notes',''))")
      [[ -n "$notes" ]] && log_info "Dev notes: $notes"

      log_success "Loaded manifest: ${#TEST_FILES[@]} test files, ${#SOURCE_FILES[@]} source files, $MIN_UNIT_TESTS min unit / $MIN_LIVE_TESTS min live"
      return
    fi
  fi

  # --- Fallback: parse story file ---
  log_info "No verify manifest — falling back to story file parsing..."
  EXPECTATIONS_SOURCE="story-parse"

  local meta_json
  local win_story_file
  win_story_file=$(to_win_path "$story_file")
  meta_json=$("$PYTHON_BIN" "$(to_win_path "$VERIFY_LIB_DIR/parse-story-meta.py")" "$win_story_file" 2>/dev/null) || true
  if [[ -z "$meta_json" ]]; then
    log_warn "Could not parse story metadata — using defaults"
    EXPECTATIONS_SOURCE="defaults"
    return
  fi

  STORY_TYPE=$(echo "$meta_json" | "$PYTHON_BIN" -c "import sys,json; print(json.load(sys.stdin)['story_type'])")
  local expected_count
  expected_count=$(echo "$meta_json" | "$PYTHON_BIN" -c "import sys,json; print(json.load(sys.stdin)['expected_test_count'])")
  MIN_UNIT_TESTS=$(( expected_count > 3 ? expected_count : 3 ))

  # For story-parsed fallback, resolve basenames to full paths via find
  # NOTE: Python on Windows emits \r\n; strip \r so paths resolve correctly
  local test_basenames=()
  while IFS= read -r line; do
    line="${line%$'\r'}"
    [[ -n "$line" ]] && test_basenames+=("$line")
  done < <(echo "$meta_json" | "$PYTHON_BIN" -c "import sys,json; [print(f) for f in json.load(sys.stdin)['test_basenames']]")

  for basename in "${test_basenames[@]}"; do
    local found
    found=$(find "$TESTS_DIR" -name "$basename" -type f 2>/dev/null | head -1 || true)
    [[ -n "$found" ]] && TEST_FILES+=("$found")
  done

  local source_basenames=()
  while IFS= read -r line; do
    line="${line%$'\r'}"
    [[ -n "$line" ]] && source_basenames+=("$line")
  done < <(echo "$meta_json" | "$PYTHON_BIN" -c "import sys,json; [print(f) for f in json.load(sys.stdin)['source_basenames']]")

  for basename in "${source_basenames[@]}"; do
    local found
    found=$(find "$PYTHON_SRC" -name "$basename" -type f 2>/dev/null | head -1 || true)
    [[ -n "$found" ]] && SOURCE_FILES+=("$found")
  done

  local has_live
  has_live=$(echo "$meta_json" | "$PYTHON_BIN" -c "import sys,json; print(json.load(sys.stdin)['has_live_mention'])")
  if [[ "$has_live" == "True" || "$STORY_TYPE" == "code" ]]; then
    MIN_LIVE_TESTS=1
  else
    MIN_LIVE_TESTS=0
  fi

  log_info "Parsed from story: ${#TEST_FILES[@]} test files, ${#SOURCE_FILES[@]} source files"
  log_info "Min tests required: $MIN_UNIT_TESTS unit / $MIN_LIVE_TESTS live"
}

# --- Find a file by basename under a root directory ---
# Returns the first match or empty string
find_file_by_basename() {
  local root="$1"
  local basename="$2"
  find "$root" -name "$basename" -type f 2>/dev/null | head -1 || true
}

# --- Main verify function ---
# Usage: run_verify_step "story-key" "story-file"
# Returns: 0 on success, 1 on failure
# Sets VERIFY_FAILURE_CONTEXT on failure
run_verify_step() {
  local story_key="$1"
  local story_file="$2"
  local step_log="$LOG_DIR/${story_key}-verify-$(date +%H%M%S).log"
  VERIFY_FAILURE_CONTEXT=""

  log_step "VERIFY: $story_key"

  # ===== Phase 0: Load verification expectations =====
  load_verify_expectations "$story_key" "$story_file"
  log_info "Expectations source: $EXPECTATIONS_SOURCE"

  # ===== Research stories: minimal verification =====
  if [[ "$STORY_TYPE" == "research" ]]; then
    log_info "Research/review story — skipping code tests"
    if grep -q "Completion Notes" "$story_file" 2>/dev/null; then
      log_success "Research story has completion notes"
    else
      log_warn "Research story may not have completion notes (non-blocking)"
    fi
    log_success "Verify step completed for research story $story_key"
    return 0
  fi

  # ===== Detect Rust stories =====
  # If test files include .rs files or verify_commands contain "cargo", this is a Rust story.
  # Skip Python-specific phases (3-6) and rely on verify_commands (Phase 8) for cargo test.
  local is_rust_story=false
  for tf in "${TEST_FILES[@]}"; do
    [[ "$tf" == *.rs ]] && is_rust_story=true && break
  done
  if [[ "$is_rust_story" == "false" ]]; then
    for vc in "${VERIFY_COMMANDS[@]}"; do
      [[ "$vc" == *"cargo"* ]] && is_rust_story=true && break
    done
  fi

  if [[ "$is_rust_story" == "true" ]]; then
    log_info "Rust story detected — using cargo test verification"

    # Phase 1-2: Check source/test files exist (same as Python)
    log_info "Phase 1: Checking expected source files..."
    local rs_missing=0
    for src_path in "${SOURCE_FILES[@]}"; do
      if [[ -f "$src_path" ]]; then
        log_info "  Found: $src_path"
      else
        log_warn "Expected source file not found: $src_path"
        rs_missing=$((rs_missing + 1))
      fi
    done
    if [[ ${#SOURCE_FILES[@]} -gt 0 && $rs_missing -eq 0 ]]; then
      log_success "All ${#SOURCE_FILES[@]} expected source files present"
    fi

    log_info "Phase 2: Checking expected test files..."
    for test_path in "${TEST_FILES[@]}"; do
      if [[ -f "$test_path" ]]; then
        log_info "  Found: $test_path"
      else
        log_error "Expected test file not found: $test_path"
        VERIFY_FAILURE_CONTEXT="MISSING TEST FILE: $test_path"
        export VERIFY_FAILURE_CONTEXT
        return 1
      fi
    done
    log_success "All ${#TEST_FILES[@]} expected test files present"

    # Phase 3-6: Skip Python test collection/execution — trust manifest counts
    log_info "Phase 3-6: Skipped (Rust story — tests run via cargo in Phase 8)"
    log_info "Manifest declares: $MIN_UNIT_TESTS unit tests, $MIN_LIVE_TESTS live tests"

    # Phase 7: Artifact checks (same as Python)
    log_info "Phase 7: Checking for leftover artifacts..."
    local partial_count
    partial_count=$(find "$PROJECT_ROOT/artifacts" -name "*.partial" 2>/dev/null | wc -l || true)
    if [[ $partial_count -gt 0 ]]; then
      VERIFY_FAILURE_CONTEXT="ARTIFACT CHECK: Found $partial_count leftover .partial files."
      export VERIFY_FAILURE_CONTEXT
      return 1
    fi

    # Phase 8: Run cargo test via verify_commands (critical for Rust stories)
    if [[ ${#VERIFY_COMMANDS[@]} -gt 0 ]]; then
      log_info "Phase 8: Running Rust verify commands..."
      for cmd in "${VERIFY_COMMANDS[@]}"; do
        log_info "  Running: $cmd"
        local cmd_output cmd_exit=0
        cmd_output=$(cd "$PROJECT_ROOT" && eval "$cmd" 2>&1) || cmd_exit=$?
        echo "--- Rust verify: $cmd ---" >> "$step_log"
        echo "$cmd_output" >> "$step_log"
        if [[ $cmd_exit -ne 0 ]]; then
          log_error "Rust verify command failed: $cmd"
          VERIFY_FAILURE_CONTEXT="RUST VERIFY FAILED: '$cmd' failed (exit $cmd_exit).
Output: $(echo "$cmd_output" | tail -30)"
          export VERIFY_FAILURE_CONTEXT
          return 1
        fi
        log_success "Passed: $cmd"
      done
    else
      log_warn "No verify_commands in manifest — cannot run cargo test. Trusting manifest counts."
    fi

    log_success "Verify step completed for Rust story $story_key"
    return 0
  fi

  # ===== Phase 1: Check expected source files exist =====
  log_info "Phase 1: Checking expected source files..."
  local missing_sources=0
  for src_path in "${SOURCE_FILES[@]}"; do
    if [[ -f "$src_path" ]]; then
      log_info "  Found: $src_path"
    else
      log_warn "Expected source file not found: $src_path"
      missing_sources=$((missing_sources + 1))
    fi
  done

  if [[ ${#SOURCE_FILES[@]} -eq 0 ]]; then
    log_info "  No source files specified (skipping)"
  elif [[ $missing_sources -gt 0 ]]; then
    # Non-blocking: if source files are missing, tests will fail anyway in later phases
    log_warn "$missing_sources source files not found (non-blocking — tests will catch real issues)"
  else
    log_success "All ${#SOURCE_FILES[@]} expected source files present"
  fi

  # ===== Phase 2: Check expected test files exist =====
  log_info "Phase 2: Checking expected test files..."
  local test_paths_for_targeted=()
  local missing_tests=0

  for test_path in "${TEST_FILES[@]}"; do
    if [[ -f "$test_path" ]]; then
      test_paths_for_targeted+=("$test_path")
      log_info "  Found: $test_path"
    else
      log_error "Expected test file not found: $test_path"
      missing_tests=$((missing_tests + 1))
    fi
  done

  if [[ ${#TEST_FILES[@]} -eq 0 ]]; then
    log_warn "No test files specified — will rely on test count enforcement"
  elif [[ $missing_tests -gt 0 ]]; then
    VERIFY_FAILURE_CONTEXT="MISSING TEST FILES: $missing_tests expected test files were not created.
Expected: ${TEST_FILES[*]}
The dev step must create these test files with all specified test methods."
    export VERIFY_FAILURE_CONTEXT
    return 1
  else
    log_success "All ${#TEST_FILES[@]} expected test files present"
  fi

  # ===== Phase 3: Collect test counts (enforce minimums) =====
  log_info "Phase 3: Collecting test counts..."

  # Count story-specific tests
  # NOTE: Python on Windows emits \r\n — pipe through tr -d '\r' before grepping
  local collect_output unit_collected
  if [[ ${#test_paths_for_targeted[@]} -gt 0 ]]; then
    collect_output=$(cd "$PYTHON_SRC" && "$PYTHON_BIN" -m pytest "${test_paths_for_targeted[@]}" --collect-only -q 2>&1 | tr -d '\r' || true)
  else
    collect_output=$(cd "$PYTHON_SRC" && "$PYTHON_BIN" -m pytest tests/ --collect-only -q 2>&1 | tr -d '\r' || true)
  fi
  unit_collected=$(echo "$collect_output" | grep -oP '^\d+(?=(/\d+)? tests? collected)' | head -1 || true)
  unit_collected=${unit_collected:-0}

  # Count live tests
  # Use targeted test files when available (they may live outside src/python/tests/)
  local live_collect_output live_collected
  if [[ ${#test_paths_for_targeted[@]} -gt 0 ]]; then
    live_collect_output=$(cd "$PYTHON_SRC" && "$PYTHON_BIN" -m pytest "${test_paths_for_targeted[@]}" -m live --collect-only -q 2>&1 | tr -d '\r' || true)
  else
    live_collect_output=$(cd "$PYTHON_SRC" && "$PYTHON_BIN" -m pytest tests/ -m live --collect-only -q 2>&1 | tr -d '\r' || true)
  fi
  live_collected=$(echo "$live_collect_output" | grep -oP '^\d+(?=(/\d+)? tests? collected)' | head -1 || true)
  live_collected=${live_collected:-0}

  log_info "Tests collected: $unit_collected story-specific, $live_collected live"
  echo "--- Test collection output ---" >> "$step_log"
  echo "$collect_output" >> "$step_log"
  echo "$live_collect_output" >> "$step_log"

  # Enforce minimum unit test count
  if [[ $unit_collected -lt $MIN_UNIT_TESTS ]]; then
    log_error "Insufficient tests: found $unit_collected, need at least $MIN_UNIT_TESTS"
    VERIFY_FAILURE_CONTEXT="INSUFFICIENT TESTS: Only $unit_collected tests collected, but $MIN_UNIT_TESTS required (from $EXPECTATIONS_SOURCE).
Test files checked: ${TEST_FILES[*]:-all tests/}
The dev step must implement all specified test cases as separate test methods."
    export VERIFY_FAILURE_CONTEXT
    return 1
  fi
  log_success "Unit test count OK ($unit_collected >= $MIN_UNIT_TESTS)"

  # Enforce minimum live test count
  if [[ $live_collected -lt $MIN_LIVE_TESTS ]]; then
    log_error "Insufficient live tests: found $live_collected, need at least $MIN_LIVE_TESTS"
    VERIFY_FAILURE_CONTEXT="INSUFFICIENT LIVE TESTS: Only $live_collected @pytest.mark.live tests found, need at least $MIN_LIVE_TESTS (from $EXPECTATIONS_SOURCE).
Live tests MUST:
1. Use the @pytest.mark.live decorator
2. Exercise real system behavior (no mocks for the system under test)
3. Verify actual outputs on disk
4. Be placed in the story's test files"
    export VERIFY_FAILURE_CONTEXT
    return 1
  fi
  log_success "Live test count OK ($live_collected >= $MIN_LIVE_TESTS)"

  # Verify specific live test names exist (manifest only)
  if [[ ${#LIVE_TEST_NAMES[@]} -gt 0 ]]; then
    log_info "Verifying named live tests from manifest..."
    local missing_live=0
    for test_name in "${LIVE_TEST_NAMES[@]}"; do
      if echo "$live_collect_output" | grep -q "$test_name"; then
        log_info "  Found: $test_name"
      else
        log_error "  Missing live test: $test_name"
        missing_live=$((missing_live + 1))
      fi
    done
    if [[ $missing_live -gt 0 ]]; then
      VERIFY_FAILURE_CONTEXT="MISSING LIVE TESTS: $missing_live live test methods listed in verify-manifest.json were not collected by pytest. Missing: ${LIVE_TEST_NAMES[*]}"
      export VERIFY_FAILURE_CONTEXT
      return 1
    fi
    log_success "All ${#LIVE_TEST_NAMES[@]} named live tests found"
  fi

  # ===== Phase 4: Run full unit test suite (regression check) =====
  log_info "Phase 4: Running full unit test suite for regression check..."

  local unit_output unit_exit=0
  unit_output=$(cd "$PYTHON_SRC" && "$PYTHON_BIN" -m pytest tests/ -x --tb=short -q 2>&1) || unit_exit=$?
  echo "--- Full unit suite output ---" >> "$step_log"
  echo "$unit_output" >> "$step_log"

  if [[ $unit_exit -ne 0 ]]; then
    log_error "Unit test regression detected!"
    VERIFY_FAILURE_CONTEXT="UNIT TEST REGRESSION: Full unit test suite failed (exit code $unit_exit).

Test output:
$(echo "$unit_output" | tail -30)

The implementation introduced a regression in existing tests. Fix the code so ALL unit tests pass, not just the new story tests."
    export VERIFY_FAILURE_CONTEXT
    return 1
  fi
  log_success "Unit tests passed (no regressions)"

  # ===== Phase 5: Run story-specific tests (targeted) =====
  if [[ ${#test_paths_for_targeted[@]} -gt 0 ]]; then
    log_info "Phase 5: Running story-specific tests..."

    local targeted_output targeted_exit=0
    targeted_output=$(cd "$PYTHON_SRC" && "$PYTHON_BIN" -m pytest "${test_paths_for_targeted[@]}" -v --tb=long 2>&1) || targeted_exit=$?
    echo "--- Story-specific test output ---" >> "$step_log"
    echo "$targeted_output" >> "$step_log"

    if [[ $targeted_exit -ne 0 ]]; then
      log_error "Story-specific tests failed!"
      VERIFY_FAILURE_CONTEXT="STORY TEST FAILURE: Tests in ${test_paths_for_targeted[*]} failed (exit code $targeted_exit).

Test output (last 50 lines):
$(echo "$targeted_output" | tail -50)

Fix the implementation so that ALL story-specific tests pass."
      export VERIFY_FAILURE_CONTEXT
      return 1
    fi
    log_success "Story-specific tests passed"
  else
    log_info "Phase 5: Skipped (no story-specific test files to target)"
  fi

  # ===== Phase 6: Run live integration tests (story-scoped) =====
  log_info "Phase 6: Running live integration tests..."

  local live_output live_exit=0
  # Scope to story test files if available, otherwise fall back to all
  if [[ ${#test_paths_for_targeted[@]} -gt 0 ]]; then
    log_info "Running story-scoped live tests: ${test_paths_for_targeted[*]}"
    live_output=$(cd "$PYTHON_SRC" && "$PYTHON_BIN" -m pytest "${test_paths_for_targeted[@]}" -m live -v --tb=long 2>&1) || live_exit=$?
  else
    live_output=$(cd "$PYTHON_SRC" && "$PYTHON_BIN" -m pytest tests/ -m live -v --tb=long 2>&1) || live_exit=$?
  fi
  echo "--- Live test output ---" >> "$step_log"
  echo "$live_output" >> "$step_log"

  # Check if all tests were deselected (no live tests in these files) — that's OK if manifest says 0
  local live_deselected
  live_deselected=$(echo "$live_output" | tr -d '\r' | grep -oP '\d+(?= deselected)' | head -1 || true)
  local live_no_tests
  live_no_tests=$(echo "$live_output" | tr -d '\r' | grep -c 'no tests ran' || true)

  if [[ $live_exit -ne 0 && "${live_no_tests:-0}" -gt 0 && $MIN_LIVE_TESTS -eq 0 ]]; then
    log_info "No live tests in story files and none required — OK"
    live_exit=0
  fi

  if [[ $live_exit -ne 0 ]]; then
    log_error "Live integration tests failed!"
    VERIFY_FAILURE_CONTEXT="LIVE TEST FAILURE: Live integration tests failed (exit code $live_exit).

Test output (last 50 lines):
$(echo "$live_output" | tail -50)

Fix the implementation so that live tests pass. Live tests run real operations (download real data,
write real files). Check that:
1. All external API calls succeed
2. Output files are written to the correct paths
3. Data content matches expected format and values
4. Crash-safe write pattern is working (no .partial files left behind)"
    export VERIFY_FAILURE_CONTEXT
    return 1
  fi
  log_success "Live integration tests passed"

  # ===== Phase 7: Artifact sanity checks =====
  log_info "Phase 7: Checking for leftover artifacts..."

  local partial_count
  partial_count=$(find "$PROJECT_ROOT/artifacts" -name "*.partial" 2>/dev/null | wc -l || true)
  if [[ $partial_count -gt 0 ]]; then
    log_warn "Found $partial_count .partial files — crash-safe writes may have failed"
    VERIFY_FAILURE_CONTEXT="ARTIFACT CHECK: Found $partial_count leftover .partial files in artifacts/. Crash-safe write pattern is not completing correctly — files should be written as .partial then renamed."
    export VERIFY_FAILURE_CONTEXT
    return 1
  fi

  # ===== Phase 8: Custom verify commands (manifest only) =====
  if [[ ${#VERIFY_COMMANDS[@]} -gt 0 ]]; then
    log_info "Phase 8: Running custom verify commands from manifest..."
    for cmd in "${VERIFY_COMMANDS[@]}"; do
      log_info "  Running: $cmd"
      local cmd_output
      cmd_output=$(cd "$PROJECT_ROOT" && eval "$cmd" 2>&1)
      local cmd_exit=$?
      echo "--- Custom command: $cmd ---" >> "$step_log"
      echo "$cmd_output" >> "$step_log"
      if [[ $cmd_exit -ne 0 ]]; then
        log_error "Custom verify command failed: $cmd"
        VERIFY_FAILURE_CONTEXT="CUSTOM VERIFY FAILED: Command '$cmd' failed (exit $cmd_exit).
Output: $(echo "$cmd_output" | tail -20)"
        export VERIFY_FAILURE_CONTEXT
        return 1
      fi
    done
    log_success "All custom verify commands passed"
  fi

  log_success "Verify step completed for $story_key — all phases passed ($EXPECTATIONS_SOURCE)"
  return 0
}
