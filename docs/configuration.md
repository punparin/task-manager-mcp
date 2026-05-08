# Configuration

## Vault path

Set the vault path via environment variable on the MCP server process:

```bash
export OBSIDIAN_VAULT_PATH=/path/to/your/obsidian/vault
```

When using Docker, mount the vault and rely on the image default
(`/vault`):

```bash
docker run -i --rm \
  -v /path/to/your/vault:/vault \
  ghcr.io/punparin/task-manager-mcp:latest
```

## Tasks folder

Tasks default to `<vault>/tasks/`. Point `TASK_MANAGER_TASKS_FOLDER`
elsewhere if your vault layout already has a home for task files —
e.g. `inbox/tasks` or `work/queue`. The path is resolved relative to
the vault root and may be nested; `..` escapes that resolve outside
the vault are rejected at startup.

```bash
# Docker
docker run -i --rm \
  -v /path/to/your/vault:/vault \
  -e TASK_MANAGER_TASKS_FOLDER=inbox/tasks \
  ghcr.io/punparin/task-manager-mcp:latest

# Local
TASK_MANAGER_TASKS_FOLDER=work/queue \
OBSIDIAN_VAULT_PATH=/path/to/your/vault \
  /path/to/task-manager-mcp/.venv/bin/python -m task_manager_mcp
```

The folder is created on first run if it doesn't exist. Hit
`/api/health` on the [Explorer](./explorer.md) to confirm which path
resolved.

## Custom actors

Out of the box, tasks can be assigned to `me` (the human), `agent`
(an MCP agent), or `claude` (a legacy alias for `agent`, kept so
vaults written before the rename keep loading). To onboard a team —
multiple humans, multiple AI agents, or both — drop a config file at
`<vault>/.task-manager/config.yml`:

```yaml
actors:
  - me
  - agent
  - alice
  - bob
  - cursor
```

The list replaces the defaults — if your team works strictly in named
handles, you can omit `me` and `agent` entirely. The config lives in
the vault, so syncing the vault syncs the actor list across the team.
Validation runs only on writes; existing task files keep loading even
if you later remove an actor (they just can't be re-saved with that
assignee). The legacy `claude` value is always accepted as an alias
for `agent`. Hit `/api/health` on the Explorer to see the resolved
list.

## Audit log

Every status transition appends one JSON line to
`<vault>/.task-manager/audit.jsonl`. The file is grow-forever and
safe to rotate / truncate independently — each task's
`last_status_change` frontmatter field carries the most recent
transition date, so the recency case keeps working after a rotation.
See [`task-format.md`](./task-format.md#status-history) for the
schema, and use `list_audit(since=, task_id=, limit=)` (MCP) or
`GET /api/audit` (Explorer) to read it.

## Register with your MCP client

The server speaks stdio MCP, so it works with any MCP-capable client.
Concrete examples below use Claude Code's `claude mcp add` CLI; for
[Cursor](https://docs.cursor.com/), [Cline](https://cline.bot/),
[Continue](https://www.continue.dev/),
[Goose](https://block.github.io/goose/),
[Windsurf](https://codeium.com/windsurf), or any other MCP host, plug
the same `docker run …` or `python -m task_manager_mcp` command into
your client's MCP server config.

### Docker

```bash
claude mcp add \
  -s user \
  task-manager \
  -- docker run -i --rm -v /path/to/your/vault:/vault ghcr.io/punparin/task-manager-mcp:latest
```

### Local virtualenv

```bash
git clone https://github.com/punparin/task-manager-mcp.git
cd task-manager-mcp
python3 -m venv .venv
.venv/bin/pip install -e .

claude mcp add \
  -e OBSIDIAN_VAULT_PATH=/path/to/your/vault \
  -s user \
  task-manager \
  -- /path/to/task-manager-mcp/.venv/bin/python -m task_manager_mcp
```
