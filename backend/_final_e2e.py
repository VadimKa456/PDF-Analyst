"""Финальная проверка приложения через живой HTTP-сервер.

Проверяет полный путь UI → API → обработка → БД → ответ:
загрузка 14 PDF, прогресс, страницы/таблицы/показатели, панель,
вопросы AI-аналитика, сравнение, таблицы, графики, экспорт и настройки.
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

import httpx

BASE = "http://127.0.0.1:8000"
ROOT = Path(__file__).resolve().parents[1]
PDFS = sorted((ROOT / "samples" / "pdfs").glob("*.pdf"))

failures: list[str] = []
checks = 0


def check(condition: bool, label: str, detail: str = "") -> None:
    global checks
    checks += 1
    if condition:
        print(f"  OK  {label}")
    else:
        failures.append(f"{label} {detail}".strip())
        print(f" FAIL {label} {detail}".strip())


def main() -> int:
    client = httpx.Client(timeout=120.0)
    pid = 0
    health = client.get(f"{BASE}/api/health").json()
    print("health:", health["status"], "docs:", health["documents"], "AI:", health["ai"])
    check(health["status"] == "ok", "API отвечает")
    check(health["tesseract"]["available"] and health["tesseract"]["russian"], "Tesseract + русский язык")
    about = health.get("about") or {}
    check(health.get("version") == "1.1.0", "Версия приложения 1.1.0", str(health.get("version")))
    check(about.get("author") == "VADIJI | AI Creative Studio", "Автор в /api/health", str(about))
    check(about.get("email") == "vadiji.ai@gmail.com", "Email автора в /api/health", str(about))
    check(about.get("license") == "MIT", "Лицензия MIT в /api/health", str(about))

    # E2E не должен отправлять документы в облако и не должен менять
    # настройки пользователя: на время теста включаем локальный режим,
    # исходные настройки восстанавливаем в конце.
    original_settings = client.get(f"{BASE}/api/settings").json()["settings"]
    client.put(f"{BASE}/api/settings", json={"ai_provider": "none"})
    print("AI на время теста: none (до теста:", original_settings.get("ai_provider"), ")")

    index = client.get(f"{BASE}/")
    check(index.status_code == 200 and '<div id="root">' in index.text, "SPA отдаётся сервером")

    project = client.post(f"{BASE}/api/projects", json={"name": "Демо: финансовые отчёты", "description": "Синтетические PDF для проверки"}).json()
    pid = project["id"]
    print("project:", pid)

    open_files = [("files", (p.name, p.read_bytes(), "application/pdf")) for p in PDFS]
    upload = client.post(f"{BASE}/api/projects/{pid}/documents", files=open_files)
    check(upload.status_code == 200, "Загрузка 14 PDF", upload.text[:200])
    check(len(upload.json().get("documents", [])) == len(PDFS), "Все файлы приняты")

    deadline = time.time() + 420
    docs: list[dict] = []
    while time.time() < deadline:
        docs = client.get(f"{BASE}/api/projects/{pid}/documents").json()
        pending = [d for d in docs if d["status"] in {"pending", "processing"}]
        ready = [d for d in docs if d["status"] == "ready"]
        errors = [d for d in docs if d["status"] == "error"]
        print(f"  обработка: готово {len(ready)}/{len(docs)}, ошибок {len(errors)}")
        if not pending:
            break
        time.sleep(2)
    check(all(d["status"] == "ready" for d in docs), "Все документы обработаны")
    check(any(d["ocr_pages"] for d in docs), "OCR выполнен для сканированного PDF")

    ready_docs = [d for d in docs if d["status"] == "ready"]
    doc_ids = [d["id"] for d in ready_docs]
    check(len(ready_docs) == len(PDFS), "Готовых документов 14", str(len(ready_docs)))

    scanned = next((d for d in ready_docs if "scanned" in d["original_name"]), None)
    if scanned:
        tables = client.get(f"{BASE}/api/documents/{scanned['id']}/tables").json()
        metrics = client.get(f"{BASE}/api/documents/{scanned['id']}/metrics?limit=1000").json()
        check(any(t["method"] == "tesseract-table" for t in tables), "Таблица восстановлена из OCR")
        check(metrics["total"] >= 10, "Показатели из скана извлечены", str(metrics["total"]))

    try:
        doc0 = next(d for d in ready_docs if d["original_name"] == "alpha_2022.pdf")
    except StopIteration:
        doc0 = ready_docs[0]
    pages = client.get(f"{BASE}/api/documents/{doc0['id']}/pages").json()
    metrics0 = client.get(f"{BASE}/api/documents/{doc0['id']}/metrics?limit=1000").json()
    tables0 = client.get(f"{BASE}/api/documents/{doc0['id']}/tables").json()
    check(len(pages) >= 1, "Страницы сохранены")
    check(metrics0["total"] >= 10, "Показатели сохранены", str(metrics0["total"]))
    check(bool(tables0), "Таблицы сохранены")
    check(all(m["page"] >= 1 for m in metrics0["items"]), "У каждого показателя есть страница")
    check(all(m["context"] for m in metrics0["items"][:5]), "У показателей есть контекст-источник")
    check(all(m["confidence"] > 0 for m in metrics0["items"][:5]), "У показателей есть уверенность")

    page_img = client.get(f"{BASE}/api/documents/{doc0['id']}/pages/1/image")
    check(page_img.status_code == 200 and page_img.content[:4] == b"\x89PNG", "Превью страницы PDF")
    pdf_file = client.get(f"{BASE}/api/documents/{doc0['id']}/file")
    check(pdf_file.status_code == 200 and pdf_file.content[:4] == b"%PDF", "Исходный PDF доступен по ссылке")

    dash = client.get(f"{BASE}/api/dashboard?project_id={pid}").json()
    check(dash["stats"]["documents"] == len(PDFS), "Панель: документы")
    check(dash["stats"]["metrics"] > 100, "Панель: показатели", str(dash["stats"]["metrics"]))
    check(dash["stats"]["pages"] >= len(PDFS), "Панель: страницы")

    options = client.get(f"{BASE}/api/options?project_id={pid}").json()
    check(any("ыручк" in item["label"] for item in options["labels"]), "Список показателей доступен")
    check(bool(options["periods"]), "Список периодов доступен", str(options["periods"][:5]))

    questions = [
        ("Какая выручка у ООО «Альфа» в 2024 году?", "search"),
        ("Сравни чистую прибыль Альфы и Беты за 2023 год", "compare"),
        ("Покажи динамику выручки по годам", "dynamics"),
        ("У какой компании максимальные активы?", "extrema"),
        ("Найди противоречия в документах", "contradictions"),
        ("Какие показатели отсутствуют за 2022 год?", "missing"),
        ("Покажи среднюю рентабельность", "average"),
        ("Найди в тексте упоминание дивидендов", "search"),
    ]
    intents = set()
    citation_ok = True
    for question, expected in questions:
        res = client.post(f"{BASE}/api/analyses", json={"project_id": pid, "query": question, "document_ids": doc_ids})
        check(res.status_code == 200, f"Вопрос: {question[:46]}", res.text[:180])
        if res.status_code != 200:
            continue
        body = res.json()
        intents.add(body.get("intent"))
        check(bool((body.get("answer") or "").strip()), f"  есть текстовый ответ ({body.get('intent')})")
        for c in body.get("citations") or []:
            if not c.get("document_id") or not c.get("page"):
                citation_ok = False
        if expected in {"compare", "dynamics", "extrema", "average"}:
            check(bool(body.get("tables")), f"  есть таблица результатов ({body.get('intent')})")
    check(citation_ok, "Все цитаты содержат документ и страницу")
    check("contradictions" in intents, "Распознан интент противоречий", str(intents))
    check("missing" in intents, "Распознан интент пропусков")
    check("dynamics" in intents, "Распознан интент динамики")

    res = client.post(f"{BASE}/api/analyses", json={"project_id": pid, "query": "Сравни выручку компаний за 2022–2025 годы", "document_ids": doc_ids})
    analysis = res.json()
    analysis_id = analysis.get("id")
    check(bool(analysis.get("charts")), "AI-аналитик вернул график")
    check(bool(analysis.get("tables")), "AI-аналитик вернул таблицу")

    res = client.post(f"{BASE}/api/compare", json={"project_id": pid, "document_ids": doc_ids[::-1][:4], "save": True})
    check(res.status_code == 200, "Сравнение документов", res.text[:200])
    compare = res.json() if res.status_code == 200 else {}
    rows = (compare.get("tables") or [{}])[0].get("rows") or []
    check(bool(rows), "Сравнительная таблица содержит строки", str(len(rows)))
    if rows:
        check(
            any(r.get("change_display") not in (None, "", "—") for r in rows),
            "Рассчитано изменение между значениями",
        )
        check(
            all(r.get("source", {}).get("document_id") for r in rows if r.get("source")),
            "В строках сравнения есть источник",
        )
    check(any(r.get("unit") for r in rows), "Единицы измерения сохранены")

    res = client.post(f"{BASE}/api/tables/build", json={"project_id": pid, "type": "summary", "document_ids": doc_ids})
    check(res.status_code == 200 and bool(res.json().get("tables")), "Пользовательская таблица")
    summary_rows = (res.json().get("tables") or [{}])[0].get("rows") or []
    check(bool(summary_rows), "Сводная таблица не пуста", str(len(summary_rows)))

    res = client.post(f"{BASE}/api/charts/build", json={"project_id": pid, "chart_type": "line", "metric_labels": ["Выручка"], "document_ids": doc_ids})
    check(res.status_code == 200 and bool(res.json().get("charts")), "График построен")
    chart = (res.json().get("charts") or [None])[0]
    if chart:
        check(bool(chart.get("plotly", {}).get("data")), "В графике есть данные")
        png = client.post(f"{BASE}/api/export/chart-png", json={"chart": chart})
        check(png.status_code == 200 and png.content[:4] == b"\x89PNG", "Экспорт графика PNG")

    for fmt in ("xlsx", "csv", "pdf"):
        out = client.post(f"{BASE}/api/export/{fmt}", json={"analysis_id": analysis_id})
        check(out.status_code == 200 and len(out.content) > 1000, f"Экспорт анализа {fmt.upper()}", str(len(out.content)))
        check("attachment" in (out.headers.get("content-disposition") or ""), f"  {fmt.upper()} скачивается файлом")

    # Сводный отчёт по проекту — тот же payload, что формирует страница «Отчёты»
    table_for_report = client.post(f"{BASE}/api/tables/build", json={"project_id": pid, "type": "summary", "document_ids": doc_ids}).json()
    payload = {
        "title": "Сводный отчёт по проекту",
        "query": "Сводный отчёт по всем документам проекта",
        "answer": compare.get("answer", ""),
        "tables": (compare.get("tables") or []) + (table_for_report.get("tables") or []),
        "charts": compare.get("charts") or [],
        "citations": compare.get("citations") or [],
        "documents": [{"id": d["id"], "name": d["original_name"]} for d in ready_docs],
        "findings": compare.get("findings") or [],
        "warnings": compare.get("warnings") or [],
    }
    for fmt in ("xlsx", "csv", "pdf"):
        out = client.post(f"{BASE}/api/export/{fmt}", json=payload)
        check(out.status_code == 200 and len(out.content) > 1000, f"Сводный отчёт {fmt.upper()}", str(len(out.content)))

    search = client.post(f"{BASE}/api/search", json={"project_id": pid, "query": "дивиденды", "limit": 5}).json()
    check(bool(search.get("hits")), "Полнотекстовый поиск", str(len(search.get("hits") or [])))

    settings = client.get(f"{BASE}/api/settings").json()
    check(settings["settings"]["ai_provider"] == "none", "Во время E2E включён локальный режим")
    check(settings["capabilities"]["documents"] >= len(PDFS), "Настройки видят документы")
    put = client.put(f"{BASE}/api/settings", json={"ai_provider": "none", "ocr_languages": "rus+eng", "ocr_dpi": 300})
    check(put.status_code == 200, "Настройки сохраняются")
    ocr = client.post(f"{BASE}/api/settings/ocr/check", json={}).json()
    check(ocr.get("available") is True, "Проверка Tesseract из настроек")

    restore_keys = (
        "ai_provider", "openai_base_url", "openai_model", "openai_embedding_model",
        "ollama_base_url", "ollama_model", "ollama_embedding_model",
        "semantic_search", "ocr_languages", "ocr_dpi",
    )
    restore = {k: original_settings[k] for k in restore_keys if original_settings.get(k) is not None}
    restored = client.put(f"{BASE}/api/settings", json=restore)
    check(
        restored.status_code == 200
        and restored.json()["settings"]["ai_provider"] == original_settings.get("ai_provider"),
        "Настройки AI восстановлены после E2E",
    )

    print(f"\nПроверок: {checks}, ошибок: {len(failures)}")
    if pid:
        cleanup = client.delete(f"{BASE}/api/projects/{pid}")
        check(cleanup.status_code == 200 and cleanup.json().get("ok") is True, "Удаление проекта через API")
        print("Тестовый проект удалён:", cleanup.status_code, "id", pid)
        # Каскадная очистка БД и FTS-индекса
        try:
            from app.database import SessionLocal
            from app.models import Analysis, Chunk, Document, Metric, Page, Project, Table
            from sqlalchemy import text

            db = SessionLocal()
            try:
                leftovers = {
                    "documents": db.query(Document).filter(Document.project_id == pid).count(),
                    "pages": db.query(Page).join(Document).filter(Document.project_id == pid).count(),
                    "tables": db.query(Table).join(Document).filter(Document.project_id == pid).count(),
                    "metrics": db.query(Metric).join(Document).filter(Document.project_id == pid).count(),
                    "chunks": db.query(Chunk).join(Document).filter(Document.project_id == pid).count(),
                    "analyses": db.query(Analysis).filter(Analysis.project_id == pid).count(),
                    "fts": db.execute(
                        text("SELECT count(*) FROM chunk_fts WHERE project_id = :p"), {"p": pid}
                    ).scalar()
                    or 0,
                }
                check(
                    all(v == 0 for v in leftovers.values()) and db.get(Project, pid) is None,
                    "Каскадная очистка проекта (БД + FTS)",
                    str(leftovers),
                )
            finally:
                db.close()
        except Exception as exc:  # noqa: BLE001
            check(False, "Каскадная очистка проекта (БД + FTS)", str(exc))
    if failures:
        print("ПРОБЛЕМЫ:")
        for f in failures:
            print(" -", f)
        return 1
    print("ВСЕ ПРОВЕРКИ ПРОЙДЕНЫ")
    print("PROJECT_ID", pid)
    return 0


if __name__ == "__main__":
    sys.exit(main())
