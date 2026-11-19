"""Точность извлечения текста, таблиц, единиц и источников из PDF."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import pytest

from app.services.analytics import metric_concept
from app.services.pdf_processor import (
    DocumentExtraction,
    ExtractedTable,
    _clean_metric_label,
    _table_metrics,
    extract_document,
    render_page_png,
)


@lru_cache(maxsize=8)
def _extract(path: str, name: str) -> DocumentExtraction:
    return extract_document(path, name)


@pytest.fixture(scope="module")
def alpha(alpha_2024_pdf: Path) -> DocumentExtraction:
    return _extract(str(alpha_2024_pdf), "alpha_2024.pdf")


@pytest.fixture(scope="module")
def english(english_pdf: Path) -> DocumentExtraction:
    return _extract(str(english_pdf), "beta_2025_english.pdf")


def test_alpha2024_extracts_page_text_and_period(alpha: DocumentExtraction) -> None:
    assert len(alpha.pages) == 1
    page = alpha.pages[0]
    assert page.method == "text"
    assert page.confidence >= 0.9
    assert "Выручка" in page.text
    assert "Чистая прибыль" in page.text
    assert alpha.default_period == "2024"
    assert alpha.text_chars > 300
    assert alpha.ocr_pages == 0


def test_alpha2024_table_headers_and_caption(alpha: DocumentExtraction) -> None:
    assert alpha.tables, "Таблица не найдена"
    table = alpha.tables[0]
    assert table.method == "pymupdf"
    assert any("2024" in h for h in table.headers)
    assert any("2023" in h for h in table.headers)
    assert len(table.rows) == 6
    assert table.title  # подпись таблицы сохранена


def test_alpha2024_revenue_values_have_unit_period_and_source(alpha: DocumentExtraction) -> None:
    revenue = [m for m in alpha.metrics if metric_concept(m.label) == "revenue"]
    assert revenue
    by_period = {m.period: m for m in revenue}
    assert "2024" in by_period and "2023" in by_period
    m = by_period["2024"]
    assert m.value == 1_648_639
    assert m.unit == "тыс. руб."
    assert m.dimension == "money"
    assert m.scale == 1000.0
    assert m.currency == "RUB"
    assert m.normalized_value == pytest.approx(1_648_639_000.0)
    assert m.page_number == 1
    assert m.source_kind == "table"
    assert m.source_ref.startswith("p1")
    assert "1 648 639" in (m.context or "")


def test_every_extracted_metric_points_to_page_and_snippet(alpha: DocumentExtraction) -> None:
    for m in alpha.metrics:
        assert m.page_number >= 1
        assert m.page_number <= len(alpha.pages)
        assert m.context
        assert m.source_ref


def test_english_pdf_is_extracted_with_english_units(english: DocumentExtraction) -> None:
    assert english.default_period == "2025"
    assert "Revenue" in english.pages[0].text
    assert english.tables
    headers = " ".join(english.tables[0].headers)
    assert "thousand RUB" in headers

    revenue = [m for m in english.metrics if metric_concept(m.label) == "revenue"]
    assert revenue
    assert all(m.currency == "RUB" for m in revenue)
    assert all(m.dimension == "money" for m in revenue)
    assert all(m.unit != "%" for m in revenue), "выручке ошибочно назначен процент"
    assert {m.period for m in revenue} >= {"2024", "2025"}


def test_english_margin_stays_percent(english: DocumentExtraction) -> None:
    margin = [m for m in english.metrics if metric_concept(m.label) == "net_profit_margin"]
    assert margin
    assert margin[0].unit == "%"
    assert margin[0].dimension == "percent"
    assert margin[0].value == pytest.approx(9.6)


def test_render_page_png_returns_valid_png(alpha_2024_pdf: Path) -> None:
    data = render_page_png(alpha_2024_pdf, 1, dpi=72)
    assert data.startswith(b"\x89PNG\r\n\x1a\n")
    assert len(data) > 1000

    with pytest.raises(ValueError):
        render_page_png(alpha_2024_pdf, 99)


def _statement_table(rows: list[list[str]]) -> ExtractedTable:
    return ExtractedTable(
        page_number=1,
        title="",
        headers=[
            "Пояснения",
            "Наименование показателя",
            "Код строки",
            "За 2020 год",
            "За 2019 год",
        ],
        rows=rows,
        method="pymupdf",
        confidence=0.95,
    )


def test_table_metrics_skip_code_column_and_apply_page_unit() -> None:
    table = _statement_table(
        [
            ["1-14", "Выручка, вт.ч.:", "2110", "4061 444 118", "4758 711 459"],
            ["", "продажа газа", "2111", "2 635 465 416", "3 311 117 094"],
        ]
    )
    metrics = _table_metrics(table, "2020", page_text="Единица измерения: тыс. руб.")
    values = {m.value for m in metrics}
    # коды строк не должны становиться значениями показателей
    assert 2110.0 not in values and 2111.0 not in values
    assert 4_061_444_118.0 in values
    assert 4_758_711_459.0 in values
    assert 2_635_465_416.0 in values
    assert all(m.unit == "тыс. руб." for m in metrics)
    assert all(m.period in {"2020", "2019"} for m in metrics)


def test_table_metrics_keep_negative_parenthesized_values() -> None:
    table = _statement_table(
        [
            ["6:П-15", "Себестоимость продаж", "2120", "(2488 200 192)", "(2657 654 354)"],
        ]
    )
    metrics = _table_metrics(table, "2020", page_text="Единица измерения: тыс. руб.")
    by_period = {m.period: m for m in metrics}
    assert by_period["2020"].value == -2_488_200_192
    assert by_period["2019"].value == -2_657_654_354
    # колонка «Пояснения» не должна попадать в название
    assert all(not m.label.startswith("6:") for m in metrics)
    assert all("Себестоимость" in m.label for m in metrics)


def test_table_metrics_support_repeating_column_groups() -> None:
    table = ExtractedTable(
        page_number=1,
        title="",
        headers=["Вид", "Период", "Сумма", "Вид", "Период", "Сумма"],
        rows=[["Выручка", "2024", "100", "Выручка", "2023", "90"]],
        method="pymupdf",
        confidence=0.9,
    )
    metrics = _table_metrics(table, "2024")
    by_period = {m.period: m.value for m in metrics}
    assert by_period == {"2024": 100.0, "2023": 90.0}


@pytest.mark.parametrize(
    ("raw", "clean"),
    [
        ("6:П-15 Себестоимость продаж", "Себестоимость продаж"),
        ("11-15 Коммерческие расходы", "Коммерческие расходы"),
        ("6;11-15 Коммерческие расходы", "Коммерческие расходы"),
        (":П-15 Управленческие расходы", "Управленческие расходы"),
        ("1-14 Выручка, вт.ч.:", "Выручка, вт.ч"),
    ],
)
def test_clean_metric_label_drops_explanation_column(raw: str, clean: str) -> None:
    assert _clean_metric_label(raw) == clean


def test_table_metrics_prefix_subitems_with_their_section() -> None:
    """Одинаковые подпункты из разных разделов не должны смешиваться."""
    table = _statement_table(
        [
            ["1-14", "Выручка, вт.ч.:", "2110", "1000", "900"],
            ["", "продажа газа", "2111", "800", "700"],
            ["6:П-15", "Себестоимость продаж", "2120", "(500)", "(400)"],
            ["", "продажа газа", "2121", "(300)", "(250)"],
        ]
    )
    metrics = _table_metrics(table, "2020", page_text="Единица измерения: тыс. руб.")
    labels = {m.label for m in metrics}
    assert "Выручка, вт.ч продажа газа" in labels
    assert "Себестоимость продаж, в т.ч. продажа газа" in labels
    # подпункт себестоимости не подменяет выручку
    revenue = [m for m in metrics if "Выручка" in m.label and "газа" in m.label]
    cost = [m for m in metrics if "Себестоимость" in m.label and "газа" in m.label]
    assert len(revenue) == 2 and len(cost) == 2
    assert all(m.value > 0 for m in revenue)
    assert all(m.value < 0 for m in cost)
