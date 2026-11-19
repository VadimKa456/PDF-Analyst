"""Целостность экспорта Excel, CSV и PDF: данные, графики, источники."""
from __future__ import annotations

import io

import pymupdf
import pytest
from openpyxl import load_workbook

from app.services.exports import export_csv, export_excel, export_pdf


@pytest.fixture(scope="module")
def payload() -> dict:
    return {
        "title": "Сравнение выручки",
        "date": "13.11.2026 10:00",
        "query": "Сравни выручку за 2024 год",
        "intent": "compare",
        "answer": "Выручка Alpha составила 100 млн руб., Beta — 120 млн руб. Рост +20,0%.",
        "documents": [{"name": "alpha_2024.pdf"}, {"name": "beta_2024.pdf"}],
        "meta": {
            "model": "Локальный аналитический движок",
            "selected_labels": ["Выручка"],
            "years": ["2024"],
        },
        "tables": [
            {
                "title": "Сравнительная таблица",
                "columns": [
                    {"key": "indicator", "label": "Показатель", "type": "string"},
                    {"key": "period", "label": "Период", "type": "string"},
                    {"key": "value_display", "label": "Значение", "type": "string"},
                    {"key": "source_display", "label": "Источник", "type": "source"},
                ],
                "rows": [
                    {
                        "indicator": "Выручка",
                        "period": "2024",
                        "value_display": "100 млн руб.",
                        "source_display": "alpha_2024.pdf, стр. 2",
                        "source": {
                            "document_id": 1,
                            "document": "alpha_2024.pdf",
                            "page": 2,
                            "snippet": "Выручка — 100 млн руб.",
                        },
                    },
                    {
                        "indicator": "Выручка",
                        "period": "2024",
                        "value_display": "120 млн руб.",
                        "source_display": "beta_2024.pdf, стр. 4",
                        "source": {
                            "document_id": 2,
                            "document": "beta_2024.pdf",
                            "page": 4,
                            "snippet": "Revenue — 120 млн руб.",
                        },
                    },
                ],
                "row_count": 2,
            }
        ],
        "findings": [
            {"type": "increase", "text": "Рост выручки Beta к Alpha: +20,0%.", "severity": "info"}
        ],
        "warnings": ["Разные валюты не сравниваются без конвертации."],
        "methods": ["Процентное изменение = (новое − базовое) / |базовое| × 100."],
        "citations": [
            {
                "document_id": 1,
                "document": "alpha_2024.pdf",
                "page": 2,
                "snippet": "Выручка — 100 млн руб.",
                "metric_id": 10,
                "source_kind": "table",
                "confidence": 0.95,
            },
            {
                "document_id": 2,
                "document": "beta_2024.pdf",
                "page": 4,
                "snippet": "Revenue — 120 млн руб.",
                "metric_id": 11,
                "source_kind": "table",
                "confidence": 0.93,
            },
        ],
        "charts": [
            {
                "title": "Динамика выручки",
                "type": "line",
                "plotly": {
                    "data": [
                        {
                            "x": ["2023", "2024"],
                            "y": [100, 120],
                            "name": "Выручка",
                            "customdata": [
                                ["2023", 2, "alpha_2024.pdf", 100],
                                ["2024", 4, "beta_2024.pdf", 120],
                            ],
                        }
                    ],
                    "layout": {"yaxis": {"type": "linear"}},
                },
            }
        ],
    }


def test_excel_contains_report_tables_sources_and_chart_data(payload: dict) -> None:
    data = export_excel(payload)
    assert data.startswith(b"PK")

    wb = load_workbook(io.BytesIO(data))
    assert wb.sheetnames == [
        "Отчёт",
        "Сравнительная таблица",
        "Источники",
        "Данные графиков",
    ]
    report = wb["Отчёт"]
    assert report["A1"].value == "Сравнение выручки"
    assert any(
        "Выручка Alpha" in str(c.value) for row in report.iter_rows() for c in row if c.value
    )

    table = wb["Сравнительная таблица"]
    assert table["A1"].value == "Сравнительная таблица"
    assert [table.cell(row=3, column=i).value for i in range(1, 5)] == [
        "Показатель",
        "Период",
        "Значение",
        "Источник",
    ]
    assert table["A4"].value == "Выручка"
    assert table["C5"].value == "120 млн руб."
    assert table["D5"].value == "beta_2024.pdf, стр. 4"

    sources = wb["Источники"]
    assert sources["A2"].value == "alpha_2024.pdf"
    assert sources["B2"].value == 2
    assert sources["C3"].value == "Revenue — 120 млн руб."

    chart = wb["Данные графиков"]
    assert chart["A2"].value == "Динамика выручки"
    assert chart["D2"].value == "2023"
    assert chart["E2"].value == 100
    assert chart["F2"].value == "alpha_2024.pdf"
    assert chart["G2"].value == 2


def test_csv_is_utf8_bom_and_contains_all_rows(payload: dict) -> None:
    data = export_csv(payload)
    assert data.startswith(b"\xef\xbb\xbf")
    text = data.decode("utf-8-sig")
    lines = text.splitlines()
    assert lines[0] == "Сравнительная таблица"
    assert lines[1] == "Показатель;Период;Значение;Источник"
    assert "Выручка;2024;100 млн руб.;alpha_2024.pdf, стр. 2" in lines
    assert "Выручка;2024;120 млн руб.;beta_2024.pdf, стр. 4" in lines


def test_csv_without_tables_falls_back_to_summary(payload: dict) -> None:
    data = export_csv({"query": "Вопрос", "answer": "Ответ", "findings": [{"text": "Факт"}]})
    text = data.decode("utf-8-sig")
    assert "Аналитический отчёт" in text
    assert "Вопрос" in text
    assert "Ответ" in text
    assert "Факт" in text


def test_pdf_contains_title_tables_and_sources(payload: dict) -> None:
    data = export_pdf(payload)
    assert data.startswith(b"%PDF")
    assert b"%%EOF" in data
    assert len(data) > 5000

    doc = pymupdf.open(stream=data, filetype="pdf")
    try:
        assert doc.page_count >= 1
        text = "\n".join(page.get_text() for page in doc)
        assert "Сравнение выручки" in text
        assert "Сравнительная таблица" in text
        assert "Источники" in text
        assert "alpha_2024.pdf" in text
    finally:
        doc.close()


def test_pdf_renders_chart_without_crashing(payload: dict) -> None:
    without_chart = export_pdf({**payload, "charts": []})
    with_chart = export_pdf(payload)
    assert len(with_chart) > len(without_chart)
