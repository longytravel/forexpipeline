#!/usr/bin/env bash
# Step 0: Epic Breakdown — break an epic into individual stories
# Reads the epic description, PRD, and architecture to generate
# story entries in epics.md and register them in sprint-status.yaml.

PLANNING_ARTIFACTS="$PROJECT_ROOT/_bmad-output/planning-artifacts"
EPICS_FILE="$PLANNING_ARTIFACTS/epics.md"
PRD_FILE="$PLANNING_ARTIFACTS/prd.md"
ARCH_FILE="$PLANNING_ARTIFACTS/architecture.md"

# Check if an epic has stories in sprint-status.yaml
epic_has_stories() {
  local epic_num="$1"
  local count
  count=$(grep -cP "^\s+${epic_num}-\d+-[a-z0-9-]+:" "$SPRINT_STATUS" 2>/dev/null || true)
  [[ "${count:-0}" -gt 0 ]]
}

# Get story keys for an epic from sprint-status.yaml (sorted by story number)
get_epic_story_keys() {
  local epic_num="$1"
  grep -oP "^\s+${epic_num}-\d+-[a-z0-9-]+(?=:)" "$SPRINT_STATUS" \
    | tr -d ' \r' \
    | sort -t'-' -k2 -n \
    || true
}

# Run the epic breakdown step
# Usage: run_breakdown_step "2"
# Returns: 0 on success, 1 on failure
run_breakdown_step() {
  local epic_num="$1"
  local step_log="$LOG_DIR/epic-${epic_num}-breakdown-$(date +%H%M%S).log"

  log_step "BREAKDOWN: Epic $epic_num"
  log_info "Step log: $step_log"

  if [[ ! -f "$EPICS_FILE" ]]; then
    log_error "epics.md not found at $EPICS_FILE"
    return 1
  fi

  if epic_has_stories "$epic_num"; then
    log_info "Epic $epic_num already has stories in sprint-status.yaml — skipping breakdown"
    return 0
  fi

  local breakdown_instruction
  read -r -d '' breakdown_instruction << 'BREAKDOWN_EOF' || true
AUTOMATED EPIC BREAKDOWN — NO USER INTERACTION:

You are breaking an epic into individual stories. This runs fully automated.

== YOUR TASK ==

1. READ the epics file to find the target Epic description (objectives, research layers,
   FRs covered, architecture decisions, E2E proof, dependencies)
2. READ the PRD for the functional requirements (FRs) referenced by the epic
3. READ the Architecture doc for the architecture decisions (Ds) referenced by the epic
4. READ Epic 1's story breakdown (Stories 1.1 through 1.9) in the epics file as a
   FORMAT REFERENCE — match their quality, detail level, and structure exactly
5. GENERATE individual stories for the epic with:
   - Story title: "### Story N.M: Descriptive Title"
   - User story: As the **operator**, I want ..., So that ...
   - Acceptance criteria in Gherkin format (Given/When/Then with **bold** keywords)
   - Each AC must reference specific FRs or Architecture decisions
6. EDIT epics.md to INSERT the new stories under the epic's section heading
   (between the epic overview paragraph and the NEXT epic's "### Epic N+1:" heading)
7. EDIT sprint-status.yaml to ADD story keys under the epic's comment block

== STORY DESIGN RULES ==

- First 1-2 stories should be RESEARCH stories (review baseline code, external research)
  following the same pattern as Stories 1.1 and 1.2 — these inform the build plan
- Research stories should be marked story_type "research" in their acceptance criteria
- Each subsequent code story should be independently implementable and testable
- Stories build on each other sequentially (story N may depend on story N-1)
- Final story should be an E2E proof (like Story 1.9) that integrates all prior stories
- Keep stories focused — each should take 1 session to implement, not 5
- Story keys use format: {epic}-{story}-kebab-case-title (e.g., 2-1-strategy-evaluator-review)

== SPRINT-STATUS.YAML FORMAT ==

Add entries under the epic comment block. Match this exact format and indentation (2 spaces):
```
  # Epic N: Title
  epic-N: in-progress
  N-1-kebab-story-name: backlog
  N-2-kebab-story-name: backlog
  ...
  epic-N-retrospective: optional
```

IMPORTANT: Update the epic status from "backlog" to "in-progress" since we are creating stories.
Also update last_updated to today's date. Preserve ALL existing content and comments.

== CRITICAL RULES ==

- Do NOT modify any Epic 1 content or any other epic's content
- Do NOT modify any existing sprint-status.yaml entries EXCEPT epic-N status
- Match the EXACT quality and detail level of Epic 1's stories
- Every acceptance criterion must reference a specific FR or Architecture decision
- Use Gherkin format: **Given** / **When** / **Then** / **And** with bold keywords
- Number all acceptance criteria sequentially
- Keep the epic's existing overview paragraph intact — add stories AFTER it
BREAKDOWN_EOF

  local prompt
  prompt="Break Epic ${epic_num} into individual stories with full acceptance criteria.

Read these files:
- Epics: ${EPICS_FILE}
- PRD: ${PRD_FILE}
- Architecture: ${ARCH_FILE}

Use Epic 1's stories (1.1 through 1.9) in the epics file as your format reference.
Add the new stories to epics.md and register them in sprint-status.yaml at ${SPRINT_STATUS}."

  local exit_code=0
  claude --print \
    --permission-mode bypassPermissions \
    --allowedTools "Read,Edit,Write,Bash,Glob,Grep" \
    --append-system-prompt "$breakdown_instruction" \
    "$prompt" \
    > "$step_log" 2>&1 || exit_code=$?

  if [[ $exit_code -ne 0 ]]; then
    log_error "Breakdown failed for Epic $epic_num (exit code: $exit_code)"
    log_info "Check log: $step_log"
    return 1
  fi

  # Verify stories were added to sprint-status.yaml
  if epic_has_stories "$epic_num"; then
    local count
    count=$(grep -cP "^\s+${epic_num}-\d+-[a-z0-9-]+:" "$SPRINT_STATUS" 2>/dev/null || true)
    log_success "Breakdown complete: $count stories added for Epic $epic_num"
    return 0
  else
    log_error "Breakdown completed but no stories found in sprint-status.yaml for Epic $epic_num"
    return 1
  fi
}
