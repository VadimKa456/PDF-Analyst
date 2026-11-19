"""Сопоставление одинаковых показателей с разными названиями (рус/англ)."""
from __future__ import annotations

import pytest

from app.services.analytics import (
    cluster_labels,
    find_relevant_clusters,
    metric_concept,
)
from conftest import make_document, make_metric


@pytest.mark.parametrize(
    ("left", "right"),
    [
        ("Выручка", "Revenue"),
        ("Выручка от реализации", "Revenue"),
        ("Чистая прибыль", "Net profit"),
        ("Прибыль чистая", "Чистая прибыль"),
        ("Совокупные активы", "Total assets"),
        ("Активы", "Совокупные активы"),
        ("Рентабельность собственного капитала", "Return on equity"),
        ("Операционные расходы", "Operating expenses"),
        ("Численность сотрудников", "Headcount"),
    ],
)
def test_metric_concept_links_ru_and_en(left: str, right: str) -> None:
    assert metric_concept(left) != ""
    assert metric_concept(left) == metric_concept(right)


def test_metric_concept_keeps_unrelated_labels_separate() -> None:
    assert metric_concept("EBITDA") == ""
    assert metric_concept("Количество договоров") == ""


def test_cluster_labels_merges_synonyms_and_languages() -> None:
    docs = [make_document(1, "alpha_2024.pdf"), make_document(2, "beta_2024.pdf")]
    records = [
        make_metric(metric_id=1, document=docs[0], label="Выручка", value=100, period="2024"),
        make_metric(metric_id=2, document=docs[1], label="Revenue", value=120, period="2024"),
        make_metric(metric_id=3, document=docs[0], label="Выручка от реализации", value=98, period="2023"),
        make_metric(metric_id=4, document=docs[0], label="Чистая прибыль", value=10, period="2024"),
        make_metric(metric_id=5, document=docs[1], label="Net profit", value=12, period="2024"),
    ]
    clusters = cluster_labels(records)

    revenue = [c for c in clusters if c.normalized == "revenue"]
    profit = [c for c in clusters if c.normalized == "net_profit"]

    assert len(revenue) == 1, [c.normalized for c in clusters]
    assert len(revenue[0].metrics) == 3
    assert len(revenue[0].documents) == 2
    assert len(profit) == 1
    assert len(profit[0].metrics) == 2
    # все варианты названий сохранены для прозрачности
    assert any("выручка" in m.lower() for m in revenue[0].members)
    assert any("revenue" in m.lower() for m in revenue[0].members)


def test_cluster_labels_uses_fuzzy_matching_for_typos() -> None:
    doc = make_document(1, "alpha_2024.pdf")
    records = [
        make_metric(metric_id=1, document=doc, label="Операционные расходы", value=10),
        make_metric(metric_id=2, document=doc, label="Операционнные расходы", value=11),
    ]
    clusters = cluster_labels(records)
    assert len(clusters) == 1
    assert len(clusters[0].metrics) == 2


def test_cluster_labels_skips_missing_values() -> None:
    doc = make_document(1, "alpha_2024.pdf")
    records = [
        make_metric(metric_id=1, document=doc, label="Выручка", value=None),
        make_metric(metric_id=2, document=doc, label="Выручка", value=100),
    ]
    clusters = cluster_labels(records)
    assert len(clusters) == 1
    assert len(clusters[0].metrics) == 1


def test_find_relevant_clusters_by_query_and_explicit_label() -> None:
    docs = [make_document(1, "alpha_2024.pdf"), make_document(2, "beta_2024.pdf")]
    records = [
        make_metric(metric_id=1, document=docs[0], label="Выручка", value=100),
        make_metric(metric_id=2, document=docs[1], label="Revenue", value=120),
        make_metric(metric_id=3, document=docs[0], label="Чистая прибыль", value=10),
    ]
    clusters = cluster_labels(records)

    by_query = find_relevant_clusters("покажи выручку за 2024", clusters)
    assert [c.normalized for c in by_query][:1] == ["revenue"]

    by_english = find_relevant_clusters("compare revenue", clusters)
    assert by_english and by_english[0].normalized == "revenue"

    explicit = find_relevant_clusters("", clusters, explicit_labels=["Выручка"])
    assert [c.normalized for c in explicit] == ["revenue"]

    unrelated = find_relevant_clusters("EBITDA", clusters)
    assert unrelated == []
