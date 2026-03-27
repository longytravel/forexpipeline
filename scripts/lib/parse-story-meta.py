#!/usr/bin/env python3
"""Extract verification metadata from a BMAD story markdown file.

Used by run-verify.sh to determine per-story test expectations.
Output: JSON to stdout.
"""
import re
import sys
import json
from pathlib import Path


def parse_story(story_path: str) -> dict:
    content = Path(story_path).read_text(encoding="utf-8")

    # --- Title ---
    title_match = re.search(r"^#\s+(.+)", content, re.MULTILINE)
    title = title_match.group(1).strip() if title_match else ""

    # --- Story type ---
    story_type = "code"
    lower_title = title.lower()
    if any(kw in lower_title for kw in ["review", "research", "analysis", "investigation"]):
        story_type = "research"
    elif any(kw in lower_title for kw in ["e2e", "end-to-end", "pipeline proof"]):
        story_type = "e2e"

    # --- Test file basenames (test_*.py anywhere in the story) ---
    # Deduplicate while preserving order
    test_basenames_raw = re.findall(r"\b(test_\w+\.py)\b", content)
    seen = set()
    test_basenames = []
    for t in test_basenames_raw:
        if t not in seen:
            seen.add(t)
            test_basenames.append(t)

    # --- Source file basenames marked as NEW ---
    new_file_lines = re.findall(r"(\w+\.py)\s+#\s*NEW", content)
    source_basenames = [f for f in new_file_lines if not f.startswith("test_")]

    # --- Count individual test cases specified in the story ---
    # Patterns like: "Unit test: `test_detect_gaps_identifies_gaps`"
    # or "11.3 Unit test:" or "11.20 Integration test:"
    named_tests = re.findall(r"`(test_\w+)`", content)
    # Also count "test:" lines in task list that describe individual tests
    test_task_lines = re.findall(
        r"(?:Unit test|Integration test|Live test|test):\s+", content, re.IGNORECASE
    )
    expected_test_count = max(len(set(named_tests)), len(test_task_lines))

    # --- Check if story explicitly mentions live/integration tests ---
    has_live_mention = bool(
        re.search(
            r"@pytest\.mark\.live|integration test|live.*test|\bmark\.live\b",
            content,
            re.IGNORECASE,
        )
    )

    # --- Count tasks ---
    task_matches = re.findall(r"-\s+\[[ x]\]\s+\*\*Task\s+\d+", content)
    task_count = len(task_matches)

    return {
        "title": title,
        "story_type": story_type,
        "test_basenames": test_basenames,
        "source_basenames": source_basenames,
        "task_count": task_count,
        "expected_test_count": expected_test_count,
        "has_live_mention": has_live_mention,
    }


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: parse-story-meta.py <story-file>", file=sys.stderr)
        sys.exit(1)

    result = parse_story(sys.argv[1])
    print(json.dumps(result))
