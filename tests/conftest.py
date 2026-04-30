import pytest

from task_manager_mcp.tasks import TaskStore


@pytest.fixture
def store(tmp_path):
    return TaskStore(tmp_path)
