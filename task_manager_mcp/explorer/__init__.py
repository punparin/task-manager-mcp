"""Explorer — FastAPI sidecar for visualizing and managing tasks.

Standalone HTTP service that reads the same vault as the MCP server, but
serves a Kanban-style board for browsers (laptop / phone via SSH tunnel
or Tailscale). Drag-and-drop updates land in task frontmatter, so the
MCP and the UI agree on a single source of truth.
"""
