# Contributing

Thanks for picking this up. The bar is "small, focused PRs with tests" — that's it. The repo is open to teammates and to the wider community on the same terms.

## Dev setup

```bash
git clone https://github.com/punparin/task-manager-mcp.git
cd task-manager-mcp
python3 -m venv .venv
.venv/bin/pip install -e ".[dev,explorer]"
.venv/bin/pre-commit install   # gates `git commit` on lint
```

You'll need an Obsidian vault path for ad-hoc local runs:

```bash
OBSIDIAN_VAULT_PATH=/tmp/test-vault .venv/bin/python -m task_manager_mcp
```

The `tasks/` folder is created automatically on first run. To test with a different folder, set `TASK_MANAGER_TASKS_FOLDER`.

## Running tests

```bash
.venv/bin/pytest tests/ -v
```

Tests use a temporary vault per case (via `tmp_path` fixture), so they don't touch your real vault.

## Linting

```bash
.venv/bin/ruff check .
.venv/bin/ruff check --fix .          # auto-fix
.venv/bin/pre-commit run --all-files  # what CI runs
```

Lint failures block the Docker build job in CI. Fix locally before pushing.

## Branch naming

Pick something short and descriptive — kebab-case, prefixed with the kind of change if helpful (`fix-`, `add-`, `refactor-`).

Examples: `add-configurable-tasks-folder`, `fix-cycle-detection-edge-case`, `refactor-explorer-routes`.

## Commit + PR title

Lowercase imperative summary, ≤70 characters, no trailing period. Match what you'd write in a git log when skimming the repo's history.

Examples:
- `render checklist progress in explorer cards`
- `handle missing blocker tasks gracefully`
- `refresh tool count and explorer features`

## PR body

```markdown
## Summary
- 1–3 bullets: what changed and why
```

Include "Closes #N" if it fixes an open issue. Skip the AI-coauthor footers — they don't add anything.

## What we look for

- **Tests for new behavior.** Especially in `deps.py` (next_task, cycle detection), `tasks.py` (task store I/O), and `checklist.py` (progress parsing) — these are the parts where regressions are easiest to introduce.
- **One logical change per PR.** A bug fix doesn't need surrounding cleanup; a new tool doesn't need to refactor the explorer. Two changes → two PRs.
- **Docs land in the same PR as the feature.** If you add, rename, or change an `@mcp.tool()` or an explorer route, update one of `docs/tools.md`, `docs/explorer.md`, `task_manager_mcp/agent_instructions.py`, or `README.md` in the same diff. The `docs-with-feature` pre-commit hook enforces this on surface diffs; CI re-runs it. Refactors that don't change the public surface are exempt.
- **CHANGELOG.md updated.** Every user-visible change adds a bullet under the `## [Unreleased]` section. Internal refactors and chores don't need an entry.
- **For Explorer UI changes**, drop a screenshot or short clip in the PR.
- **Schema-touching PRs** (e.g. new fields in task frontmatter) need a backward-compat story for vaults already populated with the old shape — see how `agent` was added as an alias for the legacy `claude` assignee value (#22) for the pattern.

## Branch hygiene

When a PR is superseded by another approach (e.g. a rebased version, a different design after review), close it with a short comment pointing to the replacement (`superseded by #N`). Don't leave it dangling.

## Releases

Maintainer cuts releases. Workflow:

1. Move the contents of `## [Unreleased]` in `CHANGELOG.md` under a new `## [vX.Y.Z] - YYYY-MM-DD` heading; leave `## [Unreleased]` empty.
2. Bump `pyproject.toml` to the new version.
3. Merge as `chore: release vX.Y.Z`.
4. Push the matching tag (`git tag vX.Y.Z && git push origin vX.Y.Z`).

Tag push triggers `docker.yml` (builds + pushes ghcr images) and `release.yml` (creates the GitHub Release with auto-generated notes). No manual release-notes editing needed unless something exceptional happened.

Prefer one feature per release over bundling — small, frequent releases let users adopt fixes and features sooner, and the changelog stays legible.
