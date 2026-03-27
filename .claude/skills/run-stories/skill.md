---
name: run-stories
description: Run BMAD stories through the automated pipeline (Dev -> Live Verify -> Dual Review -> Synthesis -> Post-Verify -> Done). Use when the user says "run stories", "automate stories", "run-stories 1-5 1-6", or "implement stories".
---

# Run Stories — Automated BMAD Pipeline

You help the user run stories through the automated story runner.

## What This Does

The story runner executes selected stories through these steps:
1. **Smart Skip** — Pre-checks if verify passes (code already on disk). Skips dev if so.
2. **Dev Story** — Implements via bmad-dev-story with live test enforcement + verify manifest
3. **Live Verify** — 8-phase verification: source files, test files, test counts, unit regression, story tests, live tests, named live tests, artifacts
4. **Dual Code Review** — BMAD (Claude) and Codex (GPT-5.4) review in parallel. Both produce findings reports only — no code changes.
5. **Review Synthesis** — A fresh Claude session reads both review reports, accepts or rejects each finding with reasoning, fixes accepted CRITICAL/HIGH issues, and runs tests. Produces a synthesis report in `reviews/`.
6. **Post-Synthesis Verify** — Re-runs 8-phase verify after synthesis fixes to catch regressions
7. **Done** — Updates sprint-status.yaml

Each step runs in a fresh `claude --print` session (uses your subscription, not API). Codex runs via `codex exec` (uses ChatGPT subscription). Failures retry up to 2 times with error context passed forward.

### Review Architecture
- **BMAD review**: Claude runs the bmad-code-review workflow. Findings only, read-only (no Edit/Write tools).
- **Codex review**: OpenAI GPT-5.4 in read-only sandbox. Independent second opinion with AC scorecard.
- **Synthesis**: Claude is the final decision-maker. Reads both reports, agrees or disagrees with each finding, fixes what it accepts, discards what it doesn't. Produces `reviews/{story-key}-synthesis-report.md`.

## Your Job

1. Ask the user which stories to run (e.g., "1-5 1-6 1-7")
2. Read `_bmad-output/implementation-artifacts/sprint-status.yaml` to show current statuses
3. Validate dependencies (story N needs N-1 done)
4. Generate and explain the bash command
5. **Always use `--daemon` flag** to avoid timeout issues
6. Use `--status` to poll progress

## Command

```bash
bash scripts/run-stories.sh [OPTIONS] <story-keys>
```

### Options
- `--daemon` — **Recommended.** Run detached from terminal (no timeout)
- `--status` — Poll daemon progress (story, step, timestamp)
- `--follow` — Follow daemon progress until completion (poll every 30s, prints step changes)
- `--stop` — Stop a running daemon
- `--max-retries N` — Max retries per story (default: 2)
- `--dry-run` — Validate without executing
- `--skip-deps` — Skip dependency checking
- `--no-smart-skip` — Always run dev step (don't pre-check verify)

### Examples

```bash
# Run stories detached (recommended)
bash scripts/run-stories.sh --daemon --skip-deps 1-7

# Follow progress live (auto-polls, exits when done)
bash scripts/run-stories.sh --follow

# One-shot status check
bash scripts/run-stories.sh --status

# Stop a running daemon
bash scripts/run-stories.sh --stop

# Dry run first
bash scripts/run-stories.sh --dry-run 1-5 1-6

# Multiple stories
bash scripts/run-stories.sh --daemon 1-7 1-8 1-9
```

## Before Running

1. Show current sprint status from sprint-status.yaml
2. Check that prerequisite stories are done
3. Remind user this runs unattended — they can walk away
4. **Always use `--daemon`** — foreground runs may timeout
5. After launching, use `--follow` to auto-poll (prints step changes, exits on completion)
6. Use `--status` for a one-shot check

## Review Outputs

After a story completes, review artifacts are at:
- `logs/story-runner/{story-key}-review-*.log` — BMAD findings
- `reviews/codex/story-{story-key}-codex-review.md` — Codex findings
- `reviews/synthesis/{story-key}-synthesis-report.md` — Synthesis decisions + what was fixed/rejected
