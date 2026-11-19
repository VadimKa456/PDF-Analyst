from __future__ import annotations

import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, text
from sqlalchemy.orm import Session

from ..config import settings
from ..database import get_db
from ..models import Analysis, Document, Project
from ..schemas import ProjectCreate, ProjectUpdate

router = APIRouter(prefix="/api/projects", tags=["projects"])


def _project_payload(db: Session, p: Project) -> dict[str, Any]:
    doc_count = db.query(func.count(Document.id)).filter(Document.project_id == p.id).scalar() or 0
    ready = (
        db.query(func.count(Document.id))
        .filter(Document.project_id == p.id, Document.status == "ready")
        .scalar()
        or 0
    )
    pages = (
        db.query(func.coalesce(func.sum(Document.page_count), 0))
        .filter(Document.project_id == p.id)
        .scalar()
        or 0
    )
    analyses = (
        db.query(func.count(Analysis.id)).filter(Analysis.project_id == p.id).scalar() or 0
    )
    return {
        "id": p.id,
        "name": p.name,
        "description": p.description or "",
        "created_at": p.created_at.isoformat() if p.created_at else None,
        "updated_at": p.updated_at.isoformat() if p.updated_at else None,
        "last_opened_at": p.last_opened_at.isoformat() if p.last_opened_at else None,
        "document_count": doc_count,
        "ready_count": ready,
        "page_count": pages,
        "analysis_count": analyses,
    }


def _get_project(db: Session, project_id: int) -> Project:
    p = db.get(Project, project_id)
    if not p:
        raise HTTPException(404, "Проект не найден")
    return p


@router.get("")
def list_projects(db: Session = Depends(get_db)):
    projects = db.query(Project).order_by(Project.last_opened_at.desc(), Project.id.desc()).all()
    return [_project_payload(db, p) for p in projects]


@router.post("")
def create_project(body: ProjectCreate, db: Session = Depends(get_db)):
    name = body.name.strip()
    if not name:
        raise HTTPException(422, "Название проекта не может быть пустым")
    project = Project(name=name, description=body.description.strip())
    db.add(project)
    db.commit()
    db.refresh(project)
    (settings.uploads_dir / f"project_{project.id}").mkdir(parents=True, exist_ok=True)
    return _project_payload(db, project)


@router.get("/{project_id}")
def get_project(project_id: int, db: Session = Depends(get_db)):
    return _project_payload(db, _get_project(db, project_id))


@router.put("/{project_id}")
def update_project(project_id: int, body: ProjectUpdate, db: Session = Depends(get_db)):
    project = _get_project(db, project_id)
    if body.name is not None:
        project.name = body.name.strip() or project.name
    if body.description is not None:
        project.description = body.description
    db.commit()
    db.refresh(project)
    return _project_payload(db, project)


@router.post("/{project_id}/open")
def open_project(project_id: int, db: Session = Depends(get_db)):
    project = _get_project(db, project_id)
    project.last_opened_at = datetime.now(timezone.utc).replace(tzinfo=None)
    db.commit()
    return _project_payload(db, project)


@router.delete("/{project_id}")
def delete_project(project_id: int, db: Session = Depends(get_db)):
    """Удаляет проект вместе со всеми документами, показателями и историями."""
    project = _get_project(db, project_id)

    # Не удаляем проект, пока идёт фоновая обработка его документов —
    # иначе воркер попытается записать результаты в уже удалённый проект.
    active = (
        db.query(func.count(Document.id))
        .filter(
            Document.project_id == project_id,
            Document.status.in_(("pending", "processing")),
        )
        .scalar()
        or 0
    )
    if active:
        raise HTTPException(
            409,
            f"В проекте обрабатывается {active} документ(ов). Дождитесь завершения и повторите удаление.",
        )

    # FTS5-индекс — виртуальная таблица без внешних ключей, поэтому его
    # нужно чистять вручную до каскадного удаления документов.
    doc_ids = [
        row[0]
        for row in db.query(Document.id).filter(Document.project_id == project_id).all()
    ]
    # FTS5-таблица не имеет внешних ключей: чистим по project_id (включая
    # возможные старые «осиротевшие» строки) и дополнительно по document_id.
    db.execute(text("DELETE FROM chunk_fts WHERE project_id = :pid"), {"pid": project_id})
    for did in doc_ids:
        db.execute(text("DELETE FROM chunk_fts WHERE document_id = :did"), {"did": did})

    folder = settings.uploads_dir / f"project_{project_id}"
    db.delete(project)
    db.commit()
    if folder.exists():
        shutil.rmtree(folder, ignore_errors=True)
    return {"ok": True, "deleted_documents": len(doc_ids), "project_id": project_id}
