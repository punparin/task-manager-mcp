"""Server-side instructions surfaced via the MCP ``initialize`` response.

Most MCP clients (Claude Code, …) inject these into the agent's system
prompt automatically, so the user gets the right defaults without
copying anything into their own ``CLAUDE.md`` / Cursor rules.

Kept terse on purpose — every byte here ships in every session. For
the operator-facing reference (statuses, custom actors, env vars,
explorer), see ``AGENT.md`` and ``README.md``.
"""

INSTRUCTIONS = """\
You have access to task-manager-mcp, an MCP server for
dependency-aware tasks stored as markdown files in an Obsidian vault.
Operating rules:

## Tool choice

- "What should I work on next?" / "pick up the next task" →
  `next_task`. It returns the highest-priority `Ready` task whose
  blockers are all `Done`/`Cancelled`. Don't pull from `list_tasks`
  and filter manually — `next_task` already does the priority +
  due-date + dependency math.
- "What's on my plate?" / "anything overdue?" → `my_tasks`. Groups
  overdue / due-today / in-progress in one round-trip. Defaults to
  `assignee=me`; pass `assignee=agent` for the agent's queue.
- "What's in flight?" → `list_tasks(status="In Progress")`.
- "Show me all P1s" → `list_tasks(priority="P1")` (cross-cuts
  statuses).
- "Tasks tagged X" → `list_tasks(tags="X")`. Pass multiple tags
  comma-separated for AND-match (`tags="backend,perf"` returns
  tasks carrying both). Use this to narrow result size when a
  bare `list_tasks` would return a wall of tasks.
- "Tasks related to X" / "similar to" / "what touches Y" (the
  fuzzy, semantic version of the question) → this MCP has no
  embedding index of its own; compose with an Obsidian semantic
  search MCP if one is loaded. Pattern: call its
  `semantic_search(query="...", path="tasks/")` first (scope to
  the tasks folder so non-task notes are filtered out), then
  enrich the returned task ids with `get_task` / `list_tasks` to
  layer in status, blockers, and due dates. If no semantic MCP is
  available, fall back to `list_tasks(tags=…)` or a `project`
  partial match.
- "What's blocked?" → `blocked_tasks`. Ready tasks waiting on
  unfinished deps — the queue that would be workable once blockers
  land.
- "What changed today?" / "what shifted recently?" → `list_audit`.
  Reads the per-vault status-change log; pass `since="YYYY-MM-DD"` for
  recency, `task_id="T-042"` to scope to one task. Each task also
  carries its latest transition date in the `last_status_change`
  frontmatter field.

## Workflow flow

```
create_task("…", priority="P2", blocked_by=["T-038"])
    ↓ when blockers Done → next_task surfaces it
start_task(T-042)             ← refuses if blockers still unfinished
    ↓ work happens
tick_item(T-042, 1, True)     ← per checkbox progress
add_comment(T-042, "looked at line 142, that's the bug")
    ↓
complete_task(T-042)          ← announces unblocked downstream tasks
```

- `start_task` is optional for trivial work — Backlog → Ready →
  In Progress is the formal flow, but going straight to
  `complete_task` works.
- `complete_task` returns `unblocked: [...]` (already-Ready dependents
  whose blockers cleared) and `promoted: [...]` (Backlog dependents
  auto-flipped to Ready because all their blockers are now terminal).
  Surface both so the user sees what just opened up.
- Never set `status: Done` via `update_task` directly. `complete_task`
  also writes `completed:` and computes the unblock list — bypassing
  it leaves the graph half-resolved.
- Don't auto-fire `complete_task` when checkboxes hit 100%. Marking
  Done has side effects (timestamp, downstream notifications) — keep
  it explicit.

## Bulk edits

- For sweeping changes across many tasks (backlog grooming, reassigning
  an area, retagging) use `bulk_update(updates=[{...}, ...])` instead of
  one `update_task` per row. Each entry takes `task_id` plus any of the
  same fields. Failures are reported per task; earlier successes don't
  roll back. After a big sweep, run `validate_dependencies` to confirm
  the graph is still coherent.

## Checklists and comments

- Flip a checkbox via `tick_item(task_id, index, checked)` with a
  1-based index. Don't rewrite the body via `update_task` to flip a
  single box — `tick_item` is in-place and won't conflict with
  concurrent Obsidian edits.
- Drop notes for future-you or another agent via
  `add_comment(task_id, text, author)`. Author defaults to `agent`.
  Comments go under `## Comments` as dated bullets and round-trip
  cleanly with hand edits in Obsidian.

## Dependency hygiene

- `task_tree(task_id)` returns an ASCII tree of upstream blockers.
  Use it before saying "this is blocked because…" so you cite the
  actual chain. Pass `direction="dependents"` to walk the other way
  (what's waiting on this task), or `direction="both"` for impact
  analysis before cancelling/rescoping.
- `add_blocker` and `update_task(blocked_by=...)` both run cycle
  detection. If they reject with a cycle error, *don't* silently
  retry with the cycle resolved — tell the user which loop was
  attempted; they probably miswrote.
- For "blocked on something external" (waiting on a person/decision),
  use `block_task(task_id, reason)`. The reason string lands on the
  task and shows in `list_tasks(status="Blocked")` triage views.
- Don't create a task graph cycle. If you're scripting many edits,
  run `validate_dependencies` afterward as a sanity check — it now
  also flags In-Progress-without-assignee, `completed:` set on a
  non-Done task, and `blocked_by` pointing to a Cancelled task.

## Task format (for reading raw markdown)

Tasks live in `<vault>/tasks/` (override with `TASK_MANAGER_TASKS_FOLDER`).
Frontmatter: `type, id, title, status, priority, assignee, project, area,
created, due, completed, last_status_change, blocked_by, tags`.
Body has `## What to do`, `## Acceptance criteria` (checklist), and
`## Comments`. Body is the source of truth for checklists and
comments — they are never mirrored to frontmatter; progress
(`{done, total, pct}`) is computed on read.

Statuses: `Backlog → Ready → In Progress → Done` (happy path).
`Blocked` and `Cancelled` are escapes; `Blocked → Ready` when the
external blocker clears. Priorities: `P1` (highest) → `P4`.
"""
