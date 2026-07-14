"""Hybrid docs index: BM25 (SQLite FTS5, stdlib) + exact cosine (numpy).

Keyword and embedding rankings are merged with reciprocal-rank fusion: exact
identifiers ("Marey", "setOverride") favour the former, paraphrases the latter.

Lifecycle: built lazily on the first question, persisted under
`backend/.rag-index/`, and staleness-checked per request by stat-ing the corpus.
Editing one doc re-embeds only its changed chunks. If the embedding endpoint is
unreachable the index degrades to keyword-only rather than failing.

Design rationale: docs/reference/llm-setup.md § Design decisions.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import numpy as np

from app.config import Settings
from app.rag.chunker import Chunk, chunk_markdown
from app.rag.embeddings import Embedder, EmbeddingsUnavailable

logger = logging.getLogger(__name__)

#: standard reciprocal-rank-fusion constant
_RRF_K = 60
#: max snippets from any one source file per answer, so a single file cannot
#: fill the whole context budget
_PER_SOURCE_CAP = 2
#: weight of the conversation history relative to the question itself
_CONTEXT_WEIGHT = 0.5
#: bump to force a rebuild when the chunking logic changes
_CHUNKER_VERSION = 1

_REPO_ROOT = Path(__file__).resolve().parents[3]
_INDEX_DIR = Path(__file__).resolve().parents[2] / ".rag-index"


@dataclass(frozen=True)
class Snippet:
    source: str
    heading: str
    text: str

    @property
    def label(self) -> str:
        return f"{self.source} › {self.heading}" if self.heading else self.source


class DocsIndex:
    """Immutable snapshot of the indexed corpus."""

    def __init__(
        self,
        *,
        chunks: list[Chunk],
        vectors: np.ndarray | None,
        embedder: Embedder,
        fingerprint: str,
        files: int,
    ) -> None:
        self.chunks = chunks
        #: unit rows aligned with `chunks`; None → keyword-only retrieval
        self.vectors = vectors
        self.fingerprint = fingerprint
        self.files = files
        self._embedder = embedder
        self._fts = _build_fts(chunks)

    @property
    def embeddings_available(self) -> bool:
        return self.vectors is not None

    async def retrieve(self, query: str, k: int, *, context: str | None = None) -> list[Snippet]:
        """The k most relevant chunks for `query`.

        `context` (the recent conversation) joins the ranking at `_CONTEXT_WEIGHT`,
        so a follow-up such as "how do I do that?" inherits its topic from the
        history while the question itself still outweighs it. Each ranking is a
        list of chunk indices, best first; they are fused (`_fuse`) and then
        diversified (`_cap_per_source`).
        """
        # Wider than k: the per-source cap needs runners-up to promote when one
        # file dominates the head of every ranking.
        pool = 4 * k
        rankings: list[tuple[list[int], float]] = [(self._bm25_ranks(query, limit=pool), 1.0)]
        if context:
            rankings.append((self._bm25_ranks(context, limit=pool), _CONTEXT_WEIGHT))

        # One batch call for both — the embedder round-trip is the expensive part.
        vectors = await self._embed_queries([query] + ([context] if context else []))
        if vectors is not None:
            rankings.append((self._cosine_ranks(vectors[0], limit=pool), 1.0))
            if context:
                rankings.append((self._cosine_ranks(vectors[1], limit=pool), _CONTEXT_WEIGHT))

        picked = self._cap_per_source(_fuse(rankings), k)
        return [Snippet(source=c.source, heading=c.heading, text=c.text) for c in (self.chunks[i] for i in picked)]

    def _cap_per_source(self, ranked: list[int], k: int) -> list[int]:
        """Top k, but at most `_PER_SOURCE_CAP` chunks from any one file.
        Slots the cap would leave empty are filled back up in rank order."""
        picked: list[int] = []
        taken: dict[str, int] = {}
        for idx in ranked:
            source = self.chunks[idx].source
            if taken.get(source, 0) >= _PER_SOURCE_CAP:
                continue
            taken[source] = taken.get(source, 0) + 1
            picked.append(idx)
            if len(picked) == k:
                return picked
        return picked + [i for i in ranked if i not in picked][: k - len(picked)]

    def _bm25_ranks(self, query: str, *, limit: int) -> list[int]:
        # Quote each token so FTS5 never parses user text as query syntax
        # (bare AND/OR/NEAR/"-" would otherwise be operators).
        tokens = re.findall(r"[A-Za-z0-9_]+", query)
        if not tokens:
            return []
        match = " OR ".join(f'"{t}"' for t in tokens)
        rows = self._fts.execute(
            "SELECT rowid FROM chunks WHERE chunks MATCH ? ORDER BY bm25(chunks) LIMIT ?",
            (match, limit),
        ).fetchall()
        return [row[0] for row in rows]

    async def _embed_queries(self, texts: list[str]) -> np.ndarray | None:
        """One batch call for question + context. None → keyword-only ranking."""
        if self.vectors is None:
            return None
        try:
            return await self._embedder.embed(texts)
        except EmbeddingsUnavailable as exc:
            logger.warning("query embedding failed (%s) — keyword-only for this question", exc)
            return None

    def _cosine_ranks(self, q: np.ndarray, *, limit: int) -> list[int]:
        scores = self.vectors @ q
        top = np.argsort(scores)[::-1][:limit]
        return [int(i) for i in top]


def _fuse(rankings: list[tuple[list[int], float]]) -> list[int]:
    """Reciprocal-rank fusion: merge weighted rankings into one, best first.

    Each ranking votes for a chunk with `weight / (_RRF_K + rank)`. Fusing on
    *rank* rather than score is what allows BM25 and cosine, whose scores are on
    unrelated scales, to be combined at all.
    """
    scores: dict[int, float] = {}
    for indices, weight in rankings:
        for rank, idx in enumerate(indices):
            scores[idx] = scores.get(idx, 0.0) + weight / (_RRF_K + rank)
    return sorted(scores, key=lambda idx: scores[idx], reverse=True)


def _build_fts(chunks: list[Chunk]) -> sqlite3.Connection:
    # In-memory and rebuilt at load: persisting it would mean keeping a second
    # storage format in sync with the chunks.
    conn = sqlite3.connect(":memory:", check_same_thread=False)
    conn.execute("CREATE VIRTUAL TABLE chunks USING fts5(text)")
    conn.executemany(
        "INSERT INTO chunks(rowid, text) VALUES (?, ?)",
        ((i, c.text) for i, c in enumerate(chunks)),
    )
    conn.commit()
    return conn


# --------------------------------------------------------------- corpus + build

def _discover(cfg: Settings) -> list[Path]:
    archive = _REPO_ROOT / "docs" / "archive"  # unmaintained by definition — never indexed
    files: list[Path] = []
    for entry in (e.strip() for e in cfg.rag_docs.split(",") if e.strip()):
        path = _REPO_ROOT / entry
        if path.is_file():
            files.append(path)
        elif path.is_dir():
            files.extend(p for p in sorted(path.rglob("*.md")) if archive not in p.parents)
    return files


def _fingerprint(cfg: Settings, files: Iterable[Path]) -> str:
    h = hashlib.sha256(f"{_CHUNKER_VERSION}|{cfg.rag_embed_model}|{cfg.rag_docs}".encode())
    for path in files:
        stat = path.stat()
        h.update(f"{path.relative_to(_REPO_ROOT)}|{stat.st_mtime_ns}|{stat.st_size}".encode())
    return h.hexdigest()


def _chunk_hash(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def _load_persisted(cfg: Settings) -> tuple[dict, np.ndarray] | None:
    """The snapshot on disk, or None if there is none or it cannot be trusted.
    Vectors from a different embedding model are meaningless, so a model change
    counts as a miss."""
    meta_path = _INDEX_DIR / "index.json"
    if not meta_path.exists():
        return None
    try:
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        if meta.get("embed_model") != cfg.rag_embed_model:
            return None
        vectors = np.load(_INDEX_DIR / "vectors.npy")
        if len(vectors) != len(meta["chunks"]):
            return None
        return meta, vectors
    except Exception:  # noqa: BLE001 — a corrupt cache is a cache miss, not an error
        logger.warning("unreadable %s — rebuilding the docs index", _INDEX_DIR)
        return None


def _persist(cfg: Settings, *, fingerprint: str, chunks: list[Chunk], vectors: np.ndarray) -> None:
    """Snapshot the index so the next process start is instant.

    Callers must pass real vectors: a cached keyword-only build would pin the
    index in its degraded state until someone edited a doc.
    """
    try:
        _INDEX_DIR.mkdir(parents=True, exist_ok=True)
        np.save(_INDEX_DIR / "vectors.npy", vectors)
        meta = {
            "fingerprint": fingerprint,
            "embed_model": cfg.rag_embed_model,
            "chunks": [{"source": c.source, "heading": c.heading, "text": c.text} for c in chunks],
        }
        (_INDEX_DIR / "index.json").write_text(json.dumps(meta), encoding="utf-8")
    except OSError as exc:
        logger.warning("could not persist docs index to %s: %s", _INDEX_DIR, exc)


async def _build(cfg: Settings, fingerprint: str, files: list[Path]) -> DocsIndex:
    embedder = Embedder(model=cfg.rag_embed_model, base_url=cfg.rag_embed_base_url, timeout_s=cfg.llm_timeout_s)
    persisted = _load_persisted(cfg)

    # Nothing changed since the snapshot: load it and skip the embedder entirely.
    if persisted and persisted[0]["fingerprint"] == fingerprint:
        meta, vectors = persisted
        chunks = [Chunk(**c) for c in meta["chunks"]]
        return DocsIndex(chunks=chunks, vectors=vectors, embedder=embedder, fingerprint=fingerprint, files=len(files))

    chunks = [
        chunk
        for path in files
        for chunk in chunk_markdown(path.read_text(encoding="utf-8"), str(path.relative_to(_REPO_ROOT)))
    ]
    vectors = await _embed_chunks(chunks, embedder, previous=persisted)

    if vectors is not None:
        _persist(cfg, fingerprint=fingerprint, chunks=chunks, vectors=vectors)
    logger.info(
        "docs index: %d chunks from %d files (embeddings: %s)",
        len(chunks), len(files), "yes" if vectors is not None else "no",
    )
    return DocsIndex(chunks=chunks, vectors=vectors, embedder=embedder, fingerprint=fingerprint, files=len(files))


async def _embed_chunks(
    chunks: list[Chunk],
    embedder: Embedder,
    *,
    previous: tuple[dict, np.ndarray] | None,
) -> np.ndarray | None:
    """Vectors for every chunk, reusing the previous snapshot's vector for any
    chunk whose text is byte-identical, so editing one doc re-embeds that doc's
    chunks rather than the whole corpus. None when the embedder is unreachable,
    which the caller turns into keyword-only retrieval."""
    if not chunks:
        return None

    cached: dict[str, np.ndarray] = {}
    if previous:
        old_meta, old_vectors = previous
        cached = {_chunk_hash(old["text"]): vector for old, vector in zip(old_meta["chunks"], old_vectors)}

    hashes = [_chunk_hash(c.text) for c in chunks]
    missing = [i for i, h in enumerate(hashes) if h not in cached]
    try:
        if missing:
            fresh = await embedder.embed([chunks[i].text for i in missing])
            for i, vector in zip(missing, fresh):
                cached[hashes[i]] = vector
    except EmbeddingsUnavailable as exc:
        logger.warning("%s — docs index degrades to keyword-only retrieval", exc)
        return None
    return np.stack([cached[h] for h in hashes])


# ------------------------------------------------------------- module accessor

_current: DocsIndex | None = None
_lock = asyncio.Lock()
#: monotonic deadline before a keyword-only index retries its build, so an
#: unreachable embedder costs at most one rebuild attempt per minute
_retry_at = 0.0


async def docs_index(cfg: Settings) -> DocsIndex | None:
    """The current index, (re)built if the docs changed. None when RAG is off."""
    global _current, _retry_at
    if not cfg.rag_enabled:
        return None
    files = _discover(cfg)
    fingerprint = _fingerprint(cfg, files)

    def usable(index: DocsIndex | None) -> bool:
        if index is None or index.fingerprint != fingerprint:
            return False
        return index.embeddings_available or asyncio.get_running_loop().time() < _retry_at

    if usable(_current):
        return _current
    async with _lock:
        if not usable(_current):
            _current = await _build(cfg, fingerprint, files)
            _retry_at = asyncio.get_running_loop().time() + 60.0
    return _current
