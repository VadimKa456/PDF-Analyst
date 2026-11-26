"""Извлечение текста, таблиц и числовых показателей из PDF.

Основной движок — PyMuPDF (текст, структура, таблицы). pdfplumber используется
как второй независимый экстрактор таблиц, Tesseract — для сканированных страниц.
Все показатели сохраняют страницу и фрагмент-источник.
"""
from __future__ import annotations

import logging
import math
import os
import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

import pymupdf
import pytesseract
from PIL import Image

from ..config import find_tesseract, get_settings
from ..utils import (
    canonical_label,
    clean_multiline,
    clean_text,
    detect_unit,
    extract_period,
    extract_years,
    guess_document_period,
    normalize_label,
    parse_number,
    parse_value,
    repair_numeric_text,
    short_snippet,
    value_with_unit,
)

logger = logging.getLogger(__name__)
settings = get_settings()

ProgressCallback = Callable[[int, str], None]

# Defensive processing ceilings for untrusted PDF files. The byte limit follows
# the upload setting; page, text and raster limits protect CPU/memory use.
MAX_PDF_PAGES = 500
MAX_PDF_FILE_BYTES = 1000 * 1024 * 1024
MAX_PAGE_TEXT_CHARS = 500_000
MAX_DOCUMENT_TEXT_CHARS = 5_000_000
MAX_PAGE_PIXELS = 12_000_000
MAX_TABLES_PER_PAGE = 100
MAX_TABLE_CELLS = 20_000
MIN_OCR_DPI = 150
MIN_PREVIEW_DPI = 36


class PDFResourceLimitError(ValueError):
    """A PDF exceeds a documented processing or rendering resource ceiling."""


METRIC_KEYWORDS = (
    "выручк", "доход", "расход", "прибыл", "убыт", "себестоим", "валов", "операцион",
    "чист", "актив", "пассив", "капитал", "долг", "кредит", "займ", "обязательств",
    "денежн", "поток", "рентабельн", "маржа", "ebitda", "ebit", "налог", "бюджет",
    "оборот", "продаж", "реализац", "затрат", "издержк", "инвестиц", "амортизац",
    "процент", "ставк", "инфляц", "объем", "количество", "численность", "сотрудник",
    "клиент", "заказ", "контракт", "стоимост", "цена", "тариф", "платеж", "сбор",
    "дебитор", "кредитор", "запас", "ликвидн", "платежеспособн", "финансов",
    "revenue", "income", "profit", "loss", "expense", "cost", "asset", "liabilit",
    "equity", "debt", "cash", "margin", "sales", "investment", "tax", "budget",
    "employee", "customer", "contract", "price", "rate", "volume", "amount", "total",
)

_UNIT_SUFFIX = (
    r"(?:%|₽|\$|€|руб\.?|рублей|долл\.?|usd|eur|тыс\.?|млн\.?|млрд\.?|"
    r"шт\.?|ед\.?|чел\.?|п\.?\s*п\.?|проц\.?|процент(?:ов|а)?|тонн?|кг|кв\.?\s*м|м2|м²)"
)
_NUM_TOKEN = (
    r"[-−–]?\s*\(?\s*\d{1,7}(?:[ \u00a0\u202f\u2009]\d{3})+(?:[.,]\d+)?\s*\)?"
    r"|[-−–]?\s*\(?\s*\d+(?:[.,]\d+)?\s*\)?"
)
_NUM_WITH_UNIT_RE = re.compile(
    rf"(?<![\w.,])(?P<num>{_NUM_TOKEN})(?P<unit>\s*{_UNIT_SUFFIX})?",
    re.IGNORECASE,
)
_DATE_LIKE_RE = re.compile(r"\b\d{1,2}[.\-/]\d{1,2}[.\-/](?:19|20)\d{2}\b")
_SENTENCE_BAD_START = (
    "составил", "составила", "составило", "составили", "равен", "равна", "равно",
    "было", "был", "была", "были", "будет", "достиг", "достигла", "достигло",
    "увеличил", "уменьшил", "вырос", "снизил", "превысил", "превышает",
)


@dataclass
class ExtractedTable:
    page_number: int
    title: str
    headers: list[str]
    rows: list[list[str]]
    method: str
    confidence: float


@dataclass
class ExtractedMetric:
    page_number: int
    label: str
    normalized_label: str
    raw_value: str
    value: float | None
    normalized_value: float | None
    unit: str
    dimension: str
    scale: float
    currency: str
    period: str
    raw_text: str
    context: str
    confidence: float
    source_kind: str
    source_ref: str
    row_index: int = -1
    col_index: int = -1
    table_id: int | None = None


@dataclass
class PageData:
    number: int
    text: str
    method: str
    confidence: float
    headings: list[str] = field(default_factory=list)
    width: float = 0
    height: float = 0
    has_tables: bool = False


@dataclass
class DocumentExtraction:
    pages: list[PageData]
    tables: list[ExtractedTable]
    metrics: list[ExtractedMetric]
    warnings: list[str]
    ocr_pages: int
    avg_confidence: float
    default_period: str
    text_chars: int
    processing_ms: int


_tesseract_ready: bool | None = None
_available_langs: set[str] = set()
_tesseract_path: str | None = None


def _ocr_config(overrides: dict[str, Any] | None = None) -> dict[str, Any]:
    cfg = {
        "enabled": settings.ocr_enabled,
        "languages": settings.ocr_languages,
        "dpi": settings.ocr_dpi,
        "min_confidence": settings.ocr_min_confidence,
        "auto": settings.ocr_auto,
        "tesseract_cmd": "",
        "max_file_bytes": MAX_PDF_FILE_BYTES,
    }
    if overrides:
        for key, value in overrides.items():
            if value is not None and key in cfg:
                cfg[key] = value
    return cfg


def configure_tesseract(cmd_override: str = "") -> tuple[bool, set[str]]:
    global _tesseract_ready, _available_langs, _tesseract_path
    cmd = (cmd_override or "").strip() or find_tesseract()
    if _tesseract_ready is not None and cmd == _tesseract_path:
        return _tesseract_ready, _available_langs
    if not cmd:
        _tesseract_ready = False
        _tesseract_path = None
        _available_langs = set()
        return False, set()
    pytesseract.pytesseract.tesseract_cmd = cmd
    tessdata = Path(cmd).parent / "tessdata"
    if tessdata.exists():
        os.environ.setdefault("TESSDATA_PREFIX", str(tessdata))
    try:
        langs = set(pytesseract.get_languages(config=""))
    except Exception:  # noqa: BLE001
        langs = set()
    _available_langs = langs
    _tesseract_ready = True
    _tesseract_path = cmd
    return True, langs


def tesseract_status(cmd_override: str = "") -> dict[str, Any]:
    ok, langs = configure_tesseract(cmd_override)
    cmd = (cmd_override or "").strip() or find_tesseract()
    return {
        "available": ok,
        "path": cmd or "",
        "languages": sorted(langs),
        "russian": "rus" in langs,
        "english": "eng" in langs,
    }


def _ocr_languages(cfg: dict[str, Any]) -> tuple[str, list[str]]:
    warnings: list[str] = []
    ok, langs = configure_tesseract(str(cfg.get("tesseract_cmd") or ""))
    requested = [x.strip() for x in str(cfg.get("languages") or "rus+eng").split("+") if x.strip()]
    if not cfg.get("enabled"):
        return "", []
    if not ok:
        return "", ["Tesseract OCR не найден. Сканированные страницы не будут распознаны. Установите Tesseract и укажите путь в настройках."]
    available = [x for x in requested if x in langs]
    if len(available) != len(requested):
        missing = set(requested) - set(available)
        warnings.append(
            "В Tesseract отсутствуют языковые пакеты: "
            + ", ".join(sorted(missing))
            + ". Доступные: "
            + ", ".join(sorted(langs))
        )
    if not available:
        return "", warnings
    return "+".join(available), warnings


def _extract_text_page(page: pymupdf.Page) -> tuple[str, list[str]]:
    """Извлекает текст, сохраняя порядок строк и помечая заголовки."""
    try:
        data = page.get_text("dict")
        items: list[tuple[float, float, str, float, bool]] = []
        for block in data.get("blocks", []):
            if block.get("type") != 0:
                continue
            for line in block.get("lines", []):
                spans = line.get("spans", [])
                if not spans:
                    continue
                text = "".join(s.get("text", "") for s in spans).strip()
                if not text:
                    continue
                x0, y0, _x1, _y1 = line.get("bbox", (0, 0, 0, 0))
                size = max(float(s.get("size", 10)) for s in spans)
                bold = any("bold" in str(s.get("font", "")).lower() for s in spans)
                items.append((round(y0, 1), round(x0, 1), text, size, bold))
        if not items:
            return clean_multiline(page.get_text("text")), []
        items.sort(key=lambda i: (i[0], i[1]))
        sizes = sorted(i[3] for i in items)
        median = sizes[len(sizes) // 2] if sizes else 10
        headings: list[str] = []
        lines: list[str] = []
        for _y, _x, text, size, bold in items:
            is_heading = (
                len(text) < 140
                and (
                    size >= median * 1.3
                    or (bold and size >= median * 1.08 and len(text) < 90)
                    or (text.isupper() and 6 <= len(text) < 100)
                )
            )
            if is_heading:
                if text not in headings:
                    headings.append(text)
                lines.append(f"\n## {text}\n")
            else:
                lines.append(text)
        return clean_multiline("\n".join(lines)), headings
    except Exception as exc:  # noqa: BLE001
        logger.debug("dict extraction failed: %s", exc)
        return clean_multiline(page.get_text("text")), []


def _needs_ocr(text: str, page: pymupdf.Page, cfg: dict[str, Any]) -> bool:
    stripped = re.sub(r"\s+", "", text or "")
    if len(stripped) >= 80:
        return False
    if not cfg.get("enabled") or not cfg.get("auto"):
        return False
    try:
        images = page.get_images(full=True)
    except Exception:  # noqa: BLE001
        images = []
    return bool(images) or len(stripped) < 15


def _preprocess_for_ocr(image: Image.Image, threshold: bool = True) -> Image.Image:
    """Готовит скан к OCR: масштаб, выравнивание, подавление шума, бинаризация.

    При ``threshold=False`` бинаризация не применяется: на некоторых сканах
    адаптивный порог «съедает» мелкие цифры в узких колонках таблиц.
    """
    try:
        import cv2
        import numpy as np

        arr = np.array(image.convert("RGB"))
        gray = cv2.cvtColor(arr, cv2.COLOR_RGB2GRAY)
        # Сканы часто приходят в 150–200 dpi. Для таблиц и мелкого шрифта
        # поднимаем ширину до ~2000 px — это заметно улучшает цифры.
        target = 2000
        if gray.shape[1] < target:
            scale = target / gray.shape[1]
            gray = cv2.resize(gray, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
        gray = _deskew_image(gray)
        gray = cv2.fastNlMeansDenoising(gray, h=10)
        if not threshold:
            return Image.fromarray(gray)
        adaptive = cv2.adaptiveThreshold(
            gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 31, 15
        )
        return Image.fromarray(adaptive)
    except Exception as exc:  # noqa: BLE001
        logger.debug("OCR preprocessing failed, using raw image: %s", exc)
        return image


def _deskew_image(gray: "Any") -> "Any":
    """Выравнивает перекошенный скан по контуру текста."""
    try:
        import cv2
        import numpy as np

        inv = cv2.bitwise_not(gray)
        coords = np.column_stack(np.where(inv > 0))
        if len(coords) < 100:
            return gray
        angle = cv2.minAreaRect(coords)[-1]
        if angle < -45:
            angle = 90 + angle
        if abs(angle) < 0.35 or abs(angle) > 12:
            return gray
        h, w = gray.shape
        matrix = cv2.getRotationMatrix2D((w / 2, h / 2), angle, 1.0)
        return cv2.warpAffine(
            gray, matrix, (w, h), flags=cv2.INTER_CUBIC,
            borderMode=cv2.BORDER_REPLICATE,
        )
    except Exception:  # noqa: BLE001
        return gray


def _preprocess_variants(image: Image.Image) -> dict[str, Image.Image]:
    """Две стратегии бинаризации: адаптивная и Otsu.

    Адаптивная лучше для основного прохода, Otsu — как запасной вариант при
    сомнительном качестве (неравномерный фон, тонкие линии таблиц).
    """
    base = _preprocess_for_ocr(image)
    # «Светлый» вариант без бинаризации: сохраняет мелкие цифры в узких колонках
    light = _preprocess_for_ocr(image, threshold=False)
    variants = {"adaptive": base, "light": light}
    try:
        import cv2
        import numpy as np

        gray = cv2.cvtColor(np.array(base.convert("RGB")), cv2.COLOR_RGB2GRAY)
        _thr, otsu = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        variants["otsu"] = Image.fromarray(otsu)
    except Exception:  # noqa: BLE001
        variants["otsu"] = base
    return variants


def _ocr_quality(text: str, mean_conf: float) -> float:
    """Оценка качества распознавания: уверенность минус числовые аномалии."""
    anomalies = 0
    anomalies += len(re.findall(r"\b\d{4,}\s\d{3}\b", text))
    anomalies += len(re.findall(r"\b\d{8,}\b", text))
    anomalies += len(re.findall(r"\d+[/\\](?=\s|$)", text))
    anomalies += len(re.findall(r"\b\d{1,3}\.\d{3,}\b", text))
    return mean_conf - anomalies * 1.5


_BORDER_NOISE_RE = re.compile(r"^[|_=~^<>\[\]{}()/\\•·\-–—]+$")


def _ocr_words(image: Image.Image, lang: str, psm: int) -> tuple[list[dict[str, Any]], float]:
    data = pytesseract.image_to_data(
        image,
        lang=lang,
        config=f"--oem 3 --psm {psm}",
        output_type=pytesseract.Output.DICT,
    )
    words: list[dict[str, Any]] = []
    confidences: list[float] = []
    texts = data.get("text", [])
    for i, conf in enumerate(data.get("conf", [])):
        try:
            c = float(conf)
        except (TypeError, ValueError):
            continue
        text = clean_text(texts[i] if i < len(texts) else "")
        if not text or c < 0:
            continue
        if c >= 0:
            confidences.append(c)
        # Рамки таблиц и мусорные символы не должны попадать в текст
        if _BORDER_NOISE_RE.fullmatch(text) and c < 85:
            continue
        if len(text) == 1 and not text.isdigit() and c < 55:
            continue
        try:
            words.append(
                {
                    "text": repair_numeric_text(text),
                    "conf": c,
                    "left": int(data["left"][i]),
                    "top": int(data["top"][i]),
                    "width": int(data["width"][i]),
                    "height": int(data["height"][i]),
                    "block": int(data.get("block_num", [0] * (i + 1))[i]),
                    "par": int(data.get("par_num", [0] * (i + 1))[i]),
                    "line": int(data.get("line_num", [0] * (i + 1))[i]),
                }
            )
        except (KeyError, IndexError):
            continue
    mean_conf = round(sum(confidences) / len(confidences), 1) if confidences else 0.0
    return words, mean_conf


def _words_to_text(words: list[dict[str, Any]]) -> str:
    """Собирает читаемый текст из слов OCR, сохраняя строки и порядок."""
    if not words:
        return ""

    groups: dict[tuple[int, int, int], list[dict[str, Any]]] = {}
    for w in words:
        key = (int(w.get("block", 0)), int(w.get("par", 0)), int(w.get("line", 0)))
        groups.setdefault(key, []).append(w)

    def render(items: list[dict[str, Any]]) -> str:
        ordered = sorted(items, key=lambda w: w["left"])
        parts: list[str] = []
        prev_end = None
        for w in ordered:
            if prev_end is not None:
                gap = w["left"] - prev_end
                if gap > max(24, w["height"] * 2.2):
                    parts.append(" | ")
                else:
                    parts.append(" ")
            parts.append(w["text"])
            prev_end = w["left"] + w["width"]
        return "".join(parts).strip()

    lines = [(key, render(items)) for key, items in groups.items()]
    lines.sort(key=lambda kv: (kv[0][0], kv[0][1], kv[0][2]))
    text = "\n".join(line for _key, line in lines if line)
    return clean_multiline(text)


def _ocr_score(text: str, confidence: float, reference_len: int = 0) -> float:
    """Оценка варианта OCR: качество минус аномалии плюс найденные числа.

    Мелкие числа в таблицах часто теряются при высокой уверенности OCR, поэтому
    вариант с большим количеством осмысленных чисел должен выигрывать даже при
    незначительно меньшей уверенности.
    """
    score = _ocr_quality(text, confidence)
    numbers = len(re.findall(r"\d+", text))
    score += min(numbers, 40) * 0.15
    if reference_len and len(text) < reference_len * 0.75:
        score -= 5.0
    return score


def _bounded_page_dpi(
    page: pymupdf.Page,
    requested_dpi: int,
    *,
    minimum_dpi: int,
    max_pixels: int = MAX_PAGE_PIXELS,
) -> int:
    """Return a safe raster DPI or reject pages that cannot be rendered safely."""
    rect = page.rect
    width_pt = abs(float(rect.width))
    height_pt = abs(float(rect.height))
    if (
        not math.isfinite(width_pt)
        or not math.isfinite(height_pt)
        or width_pt <= 0
        or height_pt <= 0
    ):
        raise PDFResourceLimitError("Некорректный размер страницы PDF.")
    requested = max(minimum_dpi, min(int(requested_dpi), 600))
    max_dpi = math.floor(math.sqrt(max_pixels * 72.0 * 72.0 / (width_pt * height_pt)))
    effective = min(requested, max_dpi)
    if effective < minimum_dpi:
        raise PDFResourceLimitError(
            "Страница PDF слишком большая для безопасной растеризации "
            f"(лимит {max_pixels:,} пикселей; минимальное разрешение {minimum_dpi} DPI)."
        )
    return effective


def _ocr_page(page: pymupdf.Page, lang: str, cfg: dict[str, Any]) -> tuple[str, float, list[dict[str, Any]]]:
    requested_dpi = max(MIN_OCR_DPI, min(int(cfg.get("dpi") or 300), 600))
    dpi = _bounded_page_dpi(page, requested_dpi, minimum_dpi=MIN_OCR_DPI)
    zoom = dpi / 72.0
    pix = page.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom), alpha=False)
    image = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
    variants = _preprocess_variants(image)

    best_words: list[dict[str, Any]] = []
    best_text = ""
    best_conf = 0.0
    best_score = -1e9

    # Основной проход + альтернативы. Выбираем не только по уверенности:
    # адаптивная бинаризация на мягких сканах может стереть цифры 1/0 в колонках.
    passes = (
        ("adaptive", 3),
        ("light", 3),
        ("adaptive", 6),
        ("light", 6),
        ("otsu", 6),
    )
    for name, psm in passes:
        variant = variants.get(name)
        if variant is None:
            continue
        try:
            words, conf = _ocr_words(variant, lang, psm)
        except Exception as exc:  # noqa: BLE001
            logger.debug("OCR pass %s/psm%s failed: %s", name, psm, exc)
            continue
        text = _words_to_text(words)
        if not text:
            continue
        if not best_text:
            best_words, best_text, best_conf = words, text, conf
            best_score = _ocr_score(text, conf)
            continue
        n_best = len(re.findall(r"\d+", best_text))
        n_alt = len(re.findall(r"\d+", text))
        # Важное улучшение: вариант нашёл существенно больше чисел, которых
        # почти нет в основном проходе (мелкие цифры в узких колонках).
        gained_numbers = n_alt > n_best and (
            n_alt >= n_best + 8 or (n_best >= 2 and n_alt >= n_best * 1.6)
        )
        score = _ocr_score(text, conf, len(best_text))
        if (gained_numbers and conf >= best_conf - 3) or score > best_score + 3:
            best_words, best_text, best_conf, best_score = words, text, conf, score

    if not best_text:
        # Полный отказ всех проходов — вернём хоть что-то с первого варианта
        best_words, best_conf = _ocr_words(variants["adaptive"], lang, 3)
        best_text = _words_to_text(best_words)
    return best_text, best_conf, best_words


def _ocr_headings(text: str) -> list[str]:
    headings = []
    for line in text.split("\n"):
        s = line.strip()
        if 4 <= len(s) <= 90 and (s.isupper() or re.match(r"^(?:раздел|глава|section)\s", s, re.I)):
            headings.append(s)
    return headings


def _ocr_tables_from_words(
    words: list[dict[str, Any]],
    page: pymupdf.Page,
    page_number: int,
    avg_confidence: float,
) -> list[ExtractedTable]:
    """Собирает таблицы со сканированной страницы по координатам слов OCR."""
    if not words:
        return []
    page_width = float(page.rect.width) or 1.0
    # ширина изображения = максимальная правая граница слов
    img_width = max((w["left"] + w["width"] for w in words), default=0) or page_width
    scale = page_width / img_width if img_width else 1.0

    rows: list[dict[str, Any]] = []
    for w in sorted(words, key=lambda w: (w["top"], w["left"])):
        cy = w["top"] + w["height"] / 2
        target = None
        for row in rows:
            if abs(row["cy"] - cy) <= max(row["height"], w["height"]) * 0.6:
                target = row
                break
        if target is None:
            rows.append({"cy": cy, "height": w["height"], "words": [w]})
        else:
            target["words"].append(w)
            target["cy"] = sum(x["top"] + x["height"] / 2 for x in target["words"]) / len(target["words"])
            target["height"] = max(target["height"], w["height"])
    rows.sort(key=lambda r: r["cy"])

    def row_cells(row: dict[str, Any]) -> list[dict[str, Any]]:
        items = sorted(row["words"], key=lambda w: w["left"])
        if not items:
            return []
        gaps = [
            (items[i]["left"] - (items[i - 1]["left"] + items[i - 1]["width"])) * scale
            for i in range(1, len(items))
        ]
        positive = sorted(g for g in gaps if g > 0) or [0]
        median = positive[len(positive) // 2]
        heights = sorted(w["height"] * scale for w in items if w["height"] > 0)
        med_height = heights[len(heights) // 2] if heights else 10.0
        # Медианный зазор в узких таблицах может быть межколоночным — тогда
        # тогда вся строка склеивается в одну ячейку. Ограничиваем порог высотой
        # слова: пробел внутри ячейки всегда меньше межколоночного зазора.
        threshold = max(7.0, min(median * 2.2, med_height * 1.6))
        groups: list[list[dict[str, Any]]] = [[items[0]]]
        for i in range(1, len(items)):
            gap = (items[i]["left"] - (items[i - 1]["left"] + items[i - 1]["width"])) * scale
            if gap > threshold:
                groups.append([items[i]])
            else:
                groups[-1].append(items[i])
        cells = []
        for group in groups:
            text = clean_text(" ".join(x["text"] for x in group))
            if not text:
                continue
            cells.append(
                {
                    "text": text,
                    "x0": min(x["left"] for x in group) * scale,
                    "x1": max(x["left"] + x["width"] for x in group) * scale,
                    "cx": sum((x["left"] + x["width"] / 2) for x in group) / len(group) * scale,
                }
            )
        return cells

    parsed_rows = [(row, row_cells(row)) for row in rows]
    result: list[ExtractedTable] = []
    for idx, (row, cells) in enumerate(parsed_rows):
        texts = [c["text"] for c in cells]
        if len(texts) < 3:
            continue
        header_text = " ".join(texts).lower()
        if not re.search(r"(?:показател|indicator)", header_text):
            continue
        header_cells = [
            c for c in cells if c["text"] and re.search(r"[A-Za-zА-Яа-я0-9]", c["text"])
        ]
        # Год может быть в заголовке документа, а не в шапке таблицы
        # (например, «БЛАНК ОЦЕНКИ … за июнь 2025 года»). Наличие года в
        # самой строке заголовка не является обязательным признаком таблицы.
        if len(header_cells) < 2:
            continue

        def word_cx(word: dict[str, Any]) -> float:
            return (word["left"] + word["width"] / 2) * scale

        # Строки-кандидаты: включаем все строки таблицы, даже без чисел —
        # в многострочных ячейках подпись и критерии занимают несколько строк,
        # а числа стоят только на части из них. _table_metrics сам склеивает
        # отложенные подписи со строкой, где есть значение.
        candidates: list[dict[str, Any]] = []
        for next_row, data_cells in parsed_rows[idx + 1:]:
            joined = " ".join(c["text"] for c in data_cells)
            if not joined.strip():
                continue
            # Конец таблицы: подписи/реквизиты после неё
            if re.search(r"(?:начальник|ознакомлен|подпись|должность|ФИО)", joined, re.I):
                break
            if re.match(r"^\s*\d+(?:\.\d+)*[.)]?\s+[А-ЯA-Z]", joined) and not re.search(r"\d{3,}", joined):
                break
            candidates.append(next_row)
            if re.search(r"(?:итого|всего|total)", joined, re.I):
                break
            if len(candidates) >= 60:
                break
        if len(candidates) < 2:
            continue

        # границы колонок по кластерам числовых слов (значения выровнены вправо)
        numeric_cx = sorted(
            word_cx(w)
            for row_dict in candidates
            for w in row_dict["words"]
            if re.fullmatch(r"[−–-]?[\d.,]+", w["text"]) and any(ch.isdigit() for ch in w["text"])
        )
        clusters: list[list[float]] = []
        for value in numeric_cx:
            if clusters and value - clusters[-1][-1] <= 30:
                clusters[-1].append(value)
            else:
                clusters.append([value])
        centers = [sum(c) / len(c) for c in clusters]
        expected_values = len(header_cells) - 1
        if len(centers) == expected_values:
            label_center = header_cells[0]["cx"]
            boundaries = [(label_center + centers[0]) / 2]
            boundaries += [(centers[i] + centers[i + 1]) / 2 for i in range(len(centers) - 1)]
        else:
            header_centers = [c["cx"] for c in header_cells]
            boundaries = [(header_centers[i] + header_centers[i + 1]) / 2 for i in range(len(header_centers) - 1)]
        column_count = len(boundaries) + 1

        def assign(row_dict: dict[str, Any]) -> list[str]:
            columns: list[list[str]] = [[] for _ in range(column_count)]
            for word in sorted(row_dict["words"], key=lambda w: w["left"]):
                cx = word_cx(word)
                target = 0
                for boundary in boundaries:
                    if cx >= boundary:
                        target += 1
                columns[target].append(word["text"])
            return [clean_text(" ".join(parts)) for parts in columns]

        body = [assign(row_dict) for row_dict in candidates]
        headers = [c["text"] for c in header_cells]
        width = max(len(r) for r in body)
        body = [r + [""] * (width - len(r)) for r in body]
        if len(headers) < width:
            headers = headers + [""] * (width - len(headers))
        headers = headers[:width]
        result.append(
            ExtractedTable(
                page_number=page_number,
                title="Таблица, распознанная OCR",
                headers=headers,
                rows=body,
                method="tesseract-table",
                confidence=round(max(0.4, min(0.9, avg_confidence / 100.0 - 0.05)), 2),
            )
        )
        break
    return result


def _normalize_table_rows(rows: list[list[Any]]) -> list[list[str]]:
    cleaned: list[list[str]] = []
    for row in rows:
        cells = [clean_text(c).replace("\n", " ") for c in (row or [])]
        cleaned.append(cells)
    # убираем полностью пустые строки/столбцы
    cleaned = [r for r in cleaned if any(c for c in r)]
    if not cleaned:
        return []
    width = max(len(r) for r in cleaned)
    cleaned = [r + [""] * (width - len(r)) for r in cleaned]
    keep_cols = [i for i in range(width) if any(r[i] for r in cleaned)]
    return [[r[i] for i in keep_cols] for r in cleaned]


def _cell_text_from_words(words: list[tuple], rect: tuple[float, float, float, float]) -> str:
    """Собирает текст ячейки из слов страницы, сохраняя пробелы.

    Встроенный ``table.extract()`` в PyMuPDF в части версий склеивает слова
    («Чистаяприбыль») и теряет разделители тысяч. Пересборка по словам
    внутри bbox ячейки даёт исходный текст с пробелами.
    """
    x0, y0, x1, y1 = rect
    inside = [
        w for w in words
        if x0 - 1 <= (w[0] + w[2]) / 2 <= x1 + 1 and y0 - 1 <= (w[1] + w[3]) / 2 <= y1 + 1
    ]
    if not inside:
        return ""
    lines: dict[int, list[tuple]] = {}
    for w in inside:
        key = round(float(w[1]) / 3.0)
        lines.setdefault(key, []).append(w)
    return "\n".join(
        " ".join(str(w[4]) for w in sorted(lines[key], key=lambda w: w[0]))
        for key in sorted(lines)
    )


def _table_matrix_from_words(page: pymupdf.Page, table: Any) -> list[list[str]]:
    """Пересобирает матрицу таблицы по bbox ячеек и словам страницы.

    ``table.extract()`` в PyMuPDF в части версий склеивает слова
    («Оплатапоокладу») и теряет десятичные разделители: корректное
    ``11 532,33`` превращается в ``1153233\\n,``. Поэтому форму таблицы берём
    из ``extract()``, а текст каждой непустой ячейки — из слов страницы,
    попавших в её bbox.

    ``table.cells`` содержит только непустые ячейки (``None`` пропущены), а
    порядок зависит от версии PyMuPDF (построчный или постолбцовый). Поэтому
    перебираем оба порядка, проверяем, что число ячеек совпало, и выбираем
    вариант с наибольшим совпадением с ``extract()``.
    """
    cells = list(getattr(table, "cells", None) or [])
    row_count = int(getattr(table, "row_count", 0) or 0)
    col_count = int(getattr(table, "col_count", 0) or 0)
    if not cells or row_count <= 0 or col_count <= 0:
        return []
    try:
        expected = table.extract() or []
    except Exception:  # noqa: BLE001
        return []
    if not expected:
        return []
    width = max(len(r) for r in expected)
    grid = [
        [("" if c is None else str(c)) for c in row] + [""] * (width - len(row))
        for row in expected
    ]
    try:
        words = page.get_text("words")
    except Exception:  # noqa: BLE001
        return []
    texts = [_cell_text_from_words(words, rect) if rect else "" for rect in cells]

    def slots(order: str) -> list[tuple[int, int]]:
        result: list[tuple[int, int]] = []
        if order == "col":
            for c in range(width):
                for r in range(len(grid)):
                    if expected[r][c] is not None:
                        result.append((r, c))
        else:
            for r in range(len(grid)):
                for c in range(len(expected[r])):
                    if expected[r][c] is not None:
                        result.append((r, c))
        return result

    def agreement(order_cells: list[tuple[int, int]]) -> float:
        hits = total = 0
        for (r, c), text in zip(order_cells, texts):
            normalized = re.sub(r"\s+", "", text).lower()
            reference = re.sub(r"\s+", "", grid[r][c]).lower()
            if not normalized and not reference:
                continue
            total += 1
            if normalized == reference:
                hits += 1
        return hits / total if total else -1.0

    best_slots: list[tuple[int, int]] | None = None
    best_score = -1.0
    for order in ("row", "col"):
        candidate = slots(order)
        if len(candidate) != len(cells):
            continue
        candidate_score = agreement(candidate)
        if candidate_score > best_score:
            best_slots, best_score = candidate, candidate_score
    if best_slots is None:
        return []

    matrix = [row[:] for row in grid]
    for (r, c), text in zip(best_slots, texts):
        rebuilt = clean_text(text)
        if rebuilt:
            matrix[r][c] = rebuilt
    return matrix


def _table_signature(headers: list[str], rows: list[list[str]]) -> str:
    sample = "|".join(headers[:8]) + "::" + "|".join(
        "~".join(r[:6]) for r in rows[:4]
    )
    return re.sub(r"\s+", " ", sample).lower()


def _find_table_caption(text: str, page_number: int) -> str:
    for line in (text or "").split("\n"):
        s = clean_text(line).lstrip("#").strip()
        if 5 <= len(s) <= 180 and re.search(
            r"(?:\bтабл|\btable\b|показател|динамик|структур)", s, re.I
        ):
            return s
    return ""


def _extract_table_header(rows: list[list[str]]) -> tuple[list[str], list[list[str]]]:
    """Отделяет строку заголовка таблицы от шапки страницы и подзаголовков.

    PyMuPDF часто включает в таблицу верхний блок страницы («Организация…»,
    «К выплате…»). Если считать его заголовком, все значения привязываются к
    первой колонке и получаются ложные показатели. Поэтому ищем первую строку,
    похожую на заголовок, и приклеиваем к ней строки-подзаголовки
    («Рабочие» + «Дни | Часы»).
    """
    if len(rows) < 2:
        return [], []

    def numeric_cells(row: list[str]) -> int:
        return sum(
            1 for c in row if c and re.fullmatch(r"[-−(]?[\d\s.,]+[)]?\s*%?", c.strip())
        )

    def header_score(row: list[str]) -> int:
        cells = [c for c in row if c]
        if len(cells) < 2 or numeric_cells(row) > max(0, len(cells) * 0.3):
            return 0
        score = sum(1 for c in cells if _HEADER_HINT_RE.search(c))
        if any(_LABEL_HEADER_RE.search(c) for c in cells):
            score += 2
        if any(_header_is_period(c) for c in cells):
            score += 1
        if any(_header_is_value(c) for c in cells):
            score += 1
        return score

    header_idx = 0
    for idx, row in enumerate(rows[:-1]):
        if header_score(row) >= 2:
            header_idx = idx
            break

    headers = [c for c in rows[header_idx]]
    body_start = header_idx + 1
    # Подзаголовки: короткие текстовые строки без чисел сразу под заголовком.
    for extra in range(2):
        if body_start >= len(rows):
            break
        row = rows[body_start]
        cells = [c for c in row if c]
        if not cells or numeric_cells(row) or len(cells) > len(headers):
            break
        if not all(len(c) <= 40 and not re.search(r"\d", c) for c in cells):
            break
        if not any(
            c and (not headers[i] or _HEADER_HINT_RE.search(c))
            for i, c in enumerate(row[: len(headers)])
        ):
            break
        for i, c in enumerate(row[: len(headers)]):
            if not c:
                continue
            headers[i] = clean_text(f"{headers[i]} {c}") if headers[i] else c
        body_start += 1
    return headers, rows[body_start:]


def _extract_tables_pymupdf(
    page: pymupdf.Page, page_text: str
) -> list[ExtractedTable]:
    result: list[ExtractedTable] = []
    try:
        finder = page.find_tables()
        tables = finder.tables
    except Exception as exc:  # noqa: BLE001
        logger.debug("find_tables failed: %s", exc)
        return result
    for table in tables:
        try:
            rows = _normalize_table_rows(table.extract() or [])
        except Exception as exc:  # noqa: BLE001
            logger.debug("table.extract failed: %s", exc)
            continue
        # PyMuPDF может склеивать слова в ячейках — пересобираем текст по словам
        try:
            word_rows = _normalize_table_rows(_table_matrix_from_words(page, table))
        except Exception as exc:  # noqa: BLE001
            logger.debug("word-based table rebuild failed: %s", exc)
            word_rows = []
        if word_rows and len(word_rows) == len(rows) and all(
            len(a) == len(b) for a, b in zip(word_rows, rows)
        ):
            rows = word_rows
        if len(rows) < 2:
            continue
        headers, body = _extract_table_header(rows)
        if not headers or not body or len(headers) < 2:
            continue
        filled = sum(1 for r in body for c in r if c)
        total = max(1, len(body) * max(1, len(headers)))
        density = filled / total
        if density < 0.2:
            continue
        result.append(
            ExtractedTable(
                page_number=page.number + 1,
                title=_find_table_caption(page_text, page.number + 1),
                headers=headers,
                rows=body,
                method="pymupdf",
                confidence=round(min(0.95, 0.7 + density * 0.25), 2),
            )
        )
    return result


def _extract_tables_pdfplumber(plumber_page: Any, page_text: str) -> list[ExtractedTable]:
    result: list[ExtractedTable] = []
    try:
        raw_tables = plumber_page.extract_tables()
    except Exception as exc:  # noqa: BLE001
        logger.debug("pdfplumber extract_tables failed: %s", exc)
        return result
    for raw in raw_tables or []:
        rows = _normalize_table_rows(raw)
        if len(rows) < 2 or len(rows[0]) < 2:
            continue
        headers, body = _extract_table_header(rows)
        if not headers or not body or len(headers) < 2:
            continue
        filled = sum(1 for r in body for c in r if c)
        total = max(1, len(body) * max(1, len(headers)))
        density = filled / total
        if density < 0.2:
            continue
        result.append(
            ExtractedTable(
                page_number=plumber_page.page_number,
                title=_find_table_caption(page_text, plumber_page.page_number),
                headers=headers,
                rows=body,
                method="pdfplumber",
                confidence=round(min(0.93, 0.65 + density * 0.25), 2),
            )
        )
    return result


def _maybe_transpose(headers: list[str], rows: list[list[str]]) -> tuple[list[str], list[list[str]]]:
    """Определяет таблицы, где годы расположены в первом столбце."""
    if not headers or not rows:
        return headers, rows
    first_col = [r[0] if r else "" for r in rows]
    year_rows = sum(1 for c in first_col if re.fullmatch(r"(?:19|20)\d{2}(?:\s*г\.?)?", c.strip()))
    text_headers = sum(1 for c in headers if re.search(r"[A-Za-zА-Яа-я]{3,}", c))
    if year_rows >= 2 and text_headers >= 2 and year_rows >= len(rows) * 0.5:
        matrix = [headers] + rows
        width = max(len(r) for r in matrix)
        matrix = [r + [""] * (width - len(r)) for r in matrix]
        transposed = [[r[c] for r in matrix] for c in range(width)]
        return transposed[0], transposed[1:]
    return headers, rows


def _clean_metric_label(label: str) -> str:
    s = clean_text(label)
    s = re.sub(r"\s+([.,;:!?])", r"\1", s)
    s = re.sub(r"^\s*(?:\d+(?:\.\d+)*[.)]?|[IVXLC]+[.)])\s*", "", s)
    s = re.sub(r"^[\s\-–—•·*]+", "", s)
    # OCR склеивает колонку «Пояснения» с названием: «6:П-15 Себестоимость».
    s = re.sub(
        r"^[\s:;.,]*\d{1,2}(?:\s*[-–]\s*\d{1,2})?\s*[:;.]?\s*"
        r"(?:[ПNп]\s*[-–]?\s*\d{1,2}(?:\s*[-–]\s*\d{1,2})?\s*)?"
        r"(?=[А-ЯЁA-Z«\"])",
        "", s,
    )
    s = re.sub(
        r"^[\s:;.,]*[ПNп]\s*[-–]?\s*\d{1,2}(?:\s*[-–]\s*\d{1,2})?\s+(?=[А-ЯЁA-Z«\"])",
        "", s,
    )
    s = re.sub(
        r"\s+(?:за|в|во|на|по|for|in|during|of)\s+(?:the\s+)?(?:fiscal\s+)?(?:year\s+)?"
        r"(?:период\s+)?(?:19|20)\d{2}\s*(?:г(?:од|ода|оду)?\.?|year)?.*$",
        "",
        s,
        flags=re.I,
    )
    s = re.sub(
        r"\s+(?:составил[аио]?|равен|равна|равно|был[аио]?|были|будет|"
        r"достиг(?:ла|ло|ли)?|увеличил(?:ась|ся|ось|ись)?|уменьшил(?:ась|ся|ось|ись)?|"
        r"вырос(?:ла|ло|ли)?|снизил(?:ась|ся|ось|ись)?|превысил[аи]?|превышает|"
        r"was|were|is|are|reached|totaled|amounted\s+to|equaled|stood\s+at|"
        r"grew|increased|decreased|rose|fell|declined|improved|"
        r"в\s+размере|в\s+сумме|на\s+уровне)\s*$",
        "",
        s,
        flags=re.I,
    )
    s = re.sub(
        r"\s+на\s+(?:конец|начало)(?:\s+(?:19|20)\d{2}\s*(?:г(?:ода|од)?\.?)?)?\s*$",
        "", s, flags=re.I,
    )
    s = re.sub(r"(?<!\d)(?:19|20)\d{2}\s*(?:г(?:ода|оду|од|\.)?)?(?!\d)", "", s)
    s = re.sub(r"\s*[:=–—-]+\s*$", "", s)
    s = re.sub(r"\s+", " ", s).strip(" .,:;")
    return s[:160]


_TRAILING_LINK_RE = re.compile(
    r"\s+(?:составил[аио]?|равен|равна|равно|был[аио]?|были|будет|"
    r"достиг(?:ла|ло|ли)?|увеличил(?:ась|ся|ось|ись)?|уменьшил(?:ась|ся|ось|ись)?|"
    r"вырос(?:ла|ло|ли)?|снизил(?:ась|ся|ось|ись)?|превысил[аи]?|превышает|"
    r"was|were|is|are|reached|totaled|amounted\s+to|equaled|stood\s+at|"
    r"grew|increased|decreased|rose|fell|declined|improved|"
    r"в\s+размере|в\s+сумме|на\s+уровне)\s*$",
    re.IGNORECASE,
)
_TRAILING_STOP_RE = re.compile(
    r"\s+(?:в|во|на|по|за|из|от|до|для|с|со|к|ко|о|об|при|что|чем|и|а|но|или|"
    r"for|in|during|of|to|at|by|with|and|or|the|a|an|"
    r"составил[аио]?|составили)\s*$",
    re.IGNORECASE,
)


def _label_from_prefix(prefix: str) -> str:
    """Выделяет подпись показателя из текста перед числом.

    Берётся последняя смысловая клауза: «... 903 126 тыс. руб., чистая
    прибыль достигла 150 626» → «чистая прибыль».
    """
    s = clean_text(prefix)
    if not s:
        return ""
    s = s.rstrip("([«\"' ")
    if not s:
        return ""
    parts = [p for p in re.split(r"(?:[.;!?•·|]+|,\s+)\s*", s) if p and p.strip()]
    clause = parts[-1] if parts else s
    clause = clause.strip(" -–—:=«»\"'")
    # убираем хвостовые связки/глаголы
    for _ in range(2):
        clause = _TRAILING_LINK_RE.sub("", clause)
        clause = _TRAILING_STOP_RE.sub("", clause).strip(" -–—:=«»\"'")
    # убираем указание периода/даты
    clause = re.sub(
        r"\s+(?:за|по\s+итогам|в|for|in|during|of)\s+(?:the\s+)?(?:fiscal\s+)?(?:year\s+)?"
        r"(?:период\s+)?(?:19|20)\d{2}\s*(?:г(?:од|ода|оду)?\.?|year)?.*$",
        "", clause, flags=re.I,
    )
    clause = re.sub(
        r"\s+на\s+(?:конец|начало)(?:\s+(?:19|20)\d{2}\s*(?:г(?:ода|од)?\.?)?)?\s*$",
        "", clause, flags=re.I,
    )
    clause = clause.strip(" -–—:=«»\"'")
    words = clause.split()
    if len(words) > 8:
        clause = " ".join(words[-8:])
    return _clean_metric_label(clause)


def _is_meaningful_label(label: str) -> bool:
    from ..utils import tokenize

    if not _looks_like_metric_label(label):
        return False
    tokens = tokenize(label)
    if not tokens:
        return False
    if not _has_metric_keyword(label) and len(tokens) < 2:
        return False
    return True


def _looks_like_metric_label(label: str) -> bool:
    if not label or len(label) < 3:
        return False
    letters = re.findall(r"[A-Za-zА-Яа-яЁё]", label)
    if len(letters) < 3:
        return False
    low = label.lower()
    if re.fullmatch(r"(?:стр\.?|страница|page|рис\.?|таблица)\s*\d*", low):
        return False
    if _DATE_LIKE_RE.fullmatch(label.strip()):
        return False
    return True


def _has_metric_keyword(label: str) -> bool:
    low = label.lower()
    return any(k in low for k in METRIC_KEYWORDS)


def _is_year_value(value: float, raw: str, unit: str) -> bool:
    if unit:
        return False
    if 1900 <= value <= 2100 and re.fullmatch(r"\d{4}", raw.strip()):
        return True
    return False


_CODE_HEADER_RE = re.compile(r"(?:код|строк|№|п\s*/\s*п|line\s*(?:no|number)?|code|row\s*(?:no|number)?)", re.I)
_PERIOD_HEADER_RE = re.compile(r"(?:период|дата|месяц|квартал|period|date|month|quarter)", re.I)
_NON_VALUE_HEADER_RE = re.compile(
    r"(?:дни|дн\.|часы|час\.|ставк|тариф|рабочи|оплачено|норм|разряд|стаж|"
    r"коэффициент|kpi|план|факт\s*/\s*план)",
    re.I,
)
_VALUE_HEADER_RE = re.compile(
    r"(?:сумм|итого|всего|начисл|удерж|выплат|значен|amount|total|value|"
    r"(?:за\s+)?(?:19|20)\d{2})",
    re.I,
)
_LABEL_HEADER_RE = re.compile(r"(?:вид|наимен|показател|name|item|description)", re.I)
_HEADER_HINT_RE = re.compile(
    r"(?:вид|наимен|показател|период|дата|месяц|квартал|сумм|итого|всего|"
    r"начисл|удерж|выплат|значен|код|строк|№|ед\.?\s*изм|дни|часы|"
    r"amount|total|value|period|date|name|item|code)",
    re.I,
)
_SECTION_END_RE = re.compile(
    r"(?::|в\s*т\.?\s*ч\.?|в\s*том\s*числе|итого|всего)\s*$", re.I
)
_TOP_LEVEL_LABEL_RE = re.compile(
    r"^(?:выручк|себестоимост|валов(?:ая|ой)\s+прибыл|коммерческ|управленческ|"
    r"прибыл|убыт|доход|расход|процент|проч|налог|актив|капитал|"
    r"revenue|cost|gross|operating|profit|loss|income|expense|asset|equity)",
    re.I,
)
_INCLUDING_RE = re.compile(r"(?:в\s*т\.?\s*ч\.?|в\s*том\s*числе)\s*[:.,]?\s*$", re.I)


def _join_section_label(section: str, label: str) -> str:
    """«Себестоимость продаж» + «продажа газа» → понятное составное название."""
    base = section.rstrip(" :.,;")
    if not base:
        return clean_text(label)
    if _INCLUDING_RE.search(base):
        return clean_text(f"{base} {label}")
    return clean_text(f"{base}, в т.ч. {label}")


def _header_is_code(header: str) -> bool:
    return bool(_CODE_HEADER_RE.search(clean_text(header)))


def _header_is_period(header: str) -> bool:
    return bool(_PERIOD_HEADER_RE.search(clean_text(header)))


def _header_is_value(header: str) -> bool:
    text = clean_text(header)
    if not text or _header_is_code(text) or _header_is_period(text):
        return False
    return bool(_VALUE_HEADER_RE.search(text))


def _header_is_non_value(header: str) -> bool:
    return bool(_NON_VALUE_HEADER_RE.search(clean_text(header)))


def _split_label_with_code(cell: str) -> tuple[str, str] | None:
    """«транспортировки газа 2114» → («транспортировки газа», «2114»)."""
    text = clean_text(cell)
    if not re.search(r"[A-Za-zА-Яа-я]", text):
        return None
    m = re.match(r"^(.*?[A-Za-zА-Яа-я].*?)[\s,;.]*(\d{3,4})$", text)
    if not m:
        return None
    prefix = m.group(1).strip(" ,;.")
    if len(prefix) < 3:
        return None
    return prefix, m.group(2)


_EMBEDDED_VALUE_RE = re.compile(
    r"^(?P<label>[^\d:;]{3,80}?)\s*:\s*"
    r"(?P<num>[-−(]?\d{1,3}(?:[ \u00a0\u202f\u2009]\d{3})+(?:[.,]\d{1,2})?"
    r"|\d+(?:[.,]\d{1,2})?)"
    r"\s*(?P<unit>%|₽|руб\.?|тыс\.?\s*руб\.?|млн\.?\s*руб\.?)?\s*[)]?\s*$",
    re.IGNORECASE,
)


def _split_embedded_value(cell: str) -> tuple[str, str] | None:
    """«Начислено: 139 319,47» → («Начислено», «139 319,47»).

    В расчётных листках суммы стоят прямо в колонке подписи, а колонка
    значений пустая. Разделяем такую ячейку, чтобы значение не потерялось.
    """
    text = clean_text(cell)
    m = _EMBEDDED_VALUE_RE.match(text)
    if not m:
        return None
    label = m.group("label").strip(" ,;:.-")
    if len(label) < 3:
        return None
    return label, clean_text(m.group("num") + " " + (m.group("unit") or ""))


def _table_groups(headers: list[str]) -> list[dict[str, int | None]]:
    """Находит повторяющиеся группы колонок: «Вид | Период | Сумма» × 2."""
    label_positions = [
        i for i, h in enumerate(headers)
        if _LABEL_HEADER_RE.search(clean_text(h))
        and not _header_is_value(h)
    ]
    if len(label_positions) < 2:
        return []
    groups: list[dict[str, int | None]] = []
    for gi, start in enumerate(label_positions):
        end = label_positions[gi + 1] if gi + 1 < len(label_positions) else len(headers)
        segment = headers[start:end]
        period_rel = next((i for i, h in enumerate(segment) if _header_is_period(h)), None)
        value_rel = next(
            (
                i for i, h in enumerate(segment)
                if _header_is_value(h) and i != period_rel
            ),
            None,
        )
        if value_rel is None:
            for i in range(len(segment)):
                if i in (0, period_rel) or _header_is_non_value(segment[i]):
                    continue
                if segment[i] or i == len(segment) - 1:
                    value_rel = i
                    break
        if value_rel is None:
            continue
        groups.append(
            {
                "label": start,
                "period": start + period_rel if period_rel is not None else None,
                "value": start + value_rel,
            }
        )
    return groups


def _page_default_unit(text: str) -> Any:
    """Единица измерения всей страницы: «Единица измерения: тыс. руб.»."""
    for line in (text or "").split("\n"):
        if re.search(r"(?:единица\s+измерения|unit\s+of\s+measure)", line, re.I):
            unit = detect_unit(line)
            if unit and unit.dimension:
                return unit
    return None


def _table_metrics(
    table: ExtractedTable,
    default_period: str,
    table_id: int | None = None,
    page_text: str = "",
) -> list[ExtractedMetric]:
    headers, rows = _maybe_transpose(table.headers, table.rows)
    if not headers or not rows:
        return []
    metrics: list[ExtractedMetric] = []
    header_periods = [extract_period(h) for h in headers]
    header_units = [detect_unit(h) for h in headers]
    caption_unit = detect_unit(table.title)
    page_unit = _page_default_unit(page_text)
    code_idx = next((i for i, h in enumerate(headers) if _header_is_code(h)), None)

    groups = _table_groups(headers)
    if groups:
        label_idx = groups[0]["label"]
        value_columns: list[int] = []
        for group in groups:
            if group["value"] is not None:
                value_columns.append(int(group["value"]))
    else:
        label_idx = next(
            (i for i, h in enumerate(headers) if _LABEL_HEADER_RE.search(clean_text(h))),
            0,
        )
        period_idx = next(
            (i for i, h in enumerate(headers) if _header_is_period(h) and i != code_idx),
            None,
        )
        value_columns = [
            i for i, h in enumerate(headers)
            if i not in (label_idx, code_idx, period_idx) and _header_is_value(h)
        ]
        if not value_columns:
            value_columns = [
                i for i, h in enumerate(headers)
                if i > label_idx
                and i not in (code_idx, period_idx)
                and not _header_is_non_value(h)
            ]

    if not value_columns:
        return []

    # Разделяем слипшиеся подписи и коды в колонке кода
    inline_targets: list[tuple[int, int | None]] = []
    if label_idx is not None:
        inline_targets.append(
            (label_idx, groups[0]["value"] if groups else (value_columns[0] if value_columns else None))
        )
    for group in groups:
        if group["label"] is not None:
            inline_targets.append((int(group["label"]), group["value"]))

    prepared: list[list[str]] = []
    for row in rows:
        new_row = [clean_text(c) for c in row]
        if code_idx is not None and code_idx < len(new_row):
            split = _split_label_with_code(new_row[code_idx])
            if split and label_idx is not None and label_idx < len(new_row):
                prefix, code = split
                if new_row[label_idx]:
                    new_row[label_idx] = clean_text(f"{new_row[label_idx]} {prefix}")
                else:
                    new_row[label_idx] = prefix
                new_row[code_idx] = code
        # «Начислено: 139 319,47» → подпись «Начислено», значение в колонке значений
        for cell_idx, value_idx in inline_targets:
            if cell_idx >= len(new_row):
                continue
            if value_idx is not None and value_idx < len(new_row) and new_row[value_idx]:
                continue
            inline = _split_embedded_value(new_row[cell_idx])
            if not inline:
                continue
            new_row[cell_idx] = inline[0]
            if value_idx is not None and value_idx < len(new_row):
                new_row[value_idx] = inline[1]
        prepared.append(new_row)

    pending_label = ""
    last_label = ""
    section_label = ""
    for r_idx, row in enumerate(prepared):
        if not row:
            continue
        label_cell = row[label_idx] if label_idx is not None and label_idx < len(row) else ""
        label = _clean_metric_label(label_cell)
        if label and re.fullmatch(r"(?:итого|всего|total)", label.strip().lower()):
            label = clean_text(label)
        group_labels: dict[int, str] = {}
        for gi, group in enumerate(groups):
            g_label_idx = group["label"]
            group_labels[gi] = (
                _clean_metric_label(row[g_label_idx])
                if g_label_idx is not None and g_label_idx < len(row)
                else ""
            )
        # продолжение подписи в колонке кода (OCR разрывает длинные названия)
        if code_idx is not None and code_idx < len(row):
            code_cell = row[code_idx]
            if code_cell and not re.fullmatch(r"\d{3,4}", code_cell):
                if re.search(r"[A-Za-zА-Яа-я]", code_cell):
                    pending_label = clean_text(f"{pending_label} {code_cell}")

        check_columns = (
            [int(g["value"]) for g in groups if g["value"] is not None]
            if groups
            else value_columns
        )
        has_values = any(
            idx < len(row) and bool(row[idx]) for idx in check_columns
        )

        if not has_values:
            if label:
                pending_label = clean_text(f"{pending_label} {label}")
            continue

        if label:
            last_label = label
        full_label = clean_text(f"{pending_label} {last_label}")
        # Подпункты («продажа газа») относятся к разделу («Выручка, вт.ч.»).
        # Это не даёт смешивать одинаковые названия из разных разделов отчёта.
        if label:
            if re.match(r"(?:итого|всего|total)\b", label, re.I):
                section_label = ""
            elif _SECTION_END_RE.search(label) or _TOP_LEVEL_LABEL_RE.match(label):
                section_label = label
            elif section_label:
                full_label = _join_section_label(section_label, full_label)
        if not _looks_like_metric_label(full_label):
            pending_label = ""
            continue
        context = short_snippet(" | ".join(c for c in row if c), 320)

        for gi, group in enumerate(
            groups
            if groups
            else [{"label": label_idx, "period": None, "value": value_idx} for value_idx in value_columns]
        ):
            value_idx = group["value"]
            if value_idx is None or value_idx >= len(row):
                continue
            cell = row[value_idx]
            if not cell:
                continue
            effective_label = group_labels.get(gi, "") if groups else ""
            effective_label = effective_label or full_label
            if not _looks_like_metric_label(effective_label):
                continue
            label_unit = detect_unit(effective_label)
            if table.method == "tesseract-table" and re.fullmatch(r"[\d\s]+", cell):
                # OCR иногда теряет пробел внутри разрядов: «1661 152» → 1661152
                cell = re.sub(r"\s+", "", cell)
            parsed = value_with_unit(cell)
            if not parsed:
                continue
            value = parsed["value"]
            unit = parsed["unit"]
            dimension = parsed["dimension"]
            scale = parsed["scale"]
            currency = parsed["currency"]
            if not unit and label_unit:
                unit, dimension, scale, currency = (
                    label_unit.display,
                    label_unit.dimension,
                    label_unit.scale,
                    label_unit.currency,
                )
            if not unit:
                hu = header_units[value_idx] if value_idx < len(header_units) else None
                unit = hu.display if hu else ""
                dimension = hu.dimension if hu else ""
                scale = hu.scale if hu else 1.0
                currency = hu.currency if hu else ""
            if not unit and caption_unit:
                unit, dimension, scale, currency = (
                    caption_unit.display,
                    caption_unit.dimension,
                    caption_unit.scale,
                    caption_unit.currency,
                )
            if not unit and page_unit:
                unit, dimension, scale, currency = (
                    page_unit.display,
                    page_unit.dimension,
                    page_unit.scale,
                    page_unit.currency,
                )
            period_cell = row[group["period"]] if group["period"] is not None and group["period"] < len(row) else ""
            period = (
                extract_period(period_cell)
                or (header_periods[value_idx] if value_idx < len(header_periods) else "")
                or extract_period(effective_label)
                or default_period
            )
            if _is_year_value(value, parsed["raw_value"], unit):
                continue
            # Номер строки в первой колонке — не показатель
            if value_idx == label_idx + 1 and value == r_idx + 1 and not unit:
                continue
            # Коды строк (2110, 2111…) не являются значениями показателя
            if code_idx is not None and value_idx == code_idx:
                continue
            metrics.append(
                ExtractedMetric(
                    page_number=table.page_number,
                    label=effective_label,
                    normalized_label=canonical_label(effective_label),
                    raw_value=parsed["raw_value"],
                    value=value,
                    normalized_value=value * scale if scale else value,
                    unit=unit,
                    dimension=dimension,
                    scale=scale,
                    currency=currency,
                    period=period,
                    raw_text=cell,
                    context=context,
                    confidence=round(min(0.95, table.confidence + 0.02), 2),
                    source_kind="table",
                    source_ref=f"p{table.page_number}:t{r_idx + 2}:c{value_idx + 1}",
                    row_index=r_idx,
                    col_index=value_idx,
                    table_id=table_id,
                )
            )
        pending_label = ""

    return metrics


_ABBR_END_RE = re.compile(
    r"(?:тыс|млн|млрд|руб|коп|чел|ед|шт|стр|рис|табл|г|гг|п|пп|пр|др|им|ул|кап)\.[\"»)]?$",
    re.IGNORECASE,
)


def _logical_lines(text: str) -> list[str]:
    """Склеивает перенесённые строки абзаца (продолжение со строчной буквы)."""
    merged: list[str] = []
    for raw in (text or "").split("\n"):
        line = clean_text(raw)
        if not line:
            continue
        prev = merged[-1] if merged else ""
        sentence_end = bool(re.search(r"[.!?:;…]$", prev)) and not _ABBR_END_RE.search(prev)
        if (
            merged
            and not prev.startswith("## ")
            and line[:1]
            and (
                (
                    not sentence_end
                    and (line[:1].islower() or line[:1] in "—–-")
                )
                or (prev[-1:].isdigit() and line[:1].isdigit())
            )
        ):
            merged[-1] = f"{merged[-1]} {line}"
            continue
        merged.append(line)
    return merged


_HEADER_NOISE_RE = re.compile(
    r"^(?:коды\b|код\b|форма\s+по|дата\b|организация\b|"
    r"идентификационный\s+номер|инн\b|вид\s+экономической|"
    r"по\s+оквэд|организационно-правовая|по\s+окопф|"
    r"единица\s+измерения|по\s+океи|пояснени|наименование\b|"
    r"показател[ья]\b|строки\b|отчет\b|отчёт\b|"
    r"бухгалтерск(?:ий|ая)\s+баланс|финансовых\s+результатах)",
    re.I,
)
_OKSM_RE = re.compile(
    r"(?:инн|окпо|окуд|оквэд|окопф|окфс|океи|огрн|кпп)\b", re.I
)


def _is_header_line(line: str) -> bool:
    """Шапки бланков и реквизиты — не показатели."""
    low = line.lower().strip()
    if not low or len(low) > 160:
        return False
    if _HEADER_NOISE_RE.match(low):
        return True
    if _OKSM_RE.search(low):
        return True
    return False


_HEADER_KV_PATTERNS = [
    (re.compile(r"К выплате\s*:?\s*[\n\r# ]*(?P<num>[-−(]?\d[\d\s\u00a0\u202f]*(?:[.,]\d{1,2})?[)]?)", re.IGNORECASE), "К выплате"),
    (re.compile(r"Оклад\s*\(тариф\)\s*:?\s*[\n\r# ]*(?P<num>[-−(]?\d[\d\s\u00a0\u202f]*(?:[.,]\d{1,2})?[)]?)", re.IGNORECASE), "Оклад (тариф)"),
    (re.compile(r"Долг за организацией на начало месяца\s*:?\s*[\n\r# ]*(?P<num>[-−(]?\d[\d\s\u00a0\u202f]*(?:[.,]\d{1,2})?[)]?)", re.IGNORECASE), "Долг за организацией на начало месяца"),
    (re.compile(r"Долг за организацией на конец месяца\s*:?\s*[\n\r# ]*(?P<num>[-−(]?\d[\d\s\u00a0\u202f]*(?:[.,]\d{1,2})?[)]?)", re.IGNORECASE), "Долг за организацией на конец месяца"),
    (re.compile(r"Долг за работником на начало месяца\s*:?\s*[\n\r# ]*(?P<num>[-−(]?\d[\d\s\u00a0\u202f]*(?:[.,]\d{1,2})?[)]?)", re.IGNORECASE), "Долг за работником на начало месяца"),
    (re.compile(r"Долг за работником на конец месяца\s*:?\s*[\n\r# ]*(?P<num>[-−(]?\d[\d\s\u00a0\u202f]*(?:[.,]\d{1,2})?[)]?)", re.IGNORECASE), "Долг за работником на конец месяца"),
]


def _header_kv_metrics(
    text: str, page_number: int, default_period: str, page_confidence: float
) -> list[ExtractedMetric]:
    """Извлекает ключевые суммы из шапки документа (например, расчётного листка)."""
    results: list[ExtractedMetric] = []
    src = clean_multiline(text)
    for rx, label in _HEADER_KV_PATTERNS:
        m = rx.search(src)
        if not m:
            continue
        raw_num = m.group("num")
        parsed = value_with_unit(raw_num)
        value = parsed["value"] if parsed else parse_number(raw_num)
        if value is None:
            continue
        if _is_year_value(value, raw_num, ""):
            continue
        context = short_snippet(src[max(0, m.start() - 20): m.end() + 40], 320)
        confidence = round(min(0.9, 0.78 * max(0.7, page_confidence)), 2)
        results.append(
            ExtractedMetric(
                page_number=page_number,
                label=label,
                normalized_label=canonical_label(label),
                raw_value=clean_text(raw_num),
                value=value,
                normalized_value=value,
                unit="",
                dimension="",
                scale=1.0,
                currency="",
                period=default_period,
                raw_text=clean_text(m.group(0)),
                context=context,
                confidence=confidence,
                source_kind="text",
                source_ref=f"p{page_number}",
            )
        )
    return results


def _text_metrics(
    text: str, page_number: int, default_period: str, page_confidence: float
) -> list[ExtractedMetric]:
    metrics: list[ExtractedMetric] = []
    for line in _logical_lines(text):
        if len(line) < 5 or line.startswith("## "):
            continue
        if _DATE_LIKE_RE.fullmatch(line):
            continue
        if _is_header_line(line):
            continue
        # Строки таблиц уже разобраны табличным экстрактором: не дублируем
        # их мусорными «показателями» из слипшихся колонок.
        if " | " in line and re.search(r"\d", line):
            continue
        # строка таблицы, распознанная как «подпись + числа» без единиц
        if re.fullmatch(r"[A-Za-zА-Яа-яЁё][^0-9]{2,80}\s+\d[\d\s]{4,}", line):
            continue
        line_matches = list(_NUM_WITH_UNIT_RE.finditer(line))
        # строка таблицы без единиц: несколько чисел подряд — не текстовая метрика
        if len(line_matches) >= 2 and not detect_unit(line):
            continue
        for m in line_matches:
            raw_num = m.group("num")
            value = parse_number(raw_num)
            if value is None:
                continue
            # Число в скобках после основного значения — обычно пересчёт в других единицах
            if line[: m.start()].rstrip().endswith("(") or raw_num.lstrip().startswith("("):
                continue
            suffix = m.group("unit") or ""
            tail = line[m.end(): m.end() + 48]
            tail = re.split(r"\d", tail)[0][:24]
            unit_source = f"{suffix} {tail}".strip()
            parsed = value_with_unit(raw_num + " " + suffix)
            if not parsed:
                continue
            value = parsed["value"]
            # Год — не показатель, даже если рядом в строке есть единицы
            if _is_year_value(value, parsed["raw_value"], ""):
                continue
            # Единицу ищем сразу после числа (тыс. руб., млн руб., %, чел. и т.д.),
            # затем в подписи перед числом
            unit_info = detect_unit(unit_source)
            if unit_info:
                unit = unit_info.display
                dimension = unit_info.dimension
                scale = unit_info.scale
                currency = unit_info.currency
            else:
                unit, dimension, scale, currency = "", "", 1.0, ""
            # Пропускаем даты (число внутри даты)
            if _DATE_LIKE_RE.search(line[max(0, m.start() - 1): m.end() + 1]):
                continue
            label = _label_from_prefix(line[: m.start()])
            if not _is_meaningful_label(label):
                continue
            if len(label) > 140 or "|" in label:
                continue
            digit_ratio = sum(ch.isdigit() for ch in label) / max(1, len(label))
            if digit_ratio > 0.3:
                continue
            # код строки/графы (2110, 0710002) — не показатель
            if re.fullmatch(r"[\d\s.,/№()-]{1,12}", label.strip()):
                continue
            keyword = _has_metric_keyword(label)
            if not unit and not keyword:
                continue
            # Отсекаем номера страниц и пунктов
            if re.fullmatch(r"\d{1,3}", label.strip()):
                continue
            period = extract_period(line, default_period)
            confidence = (0.72 if unit else 0.62) + (0.07 if keyword else 0)
            confidence = round(min(0.9, confidence * max(0.7, page_confidence)), 2)
            context = short_snippet(line, 320)
            metrics.append(
                ExtractedMetric(
                    page_number=page_number,
                    label=label,
                    normalized_label=canonical_label(label),
                    raw_value=parsed["raw_value"],
                    value=value,
                    normalized_value=value * scale if scale else value,
                    unit=unit,
                    dimension=dimension,
                    scale=scale,
                    currency=currency,
                    period=period,
                    raw_text=m.group(0).strip(),
                    context=context,
                    confidence=confidence,
                    source_kind="text",
                    source_ref=f"p{page_number}",
                )
            )
    return metrics


def chunk_text(text: str, max_chars: int = 1400, overlap: int = 180) -> list[str]:
    """Делит текст страницы на перекрывающиеся фрагменты по абзацам/предложениям."""
    text = (text or "").strip()
    if not text:
        return []
    paragraphs = [p.strip() for p in re.split(r"\n{1,}", text) if p.strip()]
    chunks: list[str] = []
    current = ""
    for p in paragraphs:
        if len(current) + len(p) + 1 <= max_chars:
            current = f"{current}\n{p}".strip()
            continue
        if current:
            chunks.append(current)
        if len(p) <= max_chars:
            current = p
            continue
        sentences = re.split(r"(?<=[.!?])\s+", p)
        current = ""
        for sentence in sentences:
            if len(current) + len(sentence) + 1 <= max_chars:
                current = f"{current} {sentence}".strip()
            else:
                if current:
                    chunks.append(current)
                if len(sentence) > max_chars:
                    for i in range(0, len(sentence), max_chars - overlap):
                        piece = sentence[i: i + max_chars]
                        if piece.strip():
                            chunks.append(piece.strip())
                    current = ""
                else:
                    current = sentence
    if current:
        chunks.append(current)
    # добавляем перекрытие
    if overlap > 0 and len(chunks) > 1:
        overlapped = [chunks[0]]
        for i in range(1, len(chunks)):
            prev_tail = overlapped[-1][-overlap:]
            if not chunks[i].startswith(prev_tail):
                overlapped.append((prev_tail + " " + chunks[i]).strip())
            else:
                overlapped.append(chunks[i])
        chunks = overlapped
    return chunks


def extract_document(
    path: str | Path,
    original_name: str,
    on_progress: ProgressCallback | None = None,
    ocr_config: dict[str, Any] | None = None,
) -> DocumentExtraction:
    import time

    started = time.perf_counter()
    ocr_cfg = _ocr_config(ocr_config)
    path = Path(path)
    warnings: list[str] = []
    pages: list[PageData] = []
    tables: list[ExtractedTable] = []
    metrics: list[ExtractedMetric] = []

    def progress(pct: int, stage: str) -> None:
        if on_progress:
            on_progress(max(0, min(100, pct)), stage)

    progress(3, "Открытие PDF")
    try:
        file_size = path.stat().st_size
    except OSError as exc:
        raise ValueError(f"Не удалось прочитать PDF: {exc}") from exc
    max_file_bytes = max(1, int(ocr_cfg.get("max_file_bytes") or settings.max_upload_mb * 1024 * 1024))
    if file_size > max_file_bytes:
        raise PDFResourceLimitError(
            f"PDF превышает допустимый размер {max_file_bytes // (1024 * 1024)} МБ."
        )

    doc = pymupdf.open(str(path))
    if doc.needs_pass:
        if not doc.authenticate(""):
            doc.close()
            raise ValueError("PDF защищён паролем. Поддерживаются только документы без пароля.")
    page_total = doc.page_count
    if page_total == 0:
        doc.close()
        raise ValueError("PDF не содержит страниц.")
    if page_total > MAX_PDF_PAGES:
        doc.close()
        raise PDFResourceLimitError(
            f"В PDF {page_total} страниц; безопасный предел обработки — {MAX_PDF_PAGES}."
        )

    try:
        first_text = clean_text(doc[0].get_text("text"))[:8000]
    except Exception:  # noqa: BLE001
        first_text = ""
    default_period = guess_document_period(first_text, original_name)

    lang, ocr_warnings = _ocr_languages(ocr_cfg)
    warnings.extend(ocr_warnings)

    plumber_doc = None
    total_text_chars = 0
    try:
        import pdfplumber

        plumber_doc = pdfplumber.open(str(path))
    except Exception as exc:  # noqa: BLE001
        warnings.append(f"pdfplumber недоступен для этого файла: {exc}")

    try:
        for idx in range(page_total):
            page = doc[idx]
            pct = 5 + int((idx / max(1, page_total)) * 65)
            progress(pct, f"Извлечение страницы {idx + 1} из {page_total}")
            text, headings = _extract_text_page(page)
            if len(text) > MAX_PAGE_TEXT_CHARS:
                raise PDFResourceLimitError(
                    f"Страница {idx + 1} содержит слишком много текста "
                    f"(>{MAX_PAGE_TEXT_CHARS:,} символов)."
                )
            method = "text"
            confidence = 0.98
            ocr_words: list[dict[str, Any]] = []
            ocr_conf = 0.0
            if _needs_ocr(text, page, ocr_cfg):
                if lang:
                    progress(pct, f"OCR страницы {idx + 1} из {page_total}")
                    try:
                        ocr_text, ocr_conf, ocr_words = _ocr_page(page, lang, ocr_cfg)
                        if ocr_text:
                            text = ocr_text
                            headings = _ocr_headings(ocr_text)
                            method = "ocr"
                            confidence = max(0.0, min(1.0, ocr_conf / 100.0))
                            if ocr_conf < float(ocr_cfg.get("min_confidence") or 65):
                                warnings.append(
                                    f"Стр. {idx + 1}: низкая уверенность OCR ({ocr_conf:.0f}%). "
                                    "Проверьте распознанный текст по оригиналу."
                                )
                        else:
                            warnings.append(f"Стр. {idx + 1}: OCR не распознал текст.")
                    except Exception as exc:  # noqa: BLE001
                        warnings.append(f"Стр. {idx + 1}: ошибка OCR — {exc}")
                        method = "ocr"
                        confidence = 0.0
                else:
                    warnings.append(f"Стр. {idx + 1}: требуется OCR, но Tesseract недоступен.")

            page_tables: list[ExtractedTable] = []
            if method == "text":
                page_tables.extend(_extract_tables_pymupdf(page, text))
                if not page_tables and plumber_doc is not None:
                    if len(text) > 200_000:
                        warnings.append(
                            f"Стр. {idx + 1}: альтернативное извлечение таблиц пропущено "
                            "из-за большого объёма текста."
                        )
                    else:
                        try:
                            plumber_page = plumber_doc.pages[idx]
                            page_tables.extend(_extract_tables_pdfplumber(plumber_page, text))
                        except Exception as exc:  # noqa: BLE001
                            logger.debug("pdfplumber page failed: %s", exc)
            elif method == "ocr" and ocr_words:
                try:
                    page_tables.extend(
                        _ocr_tables_from_words(ocr_words, page, idx + 1, ocr_conf)
                    )
                except Exception as exc:  # noqa: BLE001
                    logger.debug("OCR table rebuild failed: %s", exc)
            # Ограничиваем объём структур, которые сохраняются и индексируются.
            if len(page_tables) > MAX_TABLES_PER_PAGE:
                warnings.append(
                    f"Стр. {idx + 1}: найдено таблиц больше лимита "
                    f"{MAX_TABLES_PER_PAGE}; лишние таблицы пропущены."
                )
                page_tables = page_tables[:MAX_TABLES_PER_PAGE]

            # дедупликация таблиц
            seen: set[str] = set()
            for t in page_tables:
                cell_count = len(t.headers) + sum(len(row) for row in t.rows)
                if cell_count > MAX_TABLE_CELLS:
                    warnings.append(
                        f"Стр. {idx + 1}: таблица пропущена — "
                        f"число ячеек превышает лимит {MAX_TABLE_CELLS:,}."
                    )
                    continue
                sig = _table_signature(t.headers, t.rows)
                if sig in seen:
                    continue
                seen.add(sig)
                tables.append(t)
                metrics.extend(_table_metrics(t, default_period, page_text=text))
            metrics.extend(_header_kv_metrics(text, idx + 1, default_period, confidence))
            metrics.extend(_text_metrics(text, idx + 1, default_period, confidence))
            total_text_chars += len(text)
            if total_text_chars > MAX_DOCUMENT_TEXT_CHARS:
                raise PDFResourceLimitError(
                    "Документ содержит слишком много извлечённого текста "
                    f"(>{MAX_DOCUMENT_TEXT_CHARS:,} символов)."
                )
            pages.append(
                PageData(
                    number=idx + 1,
                    text=text,
                    method=method,
                    confidence=round(confidence, 3),
                    headings=headings[:20],
                    width=round(float(page.rect.width), 1),
                    height=round(float(page.rect.height), 1),
                    has_tables=bool(page_tables),
                )
            )

        progress(78, "Удаление дублей и проверка качества")
        # дедупликация показателей (текст и таблицы часто дублируют друг друга)
        unique: dict[tuple, ExtractedMetric] = {}
        for m in metrics:
            key = (
                m.normalized_label,
                m.period,
                round(m.value, 4) if m.value is not None else None,
                m.unit,
                m.page_number,
            )
            existing = unique.get(key)
            if existing is None or m.confidence > existing.confidence or (
                existing.source_kind == "text" and m.source_kind == "table"
            ):
                unique[key] = m
        metrics = sorted(unique.values(), key=lambda m: (m.page_number, m.row_index, m.col_index))

        ocr_pages = sum(1 for p in pages if p.method == "ocr")
        text_chars = sum(len(p.text) for p in pages)
        confidences = [p.confidence for p in pages if p.text]
        avg_confidence = round(sum(confidences) / len(confidences), 3) if confidences else 0.0
        if text_chars == 0:
            warnings.append("Текст не извлечён ни со одной страницы.")
        if ocr_pages and avg_confidence < (float(ocr_cfg.get("min_confidence") or 65) / 100.0):
            warnings.append(
                "Средняя уверенность OCR ниже порога. Результаты анализа требуют проверки."
            )
        if not tables:
            warnings.append("Таблицы не обнаружены — показатели извлечены из текста.")
        progress(92, "Сохранение результатов")
        ms = int((time.perf_counter() - started) * 1000)
        return DocumentExtraction(
            pages=pages,
            tables=tables,
            metrics=metrics,
            warnings=warnings,
            ocr_pages=ocr_pages,
            avg_confidence=avg_confidence,
            default_period=default_period,
            text_chars=text_chars,
            processing_ms=ms,
        )
    finally:
        try:
            if plumber_doc is not None:
                plumber_doc.close()
        except Exception:  # noqa: BLE001
            pass
        doc.close()


def render_page_png(path: str | Path, page_number: int, dpi: int = 110) -> bytes:
    doc = pymupdf.open(str(path))
    try:
        if page_number < 1 or page_number > doc.page_count:
            raise ValueError("Страница не найдена")
        page = doc[page_number - 1]
        effective_dpi = _bounded_page_dpi(
            page, dpi, minimum_dpi=MIN_PREVIEW_DPI
        )
        zoom = effective_dpi / 72.0
        pix = page.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom), alpha=False)
        return pix.tobytes("png")
    finally:
        doc.close()
