"""Experimental PDFium adapter.

This module is deliberately isolated from pdf_processor.py. It proves only the
basic document-open, text-extraction, geometry, and rendering boundary; it is
not a production replacement for PyMuPDF.
"""
from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from threading import RLock

import pypdfium2 as pdfium

# PDFium is not thread-safe. Serialize all calls made through this adapter.
_PDFIUM_LOCK = RLock()


@dataclass(frozen=True)
class PdfiumPageSnapshot:
    page_number: int
    text: str
    width: float
    height: float
    rotation: int


def inspect_pdf(path: str | Path) -> list[PdfiumPageSnapshot]:
    """Return text and page geometry using PDFium, with 1-based page numbers."""
    with _PDFIUM_LOCK:
        document = pdfium.PdfDocument(str(path))
        try:
            snapshots: list[PdfiumPageSnapshot] = []
            for index in range(len(document)):
                page = document[index]
                width, height = page.get_size()
                rotation = page.get_rotation()
                # get_size() reports the unrotated page box. Expose display-oriented
                # dimensions so callers see landscape geometry for 90/270 degree pages.
                if rotation in (90, 270):
                    width, height = height, width
                text_page = page.get_textpage()
                try:
                    text = text_page.get_text_bounded()
                    # PDFium emits CRLF line endings; normalize for downstream parsers.
                    text = (text or "").replace("\\r\\n", "\\n").replace("\\r", "\\n")
                finally:
                    text_page.close()
                snapshots.append(
                    PdfiumPageSnapshot(
                        page_number=index + 1,
                        text=text or "",
                        width=float(width),
                        height=float(height),
                        rotation=int(rotation),
                    )
                )
            return snapshots
        finally:
            document.close()


def render_page_png(path: str | Path, page_number: int, dpi: int = 110) -> bytes:
    """Render a 1-based page number to PNG bytes."""
    if page_number < 1:
        raise ValueError("Страница не найдена")
    if dpi < 36 or dpi > 600:
        raise ValueError("DPI должен быть в диапазоне 36–600")

    with _PDFIUM_LOCK:
        document = pdfium.PdfDocument(str(path))
        try:
            if page_number > len(document):
                raise ValueError("Страница не найдена")
            page = document[page_number - 1]
            bitmap = page.render(scale=dpi / 72.0)
            image = bitmap.to_pil()
            output = BytesIO()
            image.save(output, format="PNG")
            return output.getvalue()
        finally:
            document.close()
