"""Task Manager MCP — FastMCP server with task tools and dependency resolution."""

import json
import logging
import os
import sys
from datetime import date

from fastmcp import FastMCP

from .checklist import task_to_dict
from .checklist import tick as _tick_item
from .comments import append_comment, parse_comments
from .deps import blocked_tasks as _blocked_tasks
from .deps import detect_cycle, is_unblocked, render_tree, what_unblocks
from .deps import next_task as _next_task
from .deps import task_tree as _task_tree
from .tasks import VALID_PRIORITY, VALID_STATUS, TaskStore, canonical_assignee

logging.basicConfig(
    level=logging.INFO,
    format="%(name)s %(levelname)s: %(message)s",
    stream=sys.stderr,
)
logger = logging.getLogger("task_manager_mcp")

vault_path = os.environ.get("OBSIDIAN_VAULT_PATH")
if not vault_path:
    logger.error("OBSIDIAN_VAULT_PATH environment variable not set")
    sys.exit(1)

store = TaskStore(vault_path)
mcp = FastMCP("task-manager")


# ── Create / Read / Update ─────────────────────────────────────────────


@mcp.tool()
async def create_task(
    title: str,
    priority: str = "P3",
    assignee: str = "me",
    status: str = "Backlog",
    project: str = "",
    area: str = "",
    due: str = "",
    tags: str = "",
    blocked_by: str = "",
    body: str = "",
) -> str:
    """Create a new task. Auto-generates ID (T-001, T-002, ...).

    title: Task title (required)
    priority: P1-P4 (default P3)
    assignee: actor handle from your vault's `.task-manager/config.yml` (default 'me'; falls back to 'me'/'agent'/'claude' when no config). Legacy 'claude' is a synonym for 'agent'.
    status: Backlog/Ready/In Progress/Done/Blocked/Cancelled (default Backlog)
    project: Project name or [[wikilink]] (optional)
    area: Area like 'Backend', 'Frontend' (optional)
    due: Due date YYYY-MM-DD (optional)
    tags: Comma-separated tags (optional)
    blocked_by: Comma-separated task IDs (e.g., 'T-001,T-002')
    body: Task description / acceptance criteria in markdown (optional)
    """
    tags_list = [t.strip() for t in tags.split(",") if t.strip()] if tags else []
    deps_list = [d.strip() for d in blocked_by.split(",") if d.strip()] if blocked_by else []

    # Cycle check
    if deps_list:
        # We don't know the new ID yet, but next_id is deterministic
        new_id = store.next_id()
        cycle = detect_cycle(store, new_id, deps_list)
        if cycle:
            return f"ERROR: Would create dependency cycle: {' → '.join(cycle)}"

    task = store.create(
        title=title,
        priority=priority,
        assignee=assignee,
        status=status,
        project=project or None,
        area=area or None,
        due=due or None,
        tags=tags_list,
        blocked_by=deps_list,
        body=body,
    )
    return f"Created {task.id}: {task.title}\n{json.dumps(task_to_dict(task), indent=2, default=str)}"


@mcp.tool()
async def list_tasks(
    status: str = "",
    assignee: str = "",
    priority: str = "",
    project: str = "",
) -> str:
    """List tasks with optional filters.

    status: filter by status (e.g., 'Ready', 'In Progress')
    assignee: filter by any actor configured in the vault (legacy 'claude' is treated as 'agent')
    priority: filter by P1/P2/P3/P4
    project: filter by project name (partial match)
    """
    tasks = store.all()
    if status:
        tasks = [t for t in tasks if t.status == status]
    if assignee:
        target = canonical_assignee(assignee)
        tasks = [t for t in tasks if canonical_assignee(t.assignee) == target]
    if priority:
        tasks = [t for t in tasks if t.priority == priority]
    if project:
        tasks = [t for t in tasks if t.project and project.lower() in t.project.lower()]

    if not tasks:
        return "No tasks match those filters."

    return json.dumps([task_to_dict(t) for t in tasks], indent=2, default=str)


@mcp.tool()
async def get_task(task_id: str) -> str:
    """Get full details of a task including body content."""
    task = store.get(task_id)
    out = task_to_dict(task, include_body=True)
    return json.dumps(out, indent=2, default=str)


@mcp.tool()
async def update_task(
    task_id: str,
    title: str = "",
    status: str = "",
    priority: str = "",
    assignee: str = "",
    project: str = "",
    area: str = "",
    due: str = "",
    tags: str = "",
    body: str = "",
) -> str:
    """Update fields on an existing task. Only provided fields are changed.

    Pass empty string to leave a field unchanged.
    """
    updates = {}
    if title:
        updates["title"] = title
    if status:
        if status not in VALID_STATUS:
            return f"ERROR: Invalid status. Must be one of {VALID_STATUS}"
        updates["status"] = status
    if priority:
        if priority not in VALID_PRIORITY:
            return f"ERROR: Invalid priority. Must be one of {VALID_PRIORITY}"
        updates["priority"] = priority
    if assignee:
        try:
            store.validate_assignee(assignee)
        except ValueError as e:
            return f"ERROR: {e}"
        updates["assignee"] = assignee
    if project:
        updates["project"] = project
    if area:
        updates["area"] = area
    if due:
        updates["due"] = due
    if tags:
        updates["tags"] = [t.strip() for t in tags.split(",") if t.strip()]
    if body:
        updates["body"] = body

    task = store.update(task_id, **updates)
    return f"Updated {task.id}\n{json.dumps(task_to_dict(task), indent=2, default=str)}"


@mcp.tool()
async def tick_item(task_id: str, index: int, checked: bool = True) -> str:
    """Check or uncheck a checklist item in the task body (1-based index).

    Use this to mark sub-steps done as you progress, instead of rewriting
    the whole body via update_task. The progress rollup (done/total/pct)
    is recomputed and returned.

    task_id: Task ID (e.g. T-042)
    index: 1-based position of the checklist item within the body
    checked: True to mark `[x]`, False to mark `[ ]` (default True)
    """
    task = store.get(task_id)
    try:
        new_body, progress = _tick_item(task.body, index, checked)
    except ValueError as e:
        return f"ERROR: {e}"
    task.body = new_body
    store.save(task)
    state = "checked" if checked else "unchecked"
    item_text = progress.items[index - 1].text
    return (
        f"{state} item {index} of {task_id}: {item_text}\n"
        f"progress: {progress.done}/{progress.total} ({progress.pct}%)"
    )


@mcp.tool()
async def add_comment(task_id: str, text: str, author: str = "agent") -> str:
    """Append a dated comment under the task body's `## Comments` section.

    Use for capturing context as you work — references found, decisions
    made, follow-ups noticed. Comments are stored as plain markdown
    bullets so they're visible/editable in Obsidian directly. The
    section is created on first comment.

    task_id: Task ID (e.g. T-042)
    text: The note. Newlines are flattened to spaces — keep it to one
        thought; multi-paragraph context belongs in the body proper.
    author: Actor handle (default 'agent'). Validated against the same
        actor list used for `assignee:` (legacy 'claude' aliases to
        'agent').
    """
    if not text.strip():
        return "ERROR: comment text is empty"
    try:
        store.validate_assignee(author)
    except ValueError as e:
        return f"ERROR: {e}"
    task = store.get(task_id)
    task.body = append_comment(task.body, author, text, date.today().isoformat())
    store.save(task)
    count = len(parse_comments(task.body))
    return f"Added comment to {task_id} ({count} total)"


@mcp.tool()
async def list_comments(task_id: str) -> str:
    """List all comments on a task, oldest first."""
    task = store.get(task_id)
    comments = parse_comments(task.body)
    if not comments:
        return f"No comments on {task_id}."
    return json.dumps([c.to_dict() for c in comments], indent=2, default=str)


@mcp.tool()
async def add_blocker(task_id: str, blocked_by_id: str) -> str:
    """Add a dependency to a task. blocked_by_id must be Done before task_id can start."""
    task = store.get(task_id)
    if blocked_by_id in task.blocked_by:
        return f"{task_id} already blocked by {blocked_by_id}"
    new_deps = task.blocked_by + [blocked_by_id]
    cycle = detect_cycle(store, task_id, new_deps)
    if cycle:
        return f"ERROR: Would create cycle: {' → '.join(cycle)}"
    task.blocked_by = new_deps
    store.save(task)
    return f"{task_id} now blocked by {blocked_by_id}"


# ── Status Transitions ─────────────────────────────────────────────────


@mcp.tool()
async def start_task(task_id: str) -> str:
    """Mark task as 'In Progress'. Verifies dependencies are satisfied."""
    task = store.get(task_id)
    all_tasks = {t.id: t for t in store.all()}
    if not is_unblocked(task, all_tasks):
        unfinished = [
            d for d in task.blocked_by
            if d in all_tasks and all_tasks[d].status not in {"Done", "Cancelled"}
        ]
        return f"ERROR: Cannot start {task_id} — blocked by: {', '.join(unfinished)}"

    task.status = "In Progress"
    store.save(task)
    return f"Started {task_id}: {task.title}"


@mcp.tool()
async def complete_task(task_id: str, completion_notes: str = "") -> str:
    """Mark task as 'Done'. Optionally append completion notes to body."""
    task = store.get(task_id)
    task.status = "Done"
    task.completed = date.today().isoformat()
    if completion_notes:
        task.body = (task.body or "").rstrip() + f"\n\n## Completion Notes\n{completion_notes}\n"
    store.save(task)

    unblocked = what_unblocks(store, task_id)
    msg = f"Completed {task_id}: {task.title}"
    if unblocked:
        msg += f"\n\nUnblocked: {', '.join(t.id + ' (' + t.title + ')' for t in unblocked)}"
    return msg


@mcp.tool()
async def block_task(task_id: str, reason: str) -> str:
    """Mark task as 'Blocked' with a reason (for external blockers, not task dependencies)."""
    task = store.get(task_id)
    task.status = "Blocked"
    task.body = (task.body or "").rstrip() + f"\n\n## Blocked\n{reason}\n"
    store.save(task)
    return f"Blocked {task_id}: {reason}"


# ── Workflow ───────────────────────────────────────────────────────────


@mcp.tool()
async def next_task(assignee: str = "agent") -> str:
    """Get the next workable task: status=Ready, dependencies satisfied, sorted by priority/due/created.

    Default assignee is 'agent' so an MCP agent can ask 'what's next for me?'.
    Tasks written before the rename with `assignee: claude` are matched too.
    """
    task = _next_task(store, assignee=assignee or None)
    if not task:
        return "No workable tasks. All Ready tasks may be blocked, or none assigned."
    out = task_to_dict(task, include_body=True)
    return json.dumps(out, indent=2, default=str)


@mcp.tool()
async def my_tasks(assignee: str = "me") -> str:
    """Quick view of what's on your plate: overdue, due today, in progress.

    Default assignee is 'me'.
    """
    today = date.today().isoformat()
    tasks = store.all()
    if assignee:
        target = canonical_assignee(assignee)
        tasks = [t for t in tasks if canonical_assignee(t.assignee) == target]

    overdue = [t for t in tasks if t.due and t.due < today and t.status not in {"Done", "Cancelled"}]
    due_today = [t for t in tasks if t.due == today and t.status not in {"Done", "Cancelled"}]
    in_progress = [t for t in tasks if t.status == "In Progress"]

    return json.dumps({
        "overdue": [task_to_dict(t) for t in overdue],
        "due_today": [task_to_dict(t) for t in due_today],
        "in_progress": [task_to_dict(t) for t in in_progress],
    }, indent=2, default=str)


@mcp.tool()
async def task_tree(task_id: str) -> str:
    """Show the dependency tree for a task — what blocks it and its blockers."""
    tree = _task_tree(store, task_id)
    return render_tree(tree)


@mcp.tool()
async def blocked_tasks() -> str:
    """List all Ready tasks that are currently blocked by unfinished dependencies."""
    blocked = _blocked_tasks(store)
    if not blocked:
        return "No blocked tasks."
    out = []
    for t in blocked:
        d = task_to_dict(t)
        d["waiting_on"] = t.blocked_by
        out.append(d)
    return json.dumps(out, indent=2, default=str)


@mcp.tool()
async def validate_dependencies() -> str:
    """Check the entire task graph for cycles and missing dependencies."""
    all_tasks = {t.id: t for t in store.all()}
    issues = []
    for tid, task in all_tasks.items():
        for dep in task.blocked_by:
            if dep not in all_tasks:
                issues.append(f"{tid} references missing task: {dep}")
        cycle = detect_cycle(store, tid, task.blocked_by)
        if cycle:
            issues.append(f"Cycle detected: {' → '.join(cycle)}")

    if not issues:
        return "Dependency graph is valid. No cycles or missing dependencies."
    return "\n".join(issues)


if __name__ == "__main__":
    mcp.run()
