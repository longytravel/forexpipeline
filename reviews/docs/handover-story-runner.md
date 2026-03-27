# Story Runner — Handover Document

## What Happened This Session

We built and debugged the automated story runner pipeline. Stories 1-5, 1-6, and 1-7 were implemented and verified. The code review step has never successfully completed — see the dedicated section below.

### Stories Completed (Dev + Verify)
- **1-5 (Data Validation & Quality Scoring)**: Dev + unit tests + live tests pass. Marked done.
- **1-6 (Parquet Storage & Arrow IPC Conversion)**: Dev + full 8-phase verify pass (took 3 retries due to Windows bugs). Marked done.
- **1-7 (Timeframe Conversion)**: Dev + full 8-phase verify pass on first attempt. Smart skip correctly detected no prior code. Status: `review`.

### ALL THREE STORIES NEED CODE REVIEW
The automated code review step has failed every time. See "Review Step Problem" below.

---

## CRITICAL ISSUE: Review Step Never Completes

### What Happens
Every time the pipeline reaches the review step, `claude --print` exits without producing any output. The review log file is never created. The runner then exits (on story 1-7) or retries (which re-runs dev pointlessly).

### Evidence
- **Story 1-5**: Runner crashed at verify (Python stub bug), never reached review
- **Story 1-6**: Review started but background task timed out at 10 min. After daemon fix, still didn't complete.
- **Story 1-7**: All verify phases passed perfectly. Review step started at 16:43:47. `claude --print` process ran but produced zero output. No review log file was created. Runner exited.

### The Review Step Code (`scripts/lib/run-review.sh`)
```bash
claude --print \
  --permission-mode bypassPermissions \
  --allowedTools "Read,Edit,Write,Bash,Glob,Grep" \
  --append-system-prompt "$review_instruction" \
  "/bmad-code-review ${story_file}" \
  > "$step_log" 2>&1
```

### Why It Fails — Ranked by Likelihood

**1. MOST LIKELY: `Skill` missing from `--allowedTools`**
The `--allowedTools` list is `"Read,Edit,Write,Bash,Glob,Grep"`. It does NOT include `Skill`. The prompt `/bmad-code-review` is a slash command that invokes the Skill tool. Without `Skill` in the allowed list, `claude --print` cannot execute it and likely exits immediately with no output.

Compare with the dev step (`run-dev.sh`) which DOES include `Skill`:
```bash
--allowedTools "Read,Edit,Write,Bash,Glob,Grep,Skill" \
```

**FIX**: Add `Skill` to line 49 of `run-review.sh`:
```bash
--allowedTools "Read,Edit,Write,Bash,Glob,Grep,Skill" \
```

**2. POSSIBLE: Interactive prompts in bmad-code-review**
The bmad-code-review skill asks the user to choose review mode (single vs multi-lens) and fix mode (fix vs action items). In `--print` mode there's no user to answer. The `--append-system-prompt` instructs "choose Single Reviewer" and "choose Fix automatically" but the skill might prompt before the system prompt takes effect.

**3. POSSIBLE: Story file path format**
The `$story_file` path is `/c/Users/ROG/Projects/Forex Pipeline/...` (Git Bash format). If the review skill passes this to a tool that expects Windows paths, it could fail.

**4. UNLIKELY: Context window exhaustion**
Large stories (many source + test files) could exceed context in `--print` mode, but this would typically produce an error, not silent exit.

### Action Items
1. **Quick fix**: Add `Skill` to allowedTools in `run-review.sh` — this is almost certainly the issue
2. **Test manually**: Run `claude --print --allowedTools "Read,Edit,Write,Bash,Glob,Grep,Skill" "/bmad-code-review <story-file>"` and watch for errors
3. **Add error capture**: Log stderr separately, capture exit code, add pre/post logging around the `claude --print` call
4. **Fallback**: If bmad-code-review doesn't work in `--print` mode, write a simpler review prompt that doesn't use a skill

### Manual Workaround
Run reviews interactively until the automated step is fixed:
```bash
# In an interactive Claude Code session:
/bmad-code-review _bmad-output/implementation-artifacts/1-5-data-validation-quality-scoring.md
/bmad-code-review _bmad-output/implementation-artifacts/1-6-parquet-storage-arrow-ipc-conversion.md
/bmad-code-review _bmad-output/implementation-artifacts/1-7-timeframe-conversion.md
```

---

## How the Story Runner Works

### Pipeline Steps (per story)
```
Smart Skip → Dev → Verify (8 phases) → Code Review → Post-Review Verify → Done
```

### Command
```bash
# Run with daemon mode (recommended — no timeout)
bash scripts/run-stories.sh --daemon --skip-deps 1-7

# Check progress
bash scripts/run-stories.sh --status

# Stop
bash scripts/run-stories.sh --stop

# Dry run
bash scripts/run-stories.sh --dry-run --skip-deps 1-8
```

### Flags
- `--daemon` — Detach from terminal (no timeout). Always use this.
- `--status` — Poll JSON status: story, step, timestamp
- `--stop` — Kill running daemon
- `--skip-deps` — Skip dependency checking
- `--no-smart-skip` — Force dev step even if code exists
- `--max-retries N` — Default 2
- `--dry-run` — Validate without executing

### Smart Skip
Before running dev, checks:
1. Does a verify manifest exist for this story? (proof dev ran previously)
2. Do unit tests pass?

If both yes → skip dev, go straight to verify. If no manifest → dev hasn't run → always run dev.

### Dev Step (`scripts/lib/run-dev.sh`)
- Runs `claude --print` with `/bmad-dev-story <story-file>`
- Appends system prompt requiring:
  - `@pytest.mark.live` integration tests
  - A `verify-manifest.json` file describing what was created
- Manifest written to `logs/story-runner/<story-key>-verify-manifest.json`
- Manifest contains: source files, test files, unit/live test counts, live test names, notes

### Verify Step (`scripts/lib/run-verify.sh`)
8-phase verification:
1. **Source files exist** (non-blocking warning)
2. **Test files exist** (blocks if missing)
3. **Test count enforcement** — min unit tests + min live tests from manifest
4. **Named live test verification** — specific test methods from manifest
5. **Full unit regression** — `pytest tests/ -x` (all stories)
6. **Story-specific tests** — targeted at manifest test files
7. **Live integration tests** — `pytest -m live` (all stories)
8. **Artifact checks** — no leftover `.partial` files

Expectations loaded from (priority order):
1. Dev's verify manifest (best — exact counts and file paths)
2. Story file parsing via `parse-story-meta.py` (fallback)
3. Defaults (3 unit, 1 live)

### Review Step (`scripts/lib/run-review.sh`)
- Runs `claude --print` with `/bmad-code-review <story-file>`
- Auto-fix mode: CRITICAL/HIGH issues fixed automatically
- Verdicts: APPROVED (→ done), CHANGES_REQUIRED (→ retry), BLOCKED (→ skip)
- **CURRENTLY BROKEN** — see issue above

### Post-Review Verify
After review APPROVED, re-runs full verify to catch regressions from review's auto-fixes. If fails → back to dev retry loop.

### Retry Flow
```
Failure at any step → retry_count++ → back to smart skip/dev with failure_context
Up to 2 retries (configurable with --max-retries)
3 consecutive story failures → circuit breaker stops the batch
```

---

## Key Files

### Runner Scripts
- `scripts/run-stories.sh` — Main orchestrator
- `scripts/lib/common.sh` — Paths, Python binary, logging, `to_win_path()`, `write_runner_status()`
- `scripts/lib/run-dev.sh` — Dev step (claude --print)
- `scripts/lib/run-verify.sh` — 8-phase verify
- `scripts/lib/run-review.sh` — Code review step **(NEEDS FIX: add Skill to allowedTools)**
- `scripts/lib/parse-sprint.sh` — Sprint status YAML helpers
- `scripts/lib/update-status.sh` — Status update helpers
- `scripts/lib/parse-story-meta.py` — Extracts test expectations from story markdown

### Runtime Artifacts
- `logs/story-runner/run-YYYYMMDD-HHMMSS.log` — Main run log
- `logs/story-runner/<story>-dev-HHMMSS.log` — Dev step output (claude --print stdout)
- `logs/story-runner/<story>-verify-HHMMSS.log` — Verify step pytest output
- `logs/story-runner/<story>-review-HHMMSS.log` — Review step output
- `logs/story-runner/<story>-verify-manifest.json` — Dev's verification manifest
- `logs/story-runner/runner.pid` — Daemon PID file
- `logs/story-runner/runner-status.json` — Daemon status (polled by --status)
- `logs/story-runner/daemon-*.log` — Daemon foreground output

### Skill
- `.claude/skills/run-stories/SKILL.md` — Skill definition for `/run-stories`

---

## Windows Compatibility Fixes Applied

These are critical — they caused multiple failures before being fixed:

1. **`PYTHON_BIN`** — Uses `.venv/Scripts/python.exe`, not bare `python` (Windows Store stub)
2. **`to_win_path()`** — Converts `/c/Users/...` to `C:/Users/...` for Python `open()` calls
3. **`tr -d '\r'`** — Strips `\r` from Python stdout before grepping (Windows `\r\n`)
4. **`${line%$'\r'}`** — Strips `\r` in while-read loops reading Python output
5. **`$((x + 1))`** — Instead of `((x++))` which returns exit 1 when x=0, killing `set -e` scripts
6. **Pandas `to_csv` crash** — Windows access violation with timezone-aware datetimes. Fixed by using Python `csv` module in `downloader.py:save_raw_artifact()` and `.values.tobytes()` in `compute_data_hash()`

---

## Sprint Status

```
Epic 1: Market Data Pipeline & Project Foundation
  1-1 ClaudeBackTester review:          done
  1-2 External data research:           done
  1-3 Project structure/config/logging:  done
  1-4 Dukascopy data download:          done
  1-5 Data validation & quality:        done (needs code review)
  1-6 Parquet/Arrow IPC conversion:     done (needs code review)
  1-7 Timeframe conversion:             review (needs code review)
  1-8 Data splitting:                   ready-for-dev
  1-9 E2E pipeline proof:              ready-for-dev
```

## Test Suite (as of story 1-7 completion)
- **155+ unit tests** pass
- **11 live tests** pass across stories 1-4, 1-5, 1-6, 1-7
- Full suite runs in ~2s (unit) / ~90s (with live)

## Codex CLI
- Installed: `codex-cli 0.114.0`
- Auth: Logged in via ChatGPT subscription
- Skill installed at `~/.claude/skills/codex`
- Not yet integrated into the pipeline — consider for independent code review step
- **Codex review output should go to:** `reviews/Codex reviews/`
