"""Tests for checklist parsing, rollup, and tick mutation."""

import pytest

from task_manager_mcp.checklist import parse_checklist, task_to_dict, tick
from task_manager_mcp.tasks import Task


class TestParse:
    def test_empty_body(self):
        p = parse_checklist("")
        assert p.total == 0 and p.done == 0 and p.pct == 0
        assert p.items == []

    def test_no_checklist(self):
        p = parse_checklist("just a paragraph\nand another line\n")
        assert p.total == 0

    def test_simple_dash(self):
        p = parse_checklist("- [ ] one\n- [x] two\n- [ ] three\n")
        assert (p.done, p.total, p.pct) == (1, 3, 33)
        assert [it.text for it in p.items] == ["one", "two", "three"]

    def test_star_bullet(self):
        p = parse_checklist("* [ ] alpha\n* [x] beta\n")
        assert (p.done, p.total) == (1, 2)

    def test_capital_x_counts_as_checked(self):
        p = parse_checklist("- [X] big X\n")
        assert p.done == 1 and p.total == 1

    def test_extra_spaces_do_not_match(self):
        # `[ x ]` with surrounding spaces is intentionally not matched —
        # we only accept the canonical `[ ]` / `[x]` / `[X]` glyphs.
        p = parse_checklist("- [ x ] sloppy\n- [  ] also sloppy\n")
        assert p.total == 0

    def test_nested_items_count(self):
        body = "- [x] parent\n  - [ ] child\n    - [x] grandchild\n"
        p = parse_checklist(body)
        assert (p.done, p.total) == (2, 3)

    def test_ignores_code_fence(self):
        body = (
            "- [x] real one\n"
            "```python\n"
            "- [ ] not a real item\n"
            "- [x] also not real\n"
            "```\n"
            "- [ ] another real one\n"
        )
        p = parse_checklist(body)
        assert (p.done, p.total) == (1, 2)
        assert [it.text for it in p.items] == ["real one", "another real one"]

    def test_pct_rounding(self):
        # 2/3 → 67 (round half-to-even doesn't trip here; 66.666 → 67)
        p = parse_checklist("- [x] a\n- [x] b\n- [ ] c\n")
        assert p.pct == 67

    def test_all_done(self):
        p = parse_checklist("- [x] a\n- [x] b\n")
        assert p.pct == 100

    def test_bare_brackets_without_bullet_ignored(self):
        # Prose like "[ ] something" without the `- ` prefix shouldn't count.
        p = parse_checklist("[ ] not a checklist item\n")
        assert p.total == 0


class TestTick:
    def test_check_item(self):
        body = "- [ ] one\n- [ ] two\n- [ ] three\n"
        new_body, p = tick(body, 2, True)
        assert "- [x] two" in new_body
        assert "- [ ] one" in new_body
        assert "- [ ] three" in new_body
        assert (p.done, p.total) == (1, 3)

    def test_uncheck_item(self):
        body = "- [x] one\n- [x] two\n"
        new_body, p = tick(body, 1, False)
        assert new_body.startswith("- [ ] one\n")
        assert (p.done, p.total) == (1, 2)

    def test_preserves_indentation_and_surrounding_text(self):
        body = (
            "intro paragraph\n"
            "\n"
            "  - [ ] indented item\n"
            "trailing line\n"
        )
        new_body, _ = tick(body, 1, True)
        assert "  - [x] indented item" in new_body
        assert new_body.startswith("intro paragraph\n")
        assert new_body.endswith("trailing line\n")

    def test_only_flips_target_line(self):
        body = "- [ ] a\n- [ ] b\n- [ ] c\n"
        new_body, _ = tick(body, 3, True)
        # First two untouched.
        assert new_body.splitlines()[0] == "- [ ] a"
        assert new_body.splitlines()[1] == "- [ ] b"
        assert new_body.splitlines()[2] == "- [x] c"

    def test_index_zero_raises(self):
        with pytest.raises(ValueError, match="out of range"):
            tick("- [ ] x\n", 0, True)

    def test_index_too_large_raises(self):
        with pytest.raises(ValueError, match="out of range"):
            tick("- [ ] x\n", 5, True)

    def test_no_checklist_raises(self):
        with pytest.raises(ValueError, match="no checklist"):
            tick("just prose\n", 1, True)

    def test_checking_already_checked_is_idempotent(self):
        body = "- [x] done already\n"
        new_body, p = tick(body, 1, True)
        assert new_body == body
        assert p.done == 1


class TestTaskToDict:
    def _task(self, body: str) -> Task:
        return Task(id="T-001", title="x", body=body)

    def test_omits_progress_when_no_checklist(self):
        d = task_to_dict(self._task("just prose\n"))
        assert "progress" not in d

    def test_includes_progress_when_checklist_present(self):
        d = task_to_dict(self._task("- [ ] a\n- [x] b\n"))
        assert d["progress"] == {"done": 1, "total": 2, "pct": 50}

    def test_body_excluded_by_default(self):
        d = task_to_dict(self._task("- [ ] a\n"))
        assert "body" not in d

    def test_body_included_when_requested(self):
        d = task_to_dict(self._task("- [ ] a\n"), include_body=True)
        assert d["body"] == "- [ ] a\n"
