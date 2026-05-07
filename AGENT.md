# AGENT.md

Guidance for any MCP-capable agent (Claude Code, Cursor, Cline,
Continue, Goose, Windsurf, …) on how to use **task-manager-mcp**
effectively.

Two ways to wire this up:

1. **Agents that auto-load `AGENT.md` / `AGENTS.md` / `CLAUDE.md`** —
   drop a copy of the [system-prompt block](#system-prompt-block) into
   your project or global agent file. The agent picks it up every
   session.
2. **Agents configured via explicit system prompt** — paste the same
   block into your agent's prompt config.

The architecture / running notes at the bottom are for contributors
working in *this* repo.

## System-prompt block

Paste the section below verbatim into your agent's system prompt or
project-level rules file:

```markdown
## Task Manager MCP

You have access to task-manager-mcp, an MCP server with 16 tools for
managing dependency-aware tasks stored as markdown files in an
Obsidian vault. Follow these rules:

- When the user says "what should I work on next?" or "pick up the
  next task", call `next_task`. It returns the highest-priority
  `Ready` task whose blockers are all `Done` or `Cancelled`. Don't
  pick from `list_tasks` and filter manually — `next_task` already
  does the priority + due-date + dependency math.
- For "what's on my plate?" / "anything overdue?", call `my_tasks`.
  It groups overdue / due-today / in-progress with one round-trip.
- Before starting work on a task, call `start_task` (it verifies
  blockers are satisfied — refuses if not). When done, call
  `complete_task` — the response tells you which downstream tasks
  just unblocked, so surface that to the user.
- For checklist items in a task body, use `tick_item(task_id, index)`
  with a 1-based index. Don't rewrite the body via `update_task` to
  flip a single box — `tick_item` is in-place and won't conflict
  with concurrent Obsidian edits.
- Dropping a comment for future-you or another agent? Use
  `add_comment(task_id, text, author)` — it appends a dated bullet
  under `## Comments` in the body. Author defaults to `agent`.
- Don't auto-fire `complete_task` when all checkboxes hit 100%.
  Marking Done has side effects (timestamp, downstream unblock
  notifications) — keep it explicit.
- Don't create a task graph cycle. `add_blocker` and
  `update_task(blocked_by=...)` both validate, but if you're scripting
  many edits, run `validate_dependencies` afterward as a sanity check.
```

## When to use each tool

### "What's next?" intent

| User asks | Tool | Why |
|---|---|---|
| "What should I work on next?" | `next_task` | Highest-priority Ready task with all blockers satisfied. Built-in priority + due-date sort. |
| "Anything overdue?" / "What's on my plate today?" | `my_tasks` | Groups overdue / due-today / in-progress in one call. Defaults to `assignee=me` — pass `assignee=agent` for the agent's queue. |
| "What's in flight?" | `list_tasks status:"In Progress"` | When you want every in-flight task across assignees. |
| "Show me all P1s" | `list_tasks priority:P1` | Cross-cuts statuses; useful for triage. |
| "What's blocked?" | `blocked_tasks` | Ready tasks waiting on unfinished deps — the queue that *would* be workable once blockers land. |

### Workflow flow

```
create_task("…", priority="P2", blocked_by=["T-038"])
      ↓
when blockers Done → next_task surfaces it
      ↓
start_task(T-042)            ← refuses if blockers still unfinished
      ↓
tick_item(T-042, 1, True)    ← flip individual checkboxes as work progresses
add_comment(T-042, "looked at line 142, that's the bug")
      ↓
complete_task(T-042)         ← announces unblocked downstream tasks
```

Rules of thumb:

- `start_task` is optional — going Backlog → Ready → In Progress is
  the formal flow, but creating a task already-Ready and going
  straight to `complete_task` works for trivial work.
- `complete_task` returns `unblocked: [...]`. Surface that to the
  user so they know what just opened up.
- Never set `status: Done` via `update_task` directly. `complete_task`
  also writes the `completed:` timestamp and computes the unblock
  list — bypassing it leaves the task graph half-resolved.

### Dependency hygiene

- `task_tree(task_id)` returns an ASCII tree of upstream blockers.
  Use it before saying "this is blocked because…" so you cite the
  actual chain.
- `add_blocker` and `update_task(blocked_by=...)` both run cycle
  detection — if the call rejects with a cycle error, *don't*
  retry with the cycle resolved silently. Tell the user which loop
  was attempted; they probably miswrote.
- If a task has been `Blocked` (status, not `blocked_by`) on an
  external dependency, use `block_task(task_id, reason)`. The reason
  string lands on the task and shows in `list_tasks status:Blocked`
  triage views.

## Task format

Tasks are markdown files in `<vault>/tasks/` (or
`TASK_MANAGER_TASKS_FOLDER` if overridden):

```yaml
---
type: task
id: T-042
title: Implement rate limiting
status: Ready          # Backlog, Ready, In Progress, Done, Blocked, Cancelled
priority: P2           # P1, P2, P3, P4
assignee: agent        # me, agent (or any actor from .task-manager/config.yml)
project: "[[API Migration]]"
area: Backend
created: 2026-04-09
due: 2026-04-15
blocked_by: [T-038, T-040]
tags: [backend, performance]
---

## What to do
Add token-bucket rate limiting to the v3 API endpoints.

## Acceptance criteria
- [ ] 100 req/min per client default
- [ ] Rate limit headers returned
- [ ] Tests cover bucket exhaustion
```

Body is the source of truth for checklists and comments — never
mirrored to frontmatter. So `tick_item` and `add_comment` edit the
body directly, and progress (`{done, total, pct}`) is computed on
read.

## Operational notes

- **Statuses**: `Backlog → Ready → In Progress → Done` is the happy
  path. `Blocked` and `Cancelled` are escapes; `Blocked → Ready`
  when the external blocker clears.
- **`next_task` filters by assignee**. Default is `me`; pass
  `assignee=agent` for the agent's queue, or any custom actor.
- **Custom actors**: `<vault>/.task-manager/config.yml` lets a team
  add `alice`, `bob`, `cursor`, etc. The legacy `claude` is always
  accepted as an alias for `agent`.
- **Dependency cycles**: rejected at write time
  (`create_task` / `update_task` / `add_blocker`), so the live graph
  is guaranteed acyclic. `validate_dependencies` is for verifying
  *post-import* (e.g. after copying tasks across vaults).
- **Comments are dated, plain markdown bullets** under `## Comments`.
  Both Obsidian-side hand edits and `add_comment` calls round-trip
  cleanly; don't worry about clobbering each other.

---

# Contributing to this repo

Everything below is for contributors working in this codebase, not
for end-users wiring an agent against it.

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
- `task_manager_mcp/deps.py` — Dependency resolver, cycle detection,
  `next_task` algorithm
- `task_manager_mcp/checklist.py` — Body checklist parser
  (`- [ ]` / `- [x]`), progress rollup, `tick()` mutation. Progress
  is derived on read — never persisted in frontmatter — so the body
  is the single source of truth.
- `task_manager_mcp/comments.py` — Dated comment thread under a
  `## Comments` section in the task body. `append_comment()` creates
  the section on first call, `parse_comments()` extracts back to
  dicts. Same body-is-truth pattern as checklist — comments aren't
  mirrored to frontmatter.
- `task_manager_mcp/explorer/` — FastAPI sidecar serving a
  drag-and-drop Kanban UI over the same vault.
  `pip install -e ".[explorer]"` then
  `python -m task_manager_mcp.explorer --host 0.0.0.0 --port 8765`.
  Mutations write straight to task frontmatter, so the MCP and the
  UI share state.

## Key conventions

- Task IDs auto-incremented: T-001, T-002, …
- `next_task` returns highest-priority Ready task with all
  dependencies satisfied
- Cycle detection on every create/update
- Vault path via `OBSIDIAN_VAULT_PATH` env var
- Tasks folder defaults to `tasks/` relative to vault; override with
  `TASK_MANAGER_TASKS_FOLDER` (resolved against vault root, `..`
  escapes rejected)
- Actors (the values accepted for `assignee:`) default to
  `["me", "agent", "claude"]`. Teams can override at
  `<vault>/.task-manager/config.yml`:
  ```yaml
  actors: [me, agent, alice, bob, cursor]
  ```
  The list is loaded once at startup by `TaskStore.__init__`
  (`load_actors()` in `tasks.py`). Validation runs at the write
  boundary (`TaskStore.create` / `update` / `validate_assignee`);
  reads are permissive so files with no-longer-configured assignees
  still load. `claude` always aliases to `agent` if `agent` is in
  the list.
- Logging to stderr only (STDIO transport requirement)
- Checklist progress (`{done, total, pct}`) is computed on read
  from the body and attached to tool output only when there's at
  least one checkbox. `tick_item` flips a box in place;
  `complete_task` is still explicit even when 100%.
