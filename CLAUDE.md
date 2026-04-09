# CLAUDE.md

## Project Overview
Task management MCP server for Claude Code. Stores tasks as markdown files in an Obsidian vault with full dependency resolution. Lets you queue work, assign tasks to Claude, and have Claude pick up the next workable task automatically based on priority + dependencies.

## Running
```bash
OBSIDIAN_VAULT_PATH=/path/to/vault .venv/bin/python -m task_manager_mcp
```

## Testing
```bash
.venv/bin/pytest tests/ -v
```

## Architecture
- `task_manager_mcp/server.py` — FastMCP server, tool definitions
- `task_manager_mcp/tasks.py` — Task dataclass, status/priority enums, file I/O
- `task_manager_mcp/deps.py` — Dependency resolver, cycle detection, next_task algorithm
- `task_manager_mcp/vault.py` — Vault adapter (lightweight wrapper for file ops)

## Task Format
Tasks are stored as markdown files in `tasks/` folder of the vault:

```yaml
---
type: task
id: T-042
title: Fix auth middleware bug
status: Ready          # Backlog, Ready, In Progress, Done, Blocked, Cancelled
priority: P2           # P1, P2, P3, P4
assignee: claude       # me, claude
project: "[[API Migration]]"
area: Backend
created: 2026-04-09
due: 2026-04-12
completed: null
tags: [bug, auth]
blocked_by: [T-038, T-040]
---

## What to do
...

## Acceptance criteria
- [ ] ...
```

## Key Conventions
- Task IDs auto-incremented: T-001, T-002, ...
- `next_task` returns highest-priority Ready task with all dependencies satisfied
- Cycle detection on every create/update
- Vault path via `OBSIDIAN_VAULT_PATH` env var
- Logging to stderr only (STDIO transport requirement)
