# Tool Reference

**18 tools** for queueing, scheduling, and progressing tasks with full
dependency resolution.

| Group | Tool | Description |
|---|---|---|
| Create / read | `create_task` | Create task with auto-incrementing ID |
| | `list_tasks` | Filter by status, assignee, priority, project |
| | `get_task` | Read full task details + body |
| | `update_task` | Change any task field — incl. `blocked_by` (cycle-checked) and `completed`. Pass `"-"` to clear list/optional fields. Modifying `blocked_by` so a Backlog task ends up with no unresolved blockers auto-promotes it to Ready (skipped when status is set explicitly in the same call) |
| | `bulk_update` | Apply many `update_task` calls in one round-trip; per-task pass/fail in the response |
| Body edits | `tick_item` | Check/uncheck a checklist item in the body (1-based index) |
| | `add_comment` | Append a dated note under the task body's `## Comments` section |
| | `list_comments` | List all comments on a task |
| Dependencies | `add_blocker` | Add a dependency (with cycle check) |
| | `task_tree` | Show dependency tree as ASCII. `direction="blockers"` (default — what this waits on), `"dependents"` (what waits on this), or `"both"` |
| | `validate_dependencies` | Audit graph (cycles, missing refs) **and** workflow / state drift — In-Progress-without-assignee, `blocked_by` pointing to Cancelled, `completed:` set on a non-Done task |
| | `blocked_tasks` | List Ready tasks waiting on dependencies |
| Workflow | `start_task` | Mark In Progress (verifies deps satisfied) |
| | `complete_task` | Mark Done; auto-promotes Backlog dependents to Ready when their last blocker clears, and surfaces them under `promoted` alongside the existing `unblocked` list |
| | `block_task` | Mark Blocked with reason (external blockers) |
| | `next_task` | Get next workable task (deps satisfied, sorted by priority) |
| | `my_tasks` | Quick view: overdue, due today, in progress |
| Audit | `list_audit` | Read the per-vault status-change log — `since=YYYY-MM-DD`, `task_id=`, `limit=`. Source: `<vault>/.task-manager/audit.jsonl` |
