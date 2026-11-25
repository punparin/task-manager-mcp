# Tool Reference

**22 tools** for queueing, scheduling, and progressing tasks with full
dependency resolution.

| Group | Tool | Description |
|---|---|---|
| Create / read | `create_task` | Create task with auto-incrementing ID. Pass `epic="E-001"` to file it under an epic (warns, but still files it, if the epic is Done or Cancelled) |
| | `list_tasks` | Filter by status, assignee, priority, project, tags (comma-separated, AND-matched), epic (`epic="E-001"`, or `epic="none"` for tasks outside any epic) |
| | `get_task` | Read full task details + body |
| | `update_task` | Change any task field — incl. `blocked_by` (cycle-checked) and `completed`. Pass `"-"` to clear `blocked_by` (to `[]`), `completed` (to unset) or `epic` (remove from its epic). Modifying `blocked_by` so a Backlog task ends up with no unresolved blockers auto-promotes it to Ready (skipped when status is set explicitly in the same call). Transitioning to `Cancelled` strips dead `blocked_by` references from every dependent and promotes any that end up fully unblocked |
| | `bulk_update` | Apply many `update_task` calls in one round-trip; per-task pass/fail in the response. Accepts a subset of `update_task`'s fields: `title, status, priority, assignee, project, area, due, tags, body, epic` — `blocked_by` and `completed` must go through `update_task` so cycle-checks and auto-promote run per task |
| Body edits | `tick_item` | Check/uncheck a checklist item in the body (1-based index). Also takes an epic ID to tick one of its success criteria |
| | `add_comment` | Append a dated note under the task body's `## Comments` section |
| | `list_comments` | List all comments on a task |
| Dependencies | `add_blocker` | Add a dependency (with cycle check) |
| | `task_tree` | Show dependency tree as ASCII. `direction="blockers"` (default — what this waits on), `"dependents"` (what waits on this), or `"both"` |
| | `validate_dependencies` | Audit graph (cycles, missing refs) **and** workflow / state drift — In-Progress-without-assignee, `blocked_by` pointing to Cancelled, `completed:` set on a non-Done task — plus epic issues: tasks pointing at a missing epic, Done/Cancelled epics with open tasks |
| | `blocked_tasks` | List Ready tasks waiting on dependencies |
| Workflow | `start_task` | Mark In Progress (verifies deps satisfied) |
| | `complete_task` | Mark Done; auto-promotes Backlog dependents to Ready when their last blocker clears, and surfaces them under `promoted` alongside the existing `unblocked` list |
| | `block_task` | Mark Blocked with reason (external blockers) |
| | `next_task` | Get next workable task (deps satisfied, sorted by priority). `epic="E-001"` picks only from that epic |
| | `my_tasks` | Quick view: overdue, due today, in progress |
| Epics | `create_epic` | Create an epic (`E-001`, …) with a goal, success criteria (one per line, saved as a checklist), priority, status (`Planned`/`Active`), project, target date, colour and tags |
| | `list_epics` | Epics with progress rolled up from their tasks: done/total and %, per-status counts, blocked count, `ready_to_close`, `overdue`. `status=` one of `Planned`, `Active`, `Done`, `Cancelled`, or `open` |
| | `get_epic` | One epic: goal and body, success-criteria progress, task progress, its tasks grouped by status, and the next workable task inside it |
| | `update_epic` | Change any epic field; `"-"` clears project, due, colour or tags. Status changes are written to the audit log; `Done` stamps `completed` and reopening clears it. Closing leaves the epic's tasks alone and lists any still open |
| Audit | `list_audit` | Read the per-vault status-change log — `since=YYYY-MM-DD`, `task_id=`, `limit=`. Source: `<vault>/.task-manager/audit.jsonl` |
