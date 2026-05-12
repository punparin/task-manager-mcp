# Changelog

All notable user-visible changes to this project are recorded here.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [v0.5.5] - 2026-05-12

### Added
- `list_tasks` accepts a `tags` filter — comma-separated, AND-matched — so agents can narrow large vault queries instead of pulling every task and post-filtering (#68).

## [v0.5.4] - 2026-05-08

### Fixed
- Auto-promote backlog dependents to ready when a blocker is cancelled, not just when it's completed (#63).
- Auto-promote also fires when `update_task` clears the last unfinished blocker via `blocked_by`, matching the `complete_task` behavior (#60).

## [v0.5.3] - 2026-05-08

### Added
- Explorer Activity tab: chronological feed of every status transition, with its own since/actor/task/limit filter row (#57).
- Per-task History panel inside the side drawer, sourced from the audit log (#57).

## [v0.5.2] - 2026-05-08

### Fixed
- Explorer body text now uses prose styling, destructive actions ask for confirmation, and trailing ellipses on truncated cards are gone (#55).

## [v0.5.1] - 2026-05-07

### Added
- `task_tree` walks dependents, not just blockers — `direction="dependents"` and `direction="both"` (#53).

## [v0.5.0] - 2026-05-07

### Added
- MCP server now ships agent rules over MCP `instructions`; `AGENT.md` is no longer needed in-vault (#43, #44).
- `bulk_update` tool: apply many `update_task` calls in one round-trip with per-task pass/fail (#49).
- `validate_dependencies` catches workflow drift on top of cycle/missing-ref checks: in-progress without assignee, `completed:` set on a non-Done task, `blocked_by` pointing to a Cancelled task (#48).
- Status-change audit log written to `<vault>/.task-manager/audit.jsonl`; `list_audit` MCP tool and `GET /api/audit` endpoint expose it (#50).
- `update_task` now exposes `blocked_by` (cycle-checked) and `completed` (#46).
- Auto-promote: backlog dependents flip to Ready automatically when their last blocker completes; surfaced under `promoted` alongside `unblocked` (#45).
- Demo gifs in README for both the MCP and the explorer (#37, #39, #40).

### Fixed
- Explorer renders body markdown headings as styled headings (#42).

### Changed
- README trimmed; deeper material moved into `docs/` (#38).

## [v0.4.6] - 2026-05-07

### Added
- Explorer surfaces task comments and completion notes in the side drawer (#33).

## [v0.4.5] - 2026-05-07

### Added
- Comment thread on every task — `add_comment`, `list_comments` MCP tools and matching explorer UI (#31).
- Agent-readable `INSTALLATION.md` for one-shot MCP setup (#30).

## [v0.4.4] - 2026-05-04

### Added
- Customizable actor list via `<vault>/.task-manager/config.yml` (#28).

## [v0.4.3] - 2026-04-30

### Added
- Configurable tasks folder via `TASK_MANAGER_TASKS_FOLDER` (#24).
- `agent` accepted as canonical assignee, with `claude` kept as a legacy alias (#22).

### Changed
- README decoupled from Claude Code branding (#21).
- LICENSE and team quickstart added; GitHub issue templates landed (#23, #25, #26).

## [v0.4.2] - 2026-04-30

### Changed
- CI now runs ruff lint as part of the pipeline (#19).

## [v0.4.1] - 2026-04-30

### Fixed
- Reference docs caught up with actual surface (tool count, explorer features, endpoints) (#17).

## [v0.4.0] - 2026-04-27

### Added
- Explorer universal search across id / title / project / area / tag, package version in the header, and finished scroll-position fix (#15).

## [v0.3.0] - 2026-04-27

### Added
- Checklist progress (`{done, total, pct}`) computed from task body and rendered on cards and in the side panel (#11, #13).

### Fixed
- Explorer auto-refresh preserves scroll position (#12).

## [v0.2.2] - 2026-04-25

### Fixed
- Explorer side panel restored; blocked dependencies now render in red (#9).

## [v0.2.1] - 2026-04-25

### Changed
- Explorer uses the vault name in `obsidian://` urls so links open in the right vault (#7).

## [v0.2.0] - 2026-04-25

### Added
- Explorer obsidian-webview UX pass (#5).

## [v0.1.0] - 2026-04-25

### Added
- FastAPI explorer sidecar with kanban board and drag-to-update (#3).
- Architecture and workflow diagrams in docs (#2).

## [v0.0.1] - 2026-04-09

### Added
- Initial release: MCP server with dependency-aware task scheduling (#1).
