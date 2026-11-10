"""Bound the stdio server's lifetime to its client connection."""

import os
import signal
import subprocess
import sys
import threading


def _run_stdio(command: list[str]) -> int:
    child = subprocess.Popen(command, stdin=subprocess.PIPE)
    disconnected = threading.Event()

    def forward_stdin():
        try:
            while data := os.read(sys.stdin.fileno(), 65536):
                child.stdin.write(data)
                child.stdin.flush()
        except (BrokenPipeError, OSError):
            pass
        finally:
            try:
                child.stdin.close()
            except (BrokenPipeError, OSError):
                pass
            disconnected.set()

    def stop_requested(signum, frame):
        disconnected.set()

    previous_handlers = {
        signum: signal.signal(signum, stop_requested)
        for signum in (signal.SIGTERM, signal.SIGINT)
    }
    try:
        # A daemon reader cannot hold the launcher open after the server exits.
        threading.Thread(target=forward_stdin, daemon=True).start()
        while child.poll() is None:
            if disconnected.wait(0.1):
                # Let EOF finish in-flight work before escalating shutdown.
                try:
                    child.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    child.terminate()
                    try:
                        child.wait(timeout=2)
                    except subprocess.TimeoutExpired:
                        child.kill()
                        child.wait()
                break
        return child.returncode
    finally:
        for signum, handler in previous_handlers.items():
            signal.signal(signum, handler)


def main() -> int:
    return _run_stdio([sys.executable, "-m", "task_manager_mcp.server"])
