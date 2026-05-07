"""Tests for the comment thread under a task body."""

import pytest

from task_manager_mcp.checklist import task_to_dict
from task_manager_mcp.comments import append_comment, parse_comments
from task_manager_mcp.tasks import Task


class TestAppend:
    def test_creates_section_on_empty_body(self):
        body = append_comment("", "agent", "first note", "2026-05-07")
        assert "## Comments" in body
        assert "- **2026-05-07 agent**: first note" in body

    def test_creates_section_after_existing_body(self):
        body = append_comment("## Background\nstuff\n", "me", "see above", "2026-05-07")
        assert body.startswith("## Background")
        # Section appended at the end with a blank-line separator.
        assert "\n\n## Comments\n" in body
        assert body.rstrip().endswith("- **2026-05-07 me**: see above")

    def test_appends_to_existing_section(self):
        b1 = append_comment("", "agent", "first", "2026-05-07")
        b2 = append_comment(b1, "me", "second", "2026-05-08")
        comments = parse_comments(b2)
        assert [(c.date, c.author, c.text) for c in comments] == [
            ("2026-05-07", "agent", "first"),
            ("2026-05-08", "me", "second"),
        ]
        # Only one heading.
        assert b2.count("## Comments") == 1

    def test_appends_before_subsequent_section(self):
        body = (
            "intro\n\n"
            "## Comments\n\n"
            "- **2026-05-07 agent**: first\n\n"
            "## Completion Notes\n"
            "wrapped it up\n"
        )
        out = append_comment(body, "me", "wait", "2026-05-08")
        # New comment lands inside the Comments section, not after Completion Notes.
        comments_idx = out.index("## Comments")
        completion_idx = out.index("## Completion Notes")
        new_bullet_idx = out.index("- **2026-05-08 me**: wait")
        assert comments_idx < new_bullet_idx < completion_idx

    def test_flattens_newlines_in_text(self):
        body = append_comment("", "agent", "line one\nline two\n\nline three", "2026-05-07")
        # The bullet stays a single line; whitespace runs collapse to one space.
        bullet = next(line for line in body.splitlines() if line.startswith("-"))
        assert bullet == "- **2026-05-07 agent**: line one line two line three"


class TestParse:
    def test_no_section(self):
        assert parse_comments("just a body\n") == []

    def test_empty_section(self):
        assert parse_comments("## Comments\n\n") == []

    def test_skips_non_comment_bullets(self):
        body = (
            "## Comments\n\n"
            "- **2026-05-07 agent**: real comment\n"
            "- random bullet someone hand-edited\n"
            "not a bullet at all\n"
            "- **2026-05-08 me**: another\n"
        )
        comments = parse_comments(body)
        assert [c.author for c in comments] == ["agent", "me"]

    def test_stops_at_next_section(self):
        body = (
            "## Comments\n\n"
            "- **2026-05-07 agent**: in scope\n\n"
            "## Other\n"
            "- **2026-05-08 me**: out of scope\n"
        )
        comments = parse_comments(body)
        assert len(comments) == 1
        assert comments[0].author == "agent"

    def test_handles_custom_actor_names(self):
        body = "## Comments\n\n- **2026-05-07 alice**: hi\n- **2026-05-07 cursor**: yo\n"
        authors = [c.author for c in parse_comments(body)]
        assert authors == ["alice", "cursor"]


class TestTaskToDict:
    def test_comment_count_present_when_comments_exist(self):
        body = "## Comments\n\n- **2026-05-07 agent**: note\n- **2026-05-07 me**: ok\n"
        task = Task(id="T-001", title="t", body=body)
        d = task_to_dict(task)
        assert d["comment_count"] == 2
        # Body and full comment list only included when explicitly asked.
        assert "body" not in d
        assert "comments" not in d

    def test_no_key_when_no_comments(self):
        task = Task(id="T-001", title="t", body="just a body, no comments")
        d = task_to_dict(task)
        assert "comment_count" not in d

    def test_include_body_attaches_parsed_comments(self):
        body = "## Comments\n\n- **2026-05-07 agent**: note\n"
        task = Task(id="T-001", title="t", body=body)
        d = task_to_dict(task, include_body=True)
        assert d["comments"] == [{"date": "2026-05-07", "author": "agent", "text": "note"}]


class TestStoreRoundTrip:
    def test_comment_survives_save_and_reload(self, store):
        task = store.create(title="t")
        task.body = append_comment(task.body, "agent", "context", "2026-05-07")
        store.save(task)
        reloaded = store.get(task.id)
        comments = parse_comments(reloaded.body)
        assert len(comments) == 1
        assert comments[0].text == "context"

    def test_two_comments_round_trip(self, store):
        task = store.create(title="t")
        task.body = append_comment(task.body, "agent", "first", "2026-05-07")
        store.save(task)
        task = store.get(task.id)
        task.body = append_comment(task.body, "me", "second", "2026-05-08")
        store.save(task)
        reloaded = store.get(task.id)
        comments = parse_comments(reloaded.body)
        assert [c.author for c in comments] == ["agent", "me"]


class TestServerToolWiring:
    """The MCP tool layer is tested via the underlying functions; this
    file mirrors the assignee validation rule the tool relies on."""

    def test_valid_author_default_actors(self, store):
        # Default actor list contains 'me', 'agent', 'claude'.
        store.validate_assignee("me")
        store.validate_assignee("agent")
        store.validate_assignee("claude")  # alias

    def test_invalid_author_rejected(self, store):
        with pytest.raises(ValueError):
            store.validate_assignee("ghost")
