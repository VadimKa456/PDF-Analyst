from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..config import settings as env
from ..database import get_db
from ..models import Chunk, Document, Metric
from ..schemas import SettingsUpdate
from ..services.ai_client import AIClient
from ..services.ai_url import validate_ai_base_url
from ..services.pdf_processor import configure_tesseract, tesseract_status
from ..services.runtime_settings import (
    get_runtime_settings,
    public_settings,
    save_runtime_settings,
)

router = APIRouter(prefix="/api/settings", tags=["settings"])


def capabilities(db: Session, runtime: dict[str, Any]) -> dict[str, Any]:
    tess = tesseract_status(str(runtime.get("tesseract_cmd") or ""))
    db_size = env.db_path.stat().st_size if env.db_path.exists() else 0
    docs = db.query(Document).count()
    metrics = db.query(Metric).count()
    chunks = db.query(Chunk).count()
    return {
        "tesseract": tess,
        "data_dir": str(env.data_dir),
        "db_path": str(env.db_path),
        "db_size": db_size,
        "frontend_built": (env.frontend_dist / "index.html").exists(),
        "documents": docs,
        "metrics": metrics,
        "chunks": chunks,
        "ai_configured": bool(
            runtime.get("ai_provider") == "ollama"
            or (runtime.get("ai_provider") == "openai" and runtime.get("openai_api_key"))
        ),
    }


@router.get("")
def get_settings(db: Session = Depends(get_db)):
    runtime = get_runtime_settings(db)
    return {
        "settings": public_settings(db),
        "capabilities": capabilities(db, runtime),
    }


def _validate_patch(patch: dict[str, Any]) -> dict[str, Any]:
    selected_provider = str(patch.get("ai_provider") or "").lower()
    for key, provider, label in (
        ("openai_base_url", "openai", "OpenAI-compatible endpoint"),
        ("ollama_base_url", "ollama", "Ollama endpoint"),
    ):
        # The settings form sends both provider URLs. Validate the active
        # provider, or the URL itself when a client updates it independently.
        if (
            key in patch
            and patch[key]
            and (not selected_provider or selected_provider == provider)
        ):
            try:
                patch[key] = validate_ai_base_url(
                    str(patch[key]), setting_name=label
                )
            except ValueError as exc:
                raise HTTPException(422, str(exc)) from exc

    if "ai_provider" in patch and patch["ai_provider"] not in {"none", "openai", "ollama"}:
        raise HTTPException(422, "Провайдер AI должен быть none, openai или ollama")
    if "interface_language" in patch and patch["interface_language"] not in {"ru", "en"}:
        raise HTTPException(422, "Язык интерфейса: ru или en")
    if "ai_temperature" in patch:
        try:
            t = float(patch["ai_temperature"])
        except (TypeError, ValueError):
            raise HTTPException(422, "Температура должна быть числом") from None
        if not 0 <= t <= 2:
            raise HTTPException(422, "Температура должна быть в диапазоне 0–2")
    if "ai_timeout_seconds" in patch:
        try:
            t = int(patch["ai_timeout_seconds"])
        except (TypeError, ValueError):
            raise HTTPException(422, "Таймаут должен быть числом") from None
        if not 5 <= t <= 900:
            raise HTTPException(422, "Таймаут должен быть в диапазоне 5–900 секунд")
    if "ocr_dpi" in patch:
        try:
            dpi = int(patch["ocr_dpi"])
        except (TypeError, ValueError):
            raise HTTPException(422, "DPI должен быть числом") from None
        if not 150 <= dpi <= 600:
            raise HTTPException(422, "DPI должен быть в диапазоне 150–600")
    if "ocr_min_confidence" in patch:
        try:
            conf = float(patch["ocr_min_confidence"])
        except (TypeError, ValueError):
            raise HTTPException(422, "Порог уверенности должен быть числом") from None
        if not 0 <= conf <= 100:
            raise HTTPException(422, "Порог уверенности должен быть в диапазоне 0–100")
    if "max_upload_mb" in patch:
        try:
            size = int(patch["max_upload_mb"])
        except (TypeError, ValueError):
            raise HTTPException(422, "Размер загрузки должен быть числом") from None
        if not 1 <= size <= 1000:
            raise HTTPException(422, "Максимальный размер должен быть в диапазоне 1–1000 МБ")
    if "tesseract_cmd" in patch:
        cmd = str(patch.get("tesseract_cmd") or "").strip()
        if cmd and not Path(cmd).exists():
            raise HTTPException(422, "Указанный путь к tesseract.exe не существует")
    return patch


@router.put("")
def update_settings(body: SettingsUpdate, db: Session = Depends(get_db)):
    patch = body.model_dump(exclude_none=True)
    if patch.get("openai_api_key", "").strip() == "":
        patch.pop("openai_api_key", None)
    elif patch.get("openai_api_key") == "__clear__":
        patch["openai_api_key"] = ""
    _validate_patch(patch)
    save_runtime_settings(db, patch)
    runtime = get_runtime_settings(db)
    return {
        "settings": public_settings(db),
        "capabilities": capabilities(db, runtime),
    }


@router.post("/ai/test")
def test_ai(body: dict[str, Any] | None = None, db: Session = Depends(get_db)):
    runtime = _runtime_with_overrides(db, body)
    client = AIClient(runtime)
    return client.test()


def _runtime_with_overrides(db: Session, body: dict[str, Any] | None) -> dict[str, Any]:
    """Сохраняет настройки из БД и накладывает значения из формы (без сохранения)."""
    runtime = get_runtime_settings(db)
    overrides = body or {}
    for key in (
        "ai_provider",
        "openai_base_url",
        "openai_api_key",
        "openai_model",
        "openai_embedding_model",
        "ollama_base_url",
        "ollama_model",
        "ollama_embedding_model",
        "ai_timeout_seconds",
        "ai_temperature",
    ):
        if overrides.get(key) not in (None, ""):
            runtime[key] = overrides[key]
    if overrides.get("openai_api_key") == "__clear__":
        runtime["openai_api_key"] = ""

    selected_endpoint = {
        "openai": ("openai_base_url", "OpenAI-compatible endpoint"),
        "ollama": ("ollama_base_url", "Ollama endpoint"),
    }.get(str(runtime.get("ai_provider") or "none").lower())
    if selected_endpoint:
        key, label = selected_endpoint
        configured_url = str(runtime.get(key) or "").strip()
        if configured_url:
            try:
                runtime[key] = validate_ai_base_url(configured_url, setting_name=label)
            except ValueError as exc:
                raise HTTPException(422, str(exc)) from exc
    return runtime


@router.get("/ai/models")
def ai_models(db: Session = Depends(get_db)):
    runtime = get_runtime_settings(db)
    client = AIClient(runtime)
    try:
        return {"models": client.list_models(), "provider": client.provider}
    except Exception as exc:  # noqa: BLE001
        return {"models": [], "provider": client.provider, "error": str(exc)}


@router.post("/ai/models")
def ai_models_with_overrides(body: dict[str, Any] | None = None, db: Session = Depends(get_db)):
    """Список моделей с учётом введённых, но ещё не сохранённых настроек."""
    runtime = _runtime_with_overrides(db, body)
    client = AIClient(runtime)
    if not client.available:
        return {
            "models": [],
            "provider": client.provider,
            "error": "Провайдер не настроен или не указан API-ключ",
        }
    try:
        return {"models": client.list_models(), "provider": client.provider}
    except Exception as exc:  # noqa: BLE001
        return {"models": [], "provider": client.provider, "error": str(exc)}


@router.post("/ai/embedding/test")
def test_embedding(body: dict[str, Any] | None = None, db: Session = Depends(get_db)):
    """Проверяет, что выбранная модель эмбеддингов действительно доступна."""
    runtime = _runtime_with_overrides(db, body)
    client = AIClient(runtime)
    if not client.available:
        return {
            "ok": False,
            "model": client.embedding_model,
            "error": "Провайдер не настроен или не указан API-ключ",
        }
    try:
        vectors = client.embed(["проверка эмбеддингов"])
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "model": client.embedding_model, "error": str(exc)}
    dims = len(vectors[0]) if vectors else 0
    if not dims:
        return {"ok": False, "model": client.embedding_model, "error": "Пустой ответ embeddings"}
    return {"ok": True, "model": client.embedding_model, "dimensions": dims}


@router.post("/ocr/check")
def ocr_check(body: dict[str, Any] | None = None, db: Session = Depends(get_db)):
    runtime = get_runtime_settings(db)
    cmd = (body or {}).get("tesseract_cmd") or runtime.get("tesseract_cmd") or ""
    configure_tesseract(str(cmd))
    return tesseract_status(str(cmd))
