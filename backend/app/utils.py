"""Общие утилиты: разбор чисел, единиц, периодов, нормализация текста."""
from __future__ import annotations

import hashlib
import json
import math
import re
import unicodedata
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

NBSP = "\u00a0\u202f\u2009"
_SPACE_RE = re.compile(r"[\s\u00a0\u202f\u2009]+")
_YEAR_RE = re.compile(r"(?<!\d)((?:19|20)\d{2})(?!\d)")
_DATE_RE = re.compile(
    r"(?<!\d)(\d{1,2})[.\-/](\d{1,2})[.\-/]((?:19|20)\d{2})(?!\d)"
)
_QUARTER_RE = re.compile(
    r"(?:(?P<q>[1-4])\s*(?:кв(?:артал)?\.?|quarter)|Q(?P<q2>[1-4]))\s*[.,/\-]?\s*(?P<y>(?:19|20)\d{2})",
    re.IGNORECASE,
)
_MONTH_NAME_RE = re.compile(
    r"(?<![A-Za-zА-Яа-яЁё])(?P<month>"
    r"январ[ья]|феврал[ья]|март(?:а)?|апрел[ья]|ма[йя]|июн[ья]|июл[ья]|"
    r"август(?:а)?|сентябр[ья]|октябр[ья]|ноябр[ья]|декабр[ья]|"
    r"янв\.?|фев\.?|февр\.?|мар\.?|апр\.?|июн\.?|июл\.?|авг\.?|сен\.?|сент\.?|окт\.?|ноя\.?|дек\.?|"
    r"jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?|"
    r"aug(?:ust)?|sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?"
    r")(?![A-Za-zА-Яа-яЁё])",
    re.IGNORECASE,
)
_MONTH_PREFIXES = {
    "янв": 1, "фев": 2, "мар": 3, "апр": 4, "май": 5, "мая": 5, "июн": 6,
    "июл": 7, "авг": 8, "сен": 9, "окт": 10, "ноя": 11, "дек": 12,
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6, "jul": 7,
    "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}


def _month_number(name: str) -> int:
    key = clean_text(name).lower().replace(".", "")[:3]
    return _MONTH_PREFIXES.get(key, 0)

RU_STOPWORDS = {
    "и", "в", "во", "на", "по", "с", "со", "к", "ко", "из", "за", "от", "до", "для",
    "о", "об", "обо", "при", "про", "без", "через", "между", "над", "под", "у", "не",
    "ни", "же", "ли", "бы", "что", "как", "где", "когда", "какой", "какие", "каких",
    "какова", "каков", "это", "этот", "эта", "эти", "все", "всех", "весь", "вся",
    "всё", "мне", "нам", "вы", "ты", "он", "она", "они", "мы", "я", "его", "её",
    "их", "свой", "свои", "также", "или", "а", "но", "если", "то", "чем", "тем",
    "было", "были", "будет", "есть", "быть", "является", "показатель", "показатели",
    "значение", "значения", "данные", "данных", "документ", "документы", "документах",
    "документов", "pdf", "файл", "файлы", "файлах", "сравни", "сравнить", "сравнение",
    "сравнении", "найди", "найти", "покажи", "показать", "определи", "определить",
    "составь", "составить", "рассчитай", "рассчитать", "выведи", "вывести", "дай",
    "построй", "построить", "нужно", "нужны", "можешь", "можно", "пожалуйста",
    "проанализируй", "анализ", "анализе", "таблицу", "таблица", "таблице", "график",
    "графики", "графике", "графиках", "графиков", "динамику", "динамика", "динамике",
    "изменение", "изменения", "изменений", "рост", "снижение", "вырос", "выросли",
    "снизился", "снизилась", "увеличился", "уменьшился", "итого", "всего", "общий",
    "общая", "общие", "между", "разные", "разных", "годы", "год", "году", "года",
    "годов", "период", "периоде", "периода", "странице", "страница", "стр", "срок",
    "влияние", "причина", "причины", "вывод", "выводы", "основные", "основных",
}
EN_STOPWORDS = {
    "the", "a", "an", "and", "or", "of", "in", "on", "for", "to", "with", "by",
    "from", "all", "show", "find", "compare", "analysis", "document", "documents",
    "pdf", "please", "what", "which", "how", "is", "are", "was", "were", "be",
    "value", "values", "data", "table", "chart", "graph", "trend", "change", "year",
    "years", "between", "across", "give", "calculate", "build", "make",
}
STOPWORDS = RU_STOPWORDS | EN_STOPWORDS


@dataclass(frozen=True)
class UnitInfo:
    display: str
    dimension: str
    scale: float
    currency: str = ""


UNIT_RULES: list[tuple[re.Pattern[str], UnitInfo]] = [
    # Английские масштабы + валюта: «thousand RUB», «million USD», «bn EUR»
    (re.compile(r"(?:billion|bn)\.?\s*(?:rub|rubles?|₽)", re.I), UnitInfo("млрд руб.", "money", 1e9, "RUB")),
    (re.compile(r"(?:million|mn|mln)\.?\s*(?:rub|rubles?|₽)", re.I), UnitInfo("млн руб.", "money", 1e6, "RUB")),
    (re.compile(r"(?:thousand|k)\.?\s*(?:rub|rubles?|₽)", re.I), UnitInfo("тыс. руб.", "money", 1e3, "RUB")),
    (re.compile(r"(?:billion|bn)\.?\s*(?:usd|dollars?|\$)", re.I), UnitInfo("млрд долл.", "money", 1e9, "USD")),
    (re.compile(r"(?:million|mn|mln)\.?\s*(?:usd|dollars?|\$)", re.I), UnitInfo("млн долл.", "money", 1e6, "USD")),
    (re.compile(r"(?:thousand|k)\.?\s*(?:usd|dollars?|\$)", re.I), UnitInfo("тыс. долл.", "money", 1e3, "USD")),
    (re.compile(r"(?:billion|bn)\.?\s*(?:eur|euros?|€)", re.I), UnitInfo("млрд евро", "money", 1e9, "EUR")),
    (re.compile(r"(?:million|mn|mln)\.?\s*(?:eur|euros?|€)", re.I), UnitInfo("млн евро", "money", 1e6, "EUR")),
    (re.compile(r"(?:thousand|k)\.?\s*(?:eur|euros?|€)", re.I), UnitInfo("тыс. евро", "money", 1e3, "EUR")),
    (re.compile(r"млрд\.?\s*(?:руб|₽|рублей|р\.)", re.I), UnitInfo("млрд руб.", "money", 1e9, "RUB")),
    (re.compile(r"млн\.?\s*(?:руб|₽|рублей|р\.)", re.I), UnitInfo("млн руб.", "money", 1e6, "RUB")),
    (re.compile(r"тыс\.?\s*(?:руб|₽|рублей|р\.)", re.I), UnitInfo("тыс. руб.", "money", 1e3, "RUB")),
    (re.compile(r"млрд\.?\s*(?:долл|usd|\$)", re.I), UnitInfo("млрд долл.", "money", 1e9, "USD")),
    (re.compile(r"млн\.?\s*(?:долл|usd|\$)", re.I), UnitInfo("млн долл.", "money", 1e6, "USD")),
    (re.compile(r"тыс\.?\s*(?:долл|usd|\$)", re.I), UnitInfo("тыс. долл.", "money", 1e3, "USD")),
    (re.compile(r"млрд\.?\s*(?:евро|eur|€)", re.I), UnitInfo("млрд евро", "money", 1e9, "EUR")),
    (re.compile(r"млн\.?\s*(?:евро|eur|€)", re.I), UnitInfo("млн евро", "money", 1e6, "EUR")),
    (re.compile(r"тыс\.?\s*(?:евро|eur|€)", re.I), UnitInfo("тыс. евро", "money", 1e3, "EUR")),
    (re.compile(r"(?<![\wа-яa-z])(?:руб(?:лей|ля|ль|\.)?|₽|rub|rubles?)(?![\wа-яa-z])", re.I), UnitInfo("руб.", "money", 1.0, "RUB")),
    (re.compile(r"(?<![\wа-яa-z])(?:долл(?:ар(?:ов|а|ы)?|\.)?|usd|dollars?|\$)(?![\wа-яa-z])", re.I), UnitInfo("долл.", "money", 1.0, "USD")),
    (re.compile(r"(?<![\wа-яa-z])(?:евро|eur|euros?|€)(?![\wа-яa-z])", re.I), UnitInfo("евро", "money", 1.0, "EUR")),
    # «Проценты к получению» — название показателя, а не единица измерения,
    # поэтому требуем явный «%», «проц.» или слово «процент(ов/а)» целиком.
    (re.compile(r"%|(?<![\wа-яa-z])проц\.|(?<![\wа-яa-z])процент(?:ов|а)?(?![\wа-яa-z])", re.I), UnitInfo("%", "percent", 1.0)),
    (re.compile(r"(?<![\wа-яa-z])п\.?\s*п\.?(?![\wа-яa-z])", re.I), UnitInfo("п.п.", "pp", 1.0)),
    (re.compile(r"(?<![\wа-яa-z])тыс\.?\s*(?:шт|штук|ед)(?![\wа-яa-z])", re.I), UnitInfo("тыс. шт.", "count", 1e3)),
    (re.compile(r"(?<![\wа-яa-z])млн\.?\s*(?:шт|штук|ед)(?![\wа-яa-z])", re.I), UnitInfo("млн шт.", "count", 1e6)),
    (re.compile(r"(?<![\wа-яa-z])(?:шт(?:ук|уки|\.)?|единиц(?:а|ы)?|ед\.?)(?![\wа-яa-z])", re.I), UnitInfo("шт.", "count", 1.0)),
    (re.compile(r"(?<![\wа-яa-z])(?:чел(?:овек|\.)?|сотрудник(?:ов|а)?)(?![\wа-яa-z])", re.I), UnitInfo("чел.", "people", 1.0)),
    (re.compile(r"кв\.?\s*м|м2|м²", re.I), UnitInfo("кв. м", "area", 1.0)),
    (re.compile(r"(?<![\wа-яa-z])(?:тонн(?:ы|\.)?|т\.)(?![\wа-яa-z])", re.I), UnitInfo("т", "mass", 1000.0)),
    (re.compile(r"(?<![\wа-яa-z])кг(?![\wа-яa-z])", re.I), UnitInfo("кг", "mass", 1.0)),
    (re.compile(r"(?<![\wа-я])г\.", re.I), UnitInfo("г", "mass", 0.001)),
    (re.compile(r"(?<![\wа-яa-z])(?:млрд)(?![а-я])", re.I), UnitInfo("млрд", "number", 1e9)),
    (re.compile(r"(?<![\wа-яa-z])(?:billion|bn)\b", re.I), UnitInfo("млрд", "number", 1e9)),
    (re.compile(r"(?<![\wа-яa-z])(?:million|mln|mn)\b", re.I), UnitInfo("млн", "number", 1e6)),
    (re.compile(r"(?<![\wа-яa-z])(?:thousand)\b", re.I), UnitInfo("тыс.", "number", 1e3)),
    (re.compile(r"(?<![\wа-яa-z])(?:млн)(?![а-я])", re.I), UnitInfo("млн", "number", 1e6)),
    (re.compile(r"(?<![\wа-яa-z])(?:тыс)(?![а-я])", re.I), UnitInfo("тыс.", "number", 1e3)),
]

_NUMBER_RE = re.compile(
    r"(?<![\w.,])"
    r"(?P<prefix>[-−–]\s*)?"
    r"(?P<open>\()?"
    r"(?P<num>\d{1,7}(?:[ \u00a0\u202f\u2009]\d{3})+(?:[.,]\d+)?|\d+(?:[.,]\d+)?)"
    r"(?P<close>\))?"
    r"(?P<suffix>\s*(?:%|₽|\$|€|руб\.?|рублей|долл\.?|usd|eur|тыс\.?|млн\.?|млрд\.?|"
    r"шт\.?|ед\.?|чел\.?|п\.?\s*п\.?|проц\.?|процент(?:ов|а)?|тонн?|кг|кг\.|кв\.?\s*м|м2|м²))?",
    re.IGNORECASE,
)


def clean_text(value: Any) -> str:
    if value is None:
        return ""
    s = unicodedata.normalize("NFKC", str(value))
    s = s.replace("\x00", " ")
    s = _SPACE_RE.sub(" ", s)
    return s.strip()


def clean_multiline(value: Any) -> str:
    """Нормализует текст, сохраняя разбиение на строки и абзацы."""
    if value is None:
        return ""
    s = unicodedata.normalize("NFKC", str(value))
    s = s.replace("\x00", " ").replace("\f", "\n\r")
    lines = []
    for line in re.split(r"[\r\n]+", s):
        cleaned = _SPACE_RE.sub(" ", line).strip()
        if cleaned:
            lines.append(cleaned)
    return "\n".join(lines)


def normalize_label(value: str) -> str:
    s = clean_text(value).lower().replace("ё", "е")
    s = re.sub(r"^\s*(?:\d+(?:\.\d+)*[.)]?|[IVXLC]+[.)])\s*", "", s)
    s = re.sub(r"[«»\"'`]", "", s)
    s = re.sub(r"\s*[.,;:!?]+\s*$", "", s)
    s = re.sub(r"\s+", " ", s)
    return s.strip()


def canonical_label(value: str) -> str:
    """Нормализованное имя показателя без единиц, периодов и нумерации."""
    s = normalize_label(value)
    # Сначала убираем периоды/годы в скобках и без, затем единицы: иначе
    # «Выручка, млн руб. (2024)» оставляет единицу в названии.
    s = re.sub(r"\((?:\s*(?:19|20)\d{2}\s*(?:г\.?)?\s*)\)", "", s)
    s = re.sub(r"(?<!\d)(?:19|20)\d{2}\s*(?:г(?:ода|оду|од|\.)?)?(?!\d)", "", s)
    for _ in range(2):
        s = re.sub(
            r"\s+(?:за|в|во|на|по|for|in|during|of|the)\s*$", "", s, flags=re.I
        ).strip()
    unit = (
        r"(?:в\s+)?(?:млрд|млн|тыс\.?|billion|million|thousand)?\s*"
        r"(?:руб(?:лей|ля|\.)?|₽|rub|rubles?|долл(?:аров|\.)?|usd|dollars?|"
        r"евро|eur|euros?|%|проц(?:ент(?:ов|а)?|\.)?|шт(?:ук|\.)?|ед\.?|"
        r"чел(?:овек|\.)?|п\.?\s*п\.?)"
    )
    for _ in range(3):
        stripped = re.sub(r"[,\s]*" + unit + r"\s*$", "", s, flags=re.I)
        if stripped == s:
            break
        s = stripped
    s = re.sub(
        r"\s+(?:за|в|во|на|по|for|in|during|of|the)\s*$", "", s, flags=re.I
    )
    s = re.sub(
        r"\s+(?:за|в|во|на|по|for|in|during|of|the)\s*$", "", s, flags=re.I
    )
    s = re.sub(r"\s*[-–—,:;]+\s*$", "", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def tokenize(text: str, keep_stopwords: bool = False) -> list[str]:
    text = clean_text(text).lower().replace("ё", "е")
    words = re.findall(r"[a-zа-я0-9]+(?:[-'][a-zа-я0-9]+)*", text)
    if keep_stopwords:
        return words
    return [w for w in words if w not in STOPWORDS and len(w) > 1]


_STEM_ENDINGS = (
    "иями", "ями", "ами", "ов", "ев", "ей", "ий", "ый", "ая", "ое", "ые", "ых",
    "им", "ым", "ом", "ем", "ах", "ях", "ия", "ию", "ью", "ов", "ам", "ям",
    "а", "я", "ы", "и", "о", "е", "у", "ю", "ь",
)


def stem(word: str) -> str:
    w = word.lower().replace("ё", "е")
    if len(w) <= 4:
        return w
    for ending in _STEM_ENDINGS:
        if w.endswith(ending) and len(w) - len(ending) >= 4:
            return w[: -len(ending)]
    return w[:6] if len(w) > 7 else w


_OCR_DIGIT_MAP = str.maketrans(
    {
        "O": "0", "o": "0", "О": "0", "о": "0",
        "З": "3", "з": "3",
        "|": "1", "l": "1", "I": "1",
        "S": "5", "s": "5",
        "B": "8",
    }
)
_NUMERIC_LIKE_RE = re.compile(r"^[\s\d.,;:()\[\]{}<>+\-−–—/\\|_'\"*№%₽$€A-Za-zА-Яа-яЁё]*$")
_SHORT_UNIT_RE = re.compile(r"^[A-Za-zА-Яа-яЁё.]{0,6}$")


def _group_digits(digits: str) -> str:
    """«11532» → «11 532»: разбивает целую часть по три разряда."""
    parts = []
    while len(digits) > 3:
        parts.insert(0, digits[-3:])
        digits = digits[:-3]
    parts.insert(0, digits)
    return " ".join(p for p in parts if p)


def _repair_dangling_decimal(s: str) -> str | None:
    """Восстанавливает число, у которого OCR/PyMuPDF оторвал дробную часть.

    В ячейках встречаются значения вида ``1153233 ,`` (исходно «11 532,33») и
    ``5600чс , .`` (исходно «56,00 чс.»). Если после числа осталась висячая
    запятая без цифр, считаем две последние цифры дробной частью: в денежных
    документах это копейки, в часах/днях — сотые.
    """
    if not s:
        return None
    candidate = re.sub(r"[\s.]+$", "", s.strip())
    m = re.match(
        r"^(?P<num>\d[\d\s]*?)\s*(?P<unit>[A-Za-zА-Яа-яЁё.]{0,6})?\s*,$",
        candidate,
    )
    if not m:
        return None
    number_part = m.group("num")
    if re.search(r"[.,]\d", number_part) or re.search(r"[.,]", number_part):
        # уже есть десятичная часть с цифрами или другой разделитель — не гадаем
        return None
    digits = re.sub(r"\D", "", number_part)
    unit = clean_text((m.group("unit") or "").strip(" .,"))
    if len(digits) < 3 or (len(digits) < 4 and not unit):
        return None
    if len(digits) == 4 and 1900 <= int(digits) <= 2100:
        # «2026,» — это год, а не 20,26
        return None
    grouped = f"{_group_digits(digits[:-2])},{digits[-2:]}"
    return clean_text(f"{grouped} {unit}")


def repair_numeric_text(raw: Any) -> str:
    """Мягко исправляет типичные OCR-ошибки в числовых фрагментах.

    Не трогает обычный текст: замены применяются, только если в строке есть
    цифры и она почти целиком состоит из числовых символов. Например,
    ``258 923 66/`` → ``258 923 667``, ``4.061 444 118`` → ``4 061 444 118``.
    """
    s = clean_text(raw)
    if not s or not re.search(r"\d", s):
        return s
    # оторванная дробная часть: «1153233 ,» → «11 532,33», «5600чс , .» → «56,00 чс»
    dangling = _repair_dangling_decimal(s)
    if dangling:
        return dangling
    digits = sum(ch.isdigit() for ch in s)
    letters = re.findall(r"[A-Za-zА-Яа-яЁё]", s)
    # строки с большим количеством букв — это подписи, их не трогаем
    if letters and digits < max(2, len(letters) * 2):
        return s
    if not _NUMERIC_LIKE_RE.match(s):
        return s
    s = s.translate(_OCR_DIGIT_MAP)
    # одиночная косая черта в конце числа — почти всегда семёрка
    s = re.sub(r"(?<=\d)[/\\](?=\s*$)", "7", s)
    # мусорные рамки/разделители вокруг числа
    s = re.sub(r"^[\s\[\]{}<>|_*]+", "", s)
    s = re.sub(r"[\s\[\]{}<>|_*]+$", "", s)
    # скобки сохраняем: они означают отрицательное значение
    # пробелы внутри разрядов нормализуем: «4061 444 118» → «4 061 444 118»
    core = s.strip("()+-−– ")
    if re.fullmatch(r"[\d\s.,]+", core):
        groups = re.findall(r"\d+", core)
        if len(groups) >= 2 and all(len(g) <= 3 for g in groups[1:]) and len(groups[0]) <= 7:
            joined = "".join(groups)
            if len(joined) >= 7:
                tail = ""
                # десятичная часть после последней запятой/точки с 1–2 цифрами
                m = re.search(r"[.,](\d{1,2})$", core)
                if m:
                    tail = core[m.start():]
                    joined = joined[: -len(m.group(1))]
                parts = []
                while len(joined) > 3:
                    parts.insert(0, joined[-3:])
                    joined = joined[:-3]
                parts.insert(0, joined)
                grouped = " ".join(p for p in parts if p) + tail
                s = s.replace(core, grouped)
    return s


def parse_number(raw: str) -> float | None:
    """Разбирает число в русском/английском формате."""
    if raw is None:
        return None
    s = repair_numeric_text(raw)
    if not s:
        return None
    negative = bool(re.match(r"^\s*[-−–]", s)) or (s.strip().startswith("(") and s.strip().endswith(")"))
    s = re.sub(r"[^\d.,\-−–]", "", s).replace("−", "-").replace("–", "-")
    s = s.strip("-")
    if not s or not re.search(r"\d", s):
        return None
    if "," in s and "." in s:
        if s.rfind(",") > s.rfind("."):
            s = s.replace(".", "").replace(",", ".")
        else:
            s = s.replace(",", "")
    elif "," in s:
        parts = s.split(",")
        if len(parts) > 2 and all(len(p) == 3 for p in parts[1:]):
            s = "".join(parts)
        elif len(parts) == 2 and parts[0] in {"0", ""}:
            # «0,123» и «,123» — это дробь, а не разряды
            s = f"{parts[0] or '0'}.{parts[1]}"
        elif len(parts[-1]) == 3 and len(parts) > 1 and len(parts[0]) <= 3:
            s = s.replace(",", "")
        else:
            s = s.replace(",", ".")
    elif "." in s:
        parts = s.split(".")
        if len(parts) > 2:
            if all(len(p) == 3 for p in parts[1:]):
                # «1.234.567» — разделители разрядов
                s = "".join(parts)
            else:
                s = "".join(parts[:-1]) + "." + parts[-1]
        elif len(parts) == 2 and len(parts[1]) == 3 and len(parts[0]) <= 3 and len(s) <= 7:
            # «1.234» в финансовых документах чаще означает 1234
            s = s.replace(".", "")
        elif len(parts) == 2 and len(parts[1]) > 3 and len(parts[1]) % 3 == 0:
            # OCR потерял пробелы: «4.061444118» → 4061444118
            s = s.replace(".", "")
    try:
        value = float(s)
    except ValueError:
        return None
    return -value if negative else value


def detect_unit(text: str) -> UnitInfo | None:
    s = clean_text(text)
    if not s:
        return None
    for pattern, info in UNIT_RULES:
        if pattern.search(s):
            return info
    return None


def parse_value(raw: str) -> tuple[float | None, UnitInfo | None, str]:
    """Возвращает (число, единица, исходный числовой фрагмент)."""
    s = repair_numeric_text(clean_text(raw))
    m = _NUMBER_RE.search(s)
    if not m:
        return None, detect_unit(s), s
    value = parse_number(m.group("num"))
    if value is None:
        return None, detect_unit(s), m.group(0)
    if m.group("prefix"):
        value = -abs(value)
    if m.group("open") and m.group("close"):
        value = -abs(value)
    unit_text = " ".join(x for x in (m.group("suffix") or "", s[m.end(): m.end() + 24]) if x)
    unit = detect_unit(unit_text) or detect_unit(s[: m.start()])
    return value, unit, m.group(0).strip()


def value_with_unit(raw: str) -> dict[str, Any] | None:
    value, unit, fragment = parse_value(raw)
    if value is None:
        return None
    unit = unit or UnitInfo("", "", 1.0)
    return {
        "value": value,
        "raw_value": fragment,
        "unit": unit.display,
        "dimension": unit.dimension,
        "scale": unit.scale,
        "currency": unit.currency,
        "normalized_value": value * unit.scale,
    }


def extract_years(text: str) -> list[str]:
    years = []
    for m in _YEAR_RE.finditer(text or ""):
        y = m.group(1)
        if y not in years:
            years.append(y)
    return years


def extract_period(text: str, default: str = "") -> str:
    """Извлекает канонический период: 2024, 2024-Q1, 2024-08, 31.12.2024."""
    s = clean_text(text)
    q = _QUARTER_RE.search(s)
    if q:
        quarter = q.group("q") or q.group("q2")
        return f"{q.group('y')}-Q{quarter}"
    # Полная дата важнее, чем число-месяц внутри неё
    d = _DATE_RE.search(s)
    if d:
        return f"{int(d.group(1)):02d}.{int(d.group(2)):02d}.{d.group(3)}"
    m = re.search(r"(?<!\d)((?:19|20)\d{2})[./-](0?[1-9]|1[0-2])(?!\d)", s)
    if m:
        return f"{m.group(1)}-{int(m.group(2)):02d}"
    m = re.search(r"(?<!\d)(0?[1-9]|1[0-2])[./-]((?:19|20)\d{2})(?!\d)", s)
    if m:
        return f"{m.group(2)}-{int(m.group(1)):02d}"
    month_match = _MONTH_NAME_RE.search(s)
    if month_match:
        month = _month_number(month_match.group(1))
        if month:
            year_match = _YEAR_RE.search(s[month_match.end(): month_match.end() + 14]) or _YEAR_RE.search(
                s[max(0, month_match.start() - 10): month_match.start()]
            )
            if year_match:
                return f"{year_match.group(1)}-{month:02d}"
    years = extract_years(s)
    if years:
        return years[0]
    return default


def guess_document_period(text: str, filename: str = "") -> str:
    # Месяц + год в заголовке («РАСЧЕТНЫЙ ЛИСТОК ЗА АВГУСТ 2026») уточняют период
    # до 2026-08; для годовых отчётов остаётся только год.
    month_re = re.compile(r"^(?:19|20)\d{2}-(?:0[1-9]|1[0-2])$")
    for source in (filename, text[:600]):
        if not source:
            continue
        period = extract_period(source)
        if month_re.match(period):
            return period
    years = extract_years(filename)
    if years:
        return years[0]
    years = extract_years(text[:6000])
    if not years:
        return ""
    from collections import Counter

    return Counter(years).most_common(1)[0][0]


def format_number(value: float | int | None, digits: int = 2) -> str:
    if value is None:
        return "—"
    try:
        v = float(value)
    except (TypeError, ValueError):
        return str(value)
    if not math.isfinite(v):
        return "—"
    if abs(v) < 1e-12:
        return "0"
    if abs(v - round(v)) < 1e-9:
        return f"{int(round(v)):,}".replace(",", " ")
    # не показываем ноль вместо маленького ненулевого значения
    if abs(v) < 1:
        while digits < 6 and abs(v) < 0.5 * 10 ** (-digits):
            digits += 1
    s = f"{v:,.{digits}f}".replace(",", " ").replace(".", ",")
    return s.rstrip("0").rstrip(",")


def format_percent(value: float | None, digits: int = 1) -> str:
    if value is None:
        return "—"
    try:
        v = float(value)
    except (TypeError, ValueError):
        return str(value)
    if not math.isfinite(v):
        return "—"
    if v and abs(v) < 0.5 * 10 ** (-digits):
        while digits < 6 and abs(v) < 0.5 * 10 ** (-digits):
            digits += 1
    body = f"{abs(v):.{digits}f}".replace(".", ",")
    if not v:
        return f"{body}%"
    sign = "-" if v < 0 else "+"
    return f"{sign}{body}%"


def short_snippet(text: str, limit: int = 320) -> str:
    s = clean_text(text)
    if len(s) <= limit:
        return s
    return s[: limit - 1].rsplit(" ", 1)[0] + "…"


def snippet_around(text: str, start: int, end: int, radius: int = 160) -> str:
    s = clean_text(text)
    left = max(0, start - radius)
    right = min(len(s), end + radius)
    prefix = "…" if left > 0 else ""
    suffix = "…" if right < len(s) else ""
    return prefix + s[left:right].strip() + suffix


def sha256_file(path: Path | str, block_size: int = 1024 * 1024) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(block_size):
            h.update(chunk)
    return h.hexdigest()


def sanitize_filename(name: str) -> str:
    name = Path(name or "document.pdf").name
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name)
    name = re.sub(r"\s+", " ", name).strip(" .")
    if not name.lower().endswith(".pdf"):
        name += ".pdf"
    return name[:180]


def mask_key(key: str) -> str:
    if not key:
        return ""
    if len(key) <= 8:
        return "••••"
    return key[:4] + "••••••" + key[-4:]


def json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [json_safe(v) for v in value]
    if isinstance(value, (date,)):
        return value.isoformat()
    if isinstance(value, float):
        if value != value or value in (float("inf"), float("-inf")):
            return None
    try:
        json.dumps(value)
        return value
    except TypeError:
        return str(value)


def pct_change(old: float, new: float) -> float | None:
    if old is None or new is None:
        return None
    if abs(old) < 1e-12:
        return None
    return (new - old) / abs(old) * 100.0


def iso_now() -> str:
    from datetime import datetime

    return datetime.now().strftime("%d.%m.%Y %H:%M")
