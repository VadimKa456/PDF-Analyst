"""Покрытие извлечения: разбор чисел страницы и служебных номеров."""
from __future__ import annotations

from app.api.documents import _COVERAGE_NUM_RE, _classify_number_token


def _tokens(text: str) -> list[str]:
    return [m.group(0) for m in _COVERAGE_NUM_RE.finditer(text)]


def test_coverage_tokens_do_not_merge_adjacent_cells() -> None:
    tokens = _tokens("2110 4061 444 118 4758 711 459")
    assert tokens == ["2110", "4061", "444 118", "4758", "711 459"]


def test_coverage_tokens_keep_dates_and_decimals_whole() -> None:
    assert _tokens("на 31.12.2020 значение 46,71 %") == ["31.12.2020", "46,71"]
    assert _tokens("4.061.444 и 1 234,5") == ["4.061.444", "1 234,5"]


def test_coverage_tokens_split_ocr_broken_thousands() -> None:
    # OCR потерял пробел после первой группы — фрагменты всё равно находятся
    assert _tokens("4061 444 118") == ["4061", "444 118"]


def test_classify_service_numbers() -> None:
    assert _classify_number_token("2110", "2110", "", False, False) == "code"
    assert _classify_number_token("42", "42", "", False, False) == "code"
    assert _classify_number_token("1136050003", "1136050003", "ИНН", False, False) == "requisite"
    assert _classify_number_token("2020", "2020", "", False, False) == "year"
    assert _classify_number_token("31.12.2020", "31122020", "", False, True) == "date"
    assert _classify_number_token("4 061 444 118", "4061444118", "", True, False) == "value"
    assert _classify_number_token("999 999", "999999", "", False, False) == "value"
