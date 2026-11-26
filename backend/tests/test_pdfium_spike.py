"""Smoke tests for the isolated PDFium spike; no production code is exercised."""
from __future__ import annotations

from pathlib import Path

import pytest
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

from app.services.pdfium_spike import inspect_pdf, render_page_png


@pytest.fixture()
def tiny_pdf(tmp_path: Path) -> Path:
    path = tmp_path / "pdfium-smoke.pdf"
    pdf = canvas.Canvas(str(path), pagesize=A4)
    pdf.drawString(72, 780, "PDF Analyst PDFium smoke test")
    pdf.drawString(72, 750, "Revenue 2024: 1648639 thousand RUB")
    pdf.showPage()
    pdf.drawString(72, 780, "Second page marker")
    pdf.save()
    return path


def test_pdfium_extracts_text_and_page_geometry(tiny_pdf: Path) -> None:
    pages = inspect_pdf(tiny_pdf)

    assert len(pages) == 2
    assert pages[0].page_number == 1
    assert "PDF Analyst PDFium smoke test" in pages[0].text
    assert "Revenue 2024" in pages[0].text
    assert pages[0].width == pytest.approx(595.27, abs=1.0)
    assert pages[0].height == pytest.approx(841.89, abs=1.0)
    assert "Second page marker" in pages[1].text


def test_pdfium_renders_png_and_rejects_invalid_page(tiny_pdf: Path) -> None:
    image = render_page_png(tiny_pdf, 1, dpi=72)

    assert image.startswith(b"\x89PNG\r\n\x1a\n")
    assert len(image) > 1000

    with pytest.raises(ValueError, match="Страница не найдена"):
        render_page_png(tiny_pdf, 3)

    with pytest.raises(ValueError, match="Страница не найдена"):
        render_page_png(tiny_pdf, 0)


def test_pdfium_rejects_unreasonable_dpi(tiny_pdf: Path) -> None:
    with pytest.raises(ValueError, match="DPI"):
        render_page_png(tiny_pdf, 1, dpi=1)

def test_pdfium_reports_rotated_page_geometry(tmp_path: Path) -> None:
    """Rotated pages must expose usable, rotation-aware page dimensions."""
    path = tmp_path / "rotated-page.pdf"
    pdf = canvas.Canvas(str(path), pagesize=A4)
    pdf.setPageRotation(90)
    pdf.drawString(72, 780, "Rotated page geometry check")
    pdf.showPage()
    pdf.save()

    pages = inspect_pdf(path)

    assert len(pages) == 1
    assert pages[0].width > 0
    assert pages[0].height > 0
    assert pages[0].rotation == 90
    assert pages[0].width > pages[0].height
    assert "Rotated page geometry check" in pages[0].text
