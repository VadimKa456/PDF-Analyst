"""Тесты разбора чисел, единиц, периодов и форматирования."""
from __future__ import annotations

import math

import pytest

from app.utils import (
    canonical_label,
    detect_unit,
    extract_period,
    extract_years,
    format_number,
    format_percent,
    mask_key,
    normalize_label,
    parse_number,
    parse_value,
    pct_change,
    repair_numeric_text,
    short_snippet,
    stem,
    tokenize,
)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("1 234,56", 1234.56),
        ("1,234.56", 1234.56),
        ("1 234 567", 1234567.0),
        ("1.234", 1234.0),
        ("12,5", 12.5),
        ("(1 200)", -1200.0),
        ("-5,5", -5.5),
        ("—", None),
        ("", None),
    ],
)
def test_parse_number(raw: str, expected: float | None) -> None:
    assert parse_number(raw) == expected


def test_parse_number_rounding_is_exact() -> None:
    assert parse_number("1 191 932") == 1_191_932
    assert parse_number("4 484 297,25") == pytest.approx(4_484_297.25)


@pytest.mark.parametrize(
    ("text", "dimension", "scale", "currency"),
    [
        ("2024, тыс. руб.", "money", 1_000.0, "RUB"),
        ("млн руб.", "money", 1_000_000.0, "RUB"),
        ("млрд ₽", "money", 1_000_000_000.0, "RUB"),
        ("thousand RUB", "money", 1_000.0, "RUB"),
        ("million USD", "money", 1_000_000.0, "USD"),
        ("billion EUR", "money", 1_000_000_000.0, "EUR"),
        ("9,6 %", "percent", 1.0, ""),
        ("1 430 чел.", "people", 1.0, ""),
        ("1 200 шт.", "count", 1.0, ""),
        ("12 тонн", "mass", 1_000.0, ""),
    ],
)
def test_detect_unit(text: str, dimension: str, scale: float, currency: str) -> None:
    unit = detect_unit(text)
    assert unit is not None, text
    assert unit.dimension == dimension
    assert unit.scale == scale
    assert unit.currency == currency


def test_parse_value_keeps_sign_and_unit() -> None:
    value, unit, fragment = parse_value("(1 200) руб.")
    assert value == -1200
    assert unit is not None and unit.currency == "RUB"
    assert "1 200" in fragment

    value, unit, _ = parse_value("-5,5 %")
    assert value == -5.5
    assert unit is not None and unit.dimension == "percent"


@pytest.mark.parametrize(
    ("text", "period"),
    [
        ("31.12.2024", "31.12.2024"),
        ("1 квартал 2024", "2024-Q1"),
        ("Q2 2024", "2024-Q2"),
        ("за 2023 год", "2023"),
        ("авг 2026", "2026-08"),
        ("август 2026", "2026-08"),
        ("Aug 2026", "2026-08"),
        ("2026-08", "2026-08"),
        ("08.2026", "2026-08"),
        ("без периода", ""),
    ],
)
def test_extract_period(text: str, period: str) -> None:
    assert extract_period(text) == period


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("4.061 444 118", 4_061_444_118),
        ("4061 444 118", 4_061_444_118),
        ("258 923 66/", 258_923_667),
        ("2101057 105", 2_101_057_105),
        ("11436 458", 11_436_458),
        ("(2 488 200 192)", -2_488_200_192),
    ],
)
def test_parse_number_repairs_ocr_artifacts(raw: str, expected: float) -> None:
    assert parse_number(raw) == expected


def test_repair_numeric_text_keeps_labels_intact() -> None:
    assert repair_numeric_text("4.061 444 118") == "4 061 444 118"
    assert repair_numeric_text("258 923 66/") == "258 923 667"
    # подписи с буквами не должны искажаться
    assert repair_numeric_text("предоставление имущества в аренду") == (
        "предоставление имущества в аренду"
    )
    assert repair_numeric_text("Проценты к получению") == "Проценты к получению"


def test_repair_numeric_text_keeps_decimal_comma() -> None:
    assert repair_numeric_text("987608,84") == "987 608,84"
    assert parse_number("987608,84") == pytest.approx(987_608.84)
    assert repair_numeric_text("11532,33") == "11 532,33"


def test_repair_numeric_text_restores_dangling_decimal() -> None:
    # PyMuPDF может оторвать дробную часть: «11 532,33» → «1153233 ,»
    assert repair_numeric_text("1153233 ,") == "11 532,33"
    assert parse_number("1153233 ,") == pytest.approx(11_532.33)
    assert parse_number("1811100 ,") == pytest.approx(18_111.00)
    assert parse_number("5600чс , .") == pytest.approx(56.0)
    assert parse_number("700дн , .") == pytest.approx(7.0)
    assert parse_value("1153233 ,")[0] == pytest.approx(11_532.33)
    # год с точкой не должен превращаться в дробь
    assert parse_number("2026 год.") == 2026


def test_parse_number_keeps_leading_zero_fraction() -> None:
    assert parse_number("0,123") == pytest.approx(0.123)
    assert parse_number(",123") == pytest.approx(0.123)
    assert parse_number("0,5") == pytest.approx(0.5)


@pytest.mark.parametrize(
    "text",
    [
        "предоставление имущества в аренду",
        "Проценты к получению",
        "продажа газа",
        "предоставление услуг по организации транспортировки газа",
    ],
)
def test_detect_unit_ignores_words_containing_unit_like_fragments(text: str) -> None:
    assert detect_unit(text) is None


def test_detect_unit_still_finds_real_units() -> None:
    people = detect_unit("5 чел.")
    assert people is not None and people.dimension == "people"
    percent = detect_unit("100 %")
    assert percent is not None and percent.dimension == "percent"
    money = detect_unit("тыс. руб.")
    assert money is not None and money.scale == 1_000.0


def test_extract_years_order_and_uniqueness() -> None:
    assert extract_years("2024 и 2023, снова 2024") == ["2024", "2023"]


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("Выручка, млн руб. (2024)", "выручка"),
        ("Revenue 2025, thousand RUB", "revenue"),
        ("Чистая прибыль за 2024 г.", "чистая прибыль"),
        ("Total assets (2023), USD", "total assets"),
        ("EBITDA, % за 2024", "ebitda"),
        ("Совокупные активы", "совокупные активы"),
    ],
)
def test_canonical_label_strips_units_and_periods(raw: str, expected: str) -> None:
    assert canonical_label(raw) == expected


def test_normalize_label_handles_numbering_and_quotes() -> None:
    assert normalize_label('1. «Выручка»  за 2024 год...') == "выручка за 2024 год"


def test_pct_change_and_zero_base() -> None:
    assert pct_change(100, 120) == pytest.approx(20.0)
    assert pct_change(-100, -50) == pytest.approx(50.0)
    assert pct_change(0, 5) is None


def test_formatting_is_russian_style() -> None:
    assert format_number(1_661_152) == "1 661 152"
    assert format_number(1234.567) == "1 234,57"
    assert format_number(None) == "—"
    assert format_percent(12.34) == "+12,3%"
    assert format_percent(None) == "—"


def test_formatting_keeps_small_values_visible() -> None:
    assert format_number(0.004) == "0,004"
    assert format_number(-0.0001) == "-0,0001"
    assert format_number(0) == "0"
    assert format_percent(0) == "0,0%"
    assert format_percent(-0.04) == "-0,04%"
    assert format_percent(0.004) == "+0,004%"


def test_mask_key_never_exposes_full_secret() -> None:
    masked = mask_key("sk-1234567890abcdef")
    assert masked.startswith("sk-1")
    assert masked.endswith("cdef")
    assert "1234567890ab" not in masked
    assert mask_key("short") == "••••"
    assert mask_key("") == ""


def test_short_snippet_truncates_on_word_boundary() -> None:
    text = "Выручка компании выросла за отчётный период благодаря росту продаж"
    snippet = short_snippet(text, 25)
    assert len(snippet) <= 26
    assert snippet.endswith("…")


def test_stem_matches_word_forms() -> None:
    assert stem("прибыль") == stem("прибыли")
    assert stem("активы") == stem("активов")
    tokens = tokenize("Покажи выручку и чистую прибыль за 2024 год")
    assert "выручку" in tokens
    assert "2024" in tokens
    assert "покажи" not in tokens
