from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..database import get_db
from ..schemas import SearchRequest
from ..services import analytics
from ..services.ai_client import AIClient
from ..services.retrieval import chunk_embedding_status, hybrid_search
from ..services.runtime_settings import get_runtime_settings

router = APIRouter(prefix="/api", tags=["search"])


@router.post("/search")
def search(body: SearchRequest, db: Session = Depends(get_db)):
    runtime = get_runtime_settings(db)
    client = AIClient(runtime)
    hits, warnings = hybrid_search(
        db,
        body.project_id,
        body.query,
        body.document_ids,
        limit=max(1, min(body.limit, 50)),
        client=client,
        semantic_enabled=bool(runtime.get("semantic_search")),
    )
    labels = analytics.list_metric_labels(db, body.project_id, body.document_ids)
    return {
        "query": body.query,
        "hits": [
            {
                "chunk_id": h.chunk_id,
                "document_id": h.document_id,
                "document": h.document_name,
                "page": h.page,
                "snippet": h.snippet,
                "heading": h.heading,
                "score": h.score,
            }
            for h in hits
        ],
        "metric_suggestions": labels[:40],
        "warnings": warnings,
        "semantic": bool(runtime.get("semantic_search") and client.available),
        "embeddings": chunk_embedding_status(db, body.project_id),
    }
