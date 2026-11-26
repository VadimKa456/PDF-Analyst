"""Focused pdfplumber regressions for difficult financial-table layouts.

The fixtures are generated in-memory by ReportLab; no customer documents or
external corpus files are required. These tests validate table recovery only,
not PDFium's text extraction path.
"""
from __future__ import annotations

from pathlib import Path

import pdfplumber
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle


def _build_merged_header_pdf(path: Path) -> None:
    doc = SimpleDocTemplate(str(path), pagesize=A4)
    rows = [
        ["Financial metrics — consolidated", "", ""],
        ["Metric", "2025", "2024"],
        ["Revenue", "1250000", "1100000"],
        ["Net profit", "156000", "132000"],
    ]
    table = Table(rows, colWidths=[75 * mm, 35 * mm, 35 * mm])
    table.setStyle(TableStyle([
        ("SPAN", (0, 0), (-1, 0)),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.black),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ALIGN", (1, 1), (-1, -1), "RIGHT"),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    doc.build([table])


def _build_borderless_multiline_pdf(path: Path) -> None:
    doc = SimpleDocTemplate(str(path), pagesize=A4)
    rows = [
        ["Financial indicator\n(thousand RUB)", "Year ended\n31 Dec 2025", "Year ended\n31 Dec 2024"],
        ["Revenue", "1250000", "1100000"],
        ["Net profit", "156000", "132000"],
        ["Total assets", "3400000", "3100000"],
    ]
    table = Table(rows, colWidths=[65 * mm, 42 * mm, 42 * mm])
    # Intentionally no borders, fills, or ruling lines.
    table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 7),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
    ]))
    doc.build([table])


def _extract_text_strategy_tables(path: Path) -> list[list[list[str | None]]]:
    settings = {
        "vertical_strategy": "text",
        "horizontal_strategy": "text",
        "min_words_vertical": 1,
        "min_words_horizontal": 1,
        "text_x_tolerance": 3,
        "text_y_tolerance": 3,
    }
    with pdfplumber.open(path) as pdf:
        return [
            table
            for page in pdf.pages
            for table in (page.extract_tables(table_settings=settings) or [])
        ]


def test_pdfplumber_recovers_table_with_merged_header(tmp_path: Path) -> None:
    path = tmp_path / "merged_header.pdf"
    _build_merged_header_pdf(path)

    with pdfplumber.open(path) as pdf:
        tables = [
            table
            for page in pdf.pages
            for table in (page.extract_tables() or [])
        ]

    flattened = " ".join(
        str(cell)
        for table in tables
        for row in table
        for cell in row
        if cell is not None
    )
    assert "Financial metrics" in flattened
    assert "Revenue" in flattened
    assert "1250000" in flattened
    assert "Net profit" in flattened
    assert "156000" in flattened


def test_pdfplumber_recovers_borderless_table_with_multiline_headers(
    tmp_path: Path,
) -> None:
    path = tmp_path / "borderless_multiline_header.pdf"
    _build_borderless_multiline_pdf(path)

    tables = _extract_text_strategy_tables(path)
    flattened = " ".join(
        str(cell)
        for table in tables
        for row in table
        for cell in row
        if cell is not None
    )
    normalized = "".join(flattened.split()).casefold()

    for expected in (
        "financialindicator",
        "thousandrub",
        "2025",
        "2024",
        "revenue",
        "1250000",
        "1100000",
        "netprofit",
        "156000",
        "totalassets",
        "3400000",
    ):
        assert expected.casefold() in normalized, (
            f"Borderless table extraction missed {expected!r}; extracted: {normalized!r}"
        )
