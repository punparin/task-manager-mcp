"""Subprocess regressions for MCP stdio disconnect and shutdown."""

import json
import os
import select
import signal
import subprocess
import sys
import time

import pytest

from task_manager_mcp.stdio import _exit_code

# Relies on POSIX process groups, signals and select() on pipes.
pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="POSIX only")


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
    started = time.monotonic()
    if disconnect == "eof":
        proc.stdin.close()
    else:
        # Leave stdin open: SIGTERM must also work for a container's PID 1.
        proc.send_signal(signal.SIGTERM)
    assert proc.wait(timeout=10) == 0
    # A clean exit, well inside the grace period rather than after escalation.
    assert time.monotonic() - started < 2.5


def _launch_stub(launch, child_code):
    command = [sys.executable, "-c", child_code]
    proc = launch([
        sys.executable, "-c",
        "import sys; from task_manager_mcp.stdio import _run_stdio; "
        f"sys.exit(_run_stdio({command!r}))",
    ])
    return proc, int(_readline(proc))


@pytest.mark.parametrize("ignore_sigterm", [False, True])
def test_hung_server_is_reaped_on_eof(launch, ignore_sigterm):
    child_code = (
        "import os,signal,sys,time; "
        + ("signal.signal(signal.SIGTERM, signal.SIG_IGN); " if ignore_sigterm else "")
        + "print(os.getpid(),flush=True); sys.stdin.read(); time.sleep(60)"
    )
    proc, child_pid = _launch_stub(launch, child_code)
    proc.stdin.close()
    proc.wait(timeout=10)
    with pytest.raises(ProcessLookupError):
        os.kill(child_pid, 0)


def test_repeated_sigterm_skips_grace(launch):
    # Child ignores EOF and SIGTERM, so only SIGKILL can stop it.
    proc, child_pid = _launch_stub(
        launch,
        "import os,signal,time; signal.signal(signal.SIGTERM, signal.SIG_IGN); "
        "print(os.getpid(),flush=True); time.sleep(60)",
    )
    started = time.monotonic()
    for _ in range(3):
        proc.send_signal(signal.SIGTERM)
        time.sleep(0.2)
    assert proc.wait(timeout=10) == 128 + signal.SIGKILL
    assert time.monotonic() - started < 2.5
    with pytest.raises(ProcessLookupError):
        os.kill(child_pid, 0)


@pytest.mark.parametrize("returncode, expected", [(0, 0), (7, 7), (-15, 143), (-9, 137)])
def test_exit_code_maps_signals_to_shell_convention(returncode, expected):
    assert _exit_code(returncode) == expected


def test_child_failure_is_propagated_without_waiting_for_eof(launch):
    command = [sys.executable, "-c", "raise SystemExit(7)"]
    proc = launch([
        sys.executable, "-c",
        "import sys; from task_manager_mcp.stdio import _run_stdio; "
        f"sys.exit(_run_stdio({command!r}))",
    ])
    assert proc.wait(timeout=10) == 7
