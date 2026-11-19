from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Document, Metric
from ..services import analytics

router = APIRouter(prefix="/api", tags=["options"])


@router.get("/options")
def options(
    project_id: int,
    document_ids: str | None = Query(None, description="ID документов через запятую"),
    db: Session = Depends(get_db),
):
    doc_ids = None
    if document_ids:
        try:
            doc_ids = [int(x) for x in document_ids.split(",") if x.strip()]
        except ValueError:
            doc_ids = None
    labels = analytics.list_metric_labels(db, project_id, doc_ids)
    docs = analytics.list_documents(db, project_id, doc_ids)
    q = (
        db.query(Metric.period, Metric.unit)
        .join(Document, Document.id == Metric.document_id)
        .filter(Document.project_id == project_id, Document.status == "ready")
    )
    if doc_ids:
        q = q.filter(Metric.document_id.in_(doc_ids))
    periods = sorted({p for p, _ in q.all() if p}, reverse=True)
    units = sorted({u for _, u in q.all() if u})
    return {
        "labels": labels,
        "periods": periods,
        "units": units,
        "documents": [
            {"id": d.id, "name": d.original_name, "pages": d.page_count, "status": d.status}
            for d in docs
        ],
    }
