# Tool Reference

**16 tools** for queueing, scheduling, and progressing tasks with full
dependency resolution.

| Group | Tool | Description |
|---|---|---|
| Create / read | `create_task` | Create task with auto-incrementing ID |
| | `list_tasks` | Filter by status, assignee, priority, project |
| | `get_task` | Read full task details + body |
| | `update_task` | Change any task field |
| Body edits | `tick_item` | Check/uncheck a checklist item in the body (1-based index) |
| | `add_comment` | Append a dated note under the task body's `## Comments` section |
| | `list_comments` | List all comments on a task |
| Dependencies | `add_blocker` | Add a dependency (with cycle check) |
| | `task_tree` | Show dependency tree as ASCII |
| | `validate_dependencies` | Check for cycles + missing deps |
| | `blocked_tasks` | List Ready tasks waiting on dependencies |
| Workflow | `start_task` | Mark In Progress (verifies deps satisfied) |
| | `complete_task` | Mark Done + announce what's unblocked |
| | `block_task` | Mark Blocked with reason (external blockers) |
| | `next_task` | Get next workable task (deps satisfied, sorted by priority) |
| | `my_tasks` | Quick view: overdue, due today, in progress |
