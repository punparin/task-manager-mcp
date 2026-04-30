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

`<type>/<short-kebab-description>` where `<type>` is one of `feat`, `fix`, `chore`, `docs`, `refactor`, `test`, `perf`.

Examples: `feat/configurable-tasks-folder`, `fix/cycle-detection-edge-case`.

## Commit + PR title

[Conventional Commits](https://www.conventionalcommits.org/): `<type>(<scope>)?: <imperative summary, lowercase, no trailing period>`, ≤70 characters.

Examples:
- `feat(explorer): render checklist progress in cards`
- `fix(deps): handle missing blocker tasks gracefully`
- `docs: refresh tool count and explorer features`

## PR body

```markdown
## Summary
- 1–3 bullets: what changed and why
```

Include "Closes #N" if it fixes an open issue. Skip the AI-coauthor footers — they don't add anything.

## What we look for

- **Tests for new behavior.** Especially in `deps.py` (next_task, cycle detection), `tasks.py` (task store I/O), and `checklist.py` (progress parsing) — these are the parts where regressions are easiest to introduce.
- **One logical change per PR.** A bug fix doesn't need surrounding cleanup; a new tool doesn't need to refactor the explorer. Two changes → two PRs.
- **No new config knobs without docs.** If you're adding an env var or tool argument, document it in the README and (if it's a load-bearing convention) in `CLAUDE.md`.
- **For Explorer UI changes**, drop a screenshot or short clip in the PR.
- **Schema-touching PRs** (e.g. new fields in task frontmatter) need a backward-compat story for vaults already populated with the old shape — see how `agent` was added as an alias for the legacy `claude` assignee value (#22) for the pattern.

## Releases

Maintainer cuts releases. Workflow:

1. Bump `pyproject.toml` to the new version.
2. Merge as `chore: release vX.Y.Z`.
3. Push the matching tag (`git tag vX.Y.Z && git push origin vX.Y.Z`).

Tag push triggers `docker.yml` (builds + pushes ghcr images) and `release.yml` (creates the GitHub Release with auto-generated notes). No manual release-notes editing needed unless something exceptional happened.
