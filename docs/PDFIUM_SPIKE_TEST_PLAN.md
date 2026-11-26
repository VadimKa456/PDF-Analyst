# PDFium spike: comparison test plan

## Scope

This is an isolated engineering experiment. It does not replace the production
PyMuPDF integration and must not be merged into the application until the
acceptance checks below have been reviewed.

## Test corpus

The Windows CI job generates the repository's synthetic PDF corpus using
`samples/generate_samples.py`. It includes Russian financial statements,
an English financial statement, an audit variant, and a scanned-image PDF.

## Checks

- PDFium opens the same documents and reports the same page count as PyMuPDF.
- Page geometry is positive and available for every page.
- On text-bearing pages, normalized token precision and recall against the
  PyMuPDF baseline are each at least 0.90.
- On the scanned-only fixture, neither engine should invent an extractable
  text layer.
- pdfplumber must recover key financial table labels and period headers from
  the Russian and English fixtures.

## Known limits

- These checks cover only synthetic fixtures, not a representative customer
  corpus or malformed/password-protected PDFs.
- Text similarity does not prove identical reading order, font metadata,
  bounding boxes, or table-cell geometry.
- OCR accuracy, multi-column layouts, rotated pages, merged/borderless tables,
  large-file memory use, and Windows installer packaging remain unvalidated.
- PDFium calls are serialized by the experimental adapter because PDFium is
  not thread-safe across concurrent calls.

## Decision gate

Do not remove PyMuPDF from production based only on these smoke tests. First
run the candidate stack against a curated, permission-cleared real-world
regression corpus and compare extracted metrics, provenance, table structures,
OCR results, and rendering output.
