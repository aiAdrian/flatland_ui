"""Markdown → retrieval chunks.

One chunk per heading section, prefixed with its breadcrumb
("docs/reference/llm-setup.md › Part 1 › Troubleshooting") so both the embedder
and the keyword index see where a snippet lives. Sections longer than a small
model comfortably reads alongside three others are split on paragraph
boundaries; a `#` inside a code fence is not a heading.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

#: ~400 tokens — several of these must fit a question's context budget together
MAX_CHARS = 1600
#: below this a section is a crumb (a bare link, an empty heading) — dropped
MIN_CHARS = 40

_HEADING = re.compile(r"^(#{1,6})\s+(.+?)\s*#*\s*$")
_FENCE = re.compile(r"^\s*(```|~~~)")


@dataclass(frozen=True)
class Chunk:
    #: repo-relative path, e.g. "docs/reference/llm-setup.md"
    source: str
    #: heading breadcrumb ("Part 1 › Troubleshooting"); "" for the preamble
    heading: str
    #: what gets embedded and indexed: "<source> › <breadcrumb>\n\n<body>"
    text: str


def chunk_markdown(text: str, source: str) -> list[Chunk]:
    chunks: list[Chunk] = []
    for breadcrumb, body in _split_by_heading(text):
        body = body.strip()
        if len(body) < MIN_CHARS:
            continue
        label = f"{source} › {breadcrumb}" if breadcrumb else source
        for part in _split_long(body):
            chunks.append(Chunk(source=source, heading=breadcrumb, text=f"{label}\n\n{part}"))
    return chunks


def _split_by_heading(text: str) -> list[tuple[str, str]]:
    sections: list[tuple[str, str]] = []
    #: (level, title) of every heading on the path to the current section
    stack: list[tuple[int, str]] = []
    body: list[str] = []
    in_fence = False

    def close() -> None:
        sections.append((" › ".join(title for _, title in stack), "\n".join(body)))

    for line in text.splitlines():
        if _FENCE.match(line):
            in_fence = not in_fence
        match = None if in_fence else _HEADING.match(line)
        if not match:
            body.append(line)
            continue
        close()
        level = len(match.group(1))
        while stack and stack[-1][0] >= level:
            stack.pop()
        stack.append((level, match.group(2)))
        body = []
    close()
    return sections


def _split_long(body: str) -> list[str]:
    if len(body) <= MAX_CHARS:
        return [body]
    parts: list[str] = []
    current = ""
    for paragraph in body.split("\n\n"):
        while len(paragraph) > MAX_CHARS:  # a single oversized block: hard split
            parts.append(paragraph[:MAX_CHARS])
            paragraph = paragraph[MAX_CHARS:]
        if current and len(current) + len(paragraph) + 2 > MAX_CHARS:
            parts.append(current)
            current = paragraph
        else:
            current = f"{current}\n\n{paragraph}" if current else paragraph
    if current:
        parts.append(current)
    return [p for p in parts if p.strip()]
