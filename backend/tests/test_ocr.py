"""OCR сканированного PDF: текст, таблицы и числовые значения."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import pytest

from app.services.analytics import metric_concept
from app.services.pdf_processor import (
    DocumentExtraction,
    extract_document,
    tesseract_status,
)

STATUS = tesseract_status()
pytestmark = pytest.mark.skipif(
    not STATUS.get("available") or not STATUS.get("russian"),
    reason="Tesseract с русским языком недоступен",
)


@lru_cache(maxsize=2)
def _extract(path: str) -> DocumentExtraction:
    return extract_document(path, "alpha_2024_scanned.pdf")


@pytest.fixture(scope="module")
def scanned(scanned_pdf: Path) -> DocumentExtraction:
    return _extract(str(scanned_pdf))


def test_scanned_page_is_recognized_by_ocr(scanned: DocumentExtraction) -> None:
    assert scanned.ocr_pages == 1
    page = scanned.pages[0]
    assert page.method == "ocr"
    assert page.confidence > 0.7
    assert "Выручка" in page.text
    assert scanned.text_chars > 300


def test_ocr_table_is_rebuilt_with_headers(scanned: DocumentExtraction) -> None:
    assert scanned.tables
    table = scanned.tables[0]
    assert table.method == "tesseract-table"
    assert any("2024" in h for h in table.headers)
    assert any("2023" in h for h in table.headers)
    assert len(table.rows) == 6


def test_ocr_numbers_with_lost_thousand_separators_are_merged(
    scanned: DocumentExtraction,
) -> None:
    revenue = [m for m in scanned.metrics if metric_concept(m.label) == "revenue"]
    assert revenue
    by_period = {m.period: m for m in revenue}
    # Values are fixed by samples/generate_samples.py (seed=42); assert exact source values.
    assert by_period["2024"].value == 1_660_936
    assert by_period["2023"].value == 1_440_892
    assert by_period["2024"].unit == "тыс. руб."
    assert by_period["2024"].page_number == 1
    assert by_period["2024"].source_kind == "table"
    assert by_period["2024"].source_ref.startswith("p1:")
    # значение не потеряло разряды и нормализовано с учётом тыс. руб.
    assert by_period["2024"].normalized_value == pytest.approx(1_660_936_000.0)
    assert "1660 936" in (by_period["2024"].context or "")


def test_ocr_metrics_keep_sources_and_confidence(scanned: DocumentExtraction) -> None:
    table_metrics = [m for m in scanned.metrics if m.source_kind == "table"]
    assert table_metrics
    for m in table_metrics:
        assert m.page_number == 1
        assert m.context
        assert 0 < m.confidence <= 1
