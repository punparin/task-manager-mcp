"""Append-only status-change audit log.

Every status transition writes one JSON line to
``<vault>/.task-manager/audit.jsonl`` so the body stays clean and
"what shifted today" stays a one-pass scan instead of walking every
markdown file. The latest transition date is also mirrored into each
task's frontmatter as ``last_status_change`` so callers that only want
the recency filter (e.g. ``list_tasks``) don't need to read the log.

Schema::

    {"ts": "2026-05-07T12:34:56", "task_id": "T-042",
     "old_status": "Ready", "new_status": "In Progress",
     "actor": "agent"}

The log is grow-forever today. Operators can rotate it (move/truncate
audit.jsonl) without breaking anything — the only consumer is read-only
filtering, and the per-task ``last_status_change`` field carries
forward independently.
"""

from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path
from typing import Optional

CONFIG_DIR_NAME = ".task-manager"
AUDIT_FILE_NAME = "audit.jsonl"


def audit_path(vault: str | Path) -> Path:
    return Path(vault) / CONFIG_DIR_NAME / AUDIT_FILE_NAME


def record_transition(
    vault: str | Path,
    task_id: str,
    old_status: str,
    new_status: str,
    actor: str,
    *,
    when: Optional[datetime] = None,
) -> str:
    """Append one entry and return the ISO date the caller should mirror
    into the task's ``last_status_change`` frontmatter field.
    """
    moment = when or datetime.now()
    entry = {
        "ts": moment.isoformat(timespec="seconds"),
        "task_id": task_id,
        "old_status": old_status,
        "new_status": new_status,
        "actor": actor,
    }
    path = audit_path(vault)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    return moment.date().isoformat()


def read_audit(
    vault: str | Path,
    since: Optional[str] = None,
    task_id: Optional[str] = None,
    limit: Optional[int] = None,
) -> list[dict]:
    """Read entries from the audit log, newest first.

    ``since``: ISO date (YYYY-MM-DD) — entries strictly older are dropped.
    ``task_id``: filter to a single task.
    ``limit``: cap the returned list (after filtering, before reversal).
    """
    cutoff: Optional[date] = None
    if since:
        try:
            cutoff = date.fromisoformat(since)
        except ValueError as e:
            raise ValueError(f"`since` must be YYYY-MM-DD: {since!r}") from e

    path = audit_path(vault)
    if not path.exists():
        return []

    out: list[dict] = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                # Skip malformed lines rather than break the whole read.
                continue
            if task_id and entry.get("task_id") != task_id:
                continue
            if cutoff is not None:
                ts = entry.get("ts", "")
                try:
                    entry_date = date.fromisoformat(ts[:10])
                except ValueError:
                    continue
                if entry_date < cutoff:
                    continue
            out.append(entry)

    out.reverse()
    if limit is not None and limit > 0:
        out = out[:limit]
    return out


__all__ = [
    "AUDIT_FILE_NAME",
    "CONFIG_DIR_NAME",
    "audit_path",
    "read_audit",
    "record_transition",
]
