"""Аналитический движок.

Все вычисления выполняются на Python, LLM не используется для расчётов.
Каждый показатель хранит документ, страницу и фрагмент-источник.
"""
from __future__ import annotations

import math
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from typing import Any, Iterable

from rapidfuzz import fuzz
from sqlalchemy.orm import Session

from ..models import Chunk, Document, Metric, Page
from ..utils import (
    canonical_label,
    clean_text,
    detect_unit,
    extract_years,
    format_number,
    format_percent,
    normalize_label,
    pct_change,
    short_snippet,
    stem,
    tokenize,
)
from .retrieval import SearchHit

DEFAULT_COLORS = [
    "#4f46e5", "#0891b2", "#059669", "#d97706", "#dc2626",
    "#7c3aed", "#0d9488", "#ca8a04", "#be123c", "#2563eb",
]

# Смысловые синонимы показателей: русские и английские формулировки,
# которые обозначают один и тот же показатель и должны сравниваться.
_METRIC_CONCEPTS: list[tuple[str, tuple[str, ...]]] = [
    (
        "net_profit_margin",
        ("net profit margin", "рентабельность по чистой прибыли", "маржа чистой прибыли"),
    ),
    (
        "roe",
        ("return on equity", "roe", "рентабельность капитала", "рентабельность собственного капитала"),
    ),
    (
        "current_ratio",
        ("current ratio", "коэффициент текущей ликвидности", "текущая ликвидность"),
    ),
    ("net_profit", ("net profit", "чистая прибыль", "прибыль чистая")),
    (
        "revenue",
        ("revenue", "turnover", "sales", "выручка", "доход от реализации", "выручка от реализации"),
    ),
    ("total_assets", ("total assets", "совокупные активы", "активы")),
    ("equity", ("shareholders equity", "equity", "собственный капитал")),
    ("operating_expenses", ("operating expenses", "расходы", "затраты", "себестоимость")),
    (
        "headcount",
        ("headcount", "employees", "численность сотрудников", "среднесписочная численность"),
    ),
    ("dividends", ("dividends", "дивиденды")),
    ("productivity", ("labor productivity", "производительность труда")),
]


def metric_concept(label: str) -> str:
    """Возвращает смысловой ключ показателя для межъязыкового сопоставления."""
    c = canonical_label(label)
    if not c:
        return ""
    for concept, patterns in _METRIC_CONCEPTS:
        for pattern in patterns:
            if len(pattern) <= 4 and re.fullmatch(r"[a-z]+", pattern):
                if re.search(rf"\b{re.escape(pattern)}\b", c):
                    return concept
            elif pattern in c:
                return concept
    return ""

DIMENSION_LABELS = {
    "money": "денежный",
    "percent": "процент",
    "pp": "процентные пункты",
    "count": "количество",
    "people": "человек",
    "mass": "масса",
    "area": "площадь",
    "number": "число",
    "": "без единицы",
}


@dataclass
class MetricRecord:
    id: int
    document_id: int
    document_name: str
    document_created: Any
    page: int
    label: str
    normalized_label: str
    value: float | None
    normalized_value: float | None
    unit: str
    dimension: str
    scale: float
    currency: str
    period: str
    raw_value: str
    raw_text: str
    context: str
    confidence: float
    source_kind: str
    source_ref: str
    cluster: str = ""
    entity_key: str = ""


@dataclass
class LabelCluster:
    normalized: str
    label: str
    members: list[str] = field(default_factory=list)
    metrics: list[MetricRecord] = field(default_factory=list)

    @property
    def documents(self) -> set[int]:
        return {m.document_id for m in self.metrics}


def _entity_key(name: str) -> str:
    """Группирует документы одной организации по имени файла."""
    stem = re.sub(r"\.pdf$", "", (name or "").lower())
    stem = re.sub(r"(?<!\d)(?:19|20)\d{2}(?!\d)", " ", stem)
    stem = re.sub(
        r"(?:audit|scanned|scan|english|eng|ocr|отчет|отчёт|annual|report|"
        r"финансовый|годовой|итоги|итоговый)",
        " ",
        stem,
    )
    stem = re.sub(r"[_\-\s]+", " ", stem).strip()
    return stem or (name or "").lower()


def _record(row: Metric, doc: Document) -> MetricRecord:
    return MetricRecord(
        id=row.id,
        document_id=row.document_id,
        document_name=doc.original_name,
        document_created=doc.created_at,
        page=row.page_number,
        label=row.label or row.normalized_label,
        normalized_label=row.normalized_label or normalize_label(row.label),
        value=row.value,
        normalized_value=row.normalized_value if row.normalized_value is not None else row.value,
        unit=row.unit or "",
        dimension=row.dimension or "",
        scale=row.scale or 1.0,
        currency=row.currency or "",
        period=row.period or "",
        raw_value=row.raw_value or "",
        raw_text=row.raw_text or "",
        context=row.context or "",
        confidence=row.confidence or 0.0,
        source_kind=row.source_kind or "text",
        source_ref=row.source_ref or f"p{row.page_number}",
        entity_key=_entity_key(doc.original_name),
    )


def list_documents(db: Session, project_id: int, doc_ids: list[int] | None = None) -> list[Document]:
    q = db.query(Document).filter(
        Document.project_id == project_id, Document.status.in_(["ready", "error"])
    )
    if doc_ids:
        q = q.filter(Document.id.in_(doc_ids))
    return q.order_by(Document.created_at, Document.id).all()


def load_metrics(
    db: Session,
    project_id: int,
    doc_ids: list[int] | None = None,
    years: list[str] | None = None,
    member_labels: list[str] | None = None,
    limit: int = 60000,
) -> tuple[list[MetricRecord], bool]:
    q = (
        db.query(Metric, Document)
        .join(Document, Document.id == Metric.document_id)
        .filter(Document.project_id == project_id, Document.status == "ready")
    )
    if doc_ids:
        q = q.filter(Metric.document_id.in_(doc_ids))
    if years:
        from sqlalchemy import or_

        q = q.filter(or_(*[Metric.period.like(f"{y}%") for y in years]))
    if member_labels:
        q = q.filter(Metric.normalized_label.in_(member_labels))
    rows = q.order_by(Metric.period, Metric.document_id, Metric.page_number, Metric.id).limit(limit + 1).all()
    truncated = len(rows) > limit
    records = [_record(m, d) for m, d in rows[:limit]]
    return records, truncated


def list_metric_labels(
    db: Session, project_id: int, doc_ids: list[int] | None = None
) -> list[dict[str, Any]]:
    q = (
        db.query(Metric.normalized_label, Metric.label, Metric.id, Metric.document_id)
        .join(Document, Document.id == Metric.document_id)
        .filter(Document.project_id == project_id, Document.status == "ready")
    )
    if doc_ids:
        q = q.filter(Metric.document_id.in_(doc_ids))
    rows = q.all()
    grouped: dict[str, dict[str, Any]] = {}
    for norm, label, _mid, did in rows:
        key = norm or normalize_label(label)
        if not key:
            continue
        item = grouped.setdefault(
            key, {"normalized": key, "label": label, "count": 0, "documents": set()}
        )
        item["count"] += 1
        item["documents"].add(did)
    result = []
    for item in grouped.values():
        item["document_count"] = len(item.pop("documents"))
        result.append(item)
    result.sort(key=lambda x: (-x["count"], x["label"]))
    return result


def cluster_labels(records: list[MetricRecord], threshold: float = 90.0) -> list[LabelCluster]:
    groups: dict[str, list[MetricRecord]] = defaultdict(list)
    for r in records:
        if r.value is None:
            continue
        key = metric_concept(r.label) or r.normalized_label or normalize_label(r.label)
        if not key:
            continue
        groups[key].append(r)
    # представитель — самая частая группа
    ordered = sorted(groups.items(), key=lambda kv: -len(kv[1]))
    clusters: list[LabelCluster] = []
    mapping: dict[str, LabelCluster] = {}
    for norm, recs in ordered:
        member_norms = list(
            dict.fromkeys(
                (r.normalized_label or normalize_label(r.label)) for r in recs
            )
        )
        member_norm = member_norms[0] if member_norms else norm
        best: LabelCluster | None = None
        best_score = 0.0
        for cluster in clusters:
            score = max(
                fuzz.ratio(norm, cluster.normalized),
                fuzz.token_sort_ratio(norm, cluster.normalized),
            )
            # одинаковый набор основ слов — точное совпадение по смыслу
            stem_a = {stem(t) for t in tokenize(norm)}
            stem_b = {stem(t) for t in tokenize(cluster.normalized)}
            if stem_a and stem_a == stem_b:
                score = max(score, 99.0)
            if score > best_score:
                best_score, best = score, cluster
        if best is not None and best_score >= threshold:
            best.members.extend(member_norms)
            best.metrics.extend(recs)
            mapping[norm] = best
        else:
            label_counter = Counter(r.label for r in recs)
            display = label_counter.most_common(1)[0][0]
            cluster = LabelCluster(
                normalized=norm,
                label=clean_text(display) or norm,
                members=member_norms or [member_norm],
                metrics=list(recs),
            )
            clusters.append(cluster)
            mapping[norm] = cluster
    for c in clusters:
        c.members = list(dict.fromkeys(c.members))
        for m in c.metrics:
            m.cluster = c.normalized
        c.metrics.sort(key=lambda m: (m.period, m.document_id, m.page))
    clusters.sort(key=lambda c: (-len(c.metrics), c.label))
    return clusters


def find_relevant_clusters(
    query: str,
    clusters: list[LabelCluster],
    explicit_labels: list[str] | None = None,
    limit: int = 12,
) -> list[LabelCluster]:
    if explicit_labels:
        wanted = [canonical_label(x) for x in explicit_labels if clean_text(x)]
        wanted_concepts = {metric_concept(x) for x in explicit_labels if clean_text(x)} - {""}
        result = []
        for c in clusters:
            if c.normalized in wanted_concepts or any(
                canonical_label(m) in wanted or m in wanted
                or fuzz.token_set_ratio(canonical_label(m), w) >= 88
                for m in c.members
                for w in wanted
            ):
                result.append(c)
        return result[:limit]
    q = clean_text(query).lower()
    if re.search(r"(?:все|всех|всеми)\s+(?:показател|данн|метрик)|all\s+(?:metrics|indicators)", q):
        return clusters[:limit]
    tokens = [t for t in tokenize(query) if re.search(r"[а-яa-z]", t)]
    if not tokens:
        return []
    q_stems = {stem(t) for t in tokens}
    scored: list[tuple[float, LabelCluster]] = []
    for c in clusters:
        label_text = " ".join([c.label] + c.members)
        l_stems = {stem(t) for t in tokenize(label_text)}
        score = 0.0
        matched_tokens = 0
        for t in tokens:
            st = stem(t)
            if st in l_stems:
                score = max(score, 96.0)
                matched_tokens += 1
            elif len(st) >= 4 and any(ls.startswith(st) or st.startswith(ls) for ls in l_stems if len(ls) >= 4):
                score = max(score, 84.0)
                matched_tokens += 1
        if matched_tokens == 0:
            continue
        score = max(score, float(fuzz.token_set_ratio(" ".join(tokens), c.normalized)) * 0.95)
        if score >= 72:
            scored.append((score, c))
    scored.sort(key=lambda x: (-x[0], -len(x[1].metrics)))
    return [c for _s, c in scored[:limit]]


def parse_period_filter(query: str) -> list[str]:
    years: list[str] = []
    for m in re.finditer(r"((?:19|20)\d{2})\s*[-–—]\s*((?:19|20)\d{2})", query or ""):
        a, b = int(m.group(1)), int(m.group(2))
        if 1900 <= a <= 2100 and 1900 <= b <= 2100 and a <= b:
            years.extend(str(y) for y in range(a, b + 1))
    for y in extract_years(query):
        if y not in years:
            years.append(y)
    return sorted(set(years))


def _display_value(value: float | None, unit: str, digits: int = 2) -> str:
    if value is None:
        return "—"
    return f"{format_number(value, digits)}{(' ' + unit) if unit else ''}"


def _source(m: MetricRecord) -> dict[str, Any]:
    return {
        "document_id": m.document_id,
        "document": m.document_name,
        "page": m.page,
        "snippet": short_snippet(m.context or m.raw_text, 320),
        "metric_id": m.id,
        "value": _display_value(m.value, m.unit),
        "unit": m.unit,
        "period": m.period,
    }


def _citation(m: MetricRecord) -> dict[str, Any]:
    return {
        "document_id": m.document_id,
        "document": m.document_name,
        "page": m.page,
        "snippet": short_snippet(m.context or m.raw_text, 260),
        "metric_id": m.id,
        "source_kind": m.source_kind,
        "confidence": m.confidence,
    }


def _dedupe_citations(citations: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    seen = set()
    result = []
    for c in citations:
        key = (c.get("document_id"), c.get("page"), c.get("metric_id"), c.get("snippet", "")[:80])
        if key in seen:
            continue
        seen.add(key)
        result.append(c)
    return result


def _columns() -> list[dict[str, str]]:
    return [
        {"key": "indicator", "label": "Показатель", "type": "string"},
        {"key": "period", "label": "Период", "type": "string"},
        {"key": "document", "label": "Документ", "type": "string"},
        {"key": "value_display", "label": "Значение", "type": "string"},
        {"key": "unit", "label": "Ед.", "type": "string"},
        {"key": "change_display", "label": "Изменение", "type": "string"},
        {"key": "pct_display", "label": "Изм. %", "type": "string"},
        {"key": "trend", "label": "Тенденция", "type": "string"},
        {"key": "source_display", "label": "Источник", "type": "source"},
    ]


def _table(title: str, rows: list[dict[str, Any]], columns: list[dict[str, str]] | None = None) -> dict[str, Any]:
    return {
        "title": title,
        "columns": columns or _columns(),
        "rows": rows,
        "row_count": len(rows),
    }


def _comparable(a: MetricRecord, b: MetricRecord) -> tuple[bool, str]:
    if a.dimension != b.dimension:
        return False, f"Разные единицы измерения: {a.unit or '—'} и {b.unit or '—'}"
    if a.dimension == "money" and a.currency and b.currency and a.currency != b.currency:
        return False, f"Разные валюты: {a.currency} и {b.currency}; автоматическая конвертация не выполняется"
    return True, ""


def _rank(m: MetricRecord) -> tuple[int, float, int]:
    return (1 if m.source_kind == "table" else 0, m.confidence, m.page)


def _best_per_doc(records: list[MetricRecord]) -> tuple[dict[int, MetricRecord], list[str]]:
    warnings: list[str] = []
    by_doc: dict[int, MetricRecord] = {}
    for m in records:
        if m.value is None:
            continue
        prev = by_doc.get(m.document_id)
        if prev is None:
            by_doc[m.document_id] = m
            continue
        if _rank(m) > _rank(prev):
            by_doc[m.document_id] = m
    # внутри одного документа разные значения одного показателя за период
    for r in records:
        chosen = by_doc.get(r.document_id)
        if (
            chosen
            and r.value is not None
            and chosen.normalized_value is not None
            and r.normalized_value is not None
            and _comparable(r, chosen)[0]
            and abs(r.normalized_value - chosen.normalized_value)
            > max(1e-6, abs(chosen.normalized_value) * 0.005)
        ):
            warnings.append(
                f"В документе «{r.document_name}» для показателя «{chosen.label}» за период "
                f"{chosen.period or '—'} найдены разные значения ({_display_value(r.value, r.unit)} и "
                f"{_display_value(chosen.value, chosen.unit)}); использовано значение со стр. {chosen.page}."
            )
    return by_doc, list(dict.fromkeys(warnings))


def _docs_map(documents: list[Document]) -> dict[int, Document]:
    return {d.id: d for d in documents}


def build_comparison(
    clusters: list[LabelCluster],
    documents: list[Document],
    limit_rows: int = 2000,
) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    findings: list[dict[str, Any]] = []
    citations: list[dict[str, Any]] = []
    warnings: list[str] = []
    doc_order = {d.id: i for i, d in enumerate(documents)}
    changes: list[tuple[float, MetricRecord, MetricRecord, str]] = []

    for cluster in clusters:
        by_period: dict[str, list[MetricRecord]] = defaultdict(list)
        for m in cluster.metrics:
            if m.value is not None:
                by_period[m.period or "—"].append(m)
        for period, recs in sorted(by_period.items()):
            by_doc, w = _best_per_doc(recs)
            warnings.extend(w)
            if not by_doc:
                continue
            ordered = sorted(by_doc.values(), key=lambda m: doc_order.get(m.document_id, 999))
            base = ordered[0]
            if len(ordered) == 1:
                m = ordered[0]
                rows.append(_comparison_row(cluster, m, None, m, "—", "—", "single", "Значение найдено только в одном документе"))
                citations.append(_citation(m))
                continue
            for m in ordered:
                if m is base:
                    rows.append(_comparison_row(cluster, m, None, base, "—", "—", "base", "База сравнения"))
                    citations.append(_citation(m))
                    continue
                ok, reason = _comparable(base, m)
                if not ok:
                    rows.append(_comparison_row(cluster, m, None, base, "—", "—", "incomparable", reason))
                    warnings.append(f"{cluster.label}, {period}: {reason}")
                    citations.append(_citation(m))
                    continue
                abs_change = (m.normalized_value or 0) - (base.normalized_value or 0)
                abs_display = abs_change / (m.scale or 1.0)
                pct = pct_change(base.normalized_value or 0, m.normalized_value or 0)
                trend = "up" if abs_change > 0 else "down" if abs_change < 0 else "same"
                note = ""
                if pct is None:
                    note = "Базовое значение равно нулю — процентное изменение не определено"
                rows.append(
                    _comparison_row(
                        cluster, m, abs_display, base,
                        format_number(abs_display, 2), format_percent(pct), trend, note,
                    )
                )
                citations.append(_citation(m))
                citations.append(_citation(base))
                if pct is not None:
                    changes.append((pct, m, base, cluster.label))
            if len(ordered) >= 2:
                readable = []
                for m in ordered:
                    readable.append(f"«{m.document_name}» — {_display_value(m.value, m.unit)} (стр. {m.page})")
                findings.append(
                    {
                        "type": "comparison",
                        "text": f"{cluster.label}, период {period}: " + "; ".join(readable) + ".",
                        "document_id": ordered[0].document_id,
                        "page": ordered[0].page,
                        "severity": "info",
                    }
                )

    # ключевые изменения
    if changes:
        changes.sort(key=lambda x: x[0])
        down = changes[0]
        up = changes[-1]
        if down[0] < 0:
            findings.append(
                {
                    "type": "decrease",
                    "text": f"Наибольшее снижение: «{down[3]}» — {format_percent(down[0])} "
                            f"({_display_value(down[1].value, down[1].unit)} против "
                            f"{_display_value(down[2].value, down[2].unit)} в «{down[2].document_name}»).",
                    "document_id": down[1].document_id,
                    "page": down[1].page,
                    "severity": "warning",
                }
            )
        if up[0] > 0:
            findings.append(
                {
                    "type": "increase",
                    "text": f"Наибольший рост: «{up[3]}» — {format_percent(up[0])} "
                            f"({_display_value(up[1].value, up[1].unit)} против "
                            f"{_display_value(up[2].value, up[2].unit)} в «{up[2].document_name}»).",
                    "document_id": up[1].document_id,
                    "page": up[1].page,
                    "severity": "info",
                }
            )
    if len(rows) > limit_rows:
        warnings.append(f"Таблица ограничена {limit_rows} строками из {len(rows)}.")
        rows = rows[:limit_rows]
    if not rows:
        warnings.append("Не найдено числовых значений по выбранным показателям и документам.")
    methods = [
        "Сопоставление показателей: нормализация названий и нечёткое объединение близких формулировок.",
        "Абсолютное изменение = значение документа − значение базового документа (в единицах текущего документа).",
        "Процентное изменение = (значение − базовое значение) / |базовое значение| × 100.",
        "Значения с разными единицами или валютами не сравниваются без взаимного преобразования.",
    ]
    return {
        "tables": [_table("Сравнительная таблица", rows)],
        "findings": findings,
        "warnings": list(dict.fromkeys(warnings)),
        "citations": _dedupe_citations(citations),
        "methods": methods,
        "meta": {"groups": len({(c.normalized, m.period) for c in clusters for m in c.metrics})},
    }


def _comparison_row(
    cluster: LabelCluster,
    m: MetricRecord,
    abs_change: float | None,
    base: MetricRecord,
    abs_display: str,
    pct_display: str,
    trend: str,
    note: str,
) -> dict[str, Any]:
    if trend == "same":
        trend_label = "без изменений"
    elif trend == "up":
        trend_label = "рост"
    elif trend == "down":
        trend_label = "снижение"
    elif trend == "single":
        trend_label = "нет пары"
    elif trend == "base":
        trend_label = "база"
    else:
        trend_label = "несопоставимо"
    return {
        "indicator": cluster.label,
        "period": m.period or "—",
        "document": m.document_name,
        "document_id": m.document_id,
        "value_display": _display_value(m.value, m.unit),
        "value_num": m.value,
        "normalized_value": m.normalized_value,
        "unit": m.unit,
        "change_display": abs_display,
        "pct_display": pct_display,
        "trend": trend_label,
        "trend_code": trend,
        "base_value": _display_value(base.value, base.unit),
        "base_document": base.document_name,
        "source": _source(m),
        "source_display": f"{m.document_name}, стр. {m.page}",
        "source_document": m.document_name,
        "source_page": m.page,
        "source_snippet": short_snippet(m.context, 320),
        "note": note,
        "confidence": m.confidence,
        "dimension": m.dimension,
        "currency": m.currency,
        "period_raw": m.period,
        "metric_id": m.id,
        "indicator_variants": cluster.members,
    }


def build_dynamics(clusters: list[LabelCluster], documents: list[Document]) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    findings: list[dict[str, Any]] = []
    citations: list[dict[str, Any]] = []
    warnings: list[str] = []
    for cluster in clusters:
        by_doc: dict[int, list[MetricRecord]] = defaultdict(list)
        by_doc_best: dict[int, dict[str, MetricRecord]] = defaultdict(dict)
        for m in cluster.metrics:
            if m.value is None:
                continue
            key = m.period or "—"
            prev = by_doc_best[m.document_id].get(key)
            if prev is None or _rank(m) > _rank(prev):
                by_doc_best[m.document_id][key] = m
        for did, periods in by_doc_best.items():
            ordered = sorted(periods.values(), key=lambda m: _period_sort_key(m.period))
            prev: MetricRecord | None = None
            for m in ordered:
                change_display = "—"
                pct_display = "—"
                trend = "base"
                trend_label = "база"
                if prev is not None:
                    ok, reason = _comparable(prev, m)
                    if ok:
                        abs_change = (m.normalized_value or 0) - (prev.normalized_value or 0)
                        abs_display = abs_change / (m.scale or 1.0)
                        pct = pct_change(prev.normalized_value or 0, m.normalized_value or 0)
                        change_display = format_number(abs_display, 2)
                        pct_display = format_percent(pct)
                        trend = "up" if abs_change > 0 else "down" if abs_change < 0 else "same"
                        trend_label = {"up": "рост", "down": "снижение", "same": "без изменений"}[trend]
                        if abs_change != 0:
                            findings.append(
                                {
                                    "type": "increase" if abs_change > 0 else "decrease",
                                    "text": f"{cluster.label}, «{m.document_name}»: {prev.period or '—'} → "
                                            f"{m.period or '—'} — {_display_value(prev.value, prev.unit)} → "
                                            f"{_display_value(m.value, m.unit)} ({format_number(abs_display, 2)}; "
                                            f"{format_percent(pct)}).",
                                    "document_id": m.document_id,
                                    "page": m.page,
                                    "severity": "info",
                                }
                            )
                    else:
                        trend = "incomparable"
                        trend_label = "несопоставимо"
                        change_display = "—"
                        warnings.append(f"{cluster.label}, «{m.document_name}»: {reason}")
                rows.append(
                    {
                        "indicator": cluster.label,
                        "period": m.period or "—",
                        "document": m.document_name,
                        "document_id": m.document_id,
                        "value_display": _display_value(m.value, m.unit),
                        "value_num": m.value,
                        "normalized_value": m.normalized_value,
                        "unit": m.unit,
                        "change_display": change_display,
                        "pct_display": pct_display,
                        "trend": trend_label,
                        "trend_code": trend,
                        "source": _source(m),
                        "source_display": f"{m.document_name}, стр. {m.page}",
                        "source_document": m.document_name,
                        "source_page": m.page,
                        "source_snippet": short_snippet(m.context, 320),
                        "confidence": m.confidence,
                        "metric_id": m.id,
                        "indicator_variants": cluster.members,
                    }
                )
                citations.append(_citation(m))
                prev = m
    if not rows:
        warnings.append("Динамика не рассчитана: нет числовых значений по выбранным показателям.")
    # компактные выводы по росту/снижению
    ups = sum(1 for f in findings if f["type"] == "increase")
    downs = sum(1 for f in findings if f["type"] == "decrease")
    summary = f"Рассчитана динамика по {len(clusters)} показател(ям/ям): {ups} случаев роста, {downs} случаев снижения."
    methods = [
        "Изменение за период = значение текущего периода − значение предыдущего периода того же документа.",
        "Процент изменения = (текущее − предыдущее) / |предыдущее| × 100; при нулевой базе не рассчитывается.",
        "Нулевые значения учитываются как реальные данные, отсутствующие значения не заменяются нулём.",
    ]
    return {
        "tables": [_table("Таблица динамики показателей", rows)],
        "findings": findings[:50],
        "warnings": list(dict.fromkeys(warnings)),
        "citations": _dedupe_citations(citations),
        "methods": methods,
        "summary": summary,
        "meta": {},
    }


def _period_sort_key(period: str) -> tuple:
    if not period:
        return (3, 0, "")
    m = re.search(r"(19|20)\d{2}", period)
    year = int(m.group(0)) if m else 0
    q = re.search(r"Q([1-4])", period)
    d = re.match(r"(\d{1,2})\.(\d{1,2})\.(\d{4})", period)
    if d:
        return (0, year, f"{int(d.group(2)):02d}{int(d.group(1)):02d}")
    if q:
        return (1, year, q.group(1))
    return (2, year, period)


def build_extrema(clusters: list[LabelCluster]) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    citations: list[dict[str, Any]] = []
    findings: list[dict[str, Any]] = []
    warnings: list[str] = []
    for cluster in clusters:
        metrics = [m for m in cluster.metrics if m.value is not None]
        by_dim: dict[str, list[MetricRecord]] = defaultdict(list)
        for m in metrics:
            by_dim[m.dimension].append(m)
        if len(by_dim) > 1:
            warnings.append(
                f"«{cluster.label}»: найдены разные единицы измерения; экстремумы рассчитаны отдельно по каждой группе."
            )
        for dim, group in by_dim.items():
            comparable = [m for m in group if m.normalized_value is not None]
            if not comparable:
                continue
            mx = max(comparable, key=lambda m: m.normalized_value or 0)
            mn = min(comparable, key=lambda m: m.normalized_value or 0)
            rows.append(
                {
                    "indicator": cluster.label,
                    "max_value": _display_value(mx.value, mx.unit),
                    "max_document": mx.document_name,
                    "max_period": mx.period or "—",
                    "min_value": _display_value(mn.value, mn.unit),
                    "min_document": mn.document_name,
                    "min_period": mn.period or "—",
                    "spread": format_number((mx.normalized_value or 0) - (mn.normalized_value or 0), 2),
                    "unit": mx.unit or mn.unit,
                    "dimension": dim,
                    "max_source": _source(mx),
                    "min_source": _source(mn),
                    "source_display": f"{mx.document_name}, стр. {mx.page}; {mn.document_name}, стр. {mn.page}",
                    "source_document": mx.document_name,
                    "source_page": mx.page,
                    "source_snippet": short_snippet(mx.context, 320),
                }
            )
            citations.extend([_citation(mx), _citation(mn)])
            findings.append(
                {
                    "type": "max",
                    "text": f"Максимум «{cluster.label}»: {_display_value(mx.value, mx.unit)} — "
                            f"«{mx.document_name}», стр. {mx.page} ({mx.period or 'период не указан'}).",
                    "document_id": mx.document_id,
                    "page": mx.page,
                    "severity": "info",
                }
            )
            findings.append(
                {
                    "type": "min",
                    "text": f"Минимум «{cluster.label}»: {_display_value(mn.value, mn.unit)} — "
                            f"«{mn.document_name}», стр. {mn.page} ({mn.period or 'период не указан'}).",
                    "document_id": mn.document_id,
                    "page": mn.page,
                    "severity": "info",
                }
            )
    columns = [
        {"key": "indicator", "label": "Показатель", "type": "string"},
        {"key": "max_value", "label": "Максимум", "type": "string"},
        {"key": "max_document", "label": "Документ (макс.)", "type": "string"},
        {"key": "max_period", "label": "Период (макс.)", "type": "string"},
        {"key": "min_value", "label": "Минимум", "type": "string"},
        {"key": "min_document", "label": "Документ (мин.)", "type": "string"},
        {"key": "min_period", "label": "Период (мин.)", "type": "string"},
        {"key": "spread", "label": "Размах", "type": "string"},
        {"key": "source_display", "label": "Источники", "type": "source"},
    ]
    if not rows:
        warnings.append("Не найдено значений для определения максимума и минимума.")
    methods = [
        "Экстремумы определяются по нормализованным значениям внутри совместимых единиц измерения.",
        "Разные единицы и валюты не смешиваются: для каждой группы строится отдельная строка.",
    ]
    return {
        "tables": [_table("Максимальные и минимальные значения", rows, columns)],
        "findings": findings,
        "warnings": list(dict.fromkeys(warnings)),
        "citations": _dedupe_citations(citations),
        "methods": methods,
        "meta": {},
    }


def build_average(clusters: list[LabelCluster]) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    citations: list[dict[str, Any]] = []
    warnings: list[str] = []
    for cluster in clusters:
        by_dim: dict[str, list[MetricRecord]] = defaultdict(list)
        for m in cluster.metrics:
            if m.normalized_value is not None:
                by_dim[m.dimension].append(m)
        if len(by_dim) > 1:
            warnings.append(f"«{cluster.label}»: среднее рассчитано отдельно для разных единиц измерения.")
        for dim, group in by_dim.items():
            unit_counter = Counter(m.unit for m in group)
            display_unit = unit_counter.most_common(1)[0][0] or ""
            display_scale = next((m.scale for m in group if m.unit == display_unit), 1.0) or 1.0
            avg_norm = sum(m.normalized_value or 0 for m in group) / len(group)
            avg_display = avg_norm / (display_scale or 1.0)
            mn = min(group, key=lambda m: m.normalized_value or 0)
            mx = max(group, key=lambda m: m.normalized_value or 0)
            rows.append(
                {
                    "indicator": cluster.label,
                    "average": _display_value(avg_display, display_unit),
                    "unit": display_unit,
                    "count": len(group),
                    "documents": len({m.document_id for m in group}),
                    "min_value": _display_value(mn.value, mn.unit),
                    "max_value": _display_value(mx.value, mx.unit),
                    "formula": f"сумма {len(group)} значений / {len(group)}",
                    "source_display": f"Использовано значений: {len(group)}",
                    "source_document": "",
                    "source_page": 0,
                    "source_snippet": "",
                }
            )
            citations.extend(_citation(m) for m in group[:20])
    if not rows:
        warnings.append("Недостаточно данных для расчёта среднего значения.")
    columns = [
        {"key": "indicator", "label": "Показатель", "type": "string"},
        {"key": "average", "label": "Среднее", "type": "string"},
        {"key": "count", "label": "Кол-во значений", "type": "number"},
        {"key": "documents", "label": "Документов", "type": "number"},
        {"key": "min_value", "label": "Минимум", "type": "string"},
        {"key": "max_value", "label": "Максимум", "type": "string"},
        {"key": "formula", "label": "Метод", "type": "string"},
        {"key": "source_display", "label": "Источники", "type": "source"},
    ]
    methods = [
        "Среднее арифметическое = сумма нормализованных значений / количество значений.",
        "Пропущенные значения не заменяются нулём и не входят в количество.",
    ]
    return {
        "tables": [_table("Средние значения показателей", rows, columns)],
        "findings": [
            {
                "type": "average",
                "text": f"«{r['indicator']}»: среднее {r['average']} по {r['count']} значениям.",
                "severity": "info",
            }
            for r in rows
        ],
        "warnings": list(dict.fromkeys(warnings)),
        "citations": _dedupe_citations(citations),
        "methods": methods,
        "meta": {},
    }


def build_missing(
    clusters: list[LabelCluster],
    documents: list[Document],
    years: list[str] | None = None,
) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    warnings: list[str] = []
    doc_names = {d.id: d.original_name for d in documents}
    for cluster in clusters:
        periods = years or sorted(
            {m.period for m in cluster.metrics if m.period}, key=_period_sort_key
        ) or ["—"]
        for period in periods:
            present = {
                m.document_id
                for m in cluster.metrics
                if (m.period or "—") == (period or "—") and m.value is not None
            }
            missing = [did for did in doc_names if did not in present]
            if not missing:
                continue
            rows.append(
                {
                    "indicator": cluster.label,
                    "period": period or "—",
                    "missing_count": len(missing),
                    "missing_documents": "; ".join(doc_names[did] for did in missing),
                    "present_documents": "; ".join(
                        doc_names[did] for did in present if did in doc_names
                    ) or "—",
                    "status": "Нет данных",
                    "source_display": "Отсутствие зафиксировано по извлечённым данным",
                    "source_document": "",
                    "source_page": 0,
                    "source_snippet": "",
                }
            )
    if not rows:
        warnings.append("Отсутствующих данных по выбранным показателям и периодам не обнаружено.")
    columns = [
        {"key": "indicator", "label": "Показатель", "type": "string"},
        {"key": "period", "label": "Период", "type": "string"},
        {"key": "missing_count", "label": "Нет данных, док.", "type": "number"},
        {"key": "missing_documents", "label": "Документы без данных", "type": "string"},
        {"key": "present_documents", "label": "Документы с данными", "type": "string"},
        {"key": "status", "label": "Статус", "type": "string"},
    ]
    methods = [
        "Отсутствие данных устанавливается по отсутствию извлечённого показателя у документа за период.",
        "Нулевое значение считается присутствующим данным и не отмечается как отсутствующее.",
    ]
    return {
        "tables": [_table("Отсутствующие данные", rows, columns)],
        "findings": [
            {
                "type": "missing",
                "text": f"«{r['indicator']}» за {r['period']}: нет данных в {r['missing_count']} документ(ах) — {r['missing_documents']}.",
                "severity": "warning",
            }
            for r in rows[:30]
        ],
        "warnings": list(dict.fromkeys(warnings)),
        "citations": [],
        "methods": methods,
        "meta": {"missing_groups": len(rows)},
    }


def build_threshold(
    clusters: list[LabelCluster],
    threshold: dict[str, Any] | None,
) -> dict[str, Any]:
    if not threshold or threshold.get("value") is None:
        return {
            "tables": [],
            "findings": [],
            "warnings": ["Не указан числовой порог. Пример: «покажи показатели выручки больше 100 млн руб.»"],
            "citations": [],
            "methods": [],
            "meta": {},
        }
    op = threshold.get("op", ">")
    tnorm = threshold.get("normalized_value")
    tdim = threshold.get("dimension", "")
    tunit = threshold.get("unit", "")
    rows: list[dict[str, Any]] = []
    citations: list[dict[str, Any]] = []
    warnings: list[str] = []
    for cluster in clusters:
        for m in cluster.metrics:
            if m.normalized_value is None:
                continue
            if tdim and m.dimension != tdim:
                continue
            matched = m.normalized_value > tnorm if op == ">" else m.normalized_value < tnorm
            if not matched:
                continue
            rows.append(
                {
                    "indicator": cluster.label,
                    "period": m.period or "—",
                    "document": m.document_name,
                    "document_id": m.document_id,
                    "value_display": _display_value(m.value, m.unit),
                    "unit": m.unit,
                    "threshold_display": f"{op} {format_number(threshold.get('value'))} {tunit}".strip(),
                    "source": _source(m),
                    "source_display": f"{m.document_name}, стр. {m.page}",
                    "source_document": m.document_name,
                    "source_page": m.page,
                    "source_snippet": short_snippet(m.context, 320),
                    "metric_id": m.id,
                    "confidence": m.confidence,
                }
            )
            citations.append(_citation(m))
    if not rows:
        warnings.append(
            f"Ни один показатель не удовлетворяет условию {op} {format_number(threshold.get('value'))} {tunit}."
        )
    columns = [
        {"key": "indicator", "label": "Показатель", "type": "string"},
        {"key": "period", "label": "Период", "type": "string"},
        {"key": "document", "label": "Документ", "type": "string"},
        {"key": "value_display", "label": "Значение", "type": "string"},
        {"key": "threshold_display", "label": "Порог", "type": "string"},
        {"key": "source_display", "label": "Источник", "type": "source"},
    ]
    return {
        "tables": [_table("Значения, удовлетворяющие порогу", rows, columns)],
        "findings": [
            {
                "type": "threshold",
                "text": f"«{r['indicator']}» в «{r['document']}» (стр. {r['source_page']}) = {r['value_display']} — условие {r['threshold_display']} выполнено.",
                "document_id": r["document_id"],
                "page": r["source_page"],
                "severity": "info",
            }
            for r in rows[:30]
        ],
        "warnings": list(dict.fromkeys(warnings)),
        "citations": _dedupe_citations(citations),
        "methods": [
            "Сравнение выполняется по нормализованному значению с учётом масштаба единицы (тыс./млн/млрд).",
            "Показатели с другой размерностью не применяются к порогу.",
        ],
        "meta": {"threshold": threshold},
    }


def build_contradictions(clusters: list[LabelCluster]) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    findings: list[dict[str, Any]] = []
    citations: list[dict[str, Any]] = []
    warnings: list[str] = []
    checked = 0
    for cluster in clusters:
        by_period: dict[tuple[str, str], list[MetricRecord]] = defaultdict(list)
        for m in cluster.metrics:
            if m.value is not None:
                by_period[(m.entity_key, m.period or "—")].append(m)
        for (_entity, period), recs in by_period.items():
            by_doc, w = _best_per_doc(recs)
            warnings.extend(w)
            if len(by_doc) < 2:
                continue
            docs = list(by_doc.values())
            compatible = True
            for other in docs[1:]:
                ok, reason = _comparable(docs[0], other)
                if not ok:
                    compatible = False
                    warnings.append(f"{cluster.label}, {period}: {reason}")
                    break
            if not compatible:
                continue
            checked += 1
            values = [m.normalized_value or 0 for m in docs]
            spread = max(values) - min(values)
            base = max(abs(v) for v in values) or 1.0
            tolerance = 0.05 if docs[0].dimension in {"percent", "pp"} else max(1e-6, base * 0.005)
            if spread <= tolerance:
                continue
            for m in docs:
                rows.append(
                    {
                        "indicator": cluster.label,
                        "period": period,
                        "document": m.document_name,
                        "document_id": m.document_id,
                        "value_display": _display_value(m.value, m.unit),
                        "unit": m.unit,
                        "difference": format_number(spread / (m.scale or 1.0), 2),
                        "source": _source(m),
                        "source_display": f"{m.document_name}, стр. {m.page}",
                        "source_document": m.document_name,
                        "source_page": m.page,
                        "source_snippet": short_snippet(m.context, 320),
                        "metric_id": m.id,
                        "confidence": m.confidence,
                    }
                )
                citations.append(_citation(m))
            findings.append(
                {
                    "type": "contradiction",
                    "text": f"Противоречие: «{cluster.label}» за {period} — "
                            + "; ".join(
                                f"«{m.document_name}»: {_display_value(m.value, m.unit)} (стр. {m.page})"
                                for m in docs
                            )
                            + ".",
                    "document_id": docs[0].document_id,
                    "page": docs[0].page,
                    "severity": "warning",
                }
            )
    columns = [
        {"key": "indicator", "label": "Показатель", "type": "string"},
        {"key": "period", "label": "Период", "type": "string"},
        {"key": "document", "label": "Документ", "type": "string"},
        {"key": "value_display", "label": "Значение", "type": "string"},
        {"key": "difference", "label": "Расхождение", "type": "string"},
        {"key": "source_display", "label": "Источник", "type": "source"},
    ]
    if not rows:
        warnings.append(
            "Числовых противоречий не обнаружено среди сопоставимых показателей. "
            "Это не доказывает отсутствие противоречий в текстовых формулировках."
        )
    return {
        "tables": [_table("Противоречия между документами", rows, columns)],
        "findings": findings,
        "warnings": list(dict.fromkeys(warnings)),
        "citations": _dedupe_citations(citations),
        "methods": [
            "Противоречие фиксируется, если за один период и показатель в разных документах значения расходятся более чем на 0,5%.",
            "Для процентов и процентных пунктов допуск — 0,05 п.п.",
            "Значения в разных валютах или единицах не объявляются противоречием без преобразования.",
        ],
        "meta": {"checked_groups": checked},
    }


def build_summary_table(
    clusters: list[LabelCluster], documents: list[Document]
) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    citations: list[dict[str, Any]] = []
    warnings: list[str] = []
    doc_order = {d.id: i for i, d in enumerate(documents)}
    for cluster in clusters:
        grouped: dict[tuple[str, int], MetricRecord] = {}
        for m in cluster.metrics:
            if m.value is None:
                continue
            key = (m.period or "—", m.document_id)
            prev = grouped.get(key)
            if prev is None or _rank(m) > _rank(prev):
                grouped[key] = m
        for (period, did), m in sorted(
            grouped.items(), key=lambda kv: (_period_sort_key(kv[0][0]), doc_order.get(kv[0][1], 999))
        ):
            rows.append(
                {
                    "indicator": cluster.label,
                    "period": period,
                    "document": m.document_name,
                    "document_id": m.document_id,
                    "value_display": _display_value(m.value, m.unit),
                    "value_num": m.value,
                    "normalized_value": m.normalized_value,
                    "unit": m.unit,
                    "confidence": m.confidence,
                    "source": _source(m),
                    "source_display": f"{m.document_name}, стр. {m.page}",
                    "source_document": m.document_name,
                    "source_page": m.page,
                    "source_snippet": short_snippet(m.context, 320),
                    "metric_id": m.id,
                    "indicator_variants": cluster.members,
                }
            )
            citations.append(_citation(m))
    if len(rows) > 1500:
        warnings.append(f"Сводная таблица ограничена 1500 строками из {len(rows)}.")
        rows = rows[:1500]
    if not rows:
        warnings.append("Нет данных для построения сводной таблицы.")
    columns = [
        {"key": "indicator", "label": "Показатель", "type": "string"},
        {"key": "period", "label": "Период", "type": "string"},
        {"key": "document", "label": "Документ", "type": "string"},
        {"key": "value_display", "label": "Значение", "type": "string"},
        {"key": "unit", "label": "Ед.", "type": "string"},
        {"key": "confidence", "label": "Уверенность", "type": "number"},
        {"key": "source_display", "label": "Источник", "type": "source"},
    ]
    return {
        "tables": [_table("Сводная таблица показателей", rows, columns)],
        "findings": [
            {
                "type": "table",
                "text": f"Сформирована сводная таблица: {len(rows)} значений по {len(clusters)} показателям.",
                "severity": "info",
            }
        ],
        "warnings": list(dict.fromkeys(warnings)),
        "citations": _dedupe_citations(citations),
        "methods": ["Каждое значение взято из извлечённого показателя с указанием документа и страницы."],
        "meta": {},
    }


def build_search_result(
    hits: list[SearchHit],
    clusters: list[LabelCluster],
    warnings: list[str] | None = None,
) -> dict[str, Any]:
    citations = []
    findings = []
    for hit in hits:
        citations.append(
            {
                "document_id": hit.document_id,
                "document": hit.document_name,
                "page": hit.page,
                "snippet": hit.snippet,
                "metric_id": None,
                "source_kind": "text",
                "confidence": 0.9,
            }
        )
        findings.append(
            {
                "type": "search",
                "text": f"«{hit.document_name}», стр. {hit.page}: {hit.snippet}",
                "document_id": hit.document_id,
                "page": hit.page,
                "severity": "info",
            }
        )
    if clusters:
        summary = build_summary_table(clusters, [])
        citations.extend(summary["citations"])
        findings.extend(summary["findings"])
        tables = summary["tables"]
        warnings = list(dict.fromkeys((warnings or []) + summary["warnings"]))
    else:
        tables = []
        warnings = list(warnings or [])
    if not hits and not clusters:
        warnings.append("По запросу не найдено ни текстовых фрагментов, ни числовых показателей.")
    return {
        "tables": tables,
        "findings": findings[:40],
        "warnings": warnings,
        "citations": _dedupe_citations(citations),
        "methods": ["Поиск выполняется по тексту документов (FTS5) с указанием страницы и фрагмента."],
        "meta": {"hits": len(hits)},
    }


# ---------------------------------------------------------------------------
# Графики (Plotly-совместимые спецификации)
# ---------------------------------------------------------------------------

def _base_layout(title: str, x_label: str, y_label: str, log_y: bool = False) -> dict[str, Any]:
    return {
        "title": {"text": title, "x": 0.02, "xanchor": "left", "font": {"size": 16}},
        "xaxis": {"title": {"text": x_label}, "automargin": True, "type": "category"},
        "yaxis": {
            "title": {"text": y_label},
            "automargin": True,
            "rangemode": "tozero",
            "type": "log" if log_y else "linear",
        },
        "legend": {"orientation": "h", "y": -0.2, "x": 0},
        "margin": {"l": 60, "r": 20, "t": 50, "b": 70},
        "paper_bgcolor": "#ffffff",
        "plot_bgcolor": "#ffffff",
        "font": {"family": "Inter, Segoe UI, sans-serif", "size": 12, "color": "#334155"},
        "hovermode": "closest",
        "colorway": DEFAULT_COLORS,
    }


def _trace_type(chart_type: str) -> tuple[str, dict[str, Any]]:
    if chart_type in {"bar", "stacked", "histogram", "pie", "scatter", "heatmap"}:
        return chart_type, {}
    return "line", {}


def chart_spec_from_metrics(
    clusters: list[LabelCluster],
    chart_type: str = "line",
    title_prefix: str = "",
    log_y: bool = False,
    y_min: float | None = None,
    y_max: float | None = None,
    max_charts: int = 4,
    colors: list[str] | None = None,
    titles: list[str] | None = None,
) -> list[dict[str, Any]]:
    palette = colors or DEFAULT_COLORS
    specs: list[dict[str, Any]] = []
    for cluster in clusters[:max_charts]:
        metrics = [m for m in cluster.metrics if m.value is not None]
        if not metrics:
            continue
        dimensions = {m.dimension for m in metrics}
        if len(dimensions) > 1:
            # график по доминирующей размерности
            dim = Counter(m.dimension for m in metrics).most_common(1)[0][0]
            metrics = [m for m in metrics if m.dimension == dim]
        dim = metrics[0].dimension
        units = {m.unit for m in metrics}
        if len(units) == 1:
            use_norm = False
            unit = next(iter(units))
        else:
            use_norm = True
            unit = {"money": "базовая валюта", "percent": "%"}.get(dim, "нормализованное значение")
        by_doc: dict[int, list[MetricRecord]] = defaultdict(list)
        for m in metrics:
            by_doc[m.document_id].append(m)
        title = (titles[0] if titles and len(titles) > 0 else f"{title_prefix}{cluster.label}").strip()
        if chart_type == "pie":
            labels = []
            values = []
            texts = []
            custom = []
            for did, recs in sorted(by_doc.items()):
                last = sorted(recs, key=lambda m: _period_sort_key(m.period))[-1]
                labels.append(last.document_name)
                values.append((last.normalized_value if use_norm else last.value) or 0)
                texts.append(_display_value(last.value, last.unit))
                custom.append([last.document_id, last.page, last.document_name])
            data = [
                {
                    "type": "pie",
                    "labels": labels,
                    "values": values,
                    "text": texts,
                    "textinfo": "label+percent",
                    "hovertemplate": "%{label}<br>%{text}<extra></extra>",
                    "marker": {"colors": palette[: len(labels)]},
                }
            ]
            layout = _base_layout(title, "", unit, False)
            layout["yaxis"] = {}
            specs.append(
                {
                    "id": f"chart-{len(specs)}",
                    "title": title,
                    "type": "pie",
                    "unit": unit,
                    "plotly": {"data": data, "layout": layout},
                    "point_count": len(labels),
                }
            )
            continue
        if chart_type == "histogram":
            xs = [(m.normalized_value if use_norm else m.value) or 0 for m in metrics]
            data = [
                {
                    "type": "histogram",
                    "x": xs,
                    "name": cluster.label,
                    "marker": {"color": palette[0]},
                    "hovertemplate": "Значение: %{x}<br>Частота: %{y}<extra></extra>",
                }
            ]
            layout = _base_layout(title, unit, "Частота", False)
            specs.append(
                {
                    "id": f"chart-{len(specs)}",
                    "title": title,
                    "type": "histogram",
                    "unit": unit,
                    "plotly": {"data": data, "layout": layout},
                    "point_count": len(xs),
                }
            )
            continue
        if chart_type == "heatmap":
            periods = sorted({m.period or "—" for m in metrics}, key=_period_sort_key)
            docs = sorted(by_doc, key=lambda d: by_doc[d][0].document_name)
            z = []
            custom = []
            for did in docs:
                row = []
                crow = []
                for p in periods:
                    found = [m for m in by_doc[did] if (m.period or "—") == p]
                    if found:
                        m = found[0]
                        row.append((m.normalized_value if use_norm else m.value) or 0)
                        crow.append([m.document_id, m.page, m.document_name])
                    else:
                        row.append(None)
                        crow.append([did, 0, by_doc[did][0].document_name])
                z.append(row)
                custom.append(crow)
            data = [
                {
                    "type": "heatmap",
                    "z": z,
                    "x": periods,
                    "y": [by_doc[d][0].document_name for d in docs],
                    "customdata": custom,
                    "colorscale": "Viridis",
                    "hovertemplate": "%{y}<br>%{x}: %{z}<extra></extra>",
                }
            ]
            layout = _base_layout(title, "Период", "Документ", False)
            specs.append(
                {
                    "id": f"chart-{len(specs)}",
                    "title": title,
                    "type": "heatmap",
                    "unit": unit,
                    "plotly": {"data": data, "layout": layout},
                    "point_count": sum(1 for row in z for v in row if v is not None),
                }
            )
            continue

        has_periods = any(m.period for m in metrics)
        data = []
        point_count = 0
        for idx, (did, recs) in enumerate(sorted(by_doc.items(), key=lambda kv: kv[1][0].document_name)):
            recs = sorted(recs, key=lambda m: _period_sort_key(m.period))
            x = [(m.period or "—") for m in recs] if has_periods else [m.document_name for m in recs]
            y = [((m.normalized_value if use_norm else m.value) or 0) for m in recs]
            custom = [[m.document_id, m.page, m.document_name, _display_value(m.value, m.unit)] for m in recs]
            point_count += len(recs)
            color = palette[idx % len(palette)]
            if chart_type == "bar":
                trace = {
                    "type": "bar",
                    "x": x,
                    "y": y,
                    "name": recs[0].document_name,
                    "marker": {"color": color},
                    "customdata": custom,
                    "hovertemplate": "%{x}<br>%{customdata[3]}<br>%{customdata[2]}, стр. %{customdata[1]}<extra></extra>",
                }
            elif chart_type == "scatter":
                x = [int(extract_years(m.period)[0]) if extract_years(m.period) else i for i, m in enumerate(recs)]
                trace = {
                    "type": "scatter",
                    "mode": "markers",
                    "x": x,
                    "y": y,
                    "name": recs[0].document_name,
                    "marker": {"color": color, "size": 10},
                    "customdata": custom,
                    "hovertemplate": "%{customdata[2]}, стр. %{customdata[1]}<br>%{customdata[3]}<extra></extra>",
                }
            else:
                trace = {
                    "type": "scatter",
                    "mode": "lines+markers",
                    "x": x,
                    "y": y,
                    "name": recs[0].document_name,
                    "line": {"color": color, "width": 2.5},
                    "marker": {"color": color, "size": 8},
                    "customdata": custom,
                    "hovertemplate": "%{x}<br>%{customdata[3]}<br>%{customdata[2]}, стр. %{customdata[1]}<extra></extra>",
                }
            data.append(trace)
        layout = _base_layout(title, "Период" if has_periods else "Документ", unit, log_y)
        if chart_type in {"bar", "stacked"}:
            layout["barmode"] = "stack" if chart_type == "stacked" else "group"
        if y_min is not None:
            layout["yaxis"]["range"] = [y_min, y_max if y_max is not None else max(
                [p for tr in data for p in tr["y"]] or [1]
            )]
        layout["height"] = 380
        specs.append(
            {
                "id": f"chart-{len(specs)}",
                "title": title,
                "type": chart_type if chart_type in {"bar", "stacked", "scatter"} else "line",
                "unit": unit,
                "plotly": {"data": data, "layout": layout},
                "point_count": point_count,
                "normalized": use_norm,
            }
        )
    return specs


def build_chart_config(
    clusters: list[LabelCluster],
    chart_type: str = "line",
    x_axis: str = "period",
    title: str = "",
    log_y: bool = False,
    y_min: float | None = None,
    y_max: float | None = None,
    colors: list[str] | None = None,
) -> list[dict[str, Any]]:
    """График для страницы «Графики» с выбором оси X."""
    palette = colors or DEFAULT_COLORS
    specs: list[dict[str, Any]] = []
    if x_axis in {"period", "document"} or chart_type in {"pie", "histogram", "heatmap", "scatter"}:
        return chart_spec_from_metrics(
            clusters,
            chart_type=chart_type,
            title_prefix="",
            log_y=log_y,
            y_min=y_min,
            y_max=y_max,
            colors=palette,
            titles=[title] if title else None,
        )
    # x_axis == indicator: один график, серии по документам, по оси X — показатели
    series: dict[int, dict[str, Any]] = defaultdict(lambda: {"x": [], "y": [], "custom": []})
    for cluster in clusters:
        for m in cluster.metrics:
            if m.value is None:
                continue
            rec = series[m.document_id]
            rec["x"].append(cluster.label)
            rec["y"].append(m.normalized_value or 0)
            rec["custom"].append([m.document_id, m.page, m.document_name, _display_value(m.value, m.unit)])
    data = []
    for idx, (did, rec) in enumerate(series.items()):
        name = next(
            (m.document_name for c in clusters for m in c.metrics if m.document_id == did), str(did)
        )
        color = palette[idx % len(palette)]
        if chart_type == "bar":
            data.append(
                {
                    "type": "bar",
                    "x": rec["x"],
                    "y": rec["y"],
                    "name": name,
                    "marker": {"color": color},
                    "customdata": rec["custom"],
                    "hovertemplate": "%{x}<br>%{customdata[3]}<br>%{customdata[2]}, стр. %{customdata[1]}<extra></extra>",
                }
            )
        else:
            data.append(
                {
                    "type": "scatter",
                    "mode": "lines+markers",
                    "x": rec["x"],
                    "y": rec["y"],
                    "name": name,
                    "line": {"color": color},
                    "marker": {"color": color},
                    "customdata": rec["custom"],
                    "hovertemplate": "%{x}<br>%{customdata[3]}<br>%{customdata[2]}, стр. %{customdata[1]}<extra></extra>",
                }
            )
    layout = _base_layout(title or "Сравнение показателей", "Показатель", "Нормализованное значение", log_y)
    layout["height"] = 420
    if data:
        specs.append(
            {
                "id": "chart-0",
                "title": title or "Сравнение показателей",
                "type": chart_type if chart_type in {"bar", "stacked"} else "line",
                "unit": "нормализованные значения",
                "plotly": {"data": data, "layout": layout},
                "point_count": sum(len(r["y"]) for r in series.values()),
            }
        )
    return specs


# ---------------------------------------------------------------------------
# Текстовое сравнение
# ---------------------------------------------------------------------------

_SENT_SPLIT = re.compile(r"(?<=[.!?])\s+")


def _sentences(document: Document, pages: list[Page], limit: int = 500) -> list[dict[str, Any]]:
    result = []
    for page in pages:
        text = page.text or ""
        for part in _SENT_SPLIT.split(text):
            s = clean_text(part)
            if len(s) < 35 or len(s) > 500:
                continue
            if s.startswith("##"):
                continue
            result.append({"text": s, "page": page.number})
            if len(result) >= limit:
                return result
    return result


def compare_texts(db: Session, doc_a: Document, doc_b: Document, max_items: int = 50) -> dict[str, Any]:
    from rapidfuzz import process as rf_process

    pages_a = db.query(Page).filter(Page.document_id == doc_a.id).order_by(Page.number).all()
    pages_b = db.query(Page).filter(Page.document_id == doc_b.id).order_by(Page.number).all()
    a = _sentences(doc_a, pages_a)
    b = _sentences(doc_b, pages_b)
    if not a or not b:
        return {
            "added": [],
            "removed": [],
            "changed": [],
            "warnings": ["Недостаточно текста для текстового сравнения."],
            "summary": "Текстовое сравнение недоступно.",
        }
    b_texts = [x["text"] for x in b]
    matched_b: set[int] = set()
    changed = []
    removed = []
    for item in a:
        match = rf_process.extractOne(item["text"], b_texts, scorer=fuzz.token_set_ratio)
        if not match:
            removed.append(item)
            continue
        _text, score, idx = match
        if score >= 88:
            matched_b.add(idx)
        elif score >= 55:
            matched_b.add(idx)
            changed.append(
                {
                    "old": item["text"],
                    "new": b[idx]["text"],
                    "old_page": item["page"],
                    "new_page": b[idx]["page"],
                    "similarity": round(score, 1),
                }
            )
        else:
            removed.append(item)
        if len(changed) + len(removed) >= max_items * 2:
            break
    added = [b[i] for i in range(len(b)) if i not in matched_b]
    changed = sorted(changed, key=lambda x: -x["similarity"])[:max_items]
    return {
        "added": added[:max_items],
        "removed": removed[:max_items],
        "changed": changed,
        "warnings": [] if (added or removed or changed) else ["Существенных текстовых различий не найдено."],
        "summary": f"Изменённых формулировок: {len(changed)}, добавленных фрагментов: {len(added)}, удалённых: {len(removed)}.",
        "meta": {
            "document_a": doc_a.original_name,
            "document_b": doc_b.original_name,
            "sentences_a": len(a),
            "sentences_b": len(b),
        },
    }


def contradiction_from_text_diff(diff: dict[str, Any]) -> list[dict[str, Any]]:
    findings = []
    for item in diff.get("changed", []):
        old_nums = extract_years(item["old"]) + re.findall(r"\d+(?:[.,]\d+)?", item["old"])
        new_nums = extract_years(item["new"]) + re.findall(r"\d+(?:[.,]\d+)?", item["new"])
        if set(old_nums) != set(new_nums):
            findings.append(
                {
                    "type": "text_contradiction",
                    "text": f"Формулировки различаются числами: «{item['old'][:180]}» → «{item['new'][:180]}».",
                    "page": item.get("old_page"),
                    "severity": "warning",
                }
            )
    return findings[:20]


def source_links(citations: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return _dedupe_citations(citations)
