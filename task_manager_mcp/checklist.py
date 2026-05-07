"""Markdown checklist parsing and progress rollup.

Tasks store free-form markdown bodies, and Obsidian renders `- [ ]` /
`- [x]` lines as native checkboxes. We treat those as the canonical
substep representation: derived on read so frontmatter and body never
disagree.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .tasks import Task


_ITEM_RE = re.compile(r"^(?P<indent>\s*)(?P<bullet>[-*])\s+\[(?P<mark>[ xX])\]\s+(?P<text>.+)$")
_FENCE_RE = re.compile(r"^\s*```")


@dataclass
class ChecklistItem:
    line_no: int  # 0-based index into body.splitlines()
    indent: str
    bullet: str
    checked: bool
    text: str


@dataclass
class ChecklistProgress:
    done: int
    total: int
    pct: int
    items: list[ChecklistItem]

    def to_dict(self) -> dict:
        return {"done": self.done, "total": self.total, "pct": self.pct}


def parse_checklist(body: str) -> ChecklistProgress:
    """Scan body for `- [ ]` / `- [x]` items, ignoring fenced code blocks.

    Counts items at any depth — nested checklists contribute to the rollup.
    `[X]` (capital) counts as checked; extra spaces (`[ x ]`) do not match.
    """
    items: list[ChecklistItem] = []
    in_fence = False
    for i, line in enumerate((body or "").splitlines()):
        if _FENCE_RE.match(line):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        m = _ITEM_RE.match(line)
        if not m:
            continue
        items.append(
            ChecklistItem(
                line_no=i,
                indent=m.group("indent"),
                bullet=m.group("bullet"),
                checked=m.group("mark") in ("x", "X"),
                text=m.group("text"),
            )
        )
    done = sum(1 for it in items if it.checked)
    total = len(items)
    pct = round(100 * done / total) if total else 0
    return ChecklistProgress(done=done, total=total, pct=pct, items=items)


def tick(body: str, index: int, checked: bool) -> tuple[str, ChecklistProgress]:
    """Flip the n-th checklist item (1-based). Returns (new_body, new_progress).

    Raises ValueError for invalid index. Preserves indentation, bullet
    style, and trailing text exactly — only the `[ ]` / `[x]` glyph
    changes.
    """
    progress = parse_checklist(body)
    if progress.total == 0:
        raise ValueError("task body has no checklist items")
    if index < 1 or index > progress.total:
        raise ValueError(f"item index {index} out of range (1..{progress.total})")

    item = progress.items[index - 1]
    lines = body.splitlines(keepends=True)
    line = lines[item.line_no]
    new_mark = "x" if checked else " "
    # Replace only the first `[<mark>]` occurrence — the bullet's own marker.
    new_line = re.sub(r"\[[ xX]\]", f"[{new_mark}]", line, count=1)
    lines[item.line_no] = new_line
    new_body = "".join(lines)
    return new_body, parse_checklist(new_body)


def task_to_dict(task: "Task", *, include_body: bool = False) -> dict:
    """Serialize a Task and attach derived checklist progress.

    Omits the `progress` key when the body has no checklist items so
    consumers can treat its presence as a signal that progress is
    meaningful. Same convention for `comment_count` and (when
    `include_body` is set) `comments`.
    """
    from .comments import parse_comments

    out = task.to_dict()
    progress = parse_checklist(task.body)
    if progress.total > 0:
        out["progress"] = progress.to_dict()
    comments = parse_comments(task.body)
    if comments:
        out["comment_count"] = len(comments)
    if include_body:
        out["body"] = task.body
        if comments:
            out["comments"] = [c.to_dict() for c in comments]
    return out


__all__ = [
    "ChecklistItem",
    "ChecklistProgress",
    "parse_checklist",
    "tick",
    "task_to_dict",
]
