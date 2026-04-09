FROM python:3.13-slim

WORKDIR /app

COPY pyproject.toml .
COPY task_manager_mcp/ task_manager_mcp/
RUN pip install --no-cache-dir -e .

ENV OBSIDIAN_VAULT_PATH=/vault

ENTRYPOINT ["python", "-m", "task_manager_mcp"]
