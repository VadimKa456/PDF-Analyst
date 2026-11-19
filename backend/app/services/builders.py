"""Конструкторы пользовательских таблиц и графиков."""
from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from ..utils import clean_text
from . import analytics as an


def _filter_clusters_by_years(
    clusters: list[an.LabelCluster], years: list[str]
) -> tuple[list[an.LabelCluster], int]:
    """Оставляет показатели за выбранные годы (общая логика с query_engine)."""
    if not years:
        return clusters, 0
    from . import query_engine as qe

    return qe._filter_clusters_by_years(clusters, years)


def _select_clusters(
    records: list[an.MetricRecord],
    metric_labels: list[str] | None,
    query: str = "",
) -> list[an.LabelCluster]:
    clusters = an.cluster_labels(records)
    if metric_labels:
        wanted = {an.canonical_label(x) for x in metric_labels if clean_text(x)}
        wanted_concepts = {an.metric_concept(x) for x in metric_labels if clean_text(x)} - {""}
        selected = [
            c for c in clusters
            if c.normalized in wanted_concepts
            or any(
                an.canonical_label(m) in wanted
                or an.metric_concept(m) in wanted_concepts
                for m in c.members
            )
        ]
        if selected:
            return selected
    if query:
        return an.find_relevant_clusters(query, clusters)
    return clusters


def _apply_table_filters(
    table: dict[str, Any],
    config: dict[str, Any],
) -> tuple[dict[str, Any], list[str]]:
    warnings: list[str] = []
    rows = list(table.get("rows", []))
    filters = config.get("filters") or {}
    search = clean_text(filters.get("search", "")).lower()
    if search:
        rows = [
            r for r in rows
            if search in " ".join(
                str(r.get(k, "")) for k in (
                    "indicator", "document", "period", "value_display", "unit",
                    "source_display", "missing_documents", "document_name",
                )
            ).lower()
        ]
    min_value = filters.get("min_value")
    max_value = filters.get("max_value")
    if min_value is not None:
        try:
            mv = float(min_value)
            rows = [r for r in rows if isinstance(r.get("value_num"), (int, float)) and r["value_num"] >= mv]
        except (TypeError, ValueError):
            warnings.append("Фильтр min_value имеет нечисловое значение и не применён.")
    if max_value is not None:
        try:
            mv = float(max_value)
            rows = [r for r in rows if isinstance(r.get("value_num"), (int, float)) and r["value_num"] <= mv]
        except (TypeError, ValueError):
            warnings.append("Фильтр max_value имеет нечисловое значение и не применён.")
    periods = filters.get("periods") or []
    if periods:
        rows = [r for r in rows if str(r.get("period", "")) in {str(p) for p in periods}]
    units = filters.get("units") or []
    if units:
        rows = [r for r in rows if str(r.get("unit", "")) in {str(u) for u in units}]
    trend = filters.get("trend")
    if trend:
        allowed = {"up": {"рост"}, "down": {"снижение"}, "same": {"без изменений"}}
        rows = [r for r in rows if str(r.get("trend", "")) in allowed.get(trend, set())]

    group_by = config.get("group_by")
    if group_by:
        for r in rows:
            r["_group"] = str(r.get(group_by, ""))
        rows.sort(key=lambda r: (r.get("_group", ""), str(r.get("indicator", ""))))

    sort = config.get("sort") or []
    if isinstance(sort, list):
        for item in reversed(sort):
            if not isinstance(item, dict):
                continue
            key = item.get("key")
            if not key:
                continue
            reverse = str(item.get("dir", "asc")).lower() == "desc"
            def sort_key(r, k=key):
                v = r.get(k)
                if isinstance(v, (int, float)):
                    return (0, v)
                return (1, str(v or "").lower())
            rows.sort(key=sort_key, reverse=reverse)

    limit = config.get("limit")
    if limit and len(rows) > int(limit):
        warnings.append(f"Показаны первые {int(limit)} строк из {len(rows)}.")
        rows = rows[: int(limit)]

    columns = list(table.get("columns", []))
    requested_columns = config.get("columns")
    if requested_columns:
        allowed = set(requested_columns) | {"source_display"}
        filtered = [c for c in columns if c.get("key") in allowed]
        if filtered:
            columns = filtered
    result = {**table, "rows": rows, "columns": columns, "row_count": len(rows)}
    if group_by:
        result["group_by"] = group_by
    return result, warnings


def build_table(db: Session, project_id: int, config: dict[str, Any]) -> dict[str, Any]:
    doc_ids = config.get("document_ids") or None
    labels = config.get("metric_labels") or None
    years = [str(y) for y in (config.get("years") or []) if str(y)]
    table_type = config.get("type", "summary")
    docs = an.list_documents(db, project_id, doc_ids)
    if not docs:
        return {
            "tables": [],
            "warnings": ["Нет документов для построения таблицы."],
            "meta": {"type": table_type},
        }
    records, truncated = an.load_metrics(db, project_id, [d.id for d in docs])
    clusters = _select_clusters(records, labels, config.get("query", ""))
    selected, skipped = _filter_clusters_by_years(clusters, years)
    warnings: list[str] = []
    if truncated:
        warnings.append("Данные ограничены максимальным объёмом анализа.")
    if skipped:
        warnings.append(f"{skipped} значений без периода не включены.")
    if labels and not selected:
        warnings.append("Выбранные показатели не найдены.")

    if table_type in {"comparison", "differences"}:
        result = an.build_comparison(selected, docs)
    elif table_type == "dynamics":
        result = an.build_dynamics(selected, docs)
    elif table_type == "extrema":
        result = an.build_extrema(selected)
    elif table_type == "missing":
        result = an.build_missing(selected, docs, years)
    elif table_type == "contradictions":
        result = an.build_contradictions(selected)
    elif table_type == "threshold":
        threshold = config.get("threshold") or {}
        result = an.build_threshold(selected, threshold)
    else:
        result = an.build_summary_table(selected, docs)
    tables = []
    for table in result.get("tables", []):
        filtered, fw = _apply_table_filters(table, config)
        tables.append(filtered)
        warnings.extend(fw)
    return {
        "tables": tables,
        "warnings": list(dict.fromkeys(warnings + result.get("warnings", []))),
        "methods": result.get("methods", []),
        "meta": {
            **(result.get("meta") or {}),
            "type": table_type,
            "documents": len(docs),
            "labels": [c.label for c in selected],
            "years": years,
        },
    }


def build_chart(db: Session, project_id: int, config: dict[str, Any]) -> dict[str, Any]:
    doc_ids = config.get("document_ids") or None
    labels = config.get("metric_labels") or None
    years = [str(y) for y in (config.get("years") or []) if str(y)]
    docs = an.list_documents(db, project_id, doc_ids)
    if not docs:
        return {"charts": [], "warnings": ["Нет документов для построения графика."], "meta": {}}
    records, truncated = an.load_metrics(db, project_id, [d.id for d in docs])
    clusters = _select_clusters(records, labels, config.get("query", ""))
    selected, skipped = _filter_clusters_by_years(clusters, years)
    warnings: list[str] = []
    if truncated:
        warnings.append("Данные ограничены максимальным объёмом анализа.")
    if skipped:
        warnings.append(f"{skipped} значений без периода не включены.")
    if not selected:
        warnings.append("Выберите хотя бы один показатель с числовыми данными.")
        return {"charts": [], "warnings": warnings, "meta": {}}
    chart_type = config.get("chart_type", "line")
    if chart_type not in {"line", "bar", "stacked", "pie", "scatter", "histogram", "heatmap"}:
        chart_type = "line"
    colors = [c for c in (config.get("colors") or []) if isinstance(c, str) and c.startswith("#")]
    charts = an.build_chart_config(
        selected,
        chart_type=chart_type,
        x_axis=config.get("x_axis", "period"),
        title=clean_text(config.get("title", "")),
        log_y=bool(config.get("log_y")),
        y_min=config.get("y_min"),
        y_max=config.get("y_max"),
        colors=colors or None,
    )
    if not charts:
        warnings.append("Не удалось построить график: недостаточно числовых значений.")
    for chart in charts:
        if chart.get("normalized"):
            warnings.append(
                "В одном графике встретились разные единицы измерения; значения приведены к базовой единице. "
                "Проверьте подписи и источники."
            )
            break
    return {
        "charts": charts,
        "warnings": list(dict.fromkeys(warnings)),
        "meta": {
            "type": chart_type,
            "documents": len(docs),
            "labels": [c.label for c in selected],
            "years": years,
        },
    }


def compare_documents(
    db: Session,
    project_id: int,
    document_ids: list[int],
    metric_labels: list[str] | None = None,
    years: list[str] | None = None,
) -> dict[str, Any]:
    docs = an.list_documents(db, project_id, document_ids)
    warnings: list[str] = []
    if len(docs) < 2:
        warnings.append("Для сравнения выберите минимум два обработанных документа.")
    records, truncated = an.load_metrics(db, project_id, [d.id for d in docs])
    clusters = _select_clusters(records, metric_labels)
    selected, skipped = _filter_clusters_by_years(clusters, [str(y) for y in (years or []) if str(y)])
    if skipped:
        warnings.append(f"{skipped} значений без периода не включены.")
    if not selected:
        warnings.append("Не найдено показателей для сравнения. Проверьте выбор документов.")
    result = an.build_comparison(selected, docs)
    warnings.extend(result.get("warnings", []))
    charts = an.chart_spec_from_metrics(selected, chart_type="bar", title_prefix="Сравнение: ", max_charts=4)
    text_diff = None
    if len(docs) == 2:
        text_diff = an.compare_texts(db, docs[0], docs[1])
        warnings.extend(text_diff.get("warnings", []))
        extra_findings, extra_citations = [], []
        for item in text_diff.get("changed", [])[:10]:
            extra_findings.append(
                {
                    "type": "text_changed",
                    "text": f"Изменена формулировка ({item['similarity']}% сходства): "
                            f"«{item['old'][:200]}» → «{item['new'][:200]}» "
                            f"[«{docs[0].original_name}», стр. {item['old_page']}; "
                            f"«{docs[1].original_name}», стр. {item['new_page']}].",
                    "document_id": docs[0].id,
                    "page": item["old_page"],
                    "severity": "info",
                }
            )
        result["findings"] = result.get("findings", []) + extra_findings
        result["citations"] = result.get("citations", []) + [
            {
                "document_id": docs[0].id, "document": docs[0].original_name,
                "page": item["old_page"], "snippet": item["old"],
                "source_kind": "text", "confidence": 0.9,
            }
            for item in text_diff.get("changed", [])[:10]
        ]
        result["text_diff"] = text_diff
    elif len(docs) > 2:
        warnings.append("Текстовое сравнение доступно для двух документов; выполнено числовое сравнение всех выбранных.")
    result["charts"] = charts
    result["warnings"] = list(dict.fromkeys(warnings))
    result["meta"] = {
        **(result.get("meta") or {}),
        "documents": [{"id": d.id, "name": d.original_name, "pages": d.page_count} for d in docs],
        "labels": [c.label for c in selected],
        "truncated": truncated,
    }
    return result
