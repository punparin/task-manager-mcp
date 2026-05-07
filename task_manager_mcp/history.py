"""Status-change audit log inside the task body.

Status transitions get appended as bullets under a ``## History`` section
so they show up natively in Obsidian and round-trip through the same
frontmatter parser as the rest of the body. Format::

    ## History

    - **2026-05-07**: Ready → In Progress (agent)
    - **2026-05-07**: In Progress → Done (me)

Same shape as comments.py — kept separate to make the section purpose
obvious to humans skimming the file.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

HISTORY_HEADING = "## History"

# `- **YYYY-MM-DD**: OLD → NEW (actor)` — actor is anything non-`)` so
# handles like `agent`, `me`, `cursor`, `alice` all match. Bullets that
# don't fit are skipped silently so the section can absorb hand notes.
_HISTORY_RE = re.compile(
    r"^-\s+\*\*(?P<date>\d{4}-\d{2}-\d{2})\*\*:\s*"
    r"(?P<old>[^→]+?)\s*→\s*(?P<new>[^()]+?)\s*\((?P<actor>[^)]+)\)\s*$"
)


@dataclass
class HistoryEntry:
    date: str
    old_status: str
    new_status: str
    actor: str

    def to_dict(self) -> dict:
        return {
            "date": self.date,
            "old_status": self.old_status,
            "new_status": self.new_status,
            "actor": self.actor,
        }


def parse_history(body: str) -> list[HistoryEntry]:
    """Extract entries from the ``## History`` section.

    Returns an empty list when the section is absent or empty. Mirrors
    parse_comments — non-matching bullets are skipped.
    """
    out: list[HistoryEntry] = []
    in_section = False
    for line in (body or "").splitlines():
        stripped = line.strip()
        if stripped.startswith("## "):
            in_section = stripped == HISTORY_HEADING
            continue
        if not in_section:
            continue
        m = _HISTORY_RE.match(line)
        if m:
            out.append(
                HistoryEntry(
                    date=m.group("date"),
                    old_status=m.group("old").strip(),
                    new_status=m.group("new").strip(),
                    actor=m.group("actor").strip(),
                )
            )
    return out


def append_history(body: str, old_status: str, new_status: str, actor: str, when: str) -> str:
    """Return a new body with a status-change entry appended under ``## History``.

    Creates the section at the end of the body if it doesn't exist yet.
    """
    bullet = f"- **{when}**: {old_status} → {new_status} ({actor})"

    base = (body or "").rstrip()
    if HISTORY_HEADING in base:
        lines = base.splitlines()
        start = next(
            i for i, line in enumerate(lines) if line.strip() == HISTORY_HEADING
        )
        end = len(lines)
        for i in range(start + 1, len(lines)):
            if lines[i].lstrip().startswith("## "):
                end = i
                break
        insert_at = end
        while insert_at > start + 1 and not lines[insert_at - 1].strip():
            insert_at -= 1
        lines.insert(insert_at, bullet)
        return "\n".join(lines) + "\n"

    prefix = base + "\n\n" if base else ""
    return f"{prefix}{HISTORY_HEADING}\n\n{bullet}\n"


__all__ = ["HISTORY_HEADING", "HistoryEntry", "append_history", "parse_history"]
