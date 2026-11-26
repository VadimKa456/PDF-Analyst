from __future__ import annotations

import re
import shutil
import uuid
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse, Response
from sqlalchemy.orm import Session

from ..config import settings
from ..database import get_db
from ..models import Document, Metric, Page, Project, Table
from ..services import jobs, pdf_processor
from ..services.retrieval import remove_document_index
from ..services.runtime_settings import get_runtime_settings
from ..utils import sanitize_filename, sha256_file, short_snippet

router = APIRouter(prefix="/api", tags=["documents"])

MAX_FILES_PER_UPLOAD = 20


def _validate_upload_count(file_count: int) -> None:
    if file_count > MAX_FILES_PER_UPLOAD:
        raise HTTPException(
            413,
            f"За один раз можно загрузить не более {MAX_FILES_PER_UPLOAD} PDF-файлов.",
        )


def doc_payload(d: Document) -> dict[str, Any]:
    return {
        "id": d.id,
        "project_id": d.project_id,
        "filename": d.filename,
        "original_name": d.original_name,
        "size_bytes": d.size_bytes,
        "page_count": d.page_count,
        "status": d.status,
        "progress": d.progress,
        "stage": d.stage,
        "error": d.error,
        "warnings": d.warnings or [],
        "ocr_used": d.ocr_used,
        "ocr_pages": d.ocr_pages,
        "avg_confidence": d.avg_confidence,
        "text_chars": d.text_chars,
        "table_count": d.table_count,
        "metric_count": d.metric_count,
        "chunk_count": d.chunk_count,
        "processing_ms": d.processing_ms,
        "created_at": d.created_at.isoformat() if d.created_at else None,
        "processed_at": d.processed_at.isoformat() if d.processed_at else None,
    }


def _get_doc(db: Session, document_id: int) -> Document:
    doc = db.get(Document, document_id)
    if not doc:
        raise HTTPException(404, "Документ не найден")
    return doc


@router.get("/projects/{project_id}/documents")
def list_documents(project_id: int, db: Session = Depends(get_db)):
    if not db.get(Project, project_id):
        raise HTTPException(404, "Проект не найден")
    docs = (
        db.query(Document)
        .filter(Document.project_id == project_id)
        .order_by(Document.created_at.desc(), Document.id.desc())
        .all()
    )
    return [doc_payload(d) for d in docs]


@router.post("/projects/{project_id}/documents")
async def upload_documents(
    project_id: int,
    files: list[UploadFile] = File(...),
    db: Session = Depends(get_db),
):
    if not db.get(Project, project_id):
        raise HTTPException(404, "Проект не найден")
    runtime = get_runtime_settings(db)
    max_mb = int(runtime.get("max_upload_mb") or settings.max_upload_mb)
    max_bytes = max_mb * 1024 * 1024
    folder = settings.uploads_dir / f"project_{project_id}"
    folder.mkdir(parents=True, exist_ok=True)
    uploaded: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []

    try:
        _validate_upload_count(len(files))
    except HTTPException:
        for upload in files:
            await upload.close()
        raise

    for upload in files:
        original = sanitize_filename(upload.filename or "document.pdf")
        if not original.lower().endswith(".pdf"):
            errors.append({"filename": upload.filename or "", "error": "Поддерживаются только PDF-файлы"})
            continue
        stored = f"{uuid.uuid4().hex}.pdf"
        tmp_path = folder / (stored + ".part")
        final_path = folder / stored
        size = 0
        try:
            first = True
            with open(tmp_path, "wb") as out:
                while True:
                    chunk = await upload.read(1024 * 1024)
                    if not chunk:
                        break
                    if first:
                        if not chunk.startswith(b"%PDF"):
                            raise ValueError("Файл не является PDF (отсутствует сигнатура %PDF)")
                        first = False
                    size += len(chunk)
                    if size > max_bytes:
                        raise ValueError(f"Файл больше допустимого размера {max_mb} МБ")
                    out.write(chunk)
            if size == 0:
                raise ValueError("Пустой файл")
            tmp_path.replace(final_path)
            doc = Document(
                project_id=project_id,
                filename=stored,
                original_name=original,
                file_path=str(final_path),
                size_bytes=size,
                sha256=sha256_file(final_path),
                status="pending",
                progress=0,
                stage="В очереди",
            )
            db.add(doc)
            db.commit()
            db.refresh(doc)
            jobs.enqueue_document(doc.id)
            uploaded.append(doc_payload(doc))
        except Exception as exc:  # noqa: BLE001
            for p in (tmp_path, final_path):
                try:
                    if p.exists():
                        p.unlink()
                except OSError:
                    pass
            errors.append({"filename": upload.filename or "", "error": str(exc)})
        finally:
            await upload.close()
    return {"documents": uploaded, "errors": errors}


@router.get("/documents/{document_id}")
def get_document(document_id: int, db: Session = Depends(get_db)):
    return doc_payload(_get_doc(db, document_id))


@router.delete("/documents/{document_id}")
def delete_document(document_id: int, db: Session = Depends(get_db)):
    doc = _get_doc(db, document_id)
    path = Path(doc.file_path)
    remove_document_index(db, doc.id)
    db.delete(doc)
    db.commit()
    try:
        if path.exists():
            path.unlink()
    except OSError:
        pass
    return {"ok": True}


@router.post("/documents/{document_id}/reprocess")
def reprocess(document_id: int, db: Session = Depends(get_db)):
    doc = _get_doc(db, document_id)
    if doc.status in {"processing", "pending"}:
        raise HTTPException(409, "Документ уже обрабатывается")
    if not Path(doc.file_path).exists():
        raise HTTPException(410, "Файл PDF отсутствует на диске")
    jobs.reprocess_document(document_id)
    return {"ok": True, "status": "pending"}


@router.get("/documents/{document_id}/file")
def document_file(document_id: int, db: Session = Depends(get_db)):
    doc = _get_doc(db, document_id)
    path = Path(doc.file_path)
    if not path.exists():
        raise HTTPException(404, "Файл PDF не найден")
    return FileResponse(
        path,
        media_type="application/pdf",
        filename=doc.original_name,
        headers={"Content-Disposition": f'inline; filename="{doc.filename}"'},
    )


@router.get("/documents/{document_id}/pages")
def document_pages(document_id: int, db: Session = Depends(get_db)):
    doc = _get_doc(db, document_id)
    pages = db.query(Page).filter(Page.document_id == doc.id).order_by(Page.number).all()
    return [
        {
            "number": p.number,
            "method": p.method,
            "confidence": p.confidence,
            "has_tables": p.has_tables,
            "chars": len(p.text or ""),
            "preview": short_snippet(p.text or "", 220),
        }
        for p in pages
    ]


@router.get("/documents/{document_id}/pages/{page_number}")
def page_text(document_id: int, page_number: int, db: Session = Depends(get_db)):
    page = (
        db.query(Page)
        .filter(Page.document_id == document_id, Page.number == page_number)
        .first()
    )
    if not page:
        raise HTTPException(404, "Страница не найдена")
    return {
        "number": page.number,
        "text": page.text,
        "method": page.method,
        "confidence": page.confidence,
        "width": page.width,
        "height": page.height,
    }


@router.get("/documents/{document_id}/pages/{page_number}/image")
def page_image(document_id: int, page_number: int, db: Session = Depends(get_db)):
    doc = _get_doc(db, document_id)
    try:
        png = pdf_processor.render_page_png(doc.file_path, page_number, dpi=120)
    except pdf_processor.PDFResourceLimitError as exc:
        raise HTTPException(413, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(404, f"Не удалось отрисовать страницу: {exc}") from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(422, "Не удалось отрисовать страницу PDF.") from exc
    return Response(content=png, media_type="image/png")


@router.get("/documents/{document_id}/tables")
def document_tables(document_id: int, db: Session = Depends(get_db)):
    tables = (
        db.query(Table)
        .filter(Table.document_id == document_id)
        .order_by(Table.page_number, Table.id)
        .all()
    )
    return [
        {
            "id": t.id,
            "page": t.page_number,
            "title": t.title,
            "headers": t.headers,
            "rows": t.rows,
            "method": t.method,
            "confidence": t.confidence,
            "row_count": t.row_count,
            "col_count": t.col_count,
        }
        for t in tables
    ]


@router.get("/documents/{document_id}/metrics")
def document_metrics(
    document_id: int,
    limit: int = Query(500, ge=1, le=5000),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    doc = _get_doc(db, document_id)
    q = db.query(Metric).filter(Metric.document_id == doc.id)
    total = q.count()
    rows = q.order_by(Metric.page_number, Metric.id).offset(offset).limit(limit).all()
    return {
        "total": total,
        "items": [
            {
                "id": m.id,
                "page": m.page_number,
                "label": m.label,
                "value": m.value,
                "raw_value": m.raw_value,
                "unit": m.unit,
                "period": m.period,
                "dimension": m.dimension,
                "currency": m.currency,
                "confidence": m.confidence,
                "source_kind": m.source_kind,
                "context": m.context,
            }
            for m in rows
        ],
    }


_COVERAGE_NUM_RE = re.compile(
    r"(?<![\d.,])"
    r"(?:"
    r"\d{1,2}[./-]\d{1,2}[./-](?:19|20)\d{2}"  # дата 31.12.2020
    r"|\d{1,3}(?:[ \u00a0\u202f]\d{3})+(?:[.,]\d{1,2})?(?![\d.,])"  # 4 061 444 118
    r"|\d{1,3}(?:\.\d{3})+(?:,\d{1,2})?(?![\d.,])"  # 4.061.444
    r"|\d+(?:[.,]\d+)?"  # 1234,56
    r")"
)
_COVERAGE_DATE_RE = re.compile(r"\b\d{1,2}[./-]\d{1,2}[./-](?:19|20)\d{2}\b")
_COVERAGE_SHORT_DATE_RE = re.compile(r"\b\d{1,2}[./-]\d{1,2}\b")


def _digits(text: str) -> str:
    return re.sub(r"\D", "", text or "")


_REQUISITE_HINT_RE = re.compile(
    r"\b(?:инн|кпп|огрн|окпо|оквэд|октмо|окуд|окопф|окфс|океи|бик|"
    r"р/с|к/с|счет|счёт|account|inn|vat|registration)\b",
    re.I,
)


def _classify_number_token(
    token: str,
    digits: str,
    context: str,
    matched: bool,
    is_date: bool,
) -> str:
    """value | code | requisite | date | year — чтобы покрытие было понятным."""
    if is_date:
        return "date"
    if matched:
        return "value"
    if re.fullmatch(r"(?:19|20)\d{2}", digits):
        return "year"
    # короткие даты/диапазоны вида 01.05 (без года)
    if _COVERAGE_SHORT_DATE_RE.fullmatch(token):
        return "date"
    # идентификаторы в скобках: (09031), (1234)
    if re.search(r"\(" + re.escape(token) + r"\)", context):
        if 2 <= len(digits) <= 8:
            return "code"
    if len(digits) <= 2 and not re.search(r"[\s.,]", token):
        return "code"
    if len(digits) == 3 and not re.search(r"[\s.,]", token):
        return "code"
    if len(digits) == 4 and not re.search(r"[\s.,]", token) and 1000 <= int(digits) <= 2599:
        # коды строк отчётности (1110…2400) чаще всего 4-значные
        return "code"
    if _REQUISITE_HINT_RE.search(context):
        return "requisite"
    if len(digits) >= 8 and re.fullmatch(r"\d{8,}", token):
        return "requisite"
    # табельные/кадровые номера: 5-6 цифр без разделителей в скобках или рядом с ФИО-контекстом
    if 5 <= len(digits) <= 6 and re.fullmatch(r"\d{5,6}", token):
        # в расчётных листках часто "(09031)" — уже поймано выше; здесь общий случай
        if re.search(r"[А-ЯЁ][а-яё]+.*" + re.escape(token) + r"|" + re.escape(token), context):
            # слабый сигнал сам по себе, оставим как value если похоже на сумму без разделителей маловероятно
            pass
    return "value"


@router.get("/documents/{document_id}/coverage")
def document_coverage(document_id: int, db: Session = Depends(get_db)):
    """Покрытие извлечения: значимые числа страницы и то, что попало в показатели."""
    doc = _get_doc(db, document_id)
    pages = db.query(Page).filter(Page.document_id == doc.id).order_by(Page.number).all()
    metrics = db.query(Metric).filter(Metric.document_id == doc.id).all()
    by_page: dict[int, list[Metric]] = {}
    for m in metrics:
        by_page.setdefault(m.page_number, []).append(m)

    page_items = []
    totals = {
        "tokens": 0,
        "numbers": 0,
        "matched": 0,
        "unmatched": 0,
        "codes": 0,
        "requisites": 0,
        "dates": 0,
        "years": 0,
    }
    for page in pages:
        text = page.text or ""
        page_metrics = by_page.get(page.number, [])
        metric_digits = {_digits(m.raw_value) for m in page_metrics if m.raw_value}
        metric_digits |= {_digits(str(int(m.value))) for m in page_metrics if m.value is not None}
        metric_digits.discard("")

        numbers = []
        for match in _COVERAGE_NUM_RE.finditer(text):
            token = match.group(0).strip(" .,")
            digits = _digits(token)
            if len(digits) < 2:
                continue
            is_date = bool(_COVERAGE_DATE_RE.fullmatch(token))
            matched = digits in metric_digits or any(
                len(digits) >= 4 and (known.startswith(digits) or known.endswith(digits))
                for known in metric_digits
            )
            context = text[max(0, match.start() - 70): match.end() + 70]
            kind = _classify_number_token(token, digits, context, matched, is_date)
            numbers.append(
                {
                    "value": token,
                    "kind": kind,
                    "matched": matched,
                    "context": short_snippet(context, 160),
                }
            )

        values = [n for n in numbers if n["kind"] == "value"]
        matched_values = [n for n in values if n["matched"]]
        service = {
            "codes": sum(1 for n in numbers if n["kind"] == "code"),
            "requisites": sum(1 for n in numbers if n["kind"] == "requisite"),
            "dates": sum(1 for n in numbers if n["kind"] == "date"),
            "years": sum(1 for n in numbers if n["kind"] == "year"),
        }
        totals["tokens"] += len(numbers)
        totals["numbers"] += len(values)
        totals["matched"] += len(matched_values)
        totals["unmatched"] += len(values) - len(matched_values)
        for key in service:
            totals[key] += service[key]
        page_items.append(
            {
                "number": page.number,
                "method": page.method,
                "confidence": page.confidence,
                "chars": len(text),
                "metrics": len(page_metrics),
                "tokens": len(numbers),
                "numbers": len(values),
                "matched": len(matched_values),
                "unmatched": len(values) - len(matched_values),
                "service": service,
                "unmatched_examples": [n for n in values if not n["matched"]][:25],
            }
        )

    tables = db.query(Table).filter(Table.document_id == doc.id).order_by(Table.page_number).all()
    table_items = [
        {
            "id": t.id,
            "page": t.page_number,
            "method": t.method,
            "rows": t.row_count,
            "columns": t.col_count,
            "title": t.title,
        }
        for t in tables
    ]

    return {
        "document_id": doc.id,
        "summary": {
            "pages": len(pages),
            "metrics": len(metrics),
            "tables": len(tables),
            "tokens": totals["tokens"],
            "numbers": totals["numbers"],
            "matched": totals["matched"],
            "unmatched": totals["unmatched"],
            "match_rate": round(totals["matched"] / totals["numbers"], 3) if totals["numbers"] else 0.0,
            "service": {
                "codes": totals["codes"],
                "requisites": totals["requisites"],
                "dates": totals["dates"],
                "years": totals["years"],
            },
            "ocr_pages": sum(1 for p in pages if p.method == "ocr"),
            "avg_confidence": doc.avg_confidence,
            "source_split": {
                "text": sum(1 for m in metrics if m.source_kind == "text"),
                "table": sum(1 for m in metrics if m.source_kind == "table"),
            },
        },
        "pages": page_items,
        "tables": table_items,
    }
