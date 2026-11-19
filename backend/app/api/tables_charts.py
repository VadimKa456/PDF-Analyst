from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Project
from ..schemas import ChartRequest, TableRequest
from ..services import builders

router = APIRouter(prefix="/api", tags=["tables-charts"])


@router.post("/tables/build")
def build_table(body: TableRequest, db: Session = Depends(get_db)):
    if not db.get(Project, body.project_id):
        raise HTTPException(404, "Проект не найден")
    try:
        return builders.build_table(db, body.project_id, body.model_dump())
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(500, f"Ошибка построения таблицы: {exc}") from exc


@router.post("/charts/build")
def build_chart(body: ChartRequest, db: Session = Depends(get_db)):
    if not db.get(Project, body.project_id):
        raise HTTPException(404, "Проект не найден")
    try:
        return builders.build_chart(db, body.project_id, body.model_dump())
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(500, f"Ошибка построения графика: {exc}") from exc
