"""Bound the stdio server's lifetime to its client connection."""

import os
import queue
import signal
import subprocess
import sys
import threading
import time

# Time the server gets to exit on its own after stdin closes, then after SIGTERM.
GRACE_SECONDS = 3
TERMINATE_SECONDS = 2

_EOF, _SIGNAL, _EXITED = "eof", "signal", "exited"


def _exit_code(returncode: int) -> int:
    # Popen reports death by signal N as -N; shells and Docker expect 128 + N.
    return 128 - returncode if returncode < 0 else returncode


def _run_stdio(command: list[str]) -> int:
    # SimpleQueue.put is reentrant, so the signal handler can use it without
    # the deadlock risk of taking a lock the interrupted main thread holds.
    events: queue.SimpleQueue[str] = queue.SimpleQueue()

    def on_signal(signum, frame):
        events.put(_SIGNAL)

    # Install before spawning so an early SIGTERM can't orphan the child.
    previous_handlers = {
        signum: signal.signal(signum, on_signal)
        for signum in (signal.SIGTERM, signal.SIGINT)
    }
    try:
        child = subprocess.Popen(command, stdin=subprocess.PIPE)

        def close_child_stdin():
            try:
                child.stdin.close()
            except (OSError, ValueError):
                pass

        def forward_stdin():
            try:
                while data := os.read(sys.stdin.fileno(), 65536):
                    child.stdin.write(data)
                    child.stdin.flush()
            except (OSError, ValueError):
                # Child exited, or the main thread already closed its stdin.
                pass
            finally:
                close_child_stdin()
                events.put(_EOF)

        def watch_child():
            child.wait()
            events.put(_EXITED)

        def exits_within(timeout: float) -> bool:
            # False on timeout or on another signal, which skips the rest of
            # this stage so a repeated Ctrl-C/SIGTERM hurries shutdown along.
            deadline = time.monotonic() + timeout
            while (remaining := deadline - time.monotonic()) > 0:
                try:
                    event = events.get(timeout=remaining)
                except queue.Empty:
                    break
                if event == _EXITED:
                    return True
                if event == _SIGNAL:
                    break
            return False

        # Daemon threads cannot hold the launcher open after the server exits.
        threading.Thread(target=forward_stdin, daemon=True).start()
        threading.Thread(target=watch_child, daemon=True).start()

        if events.get() != _EXITED:
            # Give the server EOF so it shuts down normally, even when a signal
            # arrived while the client's stdin was still open.
            close_child_stdin()
            if not exits_within(GRACE_SECONDS):
                child.terminate()
                if not exits_within(TERMINATE_SECONDS):
                    child.kill()
        child.wait()
        return _exit_code(child.returncode)
    finally:
        for signum, handler in previous_handlers.items():
            signal.signal(signum, handler)


def main() -> int:
    return _run_stdio([sys.executable, "-m", "task_manager_mcp.server"])
