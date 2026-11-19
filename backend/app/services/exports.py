"""Экспорт результатов анализа в Excel, CSV и PDF."""
from __future__ import annotations

import csv
import io
import json
import logging
import re
from datetime import datetime
from typing import Any
from xml.sax.saxutils import escape

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

from ..utils import format_number

logger = logging.getLogger(__name__)

ACCENT = "4F46E5"
LIGHT = "EEF2FF"
BORDER = Side(style="thin", color="D9D9E3")


def _tables(payload: dict[str, Any]) -> list[dict[str, Any]]:
    tables = payload.get("tables") or []
    if payload.get("table"):
        tables = [payload["table"], *tables]
    return [t for t in tables if isinstance(t, dict)]


def _safe_sheet_name(name: str, used: set[str]) -> str:
    base = re.sub(r"[\[\]:*?/\\]", " ", name or "Таблица").strip() or "Таблица"
    base = base[:31]
    candidate = base
    i = 2
    while candidate in used:
        suffix = f" ({i})"
        candidate = base[: 31 - len(suffix)] + suffix
        i += 1
    used.add(candidate)
    return candidate


def _cell_value(row: dict[str, Any], col: dict[str, Any]) -> Any:
    key = col.get("key")
    v = row.get(key)
    if isinstance(v, (dict, list)):
        return json.dumps(v, ensure_ascii=False)[:32000]
    return v


def _cell_display(row: dict[str, Any], col: dict[str, Any]) -> Any:
    """Значение для CSV/PDF: числа — в русском формате с запятой."""
    value = _cell_value(row, col)
    key = str(col.get("key", ""))
    if isinstance(value, float) and (col.get("type") == "number" or key.endswith("_num")):
        return format_number(value)
    return value


def export_excel(payload: dict[str, Any]) -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = "Отчёт"
    title_font = Font(name="Calibri", size=16, bold=True, color=ACCENT)
    label_font = Font(name="Calibri", size=10, bold=True, color="64748B")
    ws["A1"] = payload.get("title") or "Аналитический отчёт"
    ws["A1"].font = title_font
    ws.merge_cells("A1:D1")
    meta_rows = [
        ("Дата формирования", payload.get("date") or datetime.now().strftime("%d.%m.%Y %H:%M")),
        ("Запрос", payload.get("query") or "—"),
        ("Тип анализа", payload.get("intent") or "—"),
        ("Документы", ", ".join(
            d.get("name", "") for d in (payload.get("documents") or []) if isinstance(d, dict)
        ) or "—"),
        ("Модель", (payload.get("meta") or {}).get("model", "Локальный аналитический движок")),
    ]
    r = 3
    for label, value in meta_rows:
        ws.cell(row=r, column=1, value=label).font = label_font
        c = ws.cell(row=r, column=2, value=value)
        c.alignment = Alignment(wrap_text=True, vertical="top")
        ws.merge_cells(start_row=r, start_column=2, end_row=r, end_column=8)
        r += 1
    r += 1
    ws.cell(row=r, column=1, value="Вывод").font = label_font
    r += 1
    answer = payload.get("answer") or payload.get("summary") or ""
    c = ws.cell(row=r, column=1, value=answer)
    c.alignment = Alignment(wrap_text=True, vertical="top")
    ws.merge_cells(start_row=r, start_column=1, end_row=r + 8, end_column=8)
    ws.row_dimensions[r].height = 140
    r += 11

    findings = payload.get("findings") or []
    if findings:
        ws.cell(row=r, column=1, value="Ключевые результаты").font = label_font
        r += 1
        for f in findings[:40]:
            text = f.get("text", "") if isinstance(f, dict) else str(f)
            c = ws.cell(row=r, column=1, value="• " + text)
            c.alignment = Alignment(wrap_text=True, vertical="top")
            ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=8)
            ws.row_dimensions[r].height = max(15, min(60, 15 * (len(text) // 100 + 1)))
            r += 1
        r += 1
    warnings = payload.get("warnings") or []
    if warnings:
        ws.cell(row=r, column=1, value="Предупреждения").font = label_font
        r += 1
        for w in warnings[:30]:
            c = ws.cell(row=r, column=1, value="• " + str(w))
            c.alignment = Alignment(wrap_text=True, vertical="top")
            ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=8)
            ws.row_dimensions[r].height = max(15, min(45, 15 * (len(str(w)) // 100 + 1)))
            r += 1
    ws.column_dimensions["A"].width = 26
    for col in "BCDEFGH":
        ws.column_dimensions[col].width = 16

    used_names = {"Отчёт"}
    for idx, table in enumerate(_tables(payload)):
        name = _safe_sheet_name(table.get("title") or f"Таблица {idx + 1}", used_names)
        sh = wb.create_sheet(name)
        sh["A1"] = table.get("title") or name
        sh["A1"].font = Font(bold=True, size=13, color=ACCENT)
        sh.merge_cells(start_row=1, start_column=1, end_row=1, end_column=max(1, len(table.get("columns", []))))
        columns = table.get("columns") or []
        rows = table.get("rows") or []
        header_fill = PatternFill("solid", fgColor=ACCENT)
        header_font = Font(color="FFFFFF", bold=True, size=10)
        for c_idx, col in enumerate(columns, start=1):
            cell = sh.cell(row=3, column=c_idx, value=col.get("label", col.get("key", "")))
            cell.fill = header_fill
            cell.font = header_font
            cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
            cell.border = Border(bottom=BORDER)
        for r_idx, row in enumerate(rows, start=4):
            for c_idx, col in enumerate(columns, start=1):
                value = _cell_value(row, col)
                cell = sh.cell(row=r_idx, column=c_idx, value=value)
                cell.alignment = Alignment(vertical="top", wrap_text=True)
                cell.border = Border(bottom=Side(style="hair", color="E2E8F0"))
                key = str(col.get("key", ""))
                if col.get("type") == "number" or key.endswith("_num") or key == "confidence":
                    if isinstance(value, (int, float)):
                        cell.number_format = "#,##0.00" if isinstance(value, float) else "#,##0"
                        cell.alignment = Alignment(horizontal="right", vertical="top")
                if key == "source_display" and value:
                    cell.font = Font(color="2563EB", size=9, underline="single")
        if columns:
            sh.freeze_panes = "A4"
            sh.auto_filter.ref = f"A3:{get_column_letter(len(columns))}{max(3, 3 + len(rows))}"
            for c_idx, col in enumerate(columns, start=1):
                label = str(col.get("label", ""))
                sample = " ".join(str(_cell_value(r, col) or "") for r in rows[:80])
                width = min(60, max(10, min(42, (len(sample) / max(1, min(len(rows), 80))) + len(label) * 0.6 + 2)))
                sh.column_dimensions[get_column_letter(c_idx)].width = width
            sh.row_dimensions[3].height = 32
        sh.sheet_view.showGridLines = False

    # источники
    sources = payload.get("citations") or []
    if sources:
        sh = wb.create_sheet("Источники")
        headers = ["Документ", "Стр.", "Фрагмент", "ID показателя", "Тип", "Уверенность"]
        for c_idx, h in enumerate(headers, start=1):
            cell = sh.cell(row=1, column=c_idx, value=h)
            cell.fill = PatternFill("solid", fgColor=ACCENT)
            cell.font = Font(color="FFFFFF", bold=True)
        for r_idx, s in enumerate(sources, start=2):
            if not isinstance(s, dict):
                continue
            values = [
                s.get("document", ""), s.get("page", ""), s.get("snippet", ""),
                s.get("metric_id", ""), s.get("source_kind", ""), s.get("confidence", ""),
            ]
            for c_idx, v in enumerate(values, start=1):
                cell = sh.cell(row=r_idx, column=c_idx, value=v)
                cell.alignment = Alignment(wrap_text=True, vertical="top")
        sh.column_dimensions["A"].width = 34
        sh.column_dimensions["B"].width = 8
        sh.column_dimensions["C"].width = 90
        sh.column_dimensions["D"].width = 14
        sh.freeze_panes = "A2"

    # данные графиков
    charts = payload.get("charts") or []
    if charts:
        sh = wb.create_sheet("Данные графиков")
        headers = ["График", "Тип", "Серия", "X", "Y", "Документ", "Страница", "Подпись"]
        for c_idx, h in enumerate(headers, start=1):
            cell = sh.cell(row=1, column=c_idx, value=h)
            cell.fill = PatternFill("solid", fgColor=ACCENT)
            cell.font = Font(color="FFFFFF", bold=True)
        row_idx = 2
        for chart in charts:
            plotly = chart.get("plotly") or {}
            for trace in plotly.get("data", []):
                xs = trace.get("x") or []
                ys = trace.get("y") or trace.get("values") or []
                custom = trace.get("customdata") or []
                name = trace.get("name") or ""
                if not isinstance(xs, list):
                    xs = [xs]
                if not isinstance(ys, list):
                    ys = [ys]
                for i, y in enumerate(ys):
                    x = xs[i] if i < len(xs) else ""
                    cust = custom[i] if i < len(custom) else []
                    doc = cust[2] if isinstance(cust, list) and len(cust) > 2 else ""
                    page = cust[1] if isinstance(cust, list) and len(cust) > 1 else ""
                    label = cust[3] if isinstance(cust, list) and len(cust) > 3 else ""
                    values = [chart.get("title", ""), chart.get("type", ""), name, x, y, doc, page, label]
                    for c_idx, v in enumerate(values, start=1):
                        sh.cell(row=row_idx, column=c_idx, value=v)
                    row_idx += 1
        for i, width in enumerate([36, 12, 24, 16, 16, 34, 10, 24], start=1):
            sh.column_dimensions[get_column_letter(i)].width = width
        sh.freeze_panes = "A2"

    bio = io.BytesIO()
    wb.save(bio)
    return bio.getvalue()


def export_csv(payload: dict[str, Any]) -> bytes:
    tables = _tables(payload)
    buf = io.StringIO()
    writer = csv.writer(buf, delimiter=";", quoting=csv.QUOTE_MINIMAL, lineterminator="\r\n")
    if tables:
        for idx, table in enumerate(tables):
            if idx > 0:
                writer.writerow([])
            writer.writerow([table.get("title") or f"Таблица {idx + 1}"])
            columns = table.get("columns") or []
            writer.writerow([c.get("label", c.get("key", "")) for c in columns])
            for row in table.get("rows") or []:
                writer.writerow([_cell_display(row, c) for c in columns])
    else:
        writer.writerow(["Аналитический отчёт"])
        writer.writerow(["Дата", payload.get("date") or datetime.now().strftime("%d.%m.%Y %H:%M")])
        writer.writerow(["Запрос", payload.get("query", "")])
        writer.writerow(["Вывод", payload.get("answer", "")])
        for f in payload.get("findings") or []:
            writer.writerow(["Результат", f.get("text", "") if isinstance(f, dict) else str(f)])
    data = buf.getvalue()
    return ("\ufeff" + data).encode("utf-8")


def _register_pdf_fonts() -> tuple[str, str]:
    from pathlib import Path

    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont

    try:
        import matplotlib

        font_dir = Path(matplotlib.get_data_path()) / "fonts" / "ttf"
        regular = font_dir / "DejaVuSans.ttf"
        bold = font_dir / "DejaVuSans-Bold.ttf"
        if regular.exists() and bold.exists():
            if "DejaVu" not in pdfmetrics.getRegisteredFontNames():
                pdfmetrics.registerFont(TTFont("DejaVu", str(regular)))
                pdfmetrics.registerFont(TTFont("DejaVu-Bold", str(bold)))
            return "DejaVu", "DejaVu-Bold"
    except Exception as exc:  # noqa: BLE001
        logger.warning("Could not register DejaVu fonts: %s", exc)
    return "Helvetica", "Helvetica-Bold"


def _chart_png(spec: dict[str, Any]) -> io.BytesIO | None:
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        plt.rcParams["font.family"] = "DejaVu Sans"
        plt.rcParams["axes.unicode_minus"] = False
        plotly = spec.get("plotly") or {}
        traces = plotly.get("data") or []
        if not traces:
            return None
        chart_type = spec.get("type", "bar")
        fig, ax = plt.subplots(figsize=(8.4, 4.0), dpi=150)
        if chart_type == "pie":
            tr = traces[0]
            labels = tr.get("labels") or []
            values = tr.get("values") or []
            if not values:
                plt.close(fig)
                return None
            ax.pie(values, labels=labels, autopct="%1.1f%%", textprops={"fontsize": 8})
            ax.set_title(spec.get("title", ""), fontsize=11)
        elif chart_type == "histogram":
            tr = traces[0]
            ax.hist(tr.get("x") or [], bins=12, color="#4f46e5", edgecolor="white")
            ax.set_title(spec.get("title", ""), fontsize=11)
            ax.grid(axis="y", alpha=0.25)
        elif chart_type == "heatmap":
            tr = traces[0]
            z = tr.get("z") or []
            if not z:
                plt.close(fig)
                return None
            im = ax.imshow(z, aspect="auto", cmap="viridis")
            ax.set_xticks(range(len(tr.get("x") or [])))
            ax.set_xticklabels(tr.get("x") or [], rotation=30, ha="right", fontsize=8)
            ax.set_yticks(range(len(tr.get("y") or [])))
            ax.set_yticklabels(tr.get("y") or [], fontsize=8)
            fig.colorbar(im, ax=ax, fraction=0.03, pad=0.02)
            ax.set_title(spec.get("title", ""), fontsize=11)
        else:
            category_x = all(not isinstance(x, (int, float)) for tr in traces for x in (tr.get("x") or []))
            all_x: list[Any] = []
            for tr in traces:
                for x in tr.get("x") or []:
                    if x not in all_x:
                        all_x.append(x)
            positions = {x: i for i, x in enumerate(all_x)}
            width = 0.8 / max(1, len(traces))
            for idx, tr in enumerate(traces):
                xs = tr.get("x") or []
                ys = tr.get("y") or []
                color = (tr.get("marker") or {}).get("color") or (tr.get("line") or {}).get("color") or "#4f46e5"
                name = tr.get("name") or f"Ряд {idx + 1}"
                if chart_type in {"bar", "stacked"}:
                    if category_x:
                        xpos = [positions[x] + (idx - (len(traces) - 1) / 2) * width for x in xs]
                        ax.bar(xpos, ys, width=width, label=name, color=color)
                    else:
                        ax.bar(xs, ys, label=name, color=color)
                else:
                    if category_x:
                        ax.plot([positions[x] for x in xs], ys, marker="o", label=name, color=color, linewidth=1.8, markersize=4)
                    else:
                        ax.plot(xs, ys, marker="o", label=name, color=color, linewidth=1.8, markersize=4)
            if category_x:
                ax.set_xticks(range(len(all_x)))
                rotation = 35 if len(all_x) > 5 else 0
                ax.set_xticklabels([str(x) for x in all_x], rotation=rotation, ha="right" if rotation else "center", fontsize=8)
            ax.grid(axis="y", alpha=0.25)
            ax.set_title(spec.get("title", ""), fontsize=11)
            if len(traces) > 1:
                ax.legend(fontsize=7, loc="best")
            if (spec.get("plotly", {}).get("layout", {}).get("yaxis", {}) or {}).get("type") == "log":
                ax.set_yscale("log")
        fig.tight_layout()
        bio = io.BytesIO()
        fig.savefig(bio, format="png", bbox_inches="tight")
        plt.close(fig)
        bio.seek(0)
        return bio
    except Exception as exc:  # noqa: BLE001
        logger.warning("Chart rendering for PDF failed: %s", exc)
        return None


def export_pdf(payload: dict[str, Any], page_size: str = "A4") -> bytes:
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_LEFT
    from reportlab.lib.pagesizes import A4, LETTER, landscape
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import cm
    from reportlab.platypus import (
        Image,
        KeepTogether,
        LongTable,
        PageBreak,
        Paragraph,
        SimpleDocTemplate,
        Spacer,
        Table,
        TableStyle,
    )

    regular, bold = _register_pdf_fonts()
    page = landscape(A4) if str(page_size).upper() == "A4-LANDSCAPE" else (
        LETTER if str(page_size).upper() == "LETTER" else A4
    )
    bio = io.BytesIO()

    def footer(canvas, doc):
        canvas.saveState()
        canvas.setFont(regular, 8)
        canvas.setFillColor(colors.HexColor("#64748B"))
        canvas.drawString(1.5 * cm, 1.0 * cm, "PDF Analyst — аналитический отчёт")
        canvas.drawRightString(page[0] - 1.5 * cm, 1.0 * cm, f"Стр. {doc.page}")
        canvas.restoreState()

    doc = SimpleDocTemplate(
        bio,
        pagesize=page,
        leftMargin=1.5 * cm,
        rightMargin=1.5 * cm,
        topMargin=1.5 * cm,
        bottomMargin=1.6 * cm,
        title=payload.get("title", "Аналитический отчёт"),
        author="PDF Analyst",
    )
    base = getSampleStyleSheet()
    styles = {
        "title": ParagraphStyle("T", parent=base["Title"], fontName=bold, fontSize=18, leading=22, textColor=colors.HexColor("#312E81"), alignment=TA_LEFT, spaceAfter=8),
        "h1": ParagraphStyle("H1", parent=base["Heading1"], fontName=bold, fontSize=13, leading=16, textColor=colors.HexColor("#4338CA"), spaceBefore=12, spaceAfter=6),
        "body": ParagraphStyle("B", parent=base["BodyText"], fontName=regular, fontSize=9.5, leading=13.5, textColor=colors.HexColor("#1E293B"), spaceAfter=4),
        "small": ParagraphStyle("S", parent=base["BodyText"], fontName=regular, fontSize=8, leading=10.5, textColor=colors.HexColor("#475569")),
        "cell": ParagraphStyle("C", parent=base["BodyText"], fontName=regular, fontSize=7, leading=9),
        "cellb": ParagraphStyle("CB", parent=base["BodyText"], fontName=bold, fontSize=7, leading=9),
        "muted": ParagraphStyle("M", parent=base["BodyText"], fontName=regular, fontSize=8.5, leading=12, textColor=colors.HexColor("#64748B")),
    }
    story: list[Any] = []
    story.append(Paragraph(escape(payload.get("title") or "Аналитический отчёт"), styles["title"]))
    date_str = payload.get("date") or datetime.now().strftime("%d.%m.%Y %H:%M")
    story.append(Paragraph(f"Дата формирования: {escape(str(date_str))}", styles["muted"]))
    query = payload.get("query")
    if query:
        story.append(Paragraph(f"<b>Запрос:</b> {escape(str(query))}", styles["body"]))
    docs = payload.get("documents") or []
    if docs:
        doc_names = ", ".join(str(d.get("name", "")) for d in docs if isinstance(d, dict))
        story.append(Paragraph(f"<b>Использованные документы ({len(docs)}):</b> {escape(doc_names)}", styles["body"]))
    meta = payload.get("meta") or {}
    params = []
    if meta.get("selected_labels"):
        params.append("Показатели: " + ", ".join(str(x) for x in meta["selected_labels"][:20]))
    if meta.get("years"):
        params.append("Период: " + ", ".join(str(x) for x in meta["years"]))
    if meta.get("model"):
        params.append("Движок: " + str(meta["model"]))
    if params:
        story.append(Paragraph("<b>Параметры анализа:</b> " + escape("; ".join(params)), styles["body"]))
    story.append(Spacer(1, 0.25 * cm))

    answer = payload.get("answer") or payload.get("summary") or ""
    if answer:
        story.append(Paragraph("Основные выводы", styles["h1"]))
        for para in str(answer).split("\n\n"):
            text = escape(para).replace("\n", "<br/>")
            if not text.strip():
                continue
            story.append(Paragraph(text, styles["body"]))
    findings = payload.get("findings") or []
    if findings:
        story.append(Paragraph("Ключевые результаты", styles["h1"]))
        for f in findings[:30]:
            text = f.get("text", "") if isinstance(f, dict) else str(f)
            if text:
                story.append(Paragraph("• " + escape(str(text)), styles["body"]))

    tables = _tables(payload)
    for table in tables:
        columns = table.get("columns") or []
        rows = table.get("rows") or []
        if not columns:
            continue
        story.append(Paragraph(escape(table.get("title") or "Таблица"), styles["h1"]))
        cell_rows = []
        header = [Paragraph(escape(str(c.get("label", ""))), styles["cellb"]) for c in columns]
        cell_rows.append(header)
        for row in rows[:80]:
            values = []
            for col in columns:
                v = _cell_display(row, col)
                values.append(Paragraph(escape("" if v is None else str(v))[:600], styles["cell"]))
            cell_rows.append(values)
        widths = [max(1.2 * cm, (page[0] - 3 * cm) * 0.92 / max(1, len(columns)))] * len(columns)
        t = LongTable(cell_rows, colWidths=widths, repeatRows=1)
        t.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#4F46E5")),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#CBD5E1")),
                    ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F8FAFC")]),
                    ("LEFTPADDING", (0, 0), (-1, -1), 3),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 3),
                    ("TOPPADDING", (0, 0), (-1, -1), 2.5),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 2.5),
                ]
            )
        )
        story.append(t)
        if len(rows) > 80:
            story.append(Paragraph(f"Показаны первые 80 строк из {len(rows)}. Полные данные — в Excel-экспорте.", styles["muted"]))
        story.append(Spacer(1, 0.25 * cm))

    charts = payload.get("charts") or []
    rendered_charts = 0
    for chart in charts[:8]:
        img = _chart_png(chart)
        if img is None:
            continue
        story.append(Paragraph(escape(chart.get("title", "График")), styles["h1"]))
        try:
            story.append(Image(img, width=page[0] - 3.2 * cm, height=(page[0] - 3.2 * cm) * 0.48))
        except Exception:  # noqa: BLE001
            pass
        story.append(Spacer(1, 0.2 * cm))
        rendered_charts += 1
    if charts and not rendered_charts:
        story.append(Paragraph("Графики не включены: не удалось отрисовать изображения. Данные графиков доступны в Excel.", styles["muted"]))

    warnings = payload.get("warnings") or []
    if warnings:
        story.append(Paragraph("Ограничения и предупреждения", styles["h1"]))
        for w in warnings[:25]:
            story.append(Paragraph("• " + escape(str(w)), styles["body"]))
    methods = payload.get("methods") or []
    if methods:
        story.append(Paragraph("Методы расчёта", styles["h1"]))
        for m in methods[:20]:
            story.append(Paragraph("• " + escape(str(m)), styles["body"]))
    sources = payload.get("citations") or []
    if sources:
        story.append(PageBreak())
        story.append(Paragraph("Источники", styles["h1"]))
        story.append(Paragraph(
            "Для каждого значения указан документ и страница. Проверьте исходный фрагмент в PDF.",
            styles["muted"],
        ))
        source_rows = [[
            Paragraph("Документ", styles["cellb"]),
            Paragraph("Стр.", styles["cellb"]),
            Paragraph("Фрагмент", styles["cellb"]),
            Paragraph("Тип", styles["cellb"]),
        ]]
        for s in sources[:200]:
            if not isinstance(s, dict):
                continue
            source_rows.append(
                [
                    Paragraph(escape(str(s.get("document", ""))), styles["cell"]),
                    Paragraph(str(s.get("page", "")), styles["cell"]),
                    Paragraph(escape(str(s.get("snippet", ""))[:500]), styles["cell"]),
                    Paragraph(escape(str(s.get("source_kind", ""))), styles["cell"]),
                ]
            )
        t = LongTable(source_rows, colWidths=[4.2 * cm, 1.2 * cm, (page[0] - 3 * cm) - 7.4 * cm, 2.0 * cm], repeatRows=1)
        t.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#4F46E5")),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#CBD5E1")),
                    ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F8FAFC")]),
                ]
            )
        )
        story.append(t)
    if not story:
        story.append(Paragraph("Нет данных для отчёта.", styles["body"]))

    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    return bio.getvalue()
