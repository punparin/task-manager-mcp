# Task Manager MCP

A [Model Context Protocol (MCP)](https://modelcontextprotocol.io/)
server for task management with **dependency resolution**. Stores
tasks as markdown files in an Obsidian vault, lets you queue work,
assign tasks to your agent, and have any MCP-capable agent (Claude
Code, Cursor, Cline, Continue, Goose, Windsurf, …) pick up the next
workable task automatically.

![Demo](./docs/demo.gif)

## Install via your agent (easiest)

Open your MCP-capable agent (Claude Code, Cursor, Cline, …), paste:

> Read this and help me install it: <https://github.com/punparin/task-manager-mcp/blob/main/INSTALLATION.md>

The agent will walk you through it — picking Docker vs Python, vault
path, tasks folder, actor list, scope — and ask before assuming
anything. See [`INSTALLATION.md`](./INSTALLATION.md) for the full
guide.

## Quickstart (manual)

```bash
# 1. Pull the image
docker pull ghcr.io/punparin/task-manager-mcp:latest

# 2. Register with your MCP client (Claude Code shown — see
#    docs/configuration.md for other clients).
claude mcp add -s user task-manager -- \
  docker run -i --rm \
    -v /path/to/your/vault:/vault \
    ghcr.io/punparin/task-manager-mcp:latest
```

Then in your agent, try:

```
create task "First demo task" P2 assignee:agent
next_task
```

The first call writes `T-001.md` into `<vault>/tasks/`; the second
returns it because nothing's blocking it. Mark it Done with
`complete_task T-001` and the agent will tell you what's now
unblocked.

Want a Kanban board for the same tasks? Run the
[Explorer](./docs/explorer.md) sidecar.

## What it does

- **Dependency resolution** — `next_task` returns tasks whose blockers
  are all Done
- **Priority + due date sorting** — P1s first, then by due date
- **Cycle detection** — prevents impossible task graphs
- **Status workflow** — Backlog → Ready → In Progress → Done (with
  Blocked / Cancelled escapes)
- **Auto-unblock notification** — when you complete a task, the agent
  tells you what's now ready
- **Body-as-truth** for checklists and comments — edits in Obsidian
  and tool calls from your agent never drift apart

See [`docs/tools.md`](./docs/tools.md) for the full 16-tool reference.

## Documentation

- [`docs/architecture.md`](./docs/architecture.md) — diagrams, status
  state machine, dependency-resolution algorithm, module layout
- [`docs/tools.md`](./docs/tools.md) — every MCP tool, grouped by role
- [`docs/task-format.md`](./docs/task-format.md) — frontmatter schema,
  comment thread, checklist progress
- [`docs/configuration.md`](./docs/configuration.md) — vault path,
  custom tasks folder, custom actors, MCP client registration
- [`docs/explorer.md`](./docs/explorer.md) — Kanban + dep graph web
  UI, REST endpoints
- [`INSTALLATION.md`](./INSTALLATION.md) — agent-driven install guide

## Contributing

See [`CONTRIBUTING.md`](./CONTRIBUTING.md) for dev setup and the bar
for PRs.
