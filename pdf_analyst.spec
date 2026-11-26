# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for PDF Analyst desktop build.

Сборка (из корня проекта, в активированном .venv):
  python -m PyInstaller --noconfirm --clean pdf_analyst.spec

Результат: dist/PDF Analyst/ (onedir). Для onefile установите onefile=True
ниже, но запуск будет медленнее и возможны проблемы с антивирусами.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs, collect_submodules

block_cipher = None
project_dir = Path(SPECPATH).resolve()
# collect_submodules("backend") требует, чтобы пакет был доступен на этапе
# выполнения spec-файла (PyInstaller не добавляет SPECPATH в sys.path сам).
for _p in (str(project_dir), str(project_dir / "backend")):
    if _p not in sys.path:
        sys.path.insert(0, _p)
onefile = False  # True -> один exe (медленный старт); False -> папка (рекомендуется)

datas = []
binaries = []
hiddenimports = []


def _is_runtime_module(module_name: str) -> bool:
    """Exclude test suites and developer-only modules from the desktop bundle."""
    parts = module_name.lower().split(".")
    if any(part in {"test", "tests", "testing"} for part in parts):
        return False
    if any(part.startswith("test_") for part in parts):
        return False
    if module_name == "backend._final_e2e":
        return False
    return True


# Frontend (собранный UI)
frontend_dist = project_dir / "frontend" / "dist"
if frontend_dist.exists():
    datas.append((str(frontend_dist), "frontend/dist"))

# .env.example как шаблон (опционально)
if (project_dir / ".env.example").exists():
    datas.append((str(project_dir / ".env.example"), "."))

# MIT-лицензия (доступна в собранном приложении)
if (project_dir / "LICENSE").exists():
    datas.append((str(project_dir / "LICENSE"), "."))

# Пакеты с неочевидными импортами/данными
for pkg in (
    "uvicorn",
    "fastapi",
    "starlette",
    "pydantic",
    "pydantic_settings",
    "sqlalchemy",
    "pymupdf",
    "pdfplumber",
    "PIL",
    "cv2",
    "numpy",
    "pandas",
    "openpyxl",
    "reportlab",
    "matplotlib",
    "rapidfuzz",
    "pytesseract",
    "httpx",
    "anyio",
    "multipart",
    "python_multipart",
):
    try:
        hiddenimports += collect_submodules(pkg, filter=_is_runtime_module)
    except Exception:
        pass
    try:
        datas += collect_data_files(pkg)
    except Exception:
        pass
    try:
        binaries += collect_dynamic_libs(pkg)
    except Exception:
        pass

# Явные скрытые импорты uvicorn/sqlalchemy
hiddenimports += [
    "uvicorn.logging",
    "uvicorn.loops",
    "uvicorn.loops.auto",
    "uvicorn.loops.asyncio",
    "uvicorn.protocols",
    "uvicorn.protocols.http",
    "uvicorn.protocols.http.auto",
    "uvicorn.protocols.http.h11_impl",
    "uvicorn.protocols.websockets",
    "uvicorn.protocols.websockets.auto",
    "uvicorn.lifespan",
    "uvicorn.lifespan.on",
    "sqlalchemy.dialects.sqlite",
]

# Backend package
hiddenimports += collect_submodules("backend", filter=_is_runtime_module)


a = Analysis(
    [str(project_dir / "desktop_app.py")],
    pathex=[str(project_dir), str(project_dir / "backend")],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "tkinter.test",
        "test",
        "pytest",
        # Большие/ненужные в рантайме части (если не используются)
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

if onefile:
    exe = EXE(
        pyz,
        a.scripts,
        a.binaries,
        a.zipfiles,
        a.datas,
        [],
        name="PDF Analyst",
        debug=False,
        bootloader_ignore_signals=False,
        strip=False,
        upx=True,
        upx_exclude=[],
        runtime_tmpdir=None,
        console=False,
        disable_windowed_traceback=False,
        argv_emulation=False,
        target_arch=None,
        codesign_identity=None,
        entitlements_file=None,
        icon=None,
    )
    coll = None
else:
    exe = EXE(
        pyz,
        a.scripts,
        [],
        exclude_binaries=True,
        name="PDF Analyst",
        debug=False,
        bootloader_ignore_signals=False,
        strip=False,
        upx=True,
        console=False,
        disable_windowed_traceback=False,
        argv_emulation=False,
        target_arch=None,
        codesign_identity=None,
        entitlements_file=None,
        icon=None,
    )
    coll = COLLECT(
        exe,
        a.binaries,
        a.zipfiles,
        a.datas,
        strip=False,
        upx=True,
        upx_exclude=[],
        name="PDF Analyst",
    )
