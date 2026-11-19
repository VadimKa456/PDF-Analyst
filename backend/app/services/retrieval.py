"""Гибридный поиск по документам: SQLite FTS5 + опциональные embeddings."""
from __future__ import annotations

import json
import logging
import math
import re
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from ..models import Chunk, Document
from ..utils import clean_text, short_snippet, snippet_around, stem, tokenize
from .ai_client import AIError, AIClient

logger = logging.getLogger(__name__)


@dataclass
class SearchHit:
    chunk_id: int
    document_id: int
    document_name: str
    page: int
    text: str
    snippet: str
    heading: str = ""
    score: float = 0.0


def index_chunks(db: Session, document: Document, chunks: list[tuple[int, int, str, str]]) -> None:
    """chunks: [(page_number, chunk_index, text, heading)]"""
    db.execute(text("DELETE FROM chunk_fts WHERE document_id = :did"), {"did": document.id})
    for page_number, chunk_index, chunk_text, heading in chunks:
        chunk = Chunk(
            document_id=document.id,
            page_number=page_number,
            chunk_index=chunk_index,
            text=chunk_text,
            heading=heading,
        )
        db.add(chunk)
        db.flush()
        db.execute(
            text(
                "INSERT INTO chunk_fts(chunk_id, document_id, page_number, project_id, text) "
                "VALUES (:cid, :did, :page, :pid, :txt)"
            ),
            {
                "cid": chunk.id,
                "did": document.id,
                "page": page_number,
                "pid": document.project_id,
                "txt": chunk_text,
            },
        )


def remove_document_index(db: Session, document_id: int) -> None:
    db.execute(text("DELETE FROM chunk_fts WHERE document_id = :did"), {"did": document_id})


def _fts_query(query: str) -> str:
    tokens = tokenize(query)
    if not tokens:
        tokens = [w for w in re.findall(r"[a-zа-я0-9]+", (query or "").lower()) if len(w) > 1]
    exprs: list[str] = []
    seen: set[str] = set()
    for token in tokens[:16]:
        variants = {token}
        if len(token) > 4:
            variants.add(stem(token))
        for v in variants:
            if v and v not in seen:
                seen.add(v)
                exprs.append(f"{v}*")
    return " OR ".join(exprs)


def _like_fallback(
    db: Session,
    project_id: int,
    query: str,
    doc_ids: list[int] | None,
    limit: int,
) -> list[SearchHit]:
    tokens = tokenize(query)[:8]
    if not tokens:
        return []
    conditions = []
    params: dict[str, Any] = {"pid": project_id, "limit": limit}
    for i, token in enumerate(tokens):
        conditions.append(f"LOWER(c.text) LIKE :t{i}")
        params[f"t{i}"] = f"%{token.lower()}%"
    doc_filter = ""
    if doc_ids:
        doc_filter = " AND c.document_id IN :doc_ids"
    sql = (
        "SELECT c.id, c.document_id, c.page_number, c.text, c.heading, d.original_name "
        "FROM chunks c JOIN documents d ON d.id = c.document_id "
        "WHERE d.project_id = :pid AND d.status = 'ready' "
        + (" AND (" + " OR ".join(conditions) + ")" if conditions else "")
        + doc_filter
        + " LIMIT :limit"
    )
    if doc_ids:
        sql = sql.replace("IN :doc_ids", "IN (" + ",".join(str(int(x)) for x in doc_ids) + ")")
    rows = db.execute(text(sql), params).mappings().all()
    hits = []
    for row in rows:
        snippet = _make_snippet(row["text"], tokens)
        hits.append(
            SearchHit(
                chunk_id=row["id"],
                document_id=row["document_id"],
                document_name=row["original_name"],
                page=row["page_number"],
                text=row["text"],
                snippet=snippet,
                heading=row["heading"] or "",
                score=0.3,
            )
        )
    return hits


def _make_snippet(text_value: str, tokens: list[str]) -> str:
    low = (text_value or "").lower()
    best = -1
    for token in tokens:
        idx = low.find(token.lower())
        if idx >= 0:
            best = idx
            break
    if best >= 0:
        return snippet_around(text_value, best, best + max(1, len(tokens[0])), 220)
    return short_snippet(text_value, 300)


def lexical_search(
    db: Session,
    project_id: int,
    query: str,
    doc_ids: list[int] | None = None,
    limit: int = 8,
) -> list[SearchHit]:
    fts_q = _fts_query(query)
    if not fts_q:
        return []
    doc_filter = ""
    params: dict[str, Any] = {"q": fts_q, "pid": project_id, "limit": limit}
    if doc_ids:
        doc_filter = " AND f.project_id = :pid AND f.document_id IN (" + ",".join(
            str(int(x)) for x in doc_ids
        ) + ")"
    else:
        doc_filter = " AND f.project_id = :pid"
    sql = (
        "SELECT f.chunk_id, f.document_id, f.page_number, f.text, "
        "bm25(chunk_fts) AS rank, d.original_name, c.heading "
        "FROM chunk_fts f "
        "JOIN documents d ON d.id = f.document_id "
        "LEFT JOIN chunks c ON c.id = f.chunk_id "
        "WHERE chunk_fts MATCH :q AND d.status = 'ready'"
        + doc_filter
        + " ORDER BY rank LIMIT :limit"
    )
    try:
        rows = db.execute(text(sql), params).mappings().all()
    except Exception as exc:  # noqa: BLE001
        logger.warning("FTS query failed, falling back to LIKE: %s", exc)
        return _like_fallback(db, project_id, query, doc_ids, limit)
    if not rows:
        return _like_fallback(db, project_id, query, doc_ids, limit)
    ranks = [abs(float(r["rank"])) for r in rows]
    max_rank = max(ranks) if ranks else 1.0
    tokens = tokenize(query)
    hits = []
    for row, rank in zip(rows, ranks):
        score = 1.0 - (rank / (max_rank + 1e-9)) if max_rank else 0.5
        hits.append(
            SearchHit(
                chunk_id=row["chunk_id"],
                document_id=row["document_id"],
                document_name=row["original_name"],
                page=row["page_number"],
                text=row["text"],
                snippet=_make_snippet(row["text"], tokens),
                heading=row["heading"] or "",
                score=round(max(0.05, score), 4),
            )
        )
    return hits


def _cosine(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


def semantic_search(
    db: Session,
    project_id: int,
    query: str,
    client: AIClient,
    doc_ids: list[int] | None = None,
    limit: int = 8,
    max_chunks: int = 400,
) -> tuple[list[SearchHit], str | None]:
    if not client.available:
        return [], "Семантический поиск недоступен: AI-провайдер не настроен."
    q = (
        db.query(Chunk)
        .join(Document, Document.id == Chunk.document_id)
        .filter(Document.project_id == project_id, Document.status == "ready")
    )
    if doc_ids:
        q = q.filter(Chunk.document_id.in_(doc_ids))
    chunks = q.order_by(Chunk.id.desc()).limit(max_chunks).all()
    if not chunks:
        return [], None
    warning = None
    try:
        missing = [c for c in chunks if not c.embedding]
        for i in range(0, len(missing), 32):
            batch = missing[i: i + 32]
            vectors = client.embed([c.text[:4000] for c in batch])
            for chunk, vec in zip(batch, vectors):
                chunk.embedding = vec
        db.commit()
        qvec = client.embed([query])[0]
    except AIError as exc:
        db.rollback()
        return [], f"Семантический поиск недоступен: {exc}"
    scored: list[tuple[float, Chunk]] = []
    for c in chunks:
        if c.embedding:
            scored.append((_cosine(qvec, c.embedding), c))
    scored.sort(key=lambda x: x[0], reverse=True)
    doc_names = {
        d.id: d.original_name
        for d in db.query(Document).filter(Document.project_id == project_id).all()
    }
    hits = []
    tokens = tokenize(query)
    for score, c in scored[:limit]:
        hits.append(
            SearchHit(
                chunk_id=c.id,
                document_id=c.document_id,
                document_name=doc_names.get(c.document_id, ""),
                page=c.page_number,
                text=c.text,
                snippet=_make_snippet(c.text, tokens),
                heading=c.heading or "",
                score=round(max(0.0, min(1.0, score)), 4),
            )
        )
    return hits, warning


def hybrid_search(
    db: Session,
    project_id: int,
    query: str,
    doc_ids: list[int] | None = None,
    limit: int = 8,
    client: AIClient | None = None,
    semantic_enabled: bool = False,
) -> tuple[list[SearchHit], list[str]]:
    warnings: list[str] = []
    lexical = lexical_search(db, project_id, query, doc_ids, limit=max(limit, 12))
    if not semantic_enabled or client is None:
        return lexical[:limit], warnings
    semantic, warn = semantic_search(db, project_id, query, client, doc_ids, limit=max(limit, 12))
    if warn:
        warnings.append(warn)
        return lexical[:limit], warnings
    combined: dict[int, SearchHit] = {}
    for hit in lexical:
        hit.score = hit.score * 0.45
        combined[hit.chunk_id] = hit
    for hit in semantic:
        if hit.chunk_id in combined:
            combined[hit.chunk_id].score += hit.score * 0.55
        else:
            hit.score = hit.score * 0.55
            combined[hit.chunk_id] = hit
    result = sorted(combined.values(), key=lambda h: h.score, reverse=True)
    if not result:
        result = lexical
    return result[:limit], warnings


def chunk_embedding_status(db: Session, project_id: int) -> dict[str, int]:
    total = (
        db.query(Chunk)
        .join(Document, Document.id == Chunk.document_id)
        .filter(Document.project_id == project_id)
        .count()
    )
    with_emb = (
        db.query(Chunk)
        .join(Document, Document.id == Chunk.document_id)
        .filter(Document.project_id == project_id, Chunk.embedding.isnot(None))
        .count()
    )
    return {"total": total, "embedded": with_emb}
