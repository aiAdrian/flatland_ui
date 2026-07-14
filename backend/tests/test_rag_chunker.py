"""Markdown chunking: heading sections, breadcrumbs, fences, size limits."""
from app.rag.chunker import MAX_CHARS, chunk_markdown

DOC = """Intro paragraph long enough to survive the minimum-size filter easily.

# Setup

## Install

Install the thing with the package manager and then configure it properly.

## Troubleshoot

If the server does not respond, restart it and check the logs for errors.

# Usage

Run the command and watch the output scroll by until it finishes cleanly.
"""


def test_splits_by_heading_with_breadcrumbs():
    chunks = chunk_markdown(DOC, "docs/guide.md")
    breadcrumbs = [c.heading for c in chunks]
    assert breadcrumbs == ["", "Setup › Install", "Setup › Troubleshoot", "Usage"]
    # The breadcrumb prefixes the indexed text, so retrieval sees the context.
    assert chunks[1].text.startswith("docs/guide.md › Setup › Install")
    assert all(c.source == "docs/guide.md" for c in chunks)


def test_heading_inside_code_fence_is_not_a_heading():
    doc = (
        "# Real\n\nBody text that is long enough to be kept as a chunk here.\n\n"
        "```bash\n# not a heading, just a comment\necho hi\n```\n"
    )
    chunks = chunk_markdown(doc, "a.md")
    assert len(chunks) == 1
    assert "# not a heading" in chunks[0].text


def test_long_sections_are_split_and_keep_their_breadcrumb():
    paragraphs = "\n\n".join(f"Paragraph {i} " + "x" * 200 for i in range(20))
    chunks = chunk_markdown(f"# Big\n\n{paragraphs}", "a.md")
    assert len(chunks) > 1
    assert all(c.heading == "Big" for c in chunks)
    assert all(len(c.text) <= MAX_CHARS + len("a.md › Big\n\n") for c in chunks)


def test_crumbs_are_dropped():
    # A heading with nothing but a link under it carries no answerable content.
    chunks = chunk_markdown("# See also\n\n[link](x.md)\n", "a.md")
    assert chunks == []
