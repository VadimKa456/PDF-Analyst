from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Project
from ..schemas import CompareRequest
from ..services import builders, query_engine

router = APIRouter(prefix="/api", tags=["compare"])


@router.post("/compare")
def compare(body: CompareRequest, db: Session = Depends(get_db)):
    project = db.get(Project, body.project_id)
    if not project:
        raise HTTPException(404, "Проект не найден")
    try:
        result = builders.compare_documents(
            db, body.project_id, body.document_ids, body.metric_labels, body.years
        )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(500, f"Ошибка сравнения: {exc}") from exc
    docs = (result.get("meta") or {}).get("documents") or []
    result["documents"] = docs
    parts = [
        "Сравнение документов: " + ", ".join(d.get("name", "") for d in docs) + ".",
        f"Сформировано строк сравнения: {sum(t.get('row_count', 0) for t in result.get('tables', []))}.",
    ]
    findings = result.get("findings") or []
    if findings:
        parts.append("Ключевые результаты:")
        parts.extend("• " + str(f.get("text", "")) for f in findings[:12] if isinstance(f, dict))
    if result.get("warnings"):
        parts.append("Предупреждения:")
        parts.extend("• " + str(w) for w in result["warnings"][:6])
    result["answer"] = "\n\n".join(parts)
    result["intent"] = "compare"
    result["query"] = "Сравнение: " + ", ".join(d.get("name", "") for d in docs)
    result.setdefault("meta", {})["engine"] = "local"
    result["meta"]["model"] = "Локальный аналитический движок"
    if body.save:
        analysis = query_engine.save_analysis(db, project.id, result["query"], result)
        result["id"] = analysis.id
        result["title"] = analysis.title
        result["created_at"] = analysis.created_at.isoformat() if analysis.created_at else None
        result["project_id"] = project.id
    return result
