"""Subprocess regressions for MCP stdio disconnect and shutdown."""

import json
import os
import select
import signal
import subprocess
import sys

import pytest


@pytest.fixture
def launch(tmp_path):
    processes = []

    def start(command):
        proc = subprocess.Popen(
            command,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            start_new_session=True,
            env={**os.environ, "OBSIDIAN_VAULT_PATH": str(tmp_path)},
        )
        processes.append(proc)
        return proc

    yield start
    for proc in processes:
        # Also clean up a child left behind if a regression kills its launcher.
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        proc.wait(timeout=10)
        proc.stdin.close()
        proc.stdout.close()


def _readline(proc):
    assert select.select([proc.stdout], [], [], 20)[0], "server response timed out"
    line = proc.stdout.readline()
    assert line, "server exited before responding"
    return line


def _send(proc, message):
    proc.stdin.write(json.dumps({"jsonrpc": "2.0", **message}) + "\n")
    proc.stdin.flush()


@pytest.mark.parametrize("disconnect", ["eof", "sigterm"])
def test_mcp_disconnect_exits(launch, disconnect):
    proc = launch([sys.executable, "-m", "task_manager_mcp"])
    _send(proc, {
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "shutdown-test", "version": "1"},
        },
    })
    assert "result" in json.loads(_readline(proc))
    _send(proc, {"method": "notifications/initialized"})
    _send(proc, {"id": 2, "method": "tools/list"})
    assert json.loads(_readline(proc))["result"]["tools"]
    if disconnect == "eof":
        proc.stdin.close()
    else:
        # Leave stdin open: SIGTERM must also work for a container's PID 1.
        proc.send_signal(signal.SIGTERM)
    proc.wait(timeout=10)
    if disconnect == "eof":
        assert proc.returncode == 0


@pytest.mark.parametrize("ignore_sigterm", [False, True])
def test_hung_server_is_reaped_on_eof(launch, ignore_sigterm):
    child_code = (
        "import os,signal,sys,time; "
        + ("signal.signal(signal.SIGTERM, signal.SIG_IGN); " if ignore_sigterm else "")
        + "print(os.getpid(),flush=True); sys.stdin.read(); time.sleep(60)"
    )
    command = [sys.executable, "-c", child_code]
    proc = launch([
        sys.executable, "-c",
        "import sys; from task_manager_mcp.stdio import _run_stdio; "
        f"sys.exit(_run_stdio({command!r}))",
    ])
    child_pid = int(_readline(proc))
    proc.stdin.close()
    proc.wait(timeout=10)
    with pytest.raises(ProcessLookupError):
        os.kill(child_pid, 0)


def test_child_failure_is_propagated_without_waiting_for_eof(launch):
    command = [sys.executable, "-c", "raise SystemExit(7)"]
    proc = launch([
        sys.executable, "-c",
        "import sys; from task_manager_mcp.stdio import _run_stdio; "
        f"sys.exit(_run_stdio({command!r}))",
    ])
    assert proc.wait(timeout=10) == 7
