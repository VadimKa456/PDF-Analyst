"""Reproducible, non-gating benchmark for the experimental PDFium adapter.

Run from the repository root after installing requirements.txt and
requirements-pdf-engine-spike.txt:
    python scripts/benchmark_pdf_engines.py --pages 200 --repeats 3

This measures sequential text extraction only. It is not an OCR, table-quality,
or peak-memory benchmark and must not be used alone to select a production
PDF engine.
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
import tempfile
import time
from pathlib import Path

from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

import fitz  # noqa: E402
import pypdfium2  # noqa: E402
from app.services.pdfium_spike import inspect_pdf  # noqa: E402


def build_corpus(path: Path, page_count: int) -> None:
    pdf = canvas.Canvas(str(path), pagesize=A4, pageCompression=1)
    width, height = A4
    for page_number in range(1, page_count + 1):
        pdf.setTitle("PDF engine benchmark corpus")
        pdf.setFont("Helvetica-Bold", 13)
        pdf.drawString(40, height - 42, f"Financial report — page {page_number}")
        pdf.setFont("Helvetica", 8)
        y = height - 65
        for row in range(1, 46):
            pdf.drawString(
                40,
                y,
                (
                    f"Company {page_number % 7 + 1} | FY{2020 + row % 7} | "
                    f"Revenue {page_number * row * 137:,} | "
                    f"Net profit {page_number * row * 19:,} | "
                    "Consolidated financial indicator"
                ),
            )
            y -= 15
        pdf.showPage()
    pdf.save()


def benchmark_pdfium(path: Path) -> tuple[int, int]:
    snapshots = inspect_pdf(path)
    return len(snapshots), sum(len(page.text) for page in snapshots)


def benchmark_pymupdf(path: Path) -> tuple[int, int]:
    characters = 0
    with fitz.open(path) as document:
        count = len(document)
        for page in document:
            characters += len(page.get_text("text") or "")
    return count, characters


def measure(engine_name: str, function, path: Path, repeats: int) -> dict:
    durations: list[float] = []
    expected_pages = None
    expected_chars = None
    for _ in range(repeats):
        started = time.perf_counter()
        pages, characters = function(path)
        durations.append(time.perf_counter() - started)
        if expected_pages is None:
            expected_pages, expected_chars = pages, characters
        elif pages != expected_pages:
            raise RuntimeError(f"{engine_name} returned inconsistent page counts")
    median_seconds = statistics.median(durations)
    return {
        "engine": engine_name,
        "pages": expected_pages,
        "characters": expected_chars,
        "median_seconds": round(median_seconds, 4),
        "pages_per_second": round(expected_pages / median_seconds, 2),
        "runs_seconds": [round(value, 4) for value in durations],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pages", type=int, default=200)
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.pages < 1 or args.repeats < 1:
        parser.error("--pages and --repeats must be positive integers")

    with tempfile.TemporaryDirectory(prefix="pdf-engine-benchmark-") as folder:
        pdf_path = Path(folder) / "benchmark.pdf"
        build_corpus(pdf_path, args.pages)
        results = {
            "corpus": {
                "pages_requested": args.pages,
                "file_size_bytes": pdf_path.stat().st_size,
                "repeats": args.repeats,
            },
            "versions": {
                "pypdfium2": getattr(pypdfium2, "__version__", "unknown"),
                "pymupdf": getattr(fitz, "VersionBind", "unknown"),
            },
            "results": [
                measure("PDFium", benchmark_pdfium, pdf_path, args.repeats),
                measure("PyMuPDF", benchmark_pymupdf, pdf_path, args.repeats),
            ],
            "limitations": [
                "Synthetic text-only corpus; not representative of all customer PDFs.",
                "Sequential text extraction only; excludes rendering, OCR, and table parsing.",
                "No peak native-memory measurement is collected.",
                "Results depend on hardware, OS, and installed library versions.",
            ],
        }
        output = json.dumps(results, ensure_ascii=False, indent=2)
        print(output)
        if args.output:
            args.output.write_text(output + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
