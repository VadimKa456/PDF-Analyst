"""Генератор тестовых PDF для проверки PDF Analyst.

Создаёт 15 документов: финансовые отчёты трёх компаний за 2022–2025,
аудиторское заключение с противоречием, англоязычный отчёт и сканированный PDF.
Данные синтетические и используются только для тестирования.
"""
from __future__ import annotations

import io
import random
from pathlib import Path

import pymupdf
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Image, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "pdfs"
FONT_DIR = Path(__file__).resolve().parents[1] / "frontend" / "node_modules"  # не используется

import matplotlib

FONT_REG = Path(matplotlib.get_data_path()) / "fonts" / "ttf" / "DejaVuSans.ttf"
FONT_BOLD = Path(matplotlib.get_data_path()) / "fonts" / "ttf" / "DejaVuSans-Bold.ttf"

pdfmetrics.registerFont(TTFont("DejaVu", str(FONT_REG)))
pdfmetrics.registerFont(TTFont("DejaVu-Bold", str(FONT_BOLD)))

random.seed(42)

COMPANIES = {
    "alpha": {
        "name": "ООО «Альфа»",
        "base_revenue": 1_250_000,
        "growth": 0.15,
        "margin": 0.125,
        "assets": 3_400_000,
        "employees": 1240,
    },
    "beta": {
        "name": "АО «Бета»",
        "base_revenue": 2_050_000,
        "growth": 0.08,
        "margin": 0.094,
        "assets": 5_200_000,
        "employees": 2180,
    },
    "gamma": {
        "name": "ООО «Гамма»",
        "base_revenue": 780_000,
        "growth": -0.03,
        "margin": 0.061,
        "assets": 1_950_000,
        "employees": 640,
    },
}
YEARS = [2022, 2023, 2024, 2025]


def money(value: float) -> str:
    return f"{int(round(value)):,}".replace(",", " ")


def fmt_pct(value: float) -> str:
    return f"{value:.1f}".replace(".", ",")


def build_pdf(
    path: Path,
    title: str,
    company: str,
    year: int,
    lang: str = "ru",
    audit: bool = False,
    dividend_change: bool = False,
) -> None:
    styles = getSampleStyleSheet()
    style_title = ParagraphStyle(
        "T", parent=styles["Title"], fontName="DejaVu-Bold", fontSize=18,
        leading=22, textColor=colors.HexColor("#1e293b"),
    )
    style_h = ParagraphStyle(
        "H", parent=styles["Heading2"], fontName="DejaVu-Bold", fontSize=12,
        leading=15, textColor=colors.HexColor("#4338ca"), spaceBefore=10,
    )
    style_body = ParagraphStyle(
        "B", parent=styles["BodyText"], fontName="DejaVu", fontSize=9.5, leading=14,
    )
    style_small = ParagraphStyle(
        "S", parent=styles["BodyText"], fontName="DejaVu", fontSize=8, leading=11,
        textColor=colors.HexColor("#64748b"),
    )
    meta = COMPANIES[company]
    growth = meta["growth"] + random.uniform(-0.01, 0.01)
    revenue = meta["base_revenue"] * ((1 + growth) ** (year - YEARS[0]))
    prev_revenue = revenue / (1 + growth)
    expenses = revenue * random.uniform(0.72, 0.82)
    profit = revenue * (meta["margin"] + random.uniform(-0.01, 0.01))
    assets = meta["assets"] * ((1 + growth) ** (year - YEARS[0]))
    capital = assets * 0.42
    employees = int(meta["employees"] * ((1 + growth / 2) ** (year - YEARS[0])))
    if audit:
        revenue = revenue * 1.04
        profit = profit * 0.96
    roe = profit / capital * 100
    current_ratio = 1.45 + random.uniform(-0.1, 0.1)

    story = []
    story.append(Paragraph(title, style_title))
    story.append(Paragraph(f"{meta['name']} · {year} · {('аудиторское заключение' if audit else 'годовой отчёт')}", style_small))
    story.append(Spacer(1, 0.3 * cm))
    story.append(Paragraph("1. Основные финансовые показатели", style_h))
    story.append(
        Paragraph(
            f"Настоящий отчёт подготовлен по итогам деятельности {meta['name']} за {year} год. "
            "Показатели приведены в соответствии с принятой учётной политикой. "
            "Суммовые значения выражены в тысячах рублей, если не указано иное.",
            style_body,
        )
    )
    data = [
        ["Показатель", f"{year} год, тыс. руб.", f"{year - 1} год, тыс. руб."],
        ["Выручка", money(revenue), money(prev_revenue)],
        ["Расходы", money(expenses), money(expenses / (1 + growth))],
        ["Чистая прибыль", money(profit), money(profit / (1 + growth))],
        ["Активы", money(assets), money(assets / (1 + growth))],
        ["Собственный капитал", money(capital), money(capital / (1 + growth))],
        ["Численность сотрудников, чел.", money(employees), money(employees - 30)],
    ]
    table = Table(data, colWidths=[6.5 * cm, 5 * cm, 5 * cm])
    table.setStyle(
        TableStyle(
            [
                ("FONTNAME", (0, 0), (-1, 0), "DejaVu-Bold"),
                ("FONTNAME", (0, 1), (-1, -1), "DejaVu"),
                ("FONTSIZE", (0, 0), (-1, -1), 8),
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#eef2ff")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#312e81")),
                ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#cbd5e1")),
                ("ALIGN", (1, 1), (-1, -1), "RIGHT"),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )
    story.append(table)
    story.append(Spacer(1, 0.25 * cm))

    story.append(Paragraph("2. Комментарии к показателям", style_h))
    story.append(
        Paragraph(
            f"Выручка за {year} год составила {money(revenue)} тыс. руб. "
            f"({money(revenue / 1000)} млн руб.), что на {fmt_pct(growth * 100)}% "
            f"{'больше' if growth >= 0 else 'меньше'} показателя предыдущего года.",
            style_body,
        )
    )
    story.append(
        Paragraph(
            f"Расходы за {year} год составили {money(expenses)} тыс. руб. "
            f"Чистая прибыль достигла {money(profit)} тыс. руб., "
            f"рентабельность по чистой прибыли — {fmt_pct(profit / revenue * 100)} %.",
            style_body,
        )
    )
    story.append(
        Paragraph(
            f"Совокупные активы на конец {year} года — {money(assets)} тыс. руб., "
            f"собственный капитал — {money(capital)} тыс. руб. "
            f"Рентабельность капитала (ROE) составила {fmt_pct(roe)} %. "
            f"Коэффициент текущей ликвидности — {fmt_pct(current_ratio)}.",
            style_body,
        )
    )
    story.append(
        Paragraph(
            f"Среднесписочная численность сотрудников — {employees} человек. "
            f"Производительность труда — {money(revenue / max(1, employees))} тыс. руб. на сотрудника.",
            style_body,
        )
    )
    story.append(Paragraph("3. Текстовые положения", style_h))
    story.append(
        Paragraph(
            "Компания придерживается консервативной финансовой политики и поддерживает "
            "достаточный уровень ликвидности. Существенных событий, способных повлиять "
            "на непрерывность деятельности, не выявлено.",
            style_body,
        )
    )
    if dividend_change:
        story.append(
            Paragraph(
                f"По итогам {year} года акционерам выплачены дивиденды в размере "
                f"{money(profit * 0.3)} тыс. руб.",
                style_body,
            )
        )
    else:
        story.append(
            Paragraph(
                f"Дивиденды по итогам {year} года не выплачивались; прибыль направлена "
                "на развитие производственной базы.",
                style_body,
            )
        )
    if audit:
        story.append(
            Paragraph(
                f"Аудиторское заключение: выручка за {year} год подтверждена в размере "
                f"{money(revenue)} тыс. руб. Проверка не выявила существенных искажений.",
                style_body,
            )
        )
    story.append(Spacer(1, 0.4 * cm))
    story.append(
        Paragraph(
            f"Источник: внутренняя финансовая отчётность {meta['name']}. "
            f"Документ сформирован для тестирования системы PDF Analyst.",
            style_small,
        )
    )

    def footer(canvas, doc):
        canvas.saveState()
        canvas.setFont("DejaVu", 7)
        canvas.setFillColor(colors.HexColor("#94a3b8"))
        canvas.drawString(2 * cm, 1.1 * cm, f"{meta['name']} · {year}")
        canvas.drawRightString(19 * cm, 1.1 * cm, f"Стр. {doc.page}")
        canvas.restoreState()

    doc = SimpleDocTemplate(
        str(path), pagesize=A4, leftMargin=2 * cm, rightMargin=2 * cm,
        topMargin=1.8 * cm, bottomMargin=1.8 * cm,
        title=title, author=meta["name"],
    )
    doc.build(story, onFirstPage=footer, onLaterPages=footer)


def build_english_pdf(path: Path) -> None:
    styles = getSampleStyleSheet()
    style_title = ParagraphStyle("T", parent=styles["Title"], fontName="DejaVu-Bold", fontSize=17, leading=21)
    style_body = ParagraphStyle("B", parent=styles["BodyText"], fontName="DejaVu", fontSize=10, leading=14)
    story = [
        Paragraph("Annual Financial Report 2025 — Beta Industries", style_title),
        Spacer(1, 0.3 * cm),
        Paragraph("All amounts are presented in thousand RUB unless stated otherwise.", style_body),
    ]
    data = [
        ["Indicator", "2025, thousand RUB", "2024, thousand RUB"],
        ["Revenue", "2 580 000", "2 390 000"],
        ["Operating expenses", "1 940 000", "1 810 000"],
        ["Net profit", "248 000", "221 000"],
        ["Total assets", "6 100 000", "5 650 000"],
    ]
    table = Table(data, colWidths=[6 * cm, 5 * cm, 5 * cm])
    table.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, 0), "DejaVu-Bold"),
        ("FONTNAME", (0, 1), (-1, -1), "DejaVu"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#cbd5e1")),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#eef2ff")),
        ("ALIGN", (1, 1), (-1, -1), "RIGHT"),
    ]))
    story += [
        table,
        Spacer(1, 0.3 * cm),
        Paragraph("Revenue for 2025 reached 2 580 000 thousand RUB (2 580 million RUB), up 7.9% year over year.", style_body),
        Paragraph("Net profit margin was 9.6%. The company remains financially stable.", style_body),
    ]
    doc = SimpleDocTemplate(str(path), pagesize=A4, leftMargin=2 * cm, rightMargin=2 * cm)
    doc.build(story)


def build_scanned_pdf(path: Path) -> None:
    """Создаёт PDF только с изображением страницы — проверка OCR."""
    from reportlab.lib.utils import ImageReader
    from reportlab.pdfgen import canvas

    # Reuse the already-generated alpha_2024 fixture so the scanned image
    # contains exactly the same deterministic ground-truth values as its
    # text-based counterpart. Rebuilding here would consume a different RNG
    # state and silently create a different financial statement.
    source = OUT / "alpha_2024.pdf"
    if not source.exists():
        raise FileNotFoundError(
            "alpha_2024.pdf must be generated before the scanned OCR fixture"
        )
    src = pymupdf.open(str(source))
    pix = src[0].get_pixmap(matrix=pymupdf.Matrix(2.2, 2.2), alpha=False)
    png = pix.tobytes("png")
    src.close()
    c = canvas.Canvas(str(path), pagesize=A4)
    c.drawImage(ImageReader(io.BytesIO(png)), 0, 0, width=A4[0], height=A4[1])
    c.showPage()
    c.save()


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for f in OUT.glob("*.pdf"):
        f.unlink()
    count = 0
    for company in COMPANIES:
        for year in YEARS:
            audit = company == "alpha" and year == 2023
            name = f"{company}_{year}{'_audit' if audit else ''}.pdf"
            label = (
                f"Аудиторское заключение по отчётности {COMPANIES[company]['name']} за {year} год"
                if audit
                else f"Финансовый отчёт {COMPANIES[company]['name']} за {year} год"
            )
            build_pdf(OUT / name, label, company, year, audit=audit, dividend_change=(year % 2 == 0))
            count += 1
    build_english_pdf(OUT / "beta_2025_english.pdf")
    count += 1
    build_scanned_pdf(OUT / "alpha_2024_scanned.pdf")
    count += 1
    print(f"Generated {count} PDF files in {OUT}")


if __name__ == "__main__":
    main()
