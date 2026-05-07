# Task Format

Each task is one markdown file in the tasks folder of the vault. The
folder defaults to `tasks/` but is configurable — see
[`configuration.md`](./configuration.md#tasks-folder).

```yaml
---
type: task
id: T-042
title: Implement rate limiting
status: Ready          # Backlog, Ready, In Progress, Done, Blocked, Cancelled
priority: P2           # P1, P2, P3, P4
assignee: agent        # me, agent (or any actor from .task-manager/config.yml)
project: "[[API Migration]]"
area: Backend
created: 2026-04-09
due: 2026-04-15
last_status_change: 2026-05-07   # auto-stamped on every transition
blocked_by: [T-038, T-040]
tags: [backend, performance]
---

## What to do
Add token-bucket rate limiting to the v3 API endpoints.

## Acceptance criteria
- [ ] 100 req/min per client default
- [ ] Rate limit headers returned
- [ ] Tests cover bucket exhaustion
```

The legacy `assignee: claude` value is always accepted as an alias for
`agent`, so vaults written before the rename still round-trip.

## Comments

Use `add_comment(task_id, text, author)` to leave a dated note under
the task body's `## Comments` section — references found, decisions
made, follow-ups noticed. Comments are plain markdown bullets so they
render natively in Obsidian and can be edited there directly:

```markdown
## Comments

- **2026-05-07 agent**: looked at auth middleware, line 142 is the bug
- **2026-05-08 me**: also need OAuth coverage, talked to alice
```

`author` is validated against the same actor list as `assignee:` (so
`me`, `agent`, or any custom actors from `.task-manager/config.yml`),
and defaults to `agent`. The section is created on first comment.
`get_task` returns parsed comments under a `comments` array, and
`list_tasks` / `next_task` show a `comment_count` so triage can see
which tasks have notes without expanding them.

## Checklist progress

Any `- [ ]` / `- [x]` items in a task body are parsed as substeps.
`get_task`, `list_tasks`, `next_task`, and `my_tasks` include a
`progress: {done, total, pct}` rollup whenever the body has at least
one checkbox — so you can see "T-042 (3/5, 60%)" without expanding the
task.

Use `tick_item(task_id, index, checked=True)` to flip a single box
without rewriting the body. Index is 1-based, counting all checkboxes
in document order (nested items included). Code fences are skipped, so
`[ ]` inside ```` ``` ```` blocks won't be miscounted.

Progress is **derived on read** — never persisted to frontmatter — so
editing the body in Obsidian and calling `tick_item` from your agent
can't drift apart. Completion is still explicit: `complete_task` does
not auto-fire when all boxes are checked, since marking Done has side
effects (timestamp, downstream unblock).

## Status history

Every status transition the server triggers — `start_task`,
`complete_task`, `block_task`, `update_task(status=…)`, the Explorer's
status patch, and the auto-promote on unblock — appends one JSON line
to `<vault>/.task-manager/audit.jsonl`:

```json
{"ts": "2026-05-07T12:34:56", "task_id": "T-042",
 "old_status": "Ready", "new_status": "In Progress",
 "actor": "agent"}
```

The body stays clean; `last_status_change` in the frontmatter answers
the recency case (e.g. `"what shifted today?"`) without scanning the
log. For the full timeline use `list_audit(since=, task_id=, limit=)`
or the Explorer's `GET /api/audit` endpoint. The log is grow-forever;
operators can rotate / truncate it independently — the per-task
`last_status_change` field carries forward.
