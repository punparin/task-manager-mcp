"""Allow running as `python -m task_manager_mcp`."""

from .stdio import main

if __name__ == "__main__":
    raise SystemExit(main())
