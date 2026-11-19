from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text

from .api import analysis, compare, dashboard, documents, exports, options, projects, search, settings as settings_api, tables_charts
from .config import settings
from .database import SessionLocal, init_db
from .models import Project
from .services import jobs
from .services.pdf_processor import tesseract_status
from .services.runtime_settings import get_runtime_settings

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)
logger = logging.getLogger("pdf-analyst")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
    from .models import Analysis, Document, Metric, Page, Table  # noqa: F401
    with SessionLocal() as db:
        if db.query(Project).first() is None:
            db.add(Project(name="Мой проект", description="Проект по умолчанию"))
            db.commit()
        try:
            db.execute(text("SELECT count(*) FROM chunk_fts"))
        except Exception:  # noqa: BLE001
            init_db()
    # Чистка «осиротевших» записей FTS от прежних версий, где удаление проекта
    # не удаляло индекс (проект/документ уже отсутствует в основных таблицах).
    with SessionLocal() as db:
        db.execute(
            text(
                "DELETE FROM chunk_fts WHERE "
                "document_id NOT IN (SELECT id FROM documents) "
                "OR project_id NOT IN (SELECT id FROM projects)"
            )
        )
        db.commit()
    resumed = jobs.resume_unfinished()
    if resumed:
        logger.info("Resumed %s unfinished documents", resumed)
    logger.info("PDF Analyst started; data=%s", settings.data_dir)
    yield
    jobs.shutdown()


app = FastAPI(
    title="PDF Analyst",
    version=settings.app_version,
    description="Локальная система анализа и сравнения PDF-документов",
    lifespan=lifespan,
    docs_url="/api/docs",
    openapi_url="/api/openapi.json",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list or ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["Content-Disposition"],
)

for router in (
    projects.router,
    documents.router,
    analysis.router,
    search.router,
    options.router,
    compare.router,
    tables_charts.router,
    dashboard.router,
    settings_api.router,
    exports.router,
):
    app.include_router(router)


@app.get("/api/health")
def health():
    with SessionLocal() as db:
        runtime = get_runtime_settings(db)
        docs = db.execute(text("SELECT count(*) FROM documents")).scalar() or 0
    return {
        "status": "ok",
        "version": settings.app_version,
        "about": {
            "name": settings.app_name,
            "version": settings.app_version,
            "author": settings.app_author,
            "email": settings.app_author_email,
            "license": settings.app_license,
            "copyright": f"© 2026 {settings.app_author}",
        },
        "documents": docs,
        "tesseract": tesseract_status(str(runtime.get("tesseract_cmd") or "")),
        "ai": {
            "provider": runtime.get("ai_provider"),
            "configured": bool(
                runtime.get("ai_provider") == "ollama"
                or (runtime.get("ai_provider") == "openai" and runtime.get("openai_api_key"))
            ),
        },
        "data_dir": str(settings.data_dir),
    }


@app.get("/api")
def api_root():
    return {
        "name": settings.app_name,
        "version": settings.app_version,
        "docs": "/api/docs",
    }


dist = settings.frontend_dist
if (dist / "assets").exists():
    app.mount("/assets", StaticFiles(directory=str(dist / "assets")), name="assets")


@app.get("/{full_path:path}", include_in_schema=False)
def spa(full_path: str):
    if full_path.startswith("api/") or full_path == "api":
        raise HTTPException(404, "Not found")
    index = dist / "index.html"
    if full_path:
        candidate = (dist / full_path).resolve()
        try:
            candidate.relative_to(dist.resolve())
        except ValueError:
            raise HTTPException(404, "Not found") from None
        if candidate.is_file():
            return FileResponse(candidate)
    if index.exists():
        return FileResponse(index, media_type="text/html")
    return HTMLResponse(
        """<!doctype html><html lang="ru"><head><meta charset="utf-8">
        <title>PDF Analyst</title><style>body{font-family:Segoe UI,sans-serif;background:#f8fafc;color:#1e293b;
        display:flex;align-items:center;justify-content:center;height:100vh;margin:0}
        .card{background:#fff;border:1px solid #e2e8f0;border-radius:16px;padding:36px;max-width:620px;
        box-shadow:0 20px 50px rgba(15,23,42,.08)}code{background:#eef2ff;padding:3px 7px;border-radius:5px;
        color:#4338ca}h1{margin-top:0}</style></head><body><div class="card">
        <h1>PDF Analyst — API работает</h1>
        <p>Frontend ещё не собран. Выполните в каталоге <code>frontend</code>:</p>
        <pre><code>npm install
npm run build</code></pre>
        <p>Затем перезапустите сервер. API документация: <a href="/api/docs">/api/docs</a>.</p>
        </div></body></html>""",
        status_code=503,
    )
