#!/usr/bin/env bash
# Step 1: Write Story — invoke claude --print with bmad-create-story workflow
# Creates the comprehensive story file from epics.md + PRD + architecture.

# Run the write step for a story
# Usage: run_write_step "2-1-strategy-evaluator-review" [retry_context]
# Returns: 0 on success, 1 on failure
run_write_step() {
  local story_key="$1"
  local retry_context="${2:-}"
  local step_log="$LOG_DIR/${story_key}-write-$(date +%H%M%S).log"

  log_step "WRITE: $story_key"
  log_info "Step log: $step_log"

  # Build the prompt
  local prompt
  if [[ -n "$retry_context" ]]; then
    prompt="RETRY: Fix issues from previous attempt. Failure context:
${retry_context}

Now re-run: /bmad-create-story ${story_key}"
  else
    prompt="/bmad-create-story ${story_key}"
  fi

  # Instructions for automation mode
  local write_instruction
  read -r -d '' write_instruction << 'WRITE_EOF' || true
AUTOMATED STORY CREATION — NO USER INTERACTION:

You are running in a fully automated pipeline via claude --print.
Follow these rules strictly:

== AUTOMATION OVERRIDES ==

1. SKIP the Team Mode Check entirely — you are running sequentially in a batch
2. SKIP web research (Step 4) unless the story involves a specific external
   library or API that requires version-specific documentation
3. When running the checklist validation (Step 6):
   - Apply ALL critical and enhancement improvements automatically
   - Do NOT present options or ask the user which to apply
   - Do NOT output interactive prompts, selection menus, or ask questions
4. Make reasonable decisions for anything ambiguous and note them in Dev Notes
5. Complete the ENTIRE workflow end-to-end without stopping

== QUALITY REQUIREMENTS ==

The story file MUST include ALL of these sections with substantive content:

1. **Story** — User story in "As a/I want/So that" format
2. **Acceptance Criteria** — Numbered, Gherkin Given/When/Then format with
   bold keywords. Each must reference specific FR or Architecture decision.
3. **Tasks / Subtasks** — Detailed checkbox format with:
   - Each task references which AC it satisfies (AC: #N)
   - Subtasks specify exact function signatures, file paths, class names
   - Include specific test method names in the test task
4. **Dev Notes** — Architecture constraints (cite D1, D2, etc. by number),
   technical requirements, performance considerations
5. **What to Reuse from ClaudeBackTester** — If applicable, specify exact
   files/functions to port, adapt, or avoid from the baseline
6. **Anti-Patterns to Avoid** — Numbered list of specific mistakes to prevent
7. **Project Structure Notes** — Exact file paths to create/modify, directory layout
8. **References** — Source citations with file paths and section names:
   [Source: planning-artifacts/architecture.md — Section Name]
9. **Dev Agent Record** — Empty sections for later population (Agent Model,
   Completion Notes, Change Log, File List)

== CRITICAL ==

- The story file is the ONLY context the dev agent will have — include EVERYTHING
- Reference architecture decisions by number (D1, D2, D10, etc.)
- Reference PRD requirements by number (FR9, FR10, FR20, etc.)
- Include function signatures with parameter types and return types
- Specify exact test method names (test_xxx) in the testing task
- For research stories: include specific questions to answer, files to review,
  and the expected output format (research artifact structure)
WRITE_EOF

  local exit_code=0
  claude --print \
    --permission-mode bypassPermissions \
    --allowedTools "Read,Edit,Write,Bash,Glob,Grep,Skill" \
    --append-system-prompt "$write_instruction" \
    "$prompt" \
    > "$step_log" 2>&1 || exit_code=$?

  if [[ $exit_code -ne 0 ]]; then
    log_error "Write step failed for $story_key (exit code: $exit_code)"
    log_info "Check log: $step_log"
    return 1
  fi

  # Check if story file was created
  local story_file
  story_file=$(get_story_file "$story_key")
  if [[ -n "$story_file" && -f "$story_file" ]]; then
    local line_count
    line_count=$(wc -l < "$story_file" | tr -d ' \r')
    log_success "Story file created: $story_file ($line_count lines)"
    return 0
  else
    log_error "Write step completed but story file not found for $story_key in $STORY_DIR"
    return 1
  fi
}
