"""Конфигурация приложения.

Значения читаются из переменных окружения / .env. Пользовательские настройки,
сохранённые в БД через интерфейс, имеют приоритет (см. services/runtime_settings.py).
"""
from __future__ import annotations

import os
import shutil
import sys
from functools import lru_cache
from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def _is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def _bundle_dir() -> Path:
    """Каталог с read-only ресурсами (исходники в dev, распакованный bundle в exe)."""
    if _is_frozen():
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).resolve().parent))
    return Path(__file__).resolve().parents[2]


def _app_dir() -> Path:
    """Базовый каталог приложения (рядом с exe или корень проекта)."""
    if _is_frozen():
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[2]


def _default_data_dir() -> Path:
    # Для установленного/упакованного приложения пишем в профиль пользователя,
    # чтобы не требовать прав на запись в Program Files.
    if _is_frozen() or os.environ.get("PDF_ANALYST_PORTABLE") == "0":
        base = Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local")
        return base / "PDF Analyst" / "data"
    return _app_dir() / "data"


ROOT_DIR = _bundle_dir()
APP_DIR = _app_dir()
BACKEND_DIR = ROOT_DIR / "backend"


def _env_files() -> tuple[str, ...]:
    candidates = []
    # .env рядом с exe/проектом имеет приоритет для конфигурации окружения
    for p in (APP_DIR / ".env", ROOT_DIR / ".env"):
        if p.exists():
            candidates.append(str(p))
    # если ничего не найдено, всё равно укажем путь рядом с приложением
    if not candidates:
        candidates.append(str(APP_DIR / ".env"))
    # уникальные, с сохранением порядка
    seen: set[str] = set()
    out: list[str] = []
    for c in candidates:
        if c not in seen:
            seen.add(c)
            out.append(c)
    return tuple(out)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=_env_files(),
        env_file_encoding="utf-8-sig",
        extra="ignore",
        case_sensitive=False,
    )

    app_name: str = "PDF Analyst"
    app_version: str = "1.1.0"
    app_author: str = "VADIJI | AI Creative Studio"
    app_author_email: str = "vadiji.ai@gmail.com"
    app_license: str = "MIT"
    host: str = "127.0.0.1"
    port: int = 8000
    data_dir: Path = _default_data_dir()
    max_upload_mb: int = 100
    cors_origins: str = (
        "http://localhost:5173,http://127.0.0.1:5173,"
        "http://localhost:8000,http://127.0.0.1:8000"
    )

    tesseract_cmd: str = ""
    ocr_enabled: bool = True
    ocr_languages: str = "rus+eng"
    ocr_dpi: int = 300
    ocr_min_confidence: float = 65.0
    ocr_auto: bool = True

    openai_api_key: str = ""
    openai_base_url: str = "https://api.openai.com/v1"
    openai_model: str = "gpt-4o-mini"
    openai_embedding_model: str = "text-embedding-3-small"

    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "llama3.1"
    ollama_embedding_model: str = "nomic-embed-text"

    ai_provider: str = "none"  # none | openai | ollama
    ai_temperature: float = 0.1
    ai_timeout_seconds: int = 90
    semantic_search: bool = False

    report_page_size: str = "A4"
    report_include_sources: bool = True

    @field_validator("data_dir", mode="after")
    @classmethod
    def _resolve_data_dir(cls, value: Path) -> Path:
        """Относительный DATA_DIR считается от каталога приложения."""
        if value.is_absolute():
            return value
        base = APP_DIR if _is_frozen() else ROOT_DIR
        return (base / value).resolve()

    @property
    def db_path(self) -> Path:
        return self.data_dir / "app.db"

    @property
    def uploads_dir(self) -> Path:
        return self.data_dir / "uploads"

    @property
    def exports_dir(self) -> Path:
        return self.data_dir / "exports"

    @property
    def frontend_dist(self) -> Path:
        # В bundle frontend кладём в <bundle>/frontend/dist
        for candidate in (ROOT_DIR / "frontend" / "dist", APP_DIR / "frontend" / "dist"):
            if (candidate / "index.html").exists():
                return candidate
        return ROOT_DIR / "frontend" / "dist"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    def ensure_dirs(self) -> None:
        for d in (self.data_dir, self.uploads_dir, self.exports_dir):
            d.mkdir(parents=True, exist_ok=True)


def find_tesseract() -> str | None:
    """Ищет исполняемый файл Tesseract в типичных местах."""
    env = os.environ.get("TESSERACT_CMD", "").strip()
    if env and Path(env).exists():
        return env
    found = shutil.which("tesseract")
    if found:
        return found
    candidates = [
        Path(os.environ.get("LOCALAPPDATA", "")) / "Programs/Tesseract-OCR/tesseract.exe",
        Path(os.environ.get("LOCALAPPDATA", "")) / "Tesseract-OCR/tesseract.exe",
        Path(r"C:\Program Files\Tesseract-OCR\tesseract.exe"),
        Path(r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe"),
        Path("/usr/bin/tesseract"),
        Path("/usr/local/bin/tesseract"),
    ]
    for p in candidates:
        try:
            if p.exists():
                return str(p)
        except OSError:
            continue
    return None


@lru_cache
def get_settings() -> Settings:
    s = Settings()
    s.ensure_dirs()
    return s


settings = get_settings()
