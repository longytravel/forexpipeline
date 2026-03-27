---
name: write-stories
description: Write BMAD story files for an epic through the automated pipeline (Breakdown -> Write -> Verify -> Ready-for-dev). Use when the user says "write stories", "create stories for epic", "write-stories", or "prepare stories for epic N".
---

# Write Stories — Automated BMAD Story Creation Pipeline

You help the user write story files through the automated story writer.

## What This Does

The story writer automates the BMAD create-story workflow with holistic quality review:
1. **Breakdown** — If the epic doesn't have individual stories yet, breaks it into stories (adds to epics.md + sprint-status.yaml)
2. **Write** — For each story, runs `bmad-create-story` to produce the comprehensive implementation file
3. **Verify** — Checks the story file has required sections, minimum quality, and acceptance criteria
4. **Codex Review** — Holistic system alignment review via Codex (GPT-5.4). Challenges PRD/architecture fit, not just story quality. Thinks about the system as a whole.
5. **Synthesis** — Claude reads Codex's review, agrees/disagrees with each observation, applies accepted improvements to the story file
6. **Post-Verify** — Re-checks story quality after synthesis edits

Each step runs in a fresh `claude --print` or `codex exec` session. Failures retry up to 2 times with error context passed forward.

## Your Job

1. Ask the user which epic to write stories for (e.g., "Epic 2")
2. Read `_bmad-output/implementation-artifacts/sprint-status.yaml` to show current statuses
3. Explain what will happen (breakdown if needed, then write each story)
4. Generate and explain the bash command
5. **Always use `--daemon` flag** to avoid timeout issues
6. Use `--status` or `--follow` to poll progress

## Command

```bash
bash scripts/write-stories.sh [OPTIONS] <story-keys...>
```

### Options
- `--epic N` — Process all stories for epic N (breakdown + write all)
- `--breakdown N` — Break epic N into stories only (no story file creation)
- `--daemon` — **Recommended.** Run detached from terminal (no timeout)
- `--status` — Poll writer progress
- `--follow` — Follow writer progress until completion (poll every 30s)
- `--stop` — Stop a running writer
- `--max-retries N` — Max retries per story (default: 2)
- `--dry-run` — Show what would run without executing

### Examples

```bash
# Write all stories for Epic 2 (breakdown + write, detached)
bash scripts/write-stories.sh --daemon --epic 2

# Just break an epic into stories (add to epics.md + sprint-status)
bash scripts/write-stories.sh --breakdown 2

# Write specific stories only
bash scripts/write-stories.sh --daemon 2-1 2-2 2-3

# Dry run to see what would happen
bash scripts/write-stories.sh --dry-run --epic 2

# Follow progress live
bash scripts/write-stories.sh --follow

# One-shot status check
bash scripts/write-stories.sh --status

# Stop a running writer
bash scripts/write-stories.sh --stop
```

## Before Running

1. Show current sprint status from sprint-status.yaml
2. If using `--epic`, explain that breakdown will run first if stories don't exist
3. Remind user this runs unattended — they can walk away
4. **Always use `--daemon`** — foreground runs may timeout
5. After launching, use `--follow` to auto-poll

## Output

After completion, artifacts are at:
- `_bmad-output/implementation-artifacts/{story-key}-*.md` — Story files
- `reviews/story-reviews/story-{story-key}-codex-review.md` — Codex holistic review
- `reviews/story-reviews/{story-key}-synthesis-report.md` — Synthesis decisions
- `logs/story-writer/{story-key}-write-*.log` — Write step logs
- `logs/story-writer/{story-key}-story-review-*.log` — Review step logs
- `logs/story-writer/{story-key}-story-synthesis-*.log` — Synthesis step logs
- `logs/story-writer/epic-{N}-breakdown-*.log` — Breakdown step logs

## After Writing

Stories are `ready-for-dev`. Run them through the implementation pipeline:
```bash
bash scripts/run-stories.sh --daemon <story-keys>
```
