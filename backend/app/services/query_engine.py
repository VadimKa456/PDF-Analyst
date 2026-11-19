"""Планирование запроса и сборка аналитического ответа (RAG + локальный движок)."""
from __future__ import annotations

import json
import logging
import re
import time
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.orm import Session

from ..models import Analysis, Document, Project
from ..utils import (
    clean_text,
    detect_unit,
    format_number,
    parse_number,
    short_snippet,
    tokenize,
    value_with_unit,
)
from . import analytics as an
from .ai_client import AIClient, AIError
from .retrieval import hybrid_search
from .runtime_settings import get_runtime_settings

logger = logging.getLogger(__name__)

INTENTS = {
    "compare", "dynamics", "extrema", "average", "missing", "threshold",
    "contradictions", "table", "search", "diff", "summary",
}


@dataclass
class Plan:
    intent: str = "search"
    years: list[str] = field(default_factory=list)
    labels: list[str] = field(default_factory=list)
    threshold: dict[str, Any] | None = None
    wants_chart: bool = False
    wants_table: bool = False
    chart_type: str = "line"
    want_text_diff: bool = False
    reasons: list[str] = field(default_factory=list)


def detect_intent(query: str, has_labels: bool) -> tuple[str, list[str]]:
    q = clean_text(query).lower()
    reasons: list[str] = []

    def hit(pattern: str) -> bool:
        if re.search(pattern, q, re.I):
            return True
        return False

    if hit(r"различи\w*\s+(?:между\s+)?верси|основн\w*\s+изменени|что\s+изменилось|отличи\w*\s+верси|diff"):
        return "diff", ["Запрос на сравнение версий/изменений в тексте"]
    if hit(r"противореч|contradict|несогласован"):
        return "contradictions", ["Запрос на поиск противоречий"]
    if hit(r"отсутств\w*|недостающ\w*|пропущ\w*|не\s+хватает|нет\s+данн|missing\s+data|missing"):
        return "missing", ["Запрос на поиск отсутствующих данных"]
    if hit(r"максим|миним|наибольш|наименьш|max(?:imum)?|min(?:imum)?"):
        return "extrema", ["Запрос на максимум/минимум"]
    if hit(r"средн\w*|average|avg\b|mean\b"):
        return "average", ["Запрос на среднее значение"]
    if hit(r"порог|превыш\w*|больше|меньше|выше|ниже|более|менее|свыше|>\s*\d|<\s*\d|threshold"):
        return "threshold", ["Запрос на фильтрацию по порогу"]
    if hit(r"сравн|сопостав|различ|отличи|compare|versus|vs\b"):
        if hit(r"график|диаграм|chart|plot"):
            reasons.append("Запрос на сравнение с визуализацией")
        return "compare", reasons + ["Запрос на сравнение показателей"]
    if hit(r"динамик|тренд|рост|снижен|вырос|упал|trend|growth|decline"):
        return "dynamics", ["Запрос на динамику показателей"]
    if hit(r"график|диаграм|chart|plot|визуализ"):
        return "dynamics", ["Запрос на построение графика"]
    if hit(r"таблиц|сводн|table"):
        return "table", ["Запрос на таблицу"]
    if hit(r"найди|найти|покажи|упомин|где\s|find|search|mention|locate"):
        return "search", ["Запрос на поиск информации"]
    if has_labels:
        return "summary", ["Запрос на сводку по показателям"]
    return "search", []


def parse_threshold(query: str) -> dict[str, Any] | None:
    q = clean_text(query)
    patterns = [
        (r"(?:больше|выше|превыша\w*|более|свыше|greater than|above|over|>)\s*(?:чем\s*)?([\d\s.,]+)\s*([%₽$€A-Za-zА-Яа-я.\s]{0,24})", ">"),
        (r"(?:меньше|ниже|менее|less than|below|under|<)\s*(?:чем\s*)?([\d\s.,]+)\s*([%₽$€A-Za-zА-Яа-я.\s]{0,24})", "<"),
        (r"порог\w*\s*[:=]?\s*([\d\s.,]+)\s*([%₽$€A-Za-zА-Яа-я.\s]{0,24})", ">"),
    ]
    for pattern, op in patterns:
        m = re.search(pattern, q, re.I)
        if not m:
            continue
        value = parse_number(m.group(1))
        if value is None or 1900 <= value <= 2100 and "." not in m.group(1) and "," not in m.group(1):
            continue
        suffix = m.group(2) or ""
        unit = detect_unit(suffix) or detect_unit(q[m.end(): m.end() + 25])
        info = value_with_unit(m.group(1) + " " + suffix)
        if info is None:
            info = {
                "value": value, "unit": unit.display if unit else "", "dimension": unit.dimension if unit else "",
                "scale": unit.scale if unit else 1.0, "currency": unit.currency if unit else "",
                "normalized_value": value * (unit.scale if unit else 1.0),
            }
        info["op"] = op
        return info
    return None


def detect_chart_type(query: str) -> str:
    q = query.lower()
    if re.search(r"накоп|stack", q):
        return "stacked"
    if re.search(r"кругов|pie|пончик|donut", q):
        return "pie"
    if re.search(r"гистограм|histogram", q):
        return "histogram"
    if re.search(r"точеч|scatter", q):
        return "scatter"
    if re.search(r"теплов|heatmap", q):
        return "heatmap"
    if re.search(r"столбч|bar\b", q):
        return "bar"
    return "line"


def build_plan(query: str, clusters: list[an.LabelCluster], explicit_labels: list[str] | None = None) -> Plan:
    q = query.lower()
    selected = an.find_relevant_clusters(query, clusters, explicit_labels)
    intent, reasons = detect_intent(query, bool(selected))
    plan = Plan(intent=intent, reasons=reasons)
    plan.years = an.parse_period_filter(query)
    plan.labels = [c.normalized for c in selected]
    plan.threshold = parse_threshold(query)
    plan.chart_type = detect_chart_type(query)
    plan.wants_chart = bool(re.search(r"график|диаграм|визуал|chart|plot|динамик|тренд", q))
    plan.wants_table = intent in {
        "compare", "dynamics", "extrema", "average", "missing", "threshold",
        "contradictions", "table", "summary",
    } or bool(re.search(r"таблиц|сводн|table", q))
    plan.want_text_diff = bool(
        re.search(r"текст|формулиров|положен|различи|изменен|верси|отличи|сравни\s+два", q)
    )
    if intent == "dynamics" and not plan.wants_chart:
        plan.wants_chart = True
    # сравнение за несколько периодов полезно сопровождать графиком
    if intent == "compare" and len(set(plan.years)) > 1:
        plan.wants_chart = True
    return plan


def _filter_clusters_by_years(
    clusters: list[an.LabelCluster], years: list[str]
) -> tuple[list[an.LabelCluster], int]:
    if not years:
        return clusters, 0
    result = []
    skipped_no_period = 0
    for c in clusters:
        metrics = []
        for m in c.metrics:
            if not m.period:
                skipped_no_period += 1
                continue
            if any(m.period.startswith(y) for y in years):
                metrics.append(m)
        if metrics:
            nc = an.LabelCluster(
                normalized=c.normalized, label=c.label, members=list(c.members), metrics=metrics
            )
            for m in metrics:
                m.cluster = nc.normalized
            result.append(nc)
    return result, skipped_no_period


def _match_documents_by_query(query: str, docs: list[Document]) -> list[Document]:
    q = clean_text(query).lower().replace("ё", "е")
    matched = []
    for d in docs:
        stem_name = d.original_name.lower().replace("ё", "е")
        stem_name = re.sub(r"\.pdf$", "", stem_name)
        parts = [p for p in re.split(r"[_\-\s.]+", stem_name) if len(p) >= 4]
        if stem_name and (stem_name in q or (len(parts) >= 2 and all(p in q for p in parts[:3]))):
            matched.append(d)
    return matched if 1 <= len(matched) <= 4 else []


def _docs_payload(docs: list[Document]) -> list[dict[str, Any]]:
    return [
        {
            "id": d.id,
            "name": d.original_name,
            "pages": d.page_count,
            "status": d.status,
            "ocr_pages": d.ocr_pages,
            "avg_confidence": d.avg_confidence,
        }
        for d in docs
    ]


def _finding_with_source(f: dict[str, Any]) -> str:
    text = f.get("text", "")
    if f.get("document_id") and "стр." not in text:
        doc = f.get("document")
        page = f.get("page")
        if doc and page:
            text += f" [{doc}, стр. {page}]"
        elif page:
            text += f" [стр. {page}]"
    return text


def _compose_answer(
    query: str,
    plan: Plan,
    docs: list[Document],
    selected: list[an.LabelCluster],
    result: dict[str, Any],
    metric_count: int,
    truncated: bool,
) -> str:
    parts: list[str] = []
    pages = sum(d.page_count or 0 for d in docs)
    intros = {
        "compare": "Выполнено сравнение показателей между документами.",
        "dynamics": "Рассчитана динамика показателей.",
        "extrema": "Определены максимальные и минимальные значения.",
        "average": "Рассчитаны средние значения.",
        "missing": "Проверено наличие данных по документам и периодам.",
        "threshold": "Выполнена фильтрация значений по порогу.",
        "contradictions": "Выполнена проверка числовых противоречий между документами.",
        "table": "Сформирована сводная таблица.",
        "diff": "Выполнено сравнение документов и их формулировок.",
        "search": "Выполнен поиск по содержимому документов.",
        "summary": "Сформирована аналитическая сводка.",
    }
    parts.append(intros.get(plan.intent, "Выполнен анализ документов."))
    parts.append(
        f"Проанализировано документов: {len(docs)}; страниц: {pages}. "
        f"Использовано извлечённых числовых значений: {metric_count}."
    )
    if plan.years:
        parts.append(f"Период анализа: {', '.join(plan.years)}.")
    if plan.threshold and plan.threshold.get("value") is not None:
        parts.append(
            f"Порог: {plan.threshold.get('op')} {format_number(plan.threshold.get('value'))} "
            f"{plan.threshold.get('unit', '')}".strip() + "."
        )
    if result.get("summary"):
        parts.append(str(result["summary"]))
    findings = result.get("findings") or []
    if findings:
        parts.append("Ключевые результаты:")
        for f in findings[:12]:
            parts.append("• " + _finding_with_source(f))
    if not findings and not any(t.get("rows") for t in result.get("tables", [])):
        parts.append(
            "В выбранных документах не найдено данных, подтверждающих ответ на запрос. "
            "Проверьте формулировку показателя, выбранные документы и период."
        )
    warnings = result.get("warnings") or []
    if truncated:
        warnings = list(warnings) + [
            "Объём извлечённых показателей превысил лимит анализа; часть данных не участвовала в расчёте."
        ]
    if warnings:
        parts.append("Ограничения и предупреждения:")
        for w in warnings[:6]:
            parts.append("• " + w)
    answer = "\n\n".join(p for p in parts if p)
    if len(answer) > 8000:
        answer = answer[:7990].rsplit(" ", 1)[0] + "…"
    return answer


def _allowed_numbers(payload: Any) -> set[float]:
    text = json.dumps(payload, ensure_ascii=False, default=str)
    values: set[float] = set()
    for token in re.findall(r"(?<![\w])[-−]?\d+(?:[.,]\d+)?", text):
        cleaned = token.replace("−", "-").replace(",", ".")
        try:
            values.add(round(float(cleaned), 6))
        except ValueError:
            continue
    return values


def _validate_ai_text(text: str, allowed: set[float]) -> tuple[bool, str | None]:
    for token in re.findall(r"(?<![\w])[-−]?\d+(?:[.,]\d+)?", text):
        cleaned = token.replace("−", "-").replace(",", ".")
        try:
            value = round(float(cleaned), 6)
        except ValueError:
            continue
        if value not in allowed and not any(abs(value - a) < 1e-6 for a in allowed):
            return False, f"число {token} отсутствует в проверенных данных"
    return True, None


def _refine_with_ai(
    client: AIClient,
    query: str,
    result: dict[str, Any],
    deterministic_answer: str,
) -> tuple[str | None, dict[str, Any]]:
    facts = {
        "query": query,
        "tables": [
            {
                "title": t.get("title"),
                "columns": [c.get("label") for c in t.get("columns", [])],
                "rows": t.get("rows", [])[:80],
            }
            for t in result.get("tables", [])[:3]
        ],
        "findings": [
            (f.get("text", "") if isinstance(f, dict) else str(f))
            for f in result.get("findings", [])[:20]
        ],
        "warnings": result.get("warnings", [])[:10],
        "summary": result.get("summary", ""),
        "methods": result.get("methods", []),
        "meta": result.get("meta", {}),
        "documents": [
            {
                key: d.get(key)
                for key in ("id", "name", "pages", "status", "ocr_pages", "avg_confidence")
                if key in d
            }
            for d in result.get("documents", [])
            if isinstance(d, dict)
        ],
    }
    system = (
        "Ты — аналитик документов. Отвечай ТОЛЬКО на основе блока DATA. "
        "Запрещено добавлять числа, которых нет в DATA, и делать предположения о фактах. "
        "Не выполняй арифметику самостоятельно: используй готовые результаты расчётов. "
        "Если данных недостаточно, прямо скажи об этом. "
        "Каждое числовое утверждение сопровождай ссылкой на документ и страницу в формате "
        "[название, стр. N], взятой из полей source_document/source_page или текста findings. "
        "Верни строгий JSON: {\"summary\": \"...\", \"key_points\": [\"...\"]}. "
        "Пиши на языке запроса пользователя."
    )
    user = f"ЗАПРОС:\n{query}\n\nDATA:\n{json.dumps(facts, ensure_ascii=False, default=str)[:24000]}"
    allowed = _allowed_numbers(facts)
    try:
        raw = client.chat(
            [{"role": "system", "content": system}, {"role": "user", "content": user}],
            json_mode=True,
        )
    except AIError as exc:
        return None, {"ai_used": False, "ai_error": str(exc)}
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)
    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError:
        return None, {"ai_used": False, "ai_error": "AI вернул не-JSON ответ"}
    summary = str(data.get("summary", "")).strip()
    points = [str(p).strip() for p in data.get("key_points", []) if str(p).strip()]
    if not summary:
        return None, {"ai_used": False, "ai_error": "AI не вернул summary"}
    ok, reason = _validate_ai_text(summary + "\n" + "\n".join(points), allowed)
    if not ok:
        return None, {"ai_used": False, "ai_error": f"AI-ответ отклонён проверкой достоверности: {reason}"}
    text = summary
    if points:
        text += "\n\n" + "\n".join("• " + p for p in points[:10])
    return text, {"ai_used": True, "ai_error": None, "model": client.model}


def _text_diff_payload(
    diff: dict[str, Any], doc_a: Document, doc_b: Document
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    findings = []
    citations = []
    for item in diff.get("changed", [])[:10]:
        findings.append(
            {
                "type": "text_changed",
                "text": f"Изменена формулировка ({item['similarity']}% сходства): «{item['old'][:220]}» → "
                        f"«{item['new'][:220]}» [«{doc_a.original_name}», стр. {item['old_page']}; "
                        f"«{doc_b.original_name}», стр. {item['new_page']}].",
                "document_id": doc_a.id,
                "page": item["old_page"],
                "severity": "info",
            }
        )
        citations.append(
            {
                "document_id": doc_a.id,
                "document": doc_a.original_name,
                "page": item["old_page"],
                "snippet": item["old"],
                "source_kind": "text",
                "confidence": 0.9,
            }
        )
        citations.append(
            {
                "document_id": doc_b.id,
                "document": doc_b.original_name,
                "page": item["new_page"],
                "snippet": item["new"],
                "source_kind": "text",
                "confidence": 0.9,
            }
        )
    for kind, label in (("added", "Добавлено"), ("removed", "Удалено")):
        for item in diff.get(kind, [])[:8]:
            doc = doc_b if kind == "added" else doc_a
            findings.append(
                {
                    "type": f"text_{kind}",
                    "text": f"{label}: «{item['text'][:240]}» [«{doc.original_name}», стр. {item['page']}].",
                    "document_id": doc.id,
                    "page": item["page"],
                    "severity": "info",
                }
            )
            citations.append(
                {
                    "document_id": doc.id,
                    "document": doc.original_name,
                    "page": item["page"],
                    "snippet": item["text"],
                    "source_kind": "text",
                    "confidence": 0.9,
                }
            )
    return findings, citations


def _extrema_chart(clusters: list[an.LabelCluster]) -> list[dict[str, Any]]:
    if not clusters:
        return []
    labels = []
    maxima = []
    minima = []
    custom_max = []
    custom_min = []
    for c in clusters[:8]:
        values = [m for m in c.metrics if m.normalized_value is not None]
        if not values:
            continue
        # не смешиваем разные размерности: берём доминирующую
        dominant = max({m.dimension for m in values}, key=lambda d: sum(1 for m in values if m.dimension == d))
        values = [m for m in values if m.dimension == dominant]
        if not values:
            continue
        mx = max(values, key=lambda m: m.normalized_value or 0)
        mn = min(values, key=lambda m: m.normalized_value or 0)
        labels.append(c.label)
        maxima.append(mx.normalized_value or 0)
        minima.append(mn.normalized_value or 0)
        custom_max.append([mx.document_id, mx.page, mx.document_name, an._display_value(mx.value, mx.unit)])
        custom_min.append([mn.document_id, mn.page, mn.document_name, an._display_value(mn.value, mn.unit)])
    if not labels:
        return []
    layout = an._base_layout("Максимум и минимум по показателям", "Показатель", "Нормализованное значение")
    layout["barmode"] = "group"
    layout["height"] = 400
    data = [
        {
            "type": "bar", "name": "Максимум", "x": labels, "y": maxima,
            "marker": {"color": "#4f46e5"}, "customdata": custom_max,
            "hovertemplate": "%{x}<br>%{customdata[3]}<br>%{customdata[2]}, стр. %{customdata[1]}<extra></extra>",
        },
        {
            "type": "bar", "name": "Минимум", "x": labels, "y": minima,
            "marker": {"color": "#94a3b8"}, "customdata": custom_min,
            "hovertemplate": "%{x}<br>%{customdata[3]}<br>%{customdata[2]}, стр. %{customdata[1]}<extra></extra>",
        },
    ]
    return [
        {
            "id": "chart-extrema",
            "title": "Максимум и минимум по показателям",
            "type": "bar",
            "unit": "нормализованные значения",
            "plotly": {"data": data, "layout": layout},
            "point_count": len(labels) * 2,
        }
    ]


def _average_chart(clusters: list[an.LabelCluster]) -> list[dict[str, Any]]:
    labels = []
    values = []
    custom = []
    for c in clusters[:10]:
        group = [m for m in c.metrics if m.normalized_value is not None]
        if not group:
            continue
        dominant = max({m.dimension for m in group}, key=lambda d: sum(1 for m in group if m.dimension == d))
        group = [m for m in group if m.dimension == dominant]
        if not group:
            continue
        avg = sum(m.normalized_value or 0 for m in group) / len(group)
        labels.append(c.label)
        values.append(avg)
        custom.append([len(group), "среднее по нормализованным значениям"])
    if not labels:
        return []
    layout = an._base_layout("Средние значения показателей", "Показатель", "Среднее (нормализованное)")
    layout["height"] = 380
    data = [
        {
            "type": "bar", "x": labels, "y": values, "marker": {"color": "#0891b2"},
            "customdata": custom, "hovertemplate": "%{x}<br>%{y}<br>Значений: %{customdata[0]}<extra></extra>",
        }
    ]
    return [
        {
            "id": "chart-average",
            "title": "Средние значения показателей",
            "type": "bar",
            "unit": "нормализованные значения",
            "plotly": {"data": data, "layout": layout},
            "point_count": len(labels),
        }
    ]


def _charts_for(
    intent: str,
    selected: list[an.LabelCluster],
    plan: Plan,
) -> list[dict[str, Any]]:
    if not selected:
        return []
    if intent == "dynamics":
        return an.chart_spec_from_metrics(
            selected, chart_type="line", title_prefix="Динамика: ", max_charts=4
        )
    if intent in {"compare", "diff", "threshold", "table", "summary"}:
        chart_type = plan.chart_type if plan.chart_type in {
            "line", "bar", "stacked", "pie", "scatter", "histogram", "heatmap"
        } else "bar"
        if not plan.wants_chart and intent not in {"table"}:
            return []
        return an.chart_spec_from_metrics(
            selected, chart_type=chart_type if chart_type != "line" else "bar",
            title_prefix="Сравнение: ", max_charts=4,
        )
    if intent == "extrema":
        return _extrema_chart(selected)
    if intent == "average":
        return _average_chart(selected)
    return []


def _empty_result(reason: str) -> dict[str, Any]:
    return {
        "summary": "",
        "findings": [],
        "warnings": [reason],
        "tables": [],
        "charts": [],
        "citations": [],
        "methods": [],
        "meta": {},
    }


def analyze(
    db: Session,
    project: Project,
    query: str,
    document_ids: list[int] | None = None,
    metric_labels: list[str] | None = None,
    options: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Возвращает (result, plan_dict)."""
    started = time.perf_counter()
    options = options or {}
    docs = an.list_documents(db, project.id, document_ids)
    ready_docs = [d for d in docs if d.status == "ready"]
    warnings: list[str] = []
    if not ready_docs:
        result = _empty_result(
            "Нет обработанных документов для анализа. Загрузите PDF и дождитесь окончания обработки."
        )
        result["answer"] = result["warnings"][0]
        result["documents"] = _docs_payload(docs)
        result["meta"]["duration_ms"] = int((time.perf_counter() - started) * 1000)
        return result, {"intent": "search", "years": [], "labels": [], "threshold": None}

    # если в запросе явно названы файлы — сужаем набор
    if not document_ids:
        mentioned = _match_documents_by_query(query, ready_docs)
        if mentioned:
            ready_docs = mentioned
            warnings.append(
                "Набор документов сужен по упоминаниям в запросе: "
                + ", ".join(d.original_name for d in mentioned)
            )

    records, truncated = an.load_metrics(db, project.id, [d.id for d in ready_docs])
    if truncated:
        warnings.append("Загружено максимальное количество показателей; часть данных не использована.")
    clusters = an.cluster_labels(records)
    if metric_labels:
        explicit = [c for c in clusters if any(
            an.canonical_label(m) in {an.canonical_label(x) for x in metric_labels}
            or any(an.canonical_label(x) in m or m in an.canonical_label(x) for x in metric_labels)
            for m in c.members
        )]
        if explicit:
            # сохраняем порядок выбранных пользователем показателей
            selected = explicit
        else:
            selected = an.find_relevant_clusters(query, clusters, metric_labels)
    else:
        selected = an.find_relevant_clusters(query, clusters)

    plan = build_plan(query, clusters, metric_labels)
    needs_metrics = plan.intent in {
        "compare", "dynamics", "extrema", "average", "missing", "threshold",
        "contradictions", "table", "diff", "summary",
    }
    if not selected and needs_metrics:
        if metric_labels:
            warnings.append(
                "Указанные показатели не найдены среди извлечённых данных. "
                "Проверьте названия показателей или выберите другой документ."
            )
        else:
            selected = clusters[: min(8, len(clusters))]
            if selected:
                warnings.append(
                    "Конкретные показатели в запросе не распознаны; использованы наиболее часто встречающиеся показатели. "
                    "Уточните названия показателей для точного анализа."
                )
    if plan.intent == "threshold" and plan.threshold is None:
        warnings.append(
            "В запросе не указан числовой порог. Укажите значение, например: «выручка больше 100 млн руб.»."
        )

    selected, skipped_no_period = _filter_clusters_by_years(selected, plan.years)
    if skipped_no_period:
        warnings.append(
            f"{skipped_no_period} значений без определённого периода не вошли в анализ за указанные годы."
        )
    if plan.years and not selected:
        warnings.append("За указанные годы не найдено значений по выбранным показателям.")

    metric_count = sum(len(c.metrics) for c in selected)
    result: dict[str, Any]

    if plan.intent == "threshold":
        result = an.build_threshold(selected, plan.threshold)
    elif plan.intent == "compare":
        result = an.build_comparison(selected, ready_docs)
    elif plan.intent == "dynamics":
        result = an.build_dynamics(selected, ready_docs)
    elif plan.intent == "extrema":
        result = an.build_extrema(selected)
    elif plan.intent == "average":
        result = an.build_average(selected)
    elif plan.intent == "missing":
        result = an.build_missing(selected, ready_docs, plan.years)
    elif plan.intent == "contradictions":
        result = an.build_contradictions(selected)
    elif plan.intent == "table":
        result = an.build_summary_table(selected, ready_docs)
    elif plan.intent == "diff":
        result = an.build_comparison(selected, ready_docs) if selected else _empty_result("")
    else:  # search / summary
        runtime = get_runtime_settings(db)
        client = AIClient(runtime)
        hits, search_warnings = hybrid_search(
            db, project.id, query, [d.id for d in ready_docs], limit=10,
            client=client, semantic_enabled=bool(runtime.get("semantic_search")),
        )
        warnings.extend(search_warnings)
        if selected:
            if plan.intent == "summary":
                result = an.build_summary_table(selected, ready_docs)
                result["findings"] = result["findings"] + [
                    {
                        "type": "search",
                        "text": f"«{h.document_name}», стр. {h.page}: {h.snippet}",
                        "document_id": h.document_id,
                        "page": h.page,
                        "severity": "info",
                    }
                    for h in hits[:5]
                ]
                result["citations"].extend(
                    {
                        "document_id": h.document_id, "document": h.document_name,
                        "page": h.page, "snippet": h.snippet, "source_kind": "text",
                        "confidence": 0.9,
                    }
                    for h in hits
                )
            else:
                result = an.build_search_result(hits, selected, warnings)
                warnings = []
        else:
            result = an.build_search_result(hits, [], warnings)
            warnings = []

    result["warnings"] = list(dict.fromkeys(warnings + result.get("warnings", [])))

    # текстовое сравнение
    text_diff = None
    if plan.want_text_diff or plan.intent in {"diff", "contradictions", "compare"}:
        if len(ready_docs) == 2:
            diff = an.compare_texts(db, ready_docs[0], ready_docs[1])
            text_diff = diff
            result["warnings"].extend(diff.get("warnings", []))
            extra_findings, extra_citations = _text_diff_payload(diff, ready_docs[0], ready_docs[1])
            result["findings"] = result.get("findings", []) + extra_findings
            result["citations"] = result.get("citations", []) + extra_citations
            if plan.intent == "contradictions":
                text_conf = an.contradiction_from_text_diff(diff)
                result["findings"] = result.get("findings", []) + text_conf
            result["findings"].insert(
                0,
                {
                    "type": "text_diff",
                    "text": f"Текстовое сравнение «{ready_docs[0].original_name}» и "
                            f"«{ready_docs[1].original_name}»: {diff.get('summary', '')}",
                    "severity": "info",
                },
            )
        elif len(ready_docs) > 2 and plan.intent == "diff":
            result["warnings"].append(
                "Для текстового сравнения выберите ровно два документа; числовое сравнение выполнено по всем выбранным."
            )

    # графики
    charts = result.get("charts") or []
    if plan.wants_chart or plan.intent in {"dynamics", "extrema", "average"}:
        if not charts:
            charts = _charts_for(plan.intent, selected, plan)
        if plan.wants_chart and not charts:
            result["warnings"].append("Графики не построены: нет числовых данных по выбранным показателям.")
    result["charts"] = charts

    # ответ локального движка
    deterministic = _compose_answer(query, plan, ready_docs, selected, result, metric_count, truncated)
    result["answer"] = deterministic
    result["meta"] = {
        **(result.get("meta") or {}),
        "engine": "local",
        "model": "Локальный аналитический движок",
        "ai_used": False,
        "metric_values": metric_count,
        "selected_labels": [c.label for c in selected],
        "label_variants": {c.normalized: c.members for c in selected},
        "years": plan.years,
        "threshold": plan.threshold,
        "documents_used": len(ready_docs),
        "duration_ms": int((time.perf_counter() - started) * 1000),
        "truncated": truncated,
    }

    # AI-формулировка (не расчёты) + проверка чисел
    runtime = get_runtime_settings(db)
    client = AIClient(runtime)
    if client.available and result.get("findings") or (client.available and result.get("tables")):
        refined, ai_meta = _refine_with_ai(client, query, result, deterministic)
        result["meta"].update(ai_meta)
        if refined:
            result["answer"] = refined
            result["ai_summary"] = refined
            result["meta"]["engine"] = "ai+local"
            result["meta"]["model"] = client.model
        elif ai_meta.get("ai_error"):
            result["warnings"].append(
                "AI-модель не использована для формулировки: " + str(ai_meta["ai_error"])[:300]
            )
    result["documents"] = _docs_payload(ready_docs)
    result["query"] = query
    result["intent"] = plan.intent
    result["plan"] = {
        "intent": plan.intent,
        "years": plan.years,
        "labels": [c.label for c in selected],
        "threshold": plan.threshold,
        "reasons": plan.reasons,
    }
    if text_diff is not None:
        result["text_diff"] = text_diff
    result["citations"] = an._dedupe_citations(result.get("citations", []))
    result["warnings"] = list(dict.fromkeys(result.get("warnings", [])))
    return result, result["plan"]


def title_for_query(query: str, intent: str) -> str:
    q = clean_text(query)
    if len(q) <= 110:
        return q
    return q[:107].rsplit(" ", 1)[0] + "…"


def save_analysis(
    db: Session,
    project_id: int,
    query: str,
    result: dict[str, Any],
) -> Analysis:
    analysis = Analysis(
        project_id=project_id,
        title=title_for_query(query, result.get("intent", "search")),
        query=query,
        intent=result.get("intent", "search"),
        answer=result.get("answer", ""),
        result=result,
        sources=result.get("citations", []),
        charts=result.get("charts", []),
        documents=result.get("documents", []),
        model=str((result.get("meta") or {}).get("model", "local")),
        duration_ms=int((result.get("meta") or {}).get("duration_ms", 0)),
    )
    db.add(analysis)
    db.commit()
    db.refresh(analysis)
    result["id"] = analysis.id
    result["title"] = analysis.title
    analysis.result = result
    db.commit()
    return analysis
