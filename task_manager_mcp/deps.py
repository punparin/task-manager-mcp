"""Dependency resolution: cycle detection, topological sort, next_task."""

from __future__ import annotations

from datetime import date
from typing import Optional

from .tasks import Task, TaskStore

PRIORITY_RANK = {"P1": 1, "P2": 2, "P3": 3, "P4": 4}
TERMINAL_STATUSES = {"Done", "Cancelled"}


def detect_cycle(store: TaskStore, task_id: str, blocked_by: list[str]) -> Optional[list[str]]:
    """Check if adding `blocked_by` to `task_id` would create a cycle.

    Returns the cycle path if found, None otherwise.
    """
    # Build a hypothetical adjacency list
    all_tasks = {t.id: t for t in store.all()}
    if task_id in all_tasks:
        # Use the proposed blocked_by
        adj = {tid: list(t.blocked_by) for tid, t in all_tasks.items()}
        adj[task_id] = list(blocked_by)
    else:
        adj = {tid: list(t.blocked_by) for tid, t in all_tasks.items()}
        adj[task_id] = list(blocked_by)

    # DFS for cycle starting from task_id
    visited = set()
    stack = []

    def dfs(node: str) -> Optional[list[str]]:
        if node in stack:
            cycle_start = stack.index(node)
            return stack[cycle_start:] + [node]
        if node in visited:
            return None
        visited.add(node)
        stack.append(node)
        for dep in adj.get(node, []):
            cycle = dfs(dep)
            if cycle:
                return cycle
        stack.pop()
        return None

    return dfs(task_id)


def is_unblocked(task: Task, all_tasks: dict[str, Task]) -> bool:
    """A task is unblocked when all blocked_by tasks are Done or Cancelled."""
    for dep_id in task.blocked_by:
        dep = all_tasks.get(dep_id)
        if dep is None:
            return False  # missing dep = blocked
        if dep.status not in TERMINAL_STATUSES:
            return False
    return True


def next_task(store: TaskStore, assignee: Optional[str] = None) -> Optional[Task]:
    """Return the next workable task.

    Selection criteria:
    - status == 'Ready'
    - assignee matches (if provided)
    - all blocked_by tasks are Done or Cancelled
    - sorted by: priority (P1 first) → due (sooner first) → created (older first)
    """
    all_tasks = {t.id: t for t in store.all()}
    candidates = []
    for t in all_tasks.values():
        if t.status != "Ready":
            continue
        if assignee and t.assignee != assignee:
            continue
        if not is_unblocked(t, all_tasks):
            continue
        candidates.append(t)

    if not candidates:
        return None

    def sort_key(t: Task):
        prio = PRIORITY_RANK.get(t.priority, 99)
        due = t.due or "9999-12-31"
        return (prio, due, t.created)

    return sorted(candidates, key=sort_key)[0]


def task_tree(store: TaskStore, task_id: str, depth: int = 0, _seen: Optional[set] = None) -> dict:
    """Build dependency tree showing what blocks this task."""
    _seen = _seen or set()
    if task_id in _seen:
        return {"id": task_id, "title": "(cycle)", "status": "?", "depth": depth, "deps": []}
    _seen = _seen | {task_id}

    try:
        t = store.get(task_id)
    except FileNotFoundError:
        return {"id": task_id, "title": "(missing)", "status": "?", "depth": depth, "deps": []}

    return {
        "id": t.id,
        "title": t.title,
        "status": t.status,
        "priority": t.priority,
        "depth": depth,
        "deps": [task_tree(store, dep, depth + 1, _seen) for dep in t.blocked_by],
    }


def render_tree(tree: dict, indent: str = "") -> str:
    """Render a task tree as ASCII."""
    status_marker = "✓" if tree["status"] == "Done" else " "
    line = f"{indent}[{status_marker}] {tree['id']}: {tree['title']} ({tree['status']})"
    lines = [line]
    deps = tree.get("deps", [])
    for i, dep in enumerate(deps):
        is_last = i == len(deps) - 1
        prefix = "└── " if is_last else "├── "
        sub_indent = indent + ("    " if is_last else "│   ")
        sub_line = render_tree(dep, sub_indent)
        # Replace first line's indent with prefix
        sub_lines = sub_line.split("\n")
        sub_lines[0] = indent + prefix + sub_lines[0][len(indent):].lstrip()
        lines.append("\n".join(sub_lines))
    return "\n".join(lines)


def blocked_tasks(store: TaskStore) -> list[Task]:
    """Return all Ready tasks that are currently blocked by unfinished dependencies."""
    all_tasks = {t.id: t for t in store.all()}
    return [t for t in all_tasks.values() if t.status == "Ready" and not is_unblocked(t, all_tasks)]


def what_unblocks(store: TaskStore, completing_task_id: str) -> list[Task]:
    """Return tasks that would become unblocked if completing_task_id is marked Done."""
    all_tasks = {t.id: t for t in store.all()}
    if completing_task_id not in all_tasks:
        return []

    # Hypothetically mark as Done
    hypothetical = dict(all_tasks)
    completing = all_tasks[completing_task_id]
    hypothetical[completing_task_id] = Task(
        **{**completing.__dict__, "status": "Done"}
    ) if hasattr(completing, "__dict__") else completing

    unblocked = []
    for t in all_tasks.values():
        if t.status != "Ready":
            continue
        if completing_task_id not in t.blocked_by:
            continue
        # Check if it would now be unblocked
        if all(
            (hypothetical.get(dep) and hypothetical[dep].status in TERMINAL_STATUSES)
            for dep in t.blocked_by
        ):
            unblocked.append(t)
    return unblocked
