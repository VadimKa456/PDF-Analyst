from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..config import settings
from ..database import get_db
from ..models import Analysis, Chunk, Document, Metric, Page, Project, Table
from ..services.runtime_settings import get_runtime_settings

router = APIRouter(prefix="/api", tags=["dashboard"])


def _empty_dashboard() -> dict[str, Any]:
    return {
        "project": None,
        "stats": {
            "documents": 0,
            "ready": 0,
            "processing": 0,
            "errors": 0,
            "pages": 0,
            "metrics": 0,
            "tables": 0,
            "chunks": 0,
            "analyses": 0,
            "saved_analyses": 0,
            "ocr_pages": 0,
            "ocr_documents": 0,
            "storage_bytes": 0,
            "avg_confidence": 0.0,
        },
        "quality": {
            "score": 0,
            "avg_confidence": 0.0,
            "ocr_documents": 0,
            "text_documents": 0,
            "warnings": [],
            "warnings_count": 0,
            "low_confidence_documents": [],
        },
        "coverage": {
            "documents_with_metrics": 0,
            "documents_with_tables": 0,
            "documents_without_metrics": [],
            "pages_with_text": 0,
            "metrics_by_source": {"text": 0, "table": 0, "other": 0},
            "by_document": [],
        },
        "top_metrics": [],
        "periods": [],
        "latest_values": [],
        "needs_attention": [],
        "recent_analyses": [],
        "recent_documents": [],
        "projects": [],
        "processing": [],
        "capabilities": {
            "ai_provider": None,
            "ai_configured": False,
            "data_dir": str(settings.data_dir),
        },
    }


@router.get("/dashboard")
def dashboard(project_id: int | None = None, db: Session = Depends(get_db)):
    project = (
        db.get(Project, project_id)
        if project_id
        else db.query(Project).order_by(Project.last_opened_at.desc()).first()
    )
    if project is None:
        return _empty_dashboard()

    docs = db.query(Document).filter(Document.project_id == project.id).all()
    doc_ids = [d.id for d in docs]
    pages = sum(d.page_count or 0 for d in docs)
    analyses = db.query(Analysis).filter(Analysis.project_id == project.id)
    recent_analyses = analyses.order_by(Analysis.created_at.desc()).limit(8).all()
    projects = db.query(Project).order_by(Project.last_opened_at.desc()).limit(8).all()
    runtime = get_runtime_settings(db)

    metric_rows: list[Metric] = []
    if doc_ids:
        metric_rows = (
            db.query(Metric)
            .filter(Metric.document_id.in_(doc_ids))
            .order_by(Metric.document_id, Metric.page_number, Metric.id)
            .limit(50000)
            .all()
        )
    chunks = (
        db.query(func.count(Chunk.id)).filter(Chunk.document_id.in_(doc_ids)).scalar() or 0
        if doc_ids
        else 0
    )
    table_count = (
        db.query(func.count(Table.id)).filter(Table.document_id.in_(doc_ids)).scalar() or 0
        if doc_ids
        else 0
    )
    pages_with_text = (
        db.query(func.count(Page.id))
        .filter(Page.document_id.in_(doc_ids), func.length(Page.text) > 0)
        .scalar()
        or 0
        if doc_ids
        else 0
    )

    docs_by_id = {d.id: d for d in docs}
    source_counter = Counter((m.source_kind or "other") for m in metric_rows)
    metrics_by_source = {
        "text": source_counter.get("text", 0),
        "table": source_counter.get("table", 0),
        "other": sum(v for k, v in source_counter.items() if k not in {"text", "table"}),
    }

    # --- Качество распознавания -------------------------------------------
    confident_docs = [d for d in docs if (d.text_chars or 0) > 0 and d.status == "ready"]
    avg_confidence = round(
        sum(d.avg_confidence or 0 for d in confident_docs) / len(confident_docs), 3
    ) if confident_docs else 0.0

    warning_items: list[dict[str, Any]] = []
    for d in docs:
        for w in d.warnings or []:
            warning_items.append({"document_id": d.id, "name": d.original_name, "text": w})

    low_confidence = [
        {
            "id": d.id,
            "name": d.original_name,
            "confidence": round(d.avg_confidence or 0, 3),
            "ocr_pages": d.ocr_pages or 0,
            "pages": d.page_count or 0,
            "warnings": len(d.warnings or []),
        }
        for d in docs
        if d.status == "ready"
        and ((d.ocr_pages or 0) > 0)
        and (d.avg_confidence or 0) < 0.9
    ]
    low_confidence.sort(key=lambda x: x["confidence"])

    ready_docs = [d for d in docs if d.status == "ready"]
    with_metrics = [d for d in ready_docs if (d.metric_count or 0) > 0]
    coverage_ratio = len(with_metrics) / len(ready_docs) if ready_docs else 0.0
    score = round(avg_confidence * 60 + coverage_ratio * 40)
    if warning_items:
        score = max(0, score - min(15, len(warning_items)))
    if docs:
        score = max(0, min(100, score))

    # --- Покрытие по документам -------------------------------------------
    by_document = [
        {
            "id": d.id,
            "name": d.original_name,
            "status": d.status,
            "pages": d.page_count or 0,
            "metrics": d.metric_count or 0,
            "tables": d.table_count or 0,
            "ocr_pages": d.ocr_pages or 0,
            "confidence": round(d.avg_confidence or 0, 3),
            "text_chars": d.text_chars or 0,
            "processing_ms": d.processing_ms or 0,
            "warnings": len(d.warnings or []),
        }
        for d in sorted(docs, key=lambda d: (d.created_at or d.id), reverse=True)
    ]
    without_metrics = [
        {"id": d.id, "name": d.original_name, "status": d.status, "pages": d.page_count or 0}
        for d in docs
        if d.status == "error" or ((d.metric_count or 0) == 0 and d.status == "ready")
    ]

    # --- Топ показателей и периоды ----------------------------------------
    grouped: dict[str, list[Metric]] = defaultdict(list)
    for m in metric_rows:
        key = m.normalized_label or (m.label or "").lower()
        if not key:
            continue
        grouped[key].append(m)

    top_metrics: list[dict[str, Any]] = []
    for key, items in grouped.items():
        doc_count = len({m.document_id for m in items})
        label_counts = Counter((m.label or "").strip() for m in items if m.label)
        unit_counts = Counter(m.unit for m in items if m.unit)
        dated = [m for m in items if m.value is not None]
        dated.sort(key=lambda m: (m.period or "", m.id))
        latest = dated[-1] if dated else None
        top_metrics.append(
            {
                "key": key,
                "label": label_counts.most_common(1)[0][0] if label_counts else key,
                "documents": doc_count,
                "count": len(items),
                "unit": unit_counts.most_common(1)[0][0] if unit_counts else "",
                "periods": sorted({m.period for m in items if m.period}),
                "latest": (
                    {
                        "metric_id": latest.id,
                        "value": latest.value,
                        "unit": latest.unit,
                        "period": latest.period,
                        "document_id": latest.document_id,
                        "document": docs_by_id.get(latest.document_id).original_name
                        if latest.document_id in docs_by_id
                        else "",
                        "page": latest.page_number,
                    }
                    if latest
                    else None
                ),
            }
        )
    top_metrics.sort(key=lambda x: (x["documents"], x["count"]), reverse=True)

    period_counter: Counter[str] = Counter()
    period_docs: dict[str, set[int]] = defaultdict(set)
    for m in metric_rows:
        if not m.period:
            continue
        period_counter[m.period] += 1
        period_docs[m.period].add(m.document_id)
    periods = [
        {"period": period, "metrics": count, "documents": len(period_docs[period])}
        for period, count in sorted(period_counter.items())
    ]

    latest_values = []
    for m in sorted(metric_rows, key=lambda m: (m.period or "", m.id), reverse=True):
        if m.value is None or len(latest_values) >= 10:
            continue
        doc = docs_by_id.get(m.document_id)
        latest_values.append(
            {
                "metric_id": m.id,
                "label": m.label,
                "value": m.value,
                "unit": m.unit,
                "period": m.period,
                "document_id": m.document_id,
                "document": doc.original_name if doc else "",
                "page": m.page_number,
                "source_kind": m.source_kind,
                "confidence": round(m.confidence or 0, 2),
            }
        )

    # --- Документы, требующие внимания ------------------------------------
    needs_attention: list[dict[str, Any]] = []
    for d in docs:
        reasons: list[str] = []
        if d.status == "error":
            reasons.append(d.error or "Ошибка обработки")
        if d.status == "ready" and (d.metric_count or 0) == 0:
            reasons.append("Не найдено ни одного показателя")
        if d.status == "ready" and (d.ocr_pages or 0) > 0 and (d.avg_confidence or 0) < 0.9:
            reasons.append(f"Низкая уверенность OCR ({round((d.avg_confidence or 0) * 100)}%)")
        if d.warnings:
            reasons.append(f"Предупреждений: {len(d.warnings)}")
        if reasons:
            needs_attention.append(
                {
                    "id": d.id,
                    "name": d.original_name,
                    "status": d.status,
                    "pages": d.page_count or 0,
                    "metrics": d.metric_count or 0,
                    "reasons": reasons[:3],
                }
            )
    needs_attention.sort(key=lambda x: (x["status"] != "error", x["metrics"]))

    return {
        "project": {"id": project.id, "name": project.name, "description": project.description},
        "stats": {
            "documents": len(docs),
            "ready": sum(1 for d in docs if d.status == "ready"),
            "processing": sum(1 for d in docs if d.status in {"pending", "processing"}),
            "errors": sum(1 for d in docs if d.status == "error"),
            "pages": pages,
            "pages_with_text": pages_with_text,
            "metrics": len(metric_rows),
            "tables": table_count,
            "chunks": chunks,
            "analyses": analyses.count(),
            "saved_analyses": analyses.filter(Analysis.saved.is_(True)).count(),
            "ocr_pages": sum(d.ocr_pages or 0 for d in docs),
            "ocr_documents": sum(1 for d in docs if (d.ocr_pages or 0) > 0),
            "storage_bytes": sum(d.size_bytes or 0 for d in docs),
            "avg_confidence": avg_confidence,
            "processing_ms": sum(d.processing_ms or 0 for d in docs),
        },
        "quality": {
            "score": score,
            "avg_confidence": avg_confidence,
            "ocr_documents": sum(1 for d in docs if (d.ocr_pages or 0) > 0),
            "text_documents": sum(1 for d in docs if (d.ocr_pages or 0) == 0),
            "warnings_count": len(warning_items),
            "warnings": warning_items[:15],
            "low_confidence_documents": low_confidence[:10],
        },
        "coverage": {
            "documents_with_metrics": len(with_metrics),
            "documents_with_tables": sum(1 for d in docs if (d.table_count or 0) > 0),
            "documents_without_metrics": without_metrics[:10],
            "pages_with_text": pages_with_text,
            "metrics_by_source": metrics_by_source,
            "by_document": by_document[:30],
        },
        "top_metrics": top_metrics[:10],
        "periods": periods,
        "latest_values": latest_values,
        "needs_attention": needs_attention[:10],
        "recent_analyses": [
            {
                "id": a.id,
                "title": a.title,
                "query": a.query,
                "intent": a.intent,
                "created_at": a.created_at.isoformat() if a.created_at else None,
                "model": a.model,
                "documents": a.documents or [],
            }
            for a in recent_analyses
        ],
        "recent_documents": [
            {
                "id": d.id,
                "name": d.original_name,
                "status": d.status,
                "pages": d.page_count,
                "metrics": d.metric_count,
                "created_at": d.created_at.isoformat() if d.created_at else None,
            }
            for d in sorted(docs, key=lambda d: d.created_at or d.id, reverse=True)[:6]
        ],
        "processing": [
            {"id": d.id, "name": d.original_name, "progress": d.progress, "stage": d.stage}
            for d in docs
            if d.status in {"pending", "processing"}
        ],
        "projects": [
            {
                "id": p.id,
                "name": p.name,
                "documents": db.query(func.count(Document.id))
                .filter(Document.project_id == p.id)
                .scalar()
                or 0,
            }
            for p in projects
        ],
        "capabilities": {
            "ai_provider": runtime.get("ai_provider"),
            "ai_configured": bool(
                runtime.get("ai_provider") == "ollama"
                or (runtime.get("ai_provider") == "openai" and runtime.get("openai_api_key"))
            ),
            "data_dir": str(settings.data_dir),
        },
    }
