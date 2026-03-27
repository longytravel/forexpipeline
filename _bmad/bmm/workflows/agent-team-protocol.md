# Agent Team Protocol

**Purpose:** Shared protocol for BMAD workflows that can benefit from Claude Code Agent Teams.
When a workflow detects multiple independent work items, it offers the user the option to
use an agent team for parallel execution instead of sequential single-agent processing.

**Prerequisite:** `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS` must be set to `"1"` in Claude Code settings.json.

---

## When to Invoke This Protocol

A workflow should invoke this protocol when it detects **batch opportunity** — multiple
independent items that could be processed in parallel. Each workflow defines its own
detection logic and team configuration.

## Protocol Steps

### Step T1: Detect Batch Opportunity

The calling workflow provides:
- `{{batch_items}}` — list of items that could be parallelized (e.g., story keys, feature names)
- `{{batch_count}}` — number of items
- `{{workflow_name}}` — which workflow would run per item
- `{{team_config}}` — workflow-specific team configuration (see below)

If `{{batch_count}}` < 2, skip this protocol entirely — no team benefit for a single item.

### Step T2: Present Team Option to User

```
TEAM MODE AVAILABLE

I've detected {{batch_count}} items that can be processed in parallel:
{{batch_items}}

**Options:**
1. **Agent Team** (recommended for {{batch_count}}+ items) — I'll create a team of
   {{recommended_team_size}} teammates. They work independently, coordinate via shared
   task list, and can message each other. You can interact with any teammate using Shift+Down.
   Uses more tokens but finishes ~{{batch_count}}x faster.

2. **Sequential** — I process each item one at a time in this session.
   Lower token cost, but takes longer.

3. **Subagents** — I spawn background workers that report back to me.
   They can't talk to each other or to you, but are simpler than a full team.

Choose [1], [2], or [3]:
```

### Step T3: Execute Based on Choice

#### Choice 1 — Agent Team

Create a Claude Code agent team using natural language. The lead (this session) coordinates.

**Team creation pattern:**
```
Create an agent team with {{recommended_team_size}} teammates for {{workflow_name}}.

Team structure:
{{team_structure}}

Coordination rules:
- Each teammate works on their assigned items independently
- Teammates share findings about patterns, conventions, or issues they discover
- When a teammate finishes an item, they claim the next unassigned item from the task list
- The lead reviews all outputs when teammates finish
- Teammates should NOT update sprint-status.yaml — the lead does that after review

Task list:
{{task_list}}
```

After team completes:
- Lead reviews all outputs for quality and consistency
- Lead updates sprint-status.yaml in one pass
- Lead reports summary to user

#### Choice 2 — Sequential

Skip this protocol. The calling workflow executes normally, one item at a time.

#### Choice 3 — Subagents

Use the Agent tool to spawn background workers. Each worker gets:
- The workflow instructions for their assigned items
- All necessary context (source documents, config)
- Instructions NOT to update sprint-status.yaml

After all subagents complete:
- Lead reviews all outputs
- Lead updates sprint-status.yaml
- Lead reports summary to user

---

## Workflow-Specific Team Configurations

### create-story

**Detection:** Count stories with status `backlog` in sprint-status.yaml.
**Recommended team size:** `min(ceil(batch_count / 3), 4)` — up to 4 teammates, ~3 stories each.
**Team structure:**
```
Each teammate is a Story Context Engine. They:
- Read epics.md, architecture.md, prd.md, and baseline mapping
- Create comprehensive story files following the create-story template
- Share architecture patterns and conventions they discover with other teammates
- Flag cross-story dependencies they identify
```
**Task list:** One task per story, each containing: story key, epic number, story number, title.

### dev-story

**Detection:** Count stories with status `ready-for-dev` in sprint-status.yaml.
**Recommended team size:** `min(batch_count, 3)` — max 3 parallel developers to limit file conflicts.
**Team structure:**
```
Each teammate is a Developer implementing stories. They:
- Follow the dev-story workflow for their assigned story
- Work in separate areas of the codebase (file conflict avoidance is critical)
- Share patterns, utilities, or conventions they establish with other teammates
- Alert the team if they need to modify a shared file
```
**Conflict avoidance:** Before assigning, check story file lists for overlapping files. Stories
touching the same files should NOT run in parallel — assign them to the same teammate sequentially.
**Task list:** One task per story with file ownership boundaries.

### code-review

**Detection:** Always available as an option (multi-lens review of a single story).
**Recommended team size:** 3 (fixed — one per review lens).
**Team structure:**
```
Three adversarial reviewers, each with a different lens:
- Teammate 1: Security & data integrity reviewer
- Teammate 2: Performance, resource management & architecture compliance reviewer
- Teammate 3: Correctness, acceptance criteria & test coverage reviewer
They challenge each other's findings and collaborate to produce a unified review.
```
**Task list:** Each reviewer gets the same story file but different review focus.

### create-epics-and-stories

**Detection:** Count number of epics being decomposed.
**Recommended team size:** `min(ceil(epic_count / 2), 4)` — ~2 epics per teammate.
**Team structure:**
```
Each teammate is a Product Strategist decomposing epics into stories. They:
- Read the PRD, architecture, and any existing epics
- Decompose their assigned epics into stories with BDD acceptance criteria
- Share cross-epic dependency findings with other teammates
- Ensure consistent story sizing and formatting across epics
```
**Task list:** One task per epic.

### qa-generate-e2e-tests

**Detection:** Count number of features/components to test.
**Recommended team size:** `min(ceil(feature_count / 2), 3)`.
**Team structure:**
```
Each teammate is a QA Engineer generating tests. They:
- Follow the qa-generate-e2e-tests workflow for their assigned features
- Share test utilities and patterns they create
- Ensure no duplicate test coverage
```
**Task list:** One task per feature/component.

---

## Display Mode Note

On Windows, split-pane mode (tmux) is not available. Agent teams will run in **in-process mode**.
Use **Shift+Down** to cycle between teammates and message them directly.
Use **Ctrl+T** to toggle the shared task list view.
