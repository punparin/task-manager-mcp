#!/usr/bin/env python3
"""Pre-commit guard: tool/route surface changes must update docs.

Fires when a commit changes the public surface of the MCP server or
the explorer (an `@mcp.tool()` decorator, an `@app.<verb>()` decorator,
or the `def` line that immediately follows one) without a matching
edit to a doc file. Pure refactors — internals only, no surface diff —
pass through unchanged.

Surface files watched:
  task_manager_mcp/server.py
  task_manager_mcp/explorer/server.py

Doc files that satisfy the check:
  docs/tools.md
  docs/explorer.md
  task_manager_mcp/agent_instructions.py
  README.md

Run manually:
  python scripts/check_docs_with_features.py
"""

from __future__ import annotations

import re
import subprocess
import sys

FEATURE_FILES = {
    "task_manager_mcp/server.py",
    "task_manager_mcp/explorer/server.py",
}
DOC_FILES = {
    "docs/tools.md",
    "docs/explorer.md",
    "task_manager_mcp/agent_instructions.py",
    "README.md",
}

DECORATOR_RE = re.compile(r"^[+-]\s*@(mcp\.tool|app\.(get|post|patch|put|delete))\b")
DEF_RE = re.compile(r"^[+-]\s*def\s+\w+\s*\(")


def staged_files() -> set[str]:
    out = subprocess.check_output(
        ["git", "diff", "--cached", "--name-only", "--diff-filter=ACMR"],
        text=True,
    )
    return {line for line in out.splitlines() if line}


def surface_changed(path: str) -> bool:
    diff = subprocess.check_output(
        ["git", "diff", "--cached", "-U1", "--", path], text=True
    ).splitlines()
    prev_was_decorator = False
    for line in diff:
        if DECORATOR_RE.match(line):
            return True
        if prev_was_decorator and DEF_RE.match(line):
            return True
        prev_was_decorator = bool(re.match(r"^\s*@(mcp\.tool|app\.\w+)", line))
    return False


def main() -> int:
    staged = staged_files()
    touched = sorted(staged & FEATURE_FILES)
    if not touched:
        return 0

    surface = [p for p in touched if surface_changed(p)]
    if not surface:
        return 0

    if staged & DOC_FILES:
        return 0

    print(
        "✗ Tool/route surface changed without updating any docs.\n\n"
        f"  Surface diffs in: {', '.join(surface)}\n"
        f"  Update at least one of:\n"
        f"    - docs/tools.md\n"
        f"    - docs/explorer.md\n"
        f"    - task_manager_mcp/agent_instructions.py\n"
        f"    - README.md\n\n"
        "  If this is a refactor that genuinely doesn't change the\n"
        "  public surface, the decorator and def lines shouldn't be\n"
        "  in the diff — adjust your patch so they aren't.\n",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
