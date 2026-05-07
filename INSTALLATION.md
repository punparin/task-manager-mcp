# Installation Guide (for AI agents)

> **For the human:** paste this file's URL into your MCP-capable agent
> (Claude Code, Cursor, Cline, …) and say *"read this and help me install
> it."* The agent will ask you everything it needs as it goes.

> **For the agent:** these are step-by-step instructions for installing
> the Task Manager MCP server on the current user's machine. Follow them
> top-to-bottom. **Ask the user any question whose answer isn't already
> in their messages or in the host environment — never assume defaults
> for paths, folders, or actor lists.** Only proceed once each prompt is
> answered. If a command fails, stop and report; do not guess fixes.

---

## Step 0 — Confirm the host OS

Run this and report the result:

```sh
uname -s             # Linux / Darwin / (WSL on Windows)
```

Don't probe for Docker or Python yet — which one matters depends on the
runtime the user picks in Step 2.

---

## Step 1 — Ask: which MCP client?

Ask the user which agent will host the MCP server. Examples: Claude Code,
Cursor, Cline, Continue, Goose, Windsurf, something else.

The registration command differs per client:

- **Claude Code:** this guide covers it directly (`claude mcp add` —
  see Step 6).
- **Anything else:** you (the agent) are responsible for figuring out
  that client's MCP registration path. Look up the client's current
  docs (web search, the client's GitHub README, or context7 if you have
  it) and apply whatever steps they specify — usually editing a JSON
  config file or running a CLI. **Confirm what you find with the user
  before writing any config.**
- **If you can't find clear, current docs** for the client, fall back
  to *Step 6 — Path C: Manual JSON* and hand the user a snippet to
  paste themselves. Do not invent a CLI or guess at a config schema.

---

## Step 2 — Ask: which runtime?

Ask this **before** anything else, because it decides which prerequisite
the user actually needs. **Recommend Docker** — it's slim, has no Python
deps to manage, and is the default install path.

| Option | When to use | What you'll need |
|---|---|---|
| **A. Docker** *(recommended)* | Default. Works as long as Docker is running. | `docker` available |
| **B. Local virtualenv** | User explicitly wants a Python install (e.g. no Docker, or wants to hack on the source). | Python 3.11+, `git` |

Phrase it: *"Do you want the Docker install (recommended — no Python
needed) or a local Python install? Pick Docker unless you have a
reason not to."*

Save the answer as `RUNTIME` ∈ {`docker`, `local`}.

### 2a. Verify the prerequisite for the chosen runtime

Only check the tool the user actually needs:

- **`RUNTIME=docker`:** run `docker --version`. If it fails, **stop**
  and tell the user Docker isn't installed or isn't on `PATH`. Ask
  whether they want to install Docker or switch to the local runtime.
  Do not try to install Docker yourself.
- **`RUNTIME=local`:** run `python3 --version`. If the version is older
  than 3.11, **stop** and tell the user. Ask whether they want to
  upgrade Python or switch to Docker. Do not try to upgrade Python
  yourself. Also confirm `git --version` works.

---

## Step 3 — Ask: where is the vault?

Tasks are stored as markdown files inside an Obsidian-style vault (any
folder of `.md` files works — Obsidian itself isn't required, but the
vault layout is what the server expects). **Do not guess this path.**

Prompt:

> *"What is the absolute path to the vault where tasks should live?
> (e.g. `/home/you/Documents/MyVault` — usually the same vault you use
> with Obsidian. The folder will hold a `tasks/` subdirectory unless you
> override it in the next step.)"*

Then verify the directory exists:

```sh
[ -d "<vault-path>" ] && echo "OK" || echo "MISSING"
```

If `MISSING`, ask the user to confirm the path before moving on. If the
folder exists but has no `.obsidian/` subdir, just note that to the user
(it still works — Task Manager only needs a writable directory) and
continue.

Save the answer as `VAULT_PATH`.

### 3a. Ask: custom tasks folder?

By default, tasks are written to `<VAULT_PATH>/tasks/`. If the user's
vault already has somewhere tasks belong (e.g. `inbox/tasks`,
`work/queue`, `projects/active/`), they can point the server there.

Ask:

> *"Where inside the vault should task files live? Default is*
> *`tasks/`. Common alternatives: `inbox/tasks`, `work/queue`, or any*
> *nested path relative to the vault root. Press enter to accept*
> *`tasks/`."*

Save the answer as `TASKS_FOLDER` (default: `tasks`). Path is resolved
relative to the vault root; `..` escapes are rejected at server
startup. The folder is created on first run if it doesn't exist — no
need to mkdir it now.

If the user picked the default, you can omit the
`TASK_MANAGER_TASKS_FOLDER` env var entirely in Step 6.

### 3b. Ask: custom actors (team setup)?

Out of the box, tasks can be assigned to two actors:

- `me` — the human
- `agent` — the MCP agent (legacy `claude` is kept as an alias)

If the user works alone with one agent, the defaults are fine — skip
this step. If they want a team (multiple humans, multiple agents, or
both), ask:

> *"Do you want a custom actor list? Skip this if it's just you + one*
> *agent. Otherwise list the names you'll use for `assignee:` —*
> *e.g. `me, agent, alice, bob, cursor`. The list **replaces** the*
> *defaults, so include `me`/`agent` if you still want them."*

If they give a list, write it to `<VAULT_PATH>/.task-manager/config.yml`:

```yaml
actors:
  - me
  - agent
  - alice
  - bob
  - cursor
```

**Show the user the YAML you're about to write and ask for
confirmation** before creating the file. If `<VAULT_PATH>/.task-manager/`
doesn't exist yet, `mkdir -p` it first. If the file already exists,
read it, ask whether to merge or replace, and don't clobber silently.

The config lives in the vault, so syncing the vault syncs the actor
list across the team. Validation runs only on writes — existing task
files keep loading even if you later remove an actor.

---

## Step 4 — Ask: scope?

Ask: *"Should this MCP be available in **all your projects** (user
scope) or only in the **current project** (project scope, written to a
checked-in `.mcp.json`)?"*

Save as `SCOPE` ∈ {`user`, `project`}. Translate to flag:

- `user` → `-s user`
- `project` → `-s project`

If the user's client is not Claude Code, this maps to whatever the
client's equivalent is — see Step 5.

---

## Step 5 — Install

### Path A — Docker

Pull the image first:

```sh
docker pull ghcr.io/punparin/task-manager-mcp:latest
```

Then build the registration command. Compose env-var flags from the
user's answers:

```sh
# Always include the vault mount:
#   -v "$VAULT_PATH:/vault"
#
# Add this only if TASKS_FOLDER is not the default "tasks":
#   -e TASK_MANAGER_TASKS_FOLDER="$TASKS_FOLDER"

claude mcp add -s "$SCOPE" task-manager -- \
  docker run -i --rm \
    -v "$VAULT_PATH:/vault" \
    <env flags from above> \
    ghcr.io/punparin/task-manager-mcp:latest
```

**Show the user the exact command you're about to run, with their
answers substituted, and ask them to confirm before executing.**

### Path B — Local virtualenv

Ask: *"Where should I clone the repo? (e.g. `~/repos/task-manager-mcp`)"*
— save as `INSTALL_DIR`. Then:

```sh
git clone https://github.com/punparin/task-manager-mcp.git "$INSTALL_DIR"
cd "$INSTALL_DIR"
python3 -m venv .venv
.venv/bin/pip install -e .
```

Register with Claude Code. Build env flags:

```sh
# Common to all:
#   -e OBSIDIAN_VAULT_PATH=$VAULT_PATH
# Plus, only if TASKS_FOLDER is not the default "tasks":
#   -e TASK_MANAGER_TASKS_FOLDER=$TASKS_FOLDER

claude mcp add -s "$SCOPE" task-manager \
  -e OBSIDIAN_VAULT_PATH="$VAULT_PATH" \
  <other env flags> \
  -- "$INSTALL_DIR/.venv/bin/python" -m task_manager_mcp
```

**Confirm the command with the user before running.**

### Path C — Other clients (Cursor, Cline, Goose, …)

First, try the client's own registration path (per Step 1). If you
*do* know the path — e.g. the user told you the config file location,
or you found current docs — apply it directly using the same command +
env values from Path A or Path B. **Always show the user the exact
config you're about to write and wait for confirmation.**

If you don't know the path, fall through to a manual JSON handoff:
print the snippet below with the user's answers substituted, and ask
them to paste it into their client's MCP config file. Do not write to
unknown paths yourself.

For Docker:

```json
{
  "task-manager": {
    "command": "docker",
    "args": [
      "run", "-i", "--rm",
      "-v", "<VAULT_PATH>:/vault",
      "ghcr.io/punparin/task-manager-mcp:latest"
    ]
  }
}
```

If `TASKS_FOLDER` is non-default, insert two more args before the
image: `"-e", "TASK_MANAGER_TASKS_FOLDER=<TASKS_FOLDER>"`.

For local:

```json
{
  "task-manager": {
    "command": "<INSTALL_DIR>/.venv/bin/python",
    "args": ["-m", "task_manager_mcp"],
    "env": {
      "OBSIDIAN_VAULT_PATH": "<VAULT_PATH>"
    }
  }
}
```

Add `"TASK_MANAGER_TASKS_FOLDER": "<TASKS_FOLDER>"` to `env` if
non-default.

Substitute every `<…>` placeholder with the user's answers. **Do not
ship placeholders.**

---

## Step 6 — Verify

After registration, ask the user to:

1. **Restart their MCP client** (Claude Code: quit and reopen; for other
   clients, follow that client's docs).
2. Ask the agent something like *"create a task called 'first demo'
   priority P3 assigned to agent"* and confirm the agent calls
   `create_task` and reports a new ID like `T-001`.
3. Then *"what's next?"* — confirm the agent calls `next_task` and
   returns that task.

If the agent says it doesn't see the `task-manager` MCP, run:

```sh
claude mcp list           # Claude Code only
```

…and report the output. If `task-manager` is missing from the list,
the registration didn't take — re-check the command from Step 5 with
the user.

If the server appears but tool calls fail, ask the user to share the
client-side error message verbatim. Common causes:

- Vault path is wrong or not mounted (Docker `-v` flag).
- `OBSIDIAN_VAULT_PATH` env var not propagated (local install).
- `TASK_MANAGER_TASKS_FOLDER` resolves outside the vault (server
  rejects `..` escapes at startup) — check the value is a path
  *relative* to the vault root, not absolute.
- Custom actors config has a YAML syntax error — server fails loudly
  at startup; tail the client-side MCP logs.

---

## Step 7 — Optional: Explorer (Kanban web UI)

Ask: *"Do you want the browser-based Explorer too? It's a Kanban board
served on port 8765 — drag-and-drop between Backlog / Ready / In
Progress / Blocked / Done lanes, dependency graph view, inline
checklist ticking. Same vault, same task files, same frontmatter."*

If yes, mirror the runtime choice from Step 2:

- **Docker:**
  ```sh
  docker pull ghcr.io/punparin/task-manager-mcp-explorer:latest
  docker run --rm -p 8765:8765 -v "$VAULT_PATH:/vault" \
    ghcr.io/punparin/task-manager-mcp-explorer:latest
  ```
- **Local:**
  ```sh
  cd "$INSTALL_DIR"
  .venv/bin/pip install -e ".[explorer]"
  OBSIDIAN_VAULT_PATH="$VAULT_PATH" \
    .venv/bin/python -m task_manager_mcp.explorer --host 0.0.0.0 --port 8765
  ```

If `TASKS_FOLDER` is non-default, also pass
`-e TASK_MANAGER_TASKS_FOLDER=$TASKS_FOLDER` (Docker) or set it in the
shell env (local).

Then open <http://127.0.0.1:8765>. The Explorer writes straight to task
frontmatter, so changes you make in the UI show up immediately for the
agent and vice versa. Hit `/api/health` to confirm the resolved vault
path and tasks folder.

---

## Step 8 — Done

Summarize back to the user:

- Vault path
- Tasks folder (default `tasks/` or custom)
- Actors (defaults `me`/`agent`, or the custom list they wrote)
- Runtime (Docker / local)
- Scope
- Whether the Explorer was installed

…and tell them which client restart they still need to do, if any.
