"""Round-trip tests for the audit log writer + reader."""

from __future__ import annotations

from datetime import datetime

import pytest

from task_manager_mcp.audit import audit_path, read_audit, record_transition


def test_record_creates_file_and_returns_iso_date(tmp_path):
    when = datetime(2026, 5, 7, 12, 0, 0)
    iso = record_transition(tmp_path, "T-001", "Backlog", "Ready", "agent", when=when)
    assert iso == "2026-05-07"
    assert audit_path(tmp_path).exists()


def test_round_trip_preserves_fields(tmp_path):
    record_transition(tmp_path, "T-001", "Backlog", "Ready", "agent",
                      when=datetime(2026, 5, 7, 9, 0, 0))
    record_transition(tmp_path, "T-001", "Ready", "In Progress", "me",
                      when=datetime(2026, 5, 7, 11, 30, 0))
    entries = read_audit(tmp_path)
    # newest first
    assert entries[0]["new_status"] == "In Progress"
    assert entries[0]["actor"] == "me"
    assert entries[1]["new_status"] == "Ready"


def test_filter_by_task_id(tmp_path):
    record_transition(tmp_path, "T-001", "Backlog", "Ready", "agent")
    record_transition(tmp_path, "T-002", "Backlog", "Ready", "agent")
    out = read_audit(tmp_path, task_id="T-002")
    assert len(out) == 1
    assert out[0]["task_id"] == "T-002"


def test_filter_by_since(tmp_path):
    record_transition(tmp_path, "T-001", "Backlog", "Ready", "agent",
                      when=datetime(2026, 5, 1, 10, 0, 0))
    record_transition(tmp_path, "T-001", "Ready", "In Progress", "agent",
                      when=datetime(2026, 5, 7, 10, 0, 0))
    out = read_audit(tmp_path, since="2026-05-05")
    assert len(out) == 1
    assert out[0]["new_status"] == "In Progress"


def test_invalid_since_raises(tmp_path):
    record_transition(tmp_path, "T-001", "Backlog", "Ready", "agent")
    with pytest.raises(ValueError):
        read_audit(tmp_path, since="last week")


def test_limit_caps_results(tmp_path):
    for i in range(5):
        record_transition(tmp_path, f"T-{i:03d}", "Backlog", "Ready", "agent",
                          when=datetime(2026, 5, 7, i, 0, 0))
    out = read_audit(tmp_path, limit=3)
    assert len(out) == 3


def test_read_returns_empty_when_log_absent(tmp_path):
    assert read_audit(tmp_path) == []


def test_skips_malformed_lines(tmp_path):
    record_transition(tmp_path, "T-001", "Backlog", "Ready", "agent")
    # Inject a junk line.
    with audit_path(tmp_path).open("a", encoding="utf-8") as f:
        f.write("{not json\n")
    out = read_audit(tmp_path)
    assert len(out) == 1
    assert out[0]["task_id"] == "T-001"
