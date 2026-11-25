"""Epics: a big-picture goal that groups tasks.

An epic is one markdown file, `E-xxx.md`, in the same folder as the
tasks (so it follows `TASK_MANAGER_TASKS_FOLDER` and sits next to its
tasks in Obsidian). Tasks join an epic through their `epic:` field.

Epic status is set by hand. Progress is derived from the epic's tasks on
every read and never written to the file, so it can't drift from them.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from typing import Optional

import frontmatter

from .checklist import parse_checklist
from .tasks import EPIC_ID_RE, VALID_PRIORITY, Task, TaskStore

EPIC_STATUS = ["Planned", "Active", "Done", "Cancelled"]
OPEN_EPIC_STATUS = {"Planned", "Active"}
TERMINAL_TASK_STATUS = {"Done", "Cancelled"}

# Named colours for chips and swimlanes in the Explorer. `color:` in the
# file may be one of these names or a `#rrggbb` hex value.
EPIC_COLORS = {
    "violet": "#a78bfa",
    "amber": "#fbbf24",
    "lime": "#a3e635",
    "sky": "#38bdf8",
    "pink": "#f472b6",
    "orange": "#fb923c",
    "teal": "#5eead4",
    "slate": "#94a3b8",
}
_HEX_RE = re.compile(r"^#[0-9a-fA-F]{6}$")

# Status order for listings: work in flight first, finished last.
_STATUS_RANK = {"Active": 0, "Planned": 1, "Done": 2, "Cancelled": 3}
_PRIORITY_RANK = {"P1": 1, "P2": 2, "P3": 3, "P4": 4}


def validate_color(value: str) -> None:
    if value not in EPIC_COLORS and not _HEX_RE.match(value):
        raise ValueError(
            f"Invalid color: {value}. Use one of {sorted(EPIC_COLORS)} or #rrggbb"
        )


@dataclass
class Epic:
    id: str
    title: str
    status: str = "Planned"
    priority: str = "P3"
    project: Optional[str] = None
    due: Optional[str] = None
    color: Optional[str] = None
    created: str = ""
    completed: Optional[str] = None
    last_status_change: Optional[str] = None
    tags: list[str] = field(default_factory=list)
    body: str = ""

    def __post_init__(self):
        if self.status not in EPIC_STATUS:
            raise ValueError(f"Invalid epic status: {self.status}. Must be one of {EPIC_STATUS}")
        if self.priority not in VALID_PRIORITY:
            raise ValueError(f"Invalid priority: {self.priority}. Must be one of {VALID_PRIORITY}")
        if self.color:
            validate_color(self.color)
        if not self.created:
            self.created = date.today().isoformat()

    @property
    def resolved_color(self) -> str:
        """Hex colour to draw with: the set colour, else one picked by id."""
        if self.color:
            return EPIC_COLORS.get(self.color, self.color)
        m = EPIC_ID_RE.match(self.id)
        palette = list(EPIC_COLORS.values())
        n = int(m.group(1)) if m else 0
        return palette[(n - 1) % len(palette)]

    def to_markdown(self) -> str:
        post = frontmatter.Post(self.body or "")
        meta = post.metadata
        meta["type"] = "epic"
        meta["id"] = self.id
        meta["title"] = self.title
        meta["status"] = self.status
        meta["priority"] = self.priority
        if self.project:
            meta["project"] = self.project
        if self.color:
            meta["color"] = self.color
        meta["created"] = self.created
        if self.due:
            meta["due"] = self.due
        if self.completed:
            meta["completed"] = self.completed
        if self.last_status_change:
            meta["last_status_change"] = self.last_status_change
        if self.tags:
            meta["tags"] = self.tags
        return frontmatter.dumps(post)

    @classmethod
    def from_markdown(cls, content: str) -> "Epic":
        post = frontmatter.loads(content)
        m = post.metadata

        def opt(key: str) -> Optional[str]:
            return str(m[key]) if m.get(key) else None

        return cls(
            id=str(m.get("id", "")),
            title=str(m.get("title", "")),
            status=str(m.get("status", "Planned")),
            priority=str(m.get("priority", "P3")),
            project=m.get("project"),
            due=opt("due"),
            color=opt("color"),
            created=str(m.get("created", "")),
            completed=opt("completed"),
            last_status_change=opt("last_status_change"),
            tags=list(m.get("tags") or []),
            body=post.content,
        )


def epic_body(goal: str = "", success_criteria: str = "") -> str:
    """Starting body for a new epic: a Goal section and a criteria checklist.

    `success_criteria` takes one criterion per line; leading `-` / `- [ ]`
    markers are optional and stripped.
    """
    parts = []
    if goal.strip():
        parts.append(f"## Goal\n{goal.strip()}\n")
    criteria = []
    for line in success_criteria.splitlines():
        text = re.sub(r"^\s*(?:[-*]\s*)?(?:\[[ xX]\]\s*)?", "", line).strip()
        if text:
            criteria.append(f"- [ ] {text}")
    if criteria:
        parts.append("## Success criteria\n" + "\n".join(criteria) + "\n")
    return "\n".join(parts)


class EpicStore:
    """Reads and writes epic files in a TaskStore's tasks folder."""

    def __init__(self, tasks: TaskStore):
        self.tasks = tasks
        self.dir = tasks.tasks_dir

    def _path_for(self, epic_id: str):
        return self.dir / f"{epic_id}.md"

    def exists(self, epic_id: str) -> bool:
        return bool(EPIC_ID_RE.match(epic_id)) and self._path_for(epic_id).exists()

    def next_id(self) -> str:
        max_n = 0
        for f in self.dir.glob("E-*.md"):
            m = EPIC_ID_RE.match(f.stem)
            if m:
                max_n = max(max_n, int(m.group(1)))
        return f"E-{max_n + 1:03d}"

    def all(self) -> list[Epic]:
        epics = []
        for f in sorted(self.dir.glob("E-*.md")):
            if not EPIC_ID_RE.match(f.stem):
                continue
            try:
                epics.append(Epic.from_markdown(f.read_text(encoding="utf-8")))
            except Exception:
                continue
        return epics

    def get(self, epic_id: str) -> Epic:
        if not self.exists(epic_id):
            raise FileNotFoundError(f"Epic not found: {epic_id}")
        return Epic.from_markdown(self._path_for(epic_id).read_text(encoding="utf-8"))

    def save(self, epic: Epic) -> None:
        self._path_for(epic.id).write_text(epic.to_markdown(), encoding="utf-8")

    def create(self, title: str, **fields) -> Epic:
        epic = Epic(id=self.next_id(), title=title, **fields)
        self.save(epic)
        return epic


def epic_progress(epic: Epic, tasks: list[Task]) -> dict:
    """Roll up the epic's tasks. Cancelled tasks don't count toward the total."""
    mine = [t for t in tasks if t.epic == epic.id]
    by_status: dict[str, int] = {}
    for t in mine:
        by_status[t.status] = by_status.get(t.status, 0) + 1
    cancelled = by_status.get("Cancelled", 0)
    total = len(mine) - cancelled
    done = by_status.get("Done", 0)
    today = date.today().isoformat()
    is_open = epic.status in OPEN_EPIC_STATUS
    return {
        "total": total,
        "done": done,
        "pct": round(done * 100 / total) if total else 0,
        "cancelled": cancelled,
        "by_status": by_status,
        "blocked": by_status.get("Blocked", 0),
        # A hint only: the epic is never closed automatically.
        "ready_to_close": is_open and total > 0 and done == total,
        "overdue": bool(is_open and epic.due and epic.due < today),
    }


def epic_to_dict(epic: Epic, tasks: list[Task], *, include_body: bool = False) -> dict:
    out = {
        "id": epic.id,
        "title": epic.title,
        "status": epic.status,
        "priority": epic.priority,
        "project": epic.project,
        "due": epic.due,
        "color": epic.resolved_color,
        "created": epic.created,
        "completed": epic.completed,
        "last_status_change": epic.last_status_change,
        "tags": epic.tags,
        "progress": epic_progress(epic, tasks),
    }
    criteria = parse_checklist(epic.body)
    if criteria.total:
        out["criteria"] = criteria.to_dict()
    if include_body:
        out["body"] = epic.body
    return out


def sort_epics(epics: list[Epic]) -> list[Epic]:
    return sorted(
        epics,
        key=lambda e: (
            _STATUS_RANK.get(e.status, 9),
            _PRIORITY_RANK.get(e.priority, 9),
            e.due or "9999-12-31",
            e.id,
        ),
    )


def open_tasks(epic_id: str, tasks: list[Task]) -> list[Task]:
    return [t for t in tasks if t.epic == epic_id and t.status not in TERMINAL_TASK_STATUS]
