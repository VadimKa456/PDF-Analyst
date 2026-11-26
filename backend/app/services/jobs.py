"""Фоновая обработка PDF с прогрессом и сохранением в SQLite."""
from __future__ import annotations

import logging
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from sqlalchemy.orm import Session

from ..database import session_scope
from ..models import Chunk, Document, Metric, Page, Table
from ..utils import short_snippet
from . import pdf_processor
from .retrieval import index_chunks, remove_document_index
from .runtime_settings import get_runtime_settings

logger = logging.getLogger(__name__)

_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="pdf-worker")
_running: set[int] = set()
_lock = threading.Lock()


def enqueue_document(document_id: int) -> bool:
    with _lock:
        if document_id in _running:
            return False
        _running.add(document_id)
    _executor.submit(_run_job, document_id)
    return True


def _set_progress(document_id: int, percent: int, stage: str) -> None:
    try:
        with session_scope() as db:
            doc = db.get(Document, document_id)
            if doc and doc.status == "processing":
                doc.progress = max(0, min(99, percent))
                doc.stage = stage
    except Exception as exc:  # noqa: BLE001
        logger.debug("progress update failed: %s", exc)


def _clear_extraction(db: Session, document_id: int) -> None:
    remove_document_index(db, document_id)
    db.query(Metric).filter(Metric.document_id == document_id).delete(synchronize_session=False)
    db.query(Table).filter(Table.document_id == document_id).delete(synchronize_session=False)
    db.query(Chunk).filter(Chunk.document_id == document_id).delete(synchronize_session=False)
    db.query(Page).filter(Page.document_id == document_id).delete(synchronize_session=False)


def process_document(document_id: int) -> None:
    """Синхронная обработка документа (используется в тестах и воркере)."""
    started_doc = None
    try:
        with session_scope() as db:
            doc = db.get(Document, document_id)
            if not doc:
                return
            started_doc = doc
            doc.status = "processing"
            doc.progress = 1
            doc.stage = "Подготовка к обработке"
            doc.error = ""
            ocr_settings = get_runtime_settings(db)
            ocr_cfg = {
                "enabled": ocr_settings.get("ocr_enabled"),
                "languages": ocr_settings.get("ocr_languages"),
                "dpi": ocr_settings.get("ocr_dpi"),
                "min_confidence": ocr_settings.get("ocr_min_confidence"),
                "auto": ocr_settings.get("ocr_auto"),
                "tesseract_cmd": ocr_settings.get("tesseract_cmd"),
                "max_file_bytes": min(
                    pdf_processor.MAX_PDF_FILE_BYTES,
                    max(1, int(ocr_settings.get("max_upload_mb") or 100)) * 1024 * 1024,
                ),
            }

        if not Path(started_doc.file_path).exists():
            raise FileNotFoundError("Файл PDF не найден на диске")

        last_progress = {"pct": -1, "stage": ""}

        def on_progress(pct: int, stage: str) -> None:
            if pct != last_progress["pct"] or stage != last_progress["stage"]:
                last_progress["pct"] = pct
                last_progress["stage"] = stage
                _set_progress(document_id, pct, stage)

        result = pdf_processor.extract_document(
            started_doc.file_path,
            started_doc.original_name,
            on_progress=on_progress,
            ocr_config=ocr_cfg,
        )

        on_progress(94, "Сохранение извлечённых данных")
        with session_scope() as db:
            doc = db.get(Document, document_id)
            if not doc:
                return
            _clear_extraction(db, document_id)
            db.flush()

            pages = [
                Page(
                    document_id=document_id,
                    number=p.number,
                    text=p.text,
                    method=p.method,
                    confidence=p.confidence,
                    has_tables=p.has_tables,
                    width=p.width,
                    height=p.height,
                )
                for p in result.pages
            ]
            db.add_all(pages)

            table_objs = []
            for t in result.tables:
                table_objs.append(
                    Table(
                        document_id=document_id,
                        page_number=t.page_number,
                        title=short_snippet(t.title, 400),
                        headers=t.headers,
                        rows=t.rows,
                        method=t.method,
                        confidence=t.confidence,
                        row_count=len(t.rows),
                        col_count=len(t.headers),
                    )
                )
            db.add_all(table_objs)
            db.flush()

            metric_objs = []
            for m in result.metrics:
                metric_objs.append(
                    Metric(
                        document_id=document_id,
                        page_number=m.page_number,
                        table_id=None,
                        label=short_snippet(m.label, 400),
                        normalized_label=short_snippet(m.normalized_label or m.label.lower(), 400),
                        raw_value=m.raw_value[:120],
                        value=m.value,
                        normalized_value=m.normalized_value,
                        unit=m.unit[:60],
                        dimension=m.dimension,
                        scale=m.scale,
                        currency=m.currency,
                        period=m.period[:60],
                        raw_text=m.raw_text,
                        context=m.context,
                        confidence=m.confidence,
                        source_kind=m.source_kind,
                        source_ref=m.source_ref,
                        row_index=m.row_index,
                        col_index=m.col_index,
                    )
                )
            db.add_all(metric_objs)

            chunk_data: list[tuple[int, int, str, str]] = []
            for p in result.pages:
                heading = p.headings[0] if p.headings else ""
                for i, chunk in enumerate(pdf_processor.chunk_text(p.text)):
                    chunk_data.append((p.number, i, chunk, heading))
            index_chunks(db, doc, chunk_data)

            doc.page_count = len(result.pages)
            doc.ocr_used = result.ocr_pages > 0
            doc.ocr_pages = result.ocr_pages
            doc.avg_confidence = result.avg_confidence
            doc.text_chars = result.text_chars
            doc.table_count = len(result.tables)
            doc.metric_count = len(result.metrics)
            doc.chunk_count = len(chunk_data)
            doc.warnings = result.warnings
            doc.processing_ms = result.processing_ms
            doc.stage = "Готово"
            doc.progress = 100
            if result.text_chars == 0:
                doc.status = "error"
                doc.error = "Не удалось извлечь текст. Проверьте, что PDF не повреждён и OCR настроен."
            else:
                doc.status = "ready"
                doc.error = ""
            from datetime import datetime, timezone

            doc.processed_at = datetime.now(timezone.utc).replace(tzinfo=None)
        logger.info("Document %s processed", document_id)
    except Exception as exc:  # noqa: BLE001
        logger.exception("Document %s processing failed", document_id)
        try:
            with session_scope() as db:
                doc = db.get(Document, document_id)
                if doc:
                    try:
                        _clear_extraction(db, document_id)
                    except Exception:  # noqa: BLE001
                        pass
                    doc.status = "error"
                    doc.error = str(exc)[:2000]
                    doc.stage = "Ошибка обработки"
                    doc.progress = 0
        except Exception:  # noqa: BLE001
            logger.exception("Could not save error status for document %s", document_id)
    finally:
        with _lock:
            _running.discard(document_id)


def _run_job(document_id: int) -> None:
    process_document(document_id)


def reprocess_document(document_id: int) -> bool:
    with session_scope() as db:
        doc = db.get(Document, document_id)
        if not doc:
            return False
        doc.status = "pending"
        doc.progress = 0
        doc.stage = "В очереди"
        doc.error = ""
    return enqueue_document(document_id)


def resume_unfinished() -> int:
    """Возобновляет обработку, прерванную перезапуском приложения."""
    ids: list[int] = []
    with session_scope() as db:
        docs = db.query(Document).filter(Document.status.in_(["pending", "processing"])).all()
        for doc in docs:
            if Path(doc.file_path).exists():
                doc.status = "pending"
                doc.progress = 0
                doc.stage = "В очереди (возобновление)"
                ids.append(doc.id)
            else:
                doc.status = "error"
                doc.error = "Файл PDF не найден на диске"
    for doc_id in ids:
        enqueue_document(doc_id)
    return len(ids)


def shutdown() -> None:
    _executor.shutdown(wait=False, cancel_futures=False)
