"""Compare PDFium text extraction with the current PyMuPDF baseline.

The generated corpus is synthetic and deterministic. These tests deliberately
compare extracted content rather than requiring byte-for-byte identical text
layout, because PDF engines may normalize whitespace and line endings.
"""
from __future__ import annotations

import re
from collections import Counter
from pathlib import Path

import pdfplumber
import pymupdf
import pytest

from app.services.pdfium_spike import inspect_pdf

ROOT = Path(__file__).resolve().parents[2]
CORPUS = ROOT / "samples" / "pdfs"


def _tokens(text: str) -> Counter[str]:
    return Counter(re.findall(r"[^\W_]+", text.casefold(), flags=re.UNICODE))


@pytest.fixture(scope="module")
def corpus_files() -> list[Path]:
    files = sorted(CORPUS.glob("*.pdf"))
    if not files:
        pytest.skip("Generated PDF corpus is missing")
    return files


@pytest.mark.parametrize("filename", [
    "alpha_2022.pdf", "alpha_2023_audit.pdf", "alpha_2024.pdf",
    "alpha_2025.pdf", "beta_2025_english.pdf",
    "alpha_2024_scanned.pdf",
])
def test_pdfium_matches_pymupdf_text_baseline(filename: str) -> None:
    path = CORPUS / filename
    assert path.is_file(), f"Missing generated corpus document: {path}"

    with pymupdf.open(path) as reference:
        reference_pages = [page.get_text("text") for page in reference]

    candidate_pages = inspect_pdf(path)

    assert len(candidate_pages) == len(reference_pages)
    for index, (reference_text, candidate) in enumerate(
        zip(reference_pages, candidate_pages), start=1
    ):
        assert candidate.page_number == index
        assert candidate.width > 0 and candidate.height > 0

        reference_tokens = _tokens(reference_text)
        candidate_tokens = _tokens(candidate.text)
        if not reference_tokens:
            assert not candidate_tokens, f"Unexpected text on blank/scanned page {index}"
            continue

        common = sum((reference_tokens & candidate_tokens).values())
        recall = common / sum(reference_tokens.values())
        precision = common / max(1, sum(candidate_tokens.values()))
        assert recall >= 0.90, (
            f"{filename}, page {index}: PDFium token recall {recall:.3f} < 0.90"
        )
        assert precision >= 0.90, (
            f"{filename}, page {index}: PDFium token precision {precision:.3f} < 0.90"
        )


@pytest.mark.parametrize(
    ("filename", "required_terms"),
    [
        ("alpha_2024.pdf", ("Выручка", "Чистая прибыль", "2024", "2023")),
        ("beta_2025_english.pdf", ("Revenue", "Net profit", "2025", "2024")),
    ],
)
def test_pdfplumber_can_recover_financial_tables(
    filename: str, required_terms: tuple[str, ...]
) -> None:
    path = CORPUS / filename
    assert path.is_file(), f"Missing generated corpus document: {path}"

    with pdfplumber.open(path) as document:
        extracted = [
            table
            for page in document.pages
            for table in (page.extract_tables() or [])
        ]

    flattened = " ".join(
        str(cell)
        for table in extracted
        for row in table
        for cell in row
        if cell is not None
    )
    for term in required_terms:
        assert term.casefold() in flattened.casefold(), (
            f"{filename}: pdfplumber did not recover expected table term {term!r}"
        )
