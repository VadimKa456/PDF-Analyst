from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Analysis, Project
from ..schemas import QueryRequest
from ..services import query_engine

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["analysis"])


def analysis_meta(a: Analysis) -> dict[str, Any]:
    return {
        "id": a.id,
        "project_id": a.project_id,
        "title": a.title,
        "query": a.query,
        "intent": a.intent,
        "answer_preview": (a.answer or "")[:400],
        "model": a.model,
        "duration_ms": a.duration_ms,
        "saved": a.saved,
        "error": a.error,
        "created_at": a.created_at.isoformat() if a.created_at else None,
        "documents": a.documents or [],
        "document_count": len(a.documents or []),
        "charts_count": len(a.charts or []),
        "sources_count": len(a.sources or []),
    }


@router.post("/analyses")
def create_analysis(body: QueryRequest, db: Session = Depends(get_db)):
    project = db.get(Project, body.project_id)
    if not project:
        raise HTTPException(404, "Проект не найден")
    query = body.query.strip()
    if not query:
        raise HTTPException(422, "Пустой запрос")
    if len(query) > 4000:
        raise HTTPException(422, "Запрос слишком длинный (максимум 4000 символов)")
    try:
        result, _plan = query_engine.analyze(
            db,
            project,
            query,
            document_ids=body.document_ids,
            metric_labels=body.metric_labels,
            options=body.options,
        )
        analysis = query_engine.save_analysis(db, project.id, query, result)
        result["id"] = analysis.id
        result["title"] = analysis.title
        result["created_at"] = analysis.created_at.isoformat() if analysis.created_at else None
        result["project_id"] = project.id
        return result
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        logger.exception("Analysis failed")
        raise HTTPException(500, f"Ошибка анализа: {exc}") from exc


@router.get("/analyses")
def list_analyses(
    project_id: int,
    saved_only: bool = False,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    q = db.query(Analysis).filter(Analysis.project_id == project_id)
    if saved_only:
        q = q.filter(Analysis.saved.is_(True))
    total = q.count()
    rows = q.order_by(Analysis.created_at.desc(), Analysis.id.desc()).offset(offset).limit(limit).all()
    return {"total": total, "items": [analysis_meta(a) for a in rows]}


@router.get("/analyses/{analysis_id}")
def get_analysis(analysis_id: int, db: Session = Depends(get_db)):
    a = db.get(Analysis, analysis_id)
    if not a:
        raise HTTPException(404, "Анализ не найден")
    result = dict(a.result or {})
    result.setdefault("id", a.id)
    result.setdefault("title", a.title)
    result.setdefault("query", a.query)
    result.setdefault("answer", a.answer)
    result.setdefault("intent", a.intent)
    result.setdefault("charts", a.charts or [])
    result.setdefault("citations", a.sources or [])
    result.setdefault("documents", a.documents or [])
    result["created_at"] = a.created_at.isoformat() if a.created_at else None
    result["saved"] = a.saved
    result["project_id"] = a.project_id
    return result


@router.put("/analyses/{analysis_id}/saved")
def set_saved(analysis_id: int, saved: bool = True, db: Session = Depends(get_db)):
    a = db.get(Analysis, analysis_id)
    if not a:
        raise HTTPException(404, "Анализ не найден")
    a.saved = saved
    db.commit()
    return analysis_meta(a)


@router.delete("/analyses/{analysis_id}")
def delete_analysis(analysis_id: int, db: Session = Depends(get_db)):
    a = db.get(Analysis, analysis_id)
    if not a:
        raise HTTPException(404, "Анализ не найден")
    db.delete(a)
    db.commit()
    return {"ok": True}


@router.post("/analyses/{analysis_id}/rerun")
def rerun_analysis(analysis_id: int, db: Session = Depends(get_db)):
    a = db.get(Analysis, analysis_id)
    if not a:
        raise HTTPException(404, "Анализ не найден")
    project = db.get(Project, a.project_id)
    if not project:
        raise HTTPException(404, "Проект не найден")
    doc_ids = [d.get("id") for d in (a.documents or []) if isinstance(d, dict) and d.get("id")]
    try:
        result, _ = query_engine.analyze(db, project, a.query, document_ids=doc_ids or None)
        new_a = query_engine.save_analysis(db, project.id, a.query, result)
        result["id"] = new_a.id
        result["title"] = new_a.title
        result["created_at"] = new_a.created_at.isoformat() if new_a.created_at else None
        result["project_id"] = project.id
        return result
    except Exception as exc:  # noqa: BLE001
        logger.exception("Analysis rerun failed")
        raise HTTPException(500, f"Ошибка анализа: {exc}") from exc
