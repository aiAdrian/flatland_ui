"""Hybrid retrieval over a hand-built index. Hermetic: the embedder is a fake
that maps keywords onto fixed axes, so cosine ranking is deterministic."""
import numpy as np

from app.rag.chunker import Chunk
from app.rag.embeddings import EmbeddingsUnavailable
from app.rag.index import DocsIndex

CHUNKS = [
    Chunk(
        source="docs/overrides.md",
        heading="Overrides",
        text="docs/overrides.md › Overrides\n\nUse setOverride to pin an action at a decision cell.",
    ),
    Chunk(
        source="docs/delays.md",
        heading="Delays",
        text="docs/delays.md › Delays\n\nA train pauses at a station when its schedule says so.",
    ),
    Chunk(
        source="docs/map.md",
        heading="Map",
        text="docs/map.md › Map\n\nThe track layout shows the rail network and the agents on it.",
    ),
]

#: axis per topic; "wait" only maps onto the delay axis via the embedder, not
#: via keywords — that asymmetry is what the paraphrase test relies on
_AXES = {"override": 0, "setoverride": 0, "wait": 1, "pauses": 1, "delay": 1, "map": 2, "layout": 2}


class FakeEmbedder:
    async def embed(self, texts):
        vectors = []
        for text in texts:
            v = np.zeros(3, dtype=np.float32)
            for word, axis in _AXES.items():
                if word in text.lower():
                    v[axis] += 1.0
            norm = np.linalg.norm(v)
            vectors.append(v / norm if norm else v)
        return np.asarray(vectors, dtype=np.float32)


class DeadEmbedder:
    async def embed(self, texts):
        raise EmbeddingsUnavailable("down")


async def _index(chunks=CHUNKS, *, embedder=None, embedded=True):
    vectors = await FakeEmbedder().embed([c.text for c in chunks]) if embedded else None
    return DocsIndex(
        chunks=chunks,
        vectors=vectors,
        embedder=embedder or FakeEmbedder(),
        fingerprint="test",
        files=len({c.source for c in chunks}),
    )


async def test_exact_identifier_is_found_by_keyword_search():
    # "setOverride" never appears in a paraphrased form — BM25 must catch it.
    index = await _index()
    top = await index.retrieve("what does setOverride do", 1)
    assert top[0].source == "docs/overrides.md"


async def test_paraphrase_is_found_by_embeddings():
    # "wait" appears nowhere in the delay chunk ("pauses"), so BM25 misses it;
    # only the embedding side can rank it first.
    index = await _index()
    top = await index.retrieve("wait", 1)
    assert top[0].source == "docs/delays.md"


async def test_no_vectors_degrades_to_keyword_only():
    index = await _index(embedded=False)
    assert index.embeddings_available is False
    top = await index.retrieve("setOverride decision cell", 1)
    assert top[0].source == "docs/overrides.md"


async def test_dead_embedder_at_query_time_still_answers():
    index = await _index(embedder=DeadEmbedder())
    top = await index.retrieve("setOverride", 1)
    assert top[0].source == "docs/overrides.md"


async def test_query_syntax_cannot_break_fts():
    # Bare AND/OR/NEAR, quotes and slashes are FTS5 operators if unquoted.
    index = await _index()
    for query in ['what is "NEAR" the /llm/chat endpoint?', "a AND OR NOT b*", "???", ""]:
        await index.retrieve(query, 2)  # must not raise


async def test_rrf_prefers_the_chunk_both_rankings_agree_on():
    # keyword hit on "setOverride" + embedding hit on the override axis
    index = await _index()
    top = await index.retrieve("setOverride override", 3)
    assert top[0].source == "docs/overrides.md"


async def test_follow_up_inherits_its_topic_from_the_context():
    # The question alone matches nothing; only the history names the topic.
    index = await _index()
    top = await index.retrieve("how do I do that?", 1, context="use setOverride at a decision cell")
    assert top[0].source == "docs/overrides.md"


async def test_a_topic_change_beats_the_context():
    # The question is weighted double, so stale history cannot hold it back.
    index = await _index()
    top = await index.retrieve("show the map layout", 1, context="use setOverride at a decision cell")
    assert top[0].source == "docs/map.md"


async def test_one_file_cannot_flood_the_answer():
    # Five chunks of one file all match; the cap must let another file through.
    flood = [
        Chunk(source="docs/big.md", heading=f"S{i}", text=f"docs/big.md › S{i}\n\noverride override override {i}")
        for i in range(5)
    ] + [
        Chunk(source="docs/other.md", heading="O", text="docs/other.md › O\n\noverride mentioned once here")
    ]
    index = await _index(flood)

    top = await index.retrieve("override", 3)
    assert sum(s.source == "docs/big.md" for s in top) == 2
    assert any(s.source == "docs/other.md" for s in top)

    # ...but when the cap would leave slots empty, they are filled back up.
    assert len(await index.retrieve("override", 5)) == 5
