"""Проверка расчётов, сравнений, противоречий и ссылок на источники."""
from __future__ import annotations

import pytest

from app.services.analytics import (
    LabelCluster,
    build_comparison,
    build_contradictions,
    build_dynamics,
    build_extrema,
    build_missing,
    build_summary_table,
)
from conftest import make_document, make_metric


def _cluster(label: str, normalized: str, metrics: list) -> LabelCluster:
    return LabelCluster(
        normalized=normalized,
        label=label,
        members=sorted({m.normalized_label for m in metrics}),
        metrics=metrics,
    )


def test_comparison_calculates_absolute_and_percent_change() -> None:
    alpha = make_document(1, "alpha_2024.pdf")
    beta = make_document(2, "beta_2024.pdf")
    metrics = [
        make_metric(metric_id=1, document=alpha, label="Выручка", value=100, period="2024"),
        make_metric(metric_id=2, document=beta, label="Revenue", value=120, period="2024"),
    ]
    result = build_comparison([_cluster("Выручка", "revenue", metrics)], [alpha, beta])

    rows = result["tables"][0]["rows"]
    assert len(rows) == 2
    base_row, growth_row = rows
    assert base_row["trend_code"] == "base"
    assert base_row["value_display"] == "100 млн руб."
    assert growth_row["trend_code"] == "up"
    assert growth_row["change_display"] == "20"
    assert growth_row["pct_display"] == "+20,0%"
    assert growth_row["base_value"] == "100 млн руб."
    assert growth_row["source_display"] == "beta_2024.pdf, стр. 1"
    assert growth_row["source_page"] == 1
    assert growth_row["source_snippet"]


def test_comparison_source_links_keep_document_and_page() -> None:
    alpha = make_document(1, "alpha_2024.pdf")
    beta = make_document(2, "beta_2024.pdf")
    metrics = [
        make_metric(metric_id=11, document=alpha, label="Выручка", value=100, page=2),
        make_metric(metric_id=12, document=beta, label="Выручка", value=90, page=7),
    ]
    result = build_comparison([_cluster("Выручка", "revenue", metrics)], [alpha, beta])

    pairs = {(c["document"], c["page"], c["metric_id"]) for c in result["citations"]}
    assert ("alpha_2024.pdf", 2, 11) in pairs
    assert ("beta_2024.pdf", 7, 12) in pairs
    for citation in result["citations"]:
        assert citation["snippet"]


def test_zero_base_does_not_produce_percent_change() -> None:
    alpha = make_document(1, "alpha_2024.pdf")
    beta = make_document(2, "beta_2024.pdf")
    metrics = [
        make_metric(metric_id=1, document=alpha, label="Выручка", value=0),
        make_metric(metric_id=2, document=beta, label="Выручка", value=50),
    ]
    result = build_comparison([_cluster("Выручка", "revenue", metrics)], [alpha, beta])

    growth = result["tables"][0]["rows"][1]
    assert growth["pct_display"] == "—"
    assert "нулю" in growth["note"]
    assert growth["trend_code"] == "up"


def test_incomparable_currencies_are_not_compared() -> None:
    alpha = make_document(1, "alpha_2024.pdf")
    usd = make_document(2, "beta_2024_usd.pdf")
    metrics = [
        make_metric(
            metric_id=1, document=alpha, label="Выручка", value=100,
            unit="млн руб.", dimension="money", scale=1e6, currency="RUB",
        ),
        make_metric(
            metric_id=2, document=usd, label="Revenue", value=120,
            unit="млн долл.", dimension="money", scale=1e6, currency="USD",
        ),
    ]
    result = build_comparison([_cluster("Выручка", "revenue", metrics)], [alpha, usd])

    row = result["tables"][0]["rows"][1]
    assert row["trend_code"] == "incomparable"
    assert row["pct_display"] == "—"
    assert any("Разные валюты" in w for w in result["warnings"])
    # расчёт процентов не выполнен, но источник всё равно указан
    assert row["source_document"] == "beta_2024_usd.pdf"


def test_incomparable_dimensions_are_not_compared() -> None:
    alpha = make_document(1, "alpha_2024.pdf")
    beta = make_document(2, "beta_2024.pdf")
    metrics = [
        make_metric(
            metric_id=1, document=alpha, label="Рентабельность", value=10,
            unit="%", dimension="percent", scale=1.0, currency="",
        ),
        make_metric(
            metric_id=2, document=beta, label="Рентабельность", value=12,
            unit="млн руб.", dimension="money", scale=1e6, currency="RUB",
        ),
    ]
    result = build_comparison([_cluster("Рентабельность", "rentabelnost", metrics)], [alpha, beta])

    row = result["tables"][0]["rows"][1]
    assert row["trend_code"] == "incomparable"
    assert any("Разные единицы" in w for w in result["warnings"])


def test_missing_distinguishes_zero_from_no_data() -> None:
    alpha = make_document(1, "alpha_2024.pdf")
    beta = make_document(2, "beta_2024.pdf")
    gamma = make_document(3, "gamma_2024.pdf")
    metrics = [
        make_metric(metric_id=1, document=alpha, label="Выручка", value=0, period="2024"),
        make_metric(metric_id=2, document=beta, label="Выручка", value=None, period="2024"),
    ]
    result = build_missing(
        [_cluster("Выручка", "revenue", metrics)], [alpha, beta, gamma], years=["2024"]
    )

    row = result["tables"][0]["rows"][0]
    assert row["missing_count"] == 2
    assert "beta_2024.pdf" in row["missing_documents"]
    assert "gamma_2024.pdf" in row["missing_documents"]
    # ноль — это присутствующие данные
    assert "alpha_2024.pdf" in row["present_documents"]
    assert "beta_2024.pdf" not in row["present_documents"]


def test_contradictions_within_same_entity() -> None:
    alpha = make_document(1, "alpha_2024.pdf")
    audit = make_document(2, "alpha_2024_audit.pdf")
    metrics = [
        make_metric(metric_id=1, document=alpha, label="Выручка", value=100, entity_key="alpha"),
        make_metric(metric_id=2, document=audit, label="Выручка", value=110, entity_key="alpha"),
    ]
    result = build_contradictions([_cluster("Выручка", "revenue", metrics)])

    assert result["findings"] and result["findings"][0]["type"] == "contradiction"
    assert len(result["tables"][0]["rows"]) == 2
    assert result["citations"]
    assert result["meta"]["checked_groups"] == 1


def test_no_contradiction_for_different_entities() -> None:
    alpha = make_document(1, "alpha_2024.pdf")
    beta = make_document(2, "beta_2024.pdf")
    metrics = [
        make_metric(metric_id=1, document=alpha, label="Выручка", value=100, entity_key="alpha"),
        make_metric(metric_id=2, document=beta, label="Выручка", value=110, entity_key="beta"),
    ]
    result = build_contradictions([_cluster("Выручка", "revenue", metrics)])

    assert result["tables"][0]["rows"] == []
    assert result["findings"] == []
    assert any("не обнаружено" in w for w in result["warnings"])


def test_contradiction_tolerance_for_small_differences() -> None:
    alpha = make_document(1, "alpha_2024.pdf")
    audit = make_document(2, "alpha_2024_audit.pdf")
    metrics = [
        make_metric(metric_id=1, document=alpha, label="Выручка", value=100, entity_key="alpha"),
        make_metric(metric_id=2, document=audit, label="Выручка", value=100.1, entity_key="alpha"),
    ]
    result = build_contradictions([_cluster("Выручка", "revenue", metrics)])
    assert result["tables"][0]["rows"] == []


def test_dynamics_across_years() -> None:
    alpha = make_document(1, "alpha_2024.pdf")
    metrics = [
        make_metric(metric_id=1, document=alpha, label="Выручка", value=100, period="2022"),
        make_metric(metric_id=2, document=alpha, label="Выручка", value=120, period="2023"),
        make_metric(metric_id=3, document=alpha, label="Выручка", value=90, period="2024"),
    ]
    result = build_dynamics([_cluster("Выручка", "revenue", metrics)], [alpha])

    rows = result["tables"][0]["rows"]
    assert [r["period"] for r in rows] == ["2022", "2023", "2024"]
    assert rows[0]["trend_code"] == "base"
    assert rows[1]["trend_code"] == "up"
    assert rows[1]["pct_display"] == "+20,0%"
    assert rows[2]["trend_code"] == "down"
    assert rows[2]["pct_display"] == "-25,0%"
    assert result["citations"]


def test_extrema_are_calculated_per_dimension() -> None:
    alpha = make_document(1, "alpha_2024.pdf")
    beta = make_document(2, "beta_2024.pdf")
    metrics = [
        make_metric(metric_id=1, document=alpha, label="Выручка", value=100, period="2023"),
        make_metric(metric_id=2, document=beta, label="Выручка", value=150, period="2024"),
        make_metric(
            metric_id=3, document=alpha, label="Рентабельность", value=12,
            unit="%", dimension="percent", scale=1.0, period="2024",
        ),
    ]
    clusters = [
        _cluster("Выручка", "revenue", metrics[:2]),
        _cluster("Рентабельность", "rentabelnost", metrics[2:]),
    ]
    result = build_extrema(clusters)

    revenue = result["tables"][0]["rows"][0]
    assert revenue["max_value"] == "150 млн руб."
    assert revenue["min_value"] == "100 млн руб."
    assert revenue["max_document"] == "beta_2024.pdf"
    assert len(result["tables"][0]["rows"]) == 2  # две размерности


def test_summary_table_contains_sources_for_every_value() -> None:
    alpha = make_document(1, "alpha_2024.pdf")
    beta = make_document(2, "beta_2024.pdf")
    metrics = [
        make_metric(metric_id=1, document=alpha, label="Выручка", value=100, page=1),
        make_metric(metric_id=2, document=beta, label="Выручка", value=120, page=4),
    ]
    result = build_summary_table([_cluster("Выручка", "revenue", metrics)], [alpha, beta])

    rows = result["tables"][0]["rows"]
    assert len(rows) == 2
    assert {(r["source_document"], r["source_page"]) for r in rows} == {
        ("alpha_2024.pdf", 1),
        ("beta_2024.pdf", 4),
    }
    assert len(result["citations"]) == 2


def test_comparison_reports_conflicting_values_in_same_document() -> None:
    alpha = make_document(1, "alpha_2024.pdf")
    beta = make_document(2, "beta_2024.pdf")
    metrics = [
        make_metric(metric_id=1, document=alpha, label="Выручка", value=100, source_kind="table"),
        make_metric(metric_id=2, document=alpha, label="Выручка", value=105, source_kind="text"),
        make_metric(metric_id=3, document=beta, label="Выручка", value=120),
    ]
    result = build_comparison([_cluster("Выручка", "revenue", metrics)], [alpha, beta])
    assert any("разные значения" in w for w in result["warnings"])
