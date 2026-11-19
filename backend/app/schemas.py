from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ProjectCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    description: str = ""


class ProjectUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None


class QueryRequest(BaseModel):
    project_id: int
    query: str = Field(min_length=1)
    document_ids: list[int] | None = None
    metric_labels: list[str] | None = None
    options: dict[str, Any] = Field(default_factory=dict)


class CompareRequest(BaseModel):
    project_id: int
    document_ids: list[int] = Field(min_length=2)
    metric_labels: list[str] | None = None
    years: list[str] | None = None
    save: bool = True


class TableRequest(BaseModel):
    project_id: int
    type: str = "summary"
    document_ids: list[int] | None = None
    metric_labels: list[str] | None = None
    years: list[str] | None = None
    columns: list[str] | None = None
    sort: list[dict[str, Any]] | None = None
    filters: dict[str, Any] = Field(default_factory=dict)
    group_by: str | None = None
    limit: int | None = 2000
    query: str = ""


class ChartRequest(BaseModel):
    project_id: int
    document_ids: list[int] | None = None
    metric_labels: list[str] | None = None
    years: list[str] | None = None
    chart_type: str = "line"
    x_axis: str = "period"
    title: str = ""
    log_y: bool = False
    y_min: float | None = None
    y_max: float | None = None
    colors: list[str] | None = None
    query: str = ""


class SearchRequest(BaseModel):
    project_id: int
    query: str
    document_ids: list[int] | None = None
    limit: int = 20


class ExportRequest(BaseModel):
    model_config = ConfigDict(extra="allow")

    analysis_id: int | None = None
    title: str | None = None
    query: str | None = None
    answer: str | None = None
    summary: str | None = None
    findings: list[Any] | None = None
    warnings: list[Any] | None = None
    methods: list[Any] | None = None
    tables: list[dict[str, Any]] | None = None
    table: dict[str, Any] | None = None
    charts: list[dict[str, Any]] | None = None
    citations: list[dict[str, Any]] | None = None
    documents: list[dict[str, Any]] | None = None
    meta: dict[str, Any] | None = None
    intent: str | None = None


class SettingsUpdate(BaseModel):
    model_config = ConfigDict(extra="allow")

    ai_provider: str | None = None
    openai_base_url: str | None = None
    openai_api_key: str | None = None
    openai_model: str | None = None
    openai_embedding_model: str | None = None
    ollama_base_url: str | None = None
    ollama_model: str | None = None
    ollama_embedding_model: str | None = None
    ai_temperature: float | None = None
    ai_timeout_seconds: int | None = None
    semantic_search: bool | None = None
    ocr_enabled: bool | None = None
    ocr_languages: str | None = None
    ocr_dpi: int | None = None
    ocr_min_confidence: float | None = None
    ocr_auto: bool | None = None
    tesseract_cmd: str | None = None
    interface_language: str | None = None
    export_page_size: str | None = None
    export_include_sources: bool | None = None
    max_upload_mb: int | None = None
