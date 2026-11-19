from __future__ import annotations

import logging
import re
from datetime import datetime
from typing import Any
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy.orm import Session

from ..config import settings
from ..database import get_db
from ..models import Analysis
from ..schemas import ExportRequest
from ..services import exports
from ..services.runtime_settings import get_runtime_settings

router = APIRouter(prefix="/api/export", tags=["export"])
logger = logging.getLogger(__name__)


def _payload_from_analysis(a: Analysis) -> dict[str, Any]:
    result = dict(a.result or {})
    result["title"] = a.title
    result["query"] = a.query
    result["answer"] = a.answer or result.get("answer", "")
    result["intent"] = a.intent
    result.setdefault("citations", a.sources or [])
    result.setdefault("charts", a.charts or [])
    result.setdefault("documents", a.documents or [])
    result.setdefault("meta", {})
    result["date"] = datetime.now().strftime("%d.%m.%Y %H:%M")
    return result


def _payload_from_body(body: ExportRequest) -> dict[str, Any]:
    data = body.model_dump(exclude_none=True)
    data["date"] = datetime.now().strftime("%d.%m.%Y %H:%M")
    if not data.get("title"):
        data["title"] = "Аналитический отчёт"
    return data


def _filename(payload: dict[str, Any], ext: str) -> str:
    title = re.sub(r"[^\w\s.-]", "", str(payload.get("title") or "report")).strip()
    title = re.sub(r"\s+", "_", title)[:60] or "report"
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return f"{title}_{stamp}.{ext}"


def _persist(content: bytes, filename: str) -> str:
    """Сохраняет файл в каталоге exports и возвращает полный путь.

    Desktop-приложение использует этот путь, чтобы показать системный диалог
    «Сохранить как» — в WebView2 скачивание через blob/<a download> работает
    ненадёжно.
    """
    try:
        settings.ensure_dirs()
        target = settings.exports_dir / filename
        target.write_bytes(content)
        return str(target.resolve())
    except Exception:  # noqa: BLE001
        logger.warning("Не удалось сохранить экспорт в %s", filename, exc_info=True)
        return ""


def _response(content: bytes, media_type: str, filename: str) -> Response:
    saved_path = _persist(content, filename)
    return Response(
        content=content,
        media_type=media_type,
        headers={
            "Content-Disposition": f"attachment; filename=\"report\"; filename*=UTF-8''{quote(filename)}",
            "X-Saved-Path": quote(saved_path, safe="/\\:"),
            "Access-Control-Expose-Headers": "Content-Disposition, X-Saved-Path",
        },
    )


@router.post("/chart-png")
def export_chart_png(body: dict[str, Any]):
    chart = body.get("chart")
    if not isinstance(chart, dict):
        raise HTTPException(422, "Не передан объект chart")
    img = exports._chart_png(chart)
    if img is None:
        raise HTTPException(500, "Не удалось отрисовать график")
    filename = f"chart_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
    content = img.getvalue()
    saved_path = _persist(content, filename)
    return Response(
        content=content,
        media_type="image/png",
        headers={
            "Content-Disposition": f"attachment; filename=\"{filename}\"",
            "X-Saved-Path": quote(saved_path, safe="/\\:"),
            "Access-Control-Expose-Headers": "Content-Disposition, X-Saved-Path",
        },
    )


@router.post("/{fmt}")
def export_result(fmt: str, body: ExportRequest, db: Session = Depends(get_db)):
    if fmt not in {"excel", "xlsx", "csv", "pdf"}:
        raise HTTPException(404, "Формат экспорта не поддерживается")
    if body.analysis_id:
        analysis = db.get(Analysis, body.analysis_id)
        if not analysis:
            raise HTTPException(404, "Анализ не найден")
        payload = _payload_from_analysis(analysis)
    else:
        payload = _payload_from_body(body)
    try:
        if fmt in {"excel", "xlsx"}:
            content = exports.export_excel(payload)
            return _response(
                content,
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                _filename(payload, "xlsx"),
            )
        if fmt == "csv":
            content = exports.export_csv(payload)
            return _response(content, "text/csv; charset=utf-8", _filename(payload, "csv"))
        runtime = get_runtime_settings(db)
        content = exports.export_pdf(payload, page_size=str(runtime.get("export_page_size") or "A4"))
        return _response(content, "application/pdf", _filename(payload, "pdf"))
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(500, f"Ошибка экспорта: {exc}") from exc
