# PDF engine benchmark

The PDFium adapter remains experimental and isolated from the production
PyMuPDF pipeline. The benchmark below is a bounded performance observation,
not a pass/fail gate and not a substitute for a permission-cleared real-world
regression corpus.

## Run on Windows

From the repository root, using the project's Python 3.12 virtual environment:

```powershell
python -m pip install -r requirements.txt
python -m pip install -r requirements-pdf-engine-spike.txt
python scripts/benchmark_pdf_engines.py --pages 200 --repeats 3 --output benchmark-results.json
```

The script generates a temporary 200-page text-heavy PDF, runs sequential text
extraction through the experimental PDFium adapter and PyMuPDF, and reports
median elapsed time, pages per second, extracted character count, file size,
and library versions. Increase `--pages` to test larger documents.

## Interpretation

- Run on the same machine, with the same power mode and no heavy background
  workloads; compare both engines within the same run.
- Repeat on the target Windows 11 computer before making packaging decisions.
- The script intentionally has no machine-dependent performance threshold.
- It does not measure peak native memory, OCR, rendering, table extraction,
  malformed PDFs, or password-protected documents.
- Faster text extraction on this synthetic corpus does not establish higher
  extraction accuracy or justify replacing PyMuPDF in production.

Record the machine CPU/RAM, Windows version, Python version, PDF file size,
and JSON output alongside any benchmark report.
