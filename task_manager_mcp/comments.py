"""Comment thread inside the task body.

Comments are appended as bullets under a `## Comments` section so they
show up natively when the user opens the task in Obsidian and round-trip
through the same frontmatter parser as the rest of the body. Format:

    ## Comments

    - **2026-05-07 agent**: looked at auth middleware, line 142 is the bug
    - **2026-05-08 me**: also need OAuth coverage
"""

from __future__ import annotations

import re
from dataclasses import dataclass

COMMENTS_HEADING = "## Comments"

# `- **YYYY-MM-DD author**: text` — author is anything non-`*` so handles
# like `cursor`, `alice`, `agent` all match. Multi-line continuations on
# subsequent indented lines aren't parsed; the bullet's first line is the
# canonical comment text.
_COMMENT_RE = re.compile(
    r"^-\s+\*\*(?P<date>\d{4}-\d{2}-\d{2})\s+(?P<author>[^*]+?)\*\*:\s*(?P<text>.*)$"
)


@dataclass
class Comment:
    date: str
    author: str
    text: str

    def to_dict(self) -> dict:
        return {"date": self.date, "author": self.author, "text": self.text}


def parse_comments(body: str) -> list[Comment]:
    """Extract comments from the `## Comments` section.

    Returns [] when the section is absent or empty. Bullets that don't
    match the canonical `- **DATE author**: text` shape are skipped so a
    user editing the section by hand can leave non-comment notes there
    without breaking the parser.
    """
    out: list[Comment] = []
    in_section = False
    for line in (body or "").splitlines():
        stripped = line.strip()
        if stripped.startswith("## "):
            in_section = stripped == COMMENTS_HEADING
            continue
        if not in_section:
            continue
        m = _COMMENT_RE.match(line)
        if m:
            out.append(
                Comment(
                    date=m.group("date"),
                    author=m.group("author").strip(),
                    text=m.group("text").strip(),
                )
            )
    return out


def append_comment(body: str, author: str, text: str, when: str) -> str:
    """Return a new body with a comment appended under `## Comments`.

    Creates the section at the end of the body if it doesn't exist yet.
    Newlines in `text` are flattened to spaces so the bullet stays a
    single line — multi-paragraph notes belong in the body proper.
    """
    flat = " ".join((text or "").split())
    bullet = f"- **{when} {author}**: {flat}"

    base = (body or "").rstrip()
    if COMMENTS_HEADING in base:
        # Append to existing section. Find the section bounds and insert
        # before the next `## ` heading (or at end of file).
        lines = base.splitlines()
        start = next(
            i for i, line in enumerate(lines) if line.strip() == COMMENTS_HEADING
        )
        end = len(lines)
        for i in range(start + 1, len(lines)):
            if lines[i].lstrip().startswith("## "):
                end = i
                break
        # Trim trailing blank lines inside the section before appending.
        insert_at = end
        while insert_at > start + 1 and not lines[insert_at - 1].strip():
            insert_at -= 1
        lines.insert(insert_at, bullet)
        return "\n".join(lines) + "\n"

    # Fresh section. Mirror block_task / complete_task: blank line, heading,
    # blank line, bullet, trailing newline.
    prefix = base + "\n\n" if base else ""
    return f"{prefix}{COMMENTS_HEADING}\n\n{bullet}\n"


__all__ = ["Comment", "COMMENTS_HEADING", "append_comment", "parse_comments"]
