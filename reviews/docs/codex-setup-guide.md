# Codex CLI Setup & Usage Guide

**Created:** 2026-03-14
**System:** Windows 11, bash shell (Git Bash / MSYS2)
**Codex Version:** codex-cli 0.114.0
**Purpose:** Run OpenAI's Codex agent from Claude Code for AI-powered code reviews and analysis

---

## What Is Codex CLI?

Codex CLI (`codex`) is OpenAI's command-line AI agent. It can:
- Read and analyze codebases
- Write and edit code
- Run shell commands in a sandboxed environment
- Perform code reviews against git diffs or entire codebases

We invoke it **from within Claude Code** using a custom skill (`/codex`), giving us a two-AI workflow: Claude orchestrates, Codex executes.

---

## Installation

```bash
# Install via npm (global)
npm install -g @openai/codex

# Verify installation
codex --version
```

## Authentication

### Option 1: ChatGPT Subscription (FREE — uses your existing plan)
```bash
codex login
# Opens browser for ChatGPT OAuth login
```

### Option 2: API Key (PAY-PER-TOKEN — billed separately)
```bash
printenv OPENAI_API_KEY | codex login --with-api-key
```

### Check current auth
```bash
codex login status
# Expected output: "Logged in using ChatGPT" (subscription)
# or: "Logged in using API key" (pay-per-token)
```

**Important:** ChatGPT subscription auth uses your existing Plus/Pro plan at no extra cost. API key auth bills per token on platform.openai.com. Always verify with `codex login status` before running expensive jobs.

---

## Core Commands

### Non-Interactive Execution (what we use from Claude Code)
```bash
codex exec [OPTIONS] "your prompt here"
```

### Code Review
```bash
codex exec review --uncommitted          # Review uncommitted changes
codex exec review --base main             # Review diff against a branch
codex exec review --commit abc123         # Review a specific commit
```

**Note:** `review` requires a git repository. For non-git directories, use a prompt-based approach instead (see Workflows below).

### Resume a Session
```bash
echo "follow-up prompt here" | codex exec --skip-git-repo-check resume --last 2>/dev/null
```
When resuming, do NOT add config flags (model, reasoning, sandbox) — they're inherited from the original session.

---

## Key Options

| Flag | Purpose | Example |
|------|---------|---------|
| `-m, --model <MODEL>` | Select model | `-m gpt-5.4` |
| `--config model_reasoning_effort="<level>"` | Reasoning depth | `--config model_reasoning_effort="high"` |
| `--sandbox <mode>` | Execution sandbox | `--sandbox read-only` |
| `--full-auto` | Auto-approve all actions | Required for write/full-access modes |
| `--skip-git-repo-check` | Skip git repo requirement | Always use from Claude Code |
| `-C, --cd <DIR>` | Set working directory | `-C /path/to/project` |

### Models (as of March 2026)
| Model | Use Case |
|-------|----------|
| `gpt-5.4` | Latest frontier model, best for complex analysis |
| `gpt-5.3-codex` | Full Codex model, good for code tasks |
| `gpt-5.3-codex-spark` | Fast variant, quick tasks |
| `gpt-5.2` | Previous generation |

### Reasoning Effort
| Level | Speed | Depth |
|-------|-------|-------|
| `xhigh` | Slowest | Maximum reasoning, most thorough |
| `high` | Moderate | Strong reasoning, good balance (recommended) |
| `medium` | Fast | Adequate for straightforward tasks |
| `low` | Fastest | Minimal reasoning |

### Sandbox Modes
| Mode | Can Read | Can Write | Network | Use Case |
|------|----------|-----------|---------|----------|
| `read-only` | Yes | No | No | Code review, analysis |
| `workspace-write` | Yes | Yes (workspace) | No | Apply edits, refactoring |
| `danger-full-access` | Yes | Yes (all) | Yes | Install deps, API calls |

---

## Workflows We've Established

### 1. Full Codebase Review (no git required)
```bash
codex exec --skip-git-repo-check \
  -m gpt-5.4 \
  --config model_reasoning_effort="high" \
  --sandbox read-only \
  "Perform a thorough code review of this entire codebase. Analyze code quality, architecture, potential bugs, security concerns, and suggest improvements." \
  2>/dev/null
```

### 2. Story-Specific Review
```bash
codex exec --skip-git-repo-check \
  -m gpt-5.4 \
  --config model_reasoning_effort="high" \
  --sandbox read-only \
  "Review the implementation of Story X.Y: <title>. The story spec is in <path>. The main implementation is in <path>. Assess each acceptance criterion: fully met, partially met, or not met. Flag bugs with specific file:line references." \
  2>/dev/null
```

### 3. Git-Based Review (requires git repo)
```bash
codex exec --skip-git-repo-check \
  -m gpt-5.4 \
  --config model_reasoning_effort="high" \
  --sandbox read-only \
  review --uncommitted \
  2>/dev/null
```

### 4. Resume for Follow-Up
```bash
echo "Dig deeper into finding #2 about timezone validation. Show me exactly what needs to change." \
  | codex exec --skip-git-repo-check resume --last 2>/dev/null
```

---

## The Claude Code `/codex` Skill

### Where It Lives
```
~/.claude/skills/codex/SKILL.md
```

### What It Does
The `/codex` skill is a Claude Code skill that:
1. Asks the user for model + reasoning effort
2. Asks for the task and sandbox mode
3. Assembles and runs the `codex exec` command
4. Captures output (suppresses stderr thinking tokens with `2>/dev/null`)
5. Summarizes results
6. Offers to resume the session for follow-ups

### How Claude Code Interacts With Codex
```
User → Claude Code → /codex skill → codex exec CLI → OpenAI API → Results → Claude Code summarizes
```

Claude Code acts as orchestrator:
- Understands the project context (stories, epics, architecture)
- Formulates the right prompt for Codex
- Critically evaluates Codex output (can disagree and push back)
- Saves results to files

Codex acts as executor:
- Reads the codebase independently
- Performs analysis with its own reasoning
- Returns structured findings with file:line references

### Critical Evaluation
The skill instructs Claude to treat Codex as a **colleague, not an authority**. If Codex and Claude disagree, Claude can resume the session and discuss:
```bash
echo "This is Claude (claude-opus-4-6) following up. I disagree with [X] because [evidence]." \
  | codex exec --skip-git-repo-check resume --last 2>/dev/null
```

---

## Tips & Lessons Learned

### `2>/dev/null` Is Essential
Codex streams thinking tokens to stderr. Without suppression, they flood the output. Always append `2>/dev/null` unless debugging.

### Non-Git Directories
The `review` subcommand requires git. For projects without git:
- Use prompt-based review (`codex exec ... "Review this codebase..."`)
- Or init git first: `git init && git add -A && git commit -m "initial"`

### `--skip-git-repo-check` Always
Claude Code may run from directories that aren't git repos. Always include this flag.

### Sandbox Determines What Codex Can Do
- For reviews: always `read-only` (safe, can't modify anything)
- For applying fixes: `workspace-write` + `--full-auto`
- For running tests: `danger-full-access` + `--full-auto` (Codex needs to execute pytest etc.)

### Output Quality
- `high` reasoning effort gives the best cost/quality balance
- Codex returns markdown with file:line hyperlinks
- Findings are severity-tagged (High/Medium/Low)
- Reviews include acceptance criteria scorecards when prompted

### Session Persistence
Codex sessions persist locally. You can resume any previous session with `resume --last` or by session ID. The resumed session keeps all prior context (files read, findings, etc.).

---

## Replicating This Setup on Another System

### Prerequisites
1. **Node.js** (for npm)
2. **Git Bash or MSYS2** (bash shell on Windows)
3. **Claude Code CLI** installed and configured
4. **ChatGPT Plus/Pro subscription** (for free Codex usage)

### Steps
1. Install Codex CLI:
   ```bash
   npm install -g @openai/codex
   codex --version  # verify
   ```

2. Authenticate with ChatGPT:
   ```bash
   codex login
   # Complete browser OAuth flow
   codex login status  # verify "Logged in using ChatGPT"
   ```

3. The `/codex` skill should already be available if using the same Claude Code skill set. If not, ensure `~/.claude/skills/codex/SKILL.md` exists with the skill definition.

4. Test with a simple read-only review:
   ```bash
   codex exec --skip-git-repo-check -m gpt-5.4 --config model_reasoning_effort="medium" --sandbox read-only "List all files in this directory and summarize what this project does." 2>/dev/null
   ```

5. Create the reviews output folder:
   ```bash
   mkdir -p "reviews/Codex reviews"
   ```

### Troubleshooting
| Issue | Fix |
|-------|-----|
| `codex: command not found` | `npm install -g @openai/codex` |
| Auth errors | `codex logout && codex login` |
| Empty output on review | Check `codex login status` and ensure git repo exists for `review` command |
| Timeout on large codebases | Increase Claude Code bash timeout (up to 600000ms / 10 min) |
| Thinking tokens in output | Ensure `2>/dev/null` is appended |

---

## File Structure

```
reviews/
└── Codex reviews/
    ├── codex-setup-guide.md          ← This file
    ├── story-1.5-codex-review.md     ← Story 1.5 review (2026-03-14)
    └── ...                           ← Future reviews go here
```
