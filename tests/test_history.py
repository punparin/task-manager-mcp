"""Round-trip tests for the status-history audit log helpers."""

from __future__ import annotations

from task_manager_mcp.history import HISTORY_HEADING, append_history, parse_history


def test_append_creates_section_when_absent():
    body = ""
    out = append_history(body, "Backlog", "Ready", "agent", "2026-05-07")
    assert HISTORY_HEADING in out
    assert "- **2026-05-07**: Backlog → Ready (agent)" in out


def test_append_under_existing_section():
    body = (
        "Some prose.\n\n"
        "## History\n\n"
        "- **2026-05-06**: Backlog → Ready (me)\n"
    )
    out = append_history(body, "Ready", "In Progress", "agent", "2026-05-07")
    lines = [line for line in out.splitlines() if line.startswith("-")]
    assert lines == [
        "- **2026-05-06**: Backlog → Ready (me)",
        "- **2026-05-07**: Ready → In Progress (agent)",
    ]


def test_append_does_not_clobber_following_section():
    body = (
        "## History\n\n"
        "- **2026-05-06**: Backlog → Ready (me)\n\n"
        "## Comments\n\n"
        "- **2026-05-06 me**: heads up\n"
    )
    out = append_history(body, "Ready", "Done", "agent", "2026-05-07")
    assert "## Comments" in out
    assert "- **2026-05-06 me**: heads up" in out
    assert "- **2026-05-07**: Ready → Done (agent)" in out
    # The new entry must land before the Comments section.
    assert out.index("- **2026-05-07**") < out.index("## Comments")


def test_parse_extracts_entries():
    body = (
        "## History\n\n"
        "- **2026-05-06**: Backlog → Ready (me)\n"
        "- **2026-05-07**: Ready → In Progress (agent)\n"
        "  random hand note that should be skipped\n"
        "- **2026-05-08**: In Progress → Done (me)\n"
    )
    entries = parse_history(body)
    assert [e.to_dict() for e in entries] == [
        {"date": "2026-05-06", "old_status": "Backlog", "new_status": "Ready", "actor": "me"},
        {"date": "2026-05-07", "old_status": "Ready", "new_status": "In Progress", "actor": "agent"},
        {"date": "2026-05-08", "old_status": "In Progress", "new_status": "Done", "actor": "me"},
    ]


def test_parse_returns_empty_when_section_absent():
    assert parse_history("just a body, no history") == []
    assert parse_history("") == []
