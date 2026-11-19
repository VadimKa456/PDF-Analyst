"""Пользовательские настройки, сохраняемые в SQLite (приоритет над .env)."""
from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from ..config import settings as env
from ..models import Setting

SETTINGS_KEY = "app"


def default_runtime_settings() -> dict[str, Any]:
    return {
        "ai_provider": env.ai_provider if env.ai_provider in {"none", "openai", "ollama"} else "none",
        "openai_base_url": env.openai_base_url,
        "openai_api_key": env.openai_api_key,
        "openai_model": env.openai_model,
        "openai_embedding_model": env.openai_embedding_model,
        "ollama_base_url": env.ollama_base_url,
        "ollama_model": env.ollama_model,
        "ollama_embedding_model": env.ollama_embedding_model,
        "ai_temperature": env.ai_temperature,
        "ai_timeout_seconds": env.ai_timeout_seconds,
        "semantic_search": env.semantic_search,
        "ocr_enabled": env.ocr_enabled,
        "ocr_languages": env.ocr_languages,
        "ocr_dpi": env.ocr_dpi,
        "ocr_min_confidence": env.ocr_min_confidence,
        "ocr_auto": env.ocr_auto,
        "tesseract_cmd": env.tesseract_cmd,
        "interface_language": "ru",
        "export_page_size": env.report_page_size,
        "export_include_sources": env.report_include_sources,
        "max_upload_mb": env.max_upload_mb,
    }


def get_runtime_settings(db: Session) -> dict[str, Any]:
    row = db.get(Setting, SETTINGS_KEY)
    merged = default_runtime_settings()
    if row and isinstance(row.value, dict):
        merged.update(row.value)
    return merged


def save_runtime_settings(db: Session, patch: dict[str, Any]) -> dict[str, Any]:
    row = db.get(Setting, SETTINGS_KEY)
    current = get_runtime_settings(db)
    allowed = set(default_runtime_settings().keys())
    for key, value in (patch or {}).items():
        if key in allowed:
            current[key] = value
    if row is None:
        row = Setting(key=SETTINGS_KEY, value=current)
        db.add(row)
    else:
        row.value = current
    db.commit()
    # применяем настройки OCR на лету
    if "tesseract_cmd" in patch or "ocr_languages" in patch:
        from . import pdf_processor

        pdf_processor._tesseract_ready = None  # noqa: SLF001
    return current


def public_settings(db: Session) -> dict[str, Any]:
    from ..utils import mask_key

    s = get_runtime_settings(db)
    s = dict(s)
    configured = bool(
        s.get("ai_provider") == "ollama"
        or (s.get("ai_provider") == "openai" and s.get("openai_api_key"))
    )
    s["openai_api_key_masked"] = mask_key(s.get("openai_api_key", ""))
    s["openai_api_key"] = ""
    s["ai_configured"] = configured
    return s
