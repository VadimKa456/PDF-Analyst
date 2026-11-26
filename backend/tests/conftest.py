"""Общие фикстуры и помощники для тестов."""
from __future__ import annotations

import os
import sys
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

ROOT_DIR = BACKEND_DIR.parent
SAMPLES_DIR = ROOT_DIR / "samples" / "pdfs"


def make_document(doc_id: int, name: str) -> SimpleNamespace:
    """Лёгкая замена ORM-модели Document для чистых тестов аналитики."""
    return SimpleNamespace(
        id=doc_id,
        original_name=name,
        created_at=datetime(2024, 1, 1),
    )


def make_metric(
    *,
    metric_id: int,
    document: SimpleNamespace,
    label: str,
    value: float | None,
    unit: str = "млн руб.",
    dimension: str = "money",
    scale: float = 1_000_000.0,
    currency: str = "RUB",
    period: str = "2024",
    page: int = 1,
    context: str | None = None,
    source_kind: str = "table",
    confidence: float = 0.95,
    entity_key: str = "",
    normalized_label: str | None = None,
) -> Any:
    from app.services.analytics import MetricRecord
    from app.utils import canonical_label, normalize_label

    norm = normalized_label if normalized_label is not None else canonical_label(label)
    return MetricRecord(
        id=metric_id,
        document_id=document.id,
        document_name=document.original_name,
        document_created=document.created_at,
        page=page,
        label=label,
        normalized_label=norm or normalize_label(label),
        value=value,
        normalized_value=None if value is None else value * scale,
        unit=unit,
        dimension=dimension,
        scale=scale,
        currency=currency,
        period=period,
        raw_value="" if value is None else f"{value:g}",
        raw_text=f"{label}: {value}",
        context=context or f"{document.original_name}, стр. {page}: {label} — {value} {unit}",
        confidence=confidence,
        source_kind=source_kind,
        source_ref=f"p{page}",
        entity_key=entity_key,
    )


@pytest.fixture(scope="session")
def samples_dir() -> Path:
    if not SAMPLES_DIR.exists():
        pytest.skip(f"Каталог с примерами PDF не найден: {SAMPLES_DIR}")
    return SAMPLES_DIR


@pytest.fixture(scope="session")
def alpha_2024_pdf(samples_dir: Path) -> Path:
    path = samples_dir / "alpha_2024.pdf"
    if not path.exists():
        pytest.skip(f"Нет файла {path}")
    return path


@pytest.fixture(scope="session")
def english_pdf(samples_dir: Path) -> Path:
    path = samples_dir / "beta_2025_english.pdf"
    if not path.exists():
        pytest.skip(f"Нет файла {path}")
    return path


@pytest.fixture(scope="session")
def scanned_pdf(samples_dir: Path) -> Path:
    path = samples_dir / "alpha_2024_scanned.pdf"
    if not path.exists():
        pytest.skip(f"Нет файла {path}")
    return path
