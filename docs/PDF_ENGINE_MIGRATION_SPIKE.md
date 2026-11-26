# PDF engine migration spike — implementation map

**Status:** design checkpoint only; no production code changed  
**Target branch:** `commercial-readiness/license-audit`  
**Baseline:** `main`, PDF Analyst 1.1.0

## Why an adapter is required

A repository-wide scan of `backend/app/services/pdf_processor.py` found direct PyMuPDF calls in the following areas:

| Current operation | Current API | Candidate implementation |
|---|---|---|
| Open PDF / page count | `pymupdf.open`, `doc.page_count` | `pypdfium2.PdfDocument`, `len(doc)` |
| First-page text for period detection | `page.get_text("text")` | `pdfplumber.Page.extract_text()` or PDFium textpage |
| Page text and heading detection | `page.get_text("dict")` with spans, font sizes, bold/font names, bbox | `pdfplumber.Page.chars` / `extract_words` grouped by y/x and font metadata |
| Page image detection for OCR | `page.get_images(full=True)` | pdfplumber page image objects plus extracted-text length; verify on mixed/vector pages |
| Rasterization for OCR | `page.get_pixmap(matrix=..., alpha=False)` | `pypdfium2` page `.render(scale=dpi/72)`, convert bitmap to PIL |
| OCR page width / scale | `page.rect.width` | `pypdfium2` `.get_size()` (points) |
| OCR table geometry | `page.rect.width` | same PDFium page size; retain Tesseract word coordinate scaling |
| Digital table detection | `page.find_tables()`, `table.cells`, `table.extract()` | `pdfplumber.Page.find_tables()` / `extract_tables()`; preserve current post-processing and cell cleanup |
| Rebuild table cell text from positioned words | `page.get_text("words")` and PyMuPDF table bboxes | `pdfplumber.Page.extract_words()` plus pdfplumber table cell bboxes |
| Page number / dimensions | `page.number`, `page.rect.width/height` | explicit 0-based loop index + PDFium `.get_size()` |
| Preview PNG | `page.get_pixmap()` and `.tobytes("png")` | PDFium render + PIL PNG bytes |
| Password detection | `doc.needs_pass`, `doc.authenticate("")` | PDFium password handling; explicitly test empty and non-empty passwords and error mapping |
| Resource cleanup | `doc.close()` | PDFium document/page close semantics; ensure context managers/finally blocks |

## Proposed internal boundary

Create a small internal page/document adapter rather than spreading library-specific calls throughout the 1,900-line processor.

Suggested interface (illustrative, not committed code):

- `open_document(path) -> PdfDocumentAdapter`
- `page_count`
- `page(index) -> PdfPageAdapter`
- `page.get_text_and_headings() -> (text, headings)`
- `page.get_size() -> (width_pt, height_pt)`
- `page.has_embedded_images()`
- `page.render(dpi) -> PIL.Image`
- `page.extract_tables() -> list[ExtractedTable]`
- `page.extract_words() -> positioned word records`
- `close()`

The processor's domain logic should continue to consume its existing `PageData`, `ExtractedTable`, and `ExtractedMetric` dataclasses. This reduces the size of the migration and keeps financial metric parsing, normalization, deduplication, provenance and reporting independent of the PDF engine.

## Important technical cautions

1. PDFium and pdfplumber coordinate systems may differ in origin/orientation. Normalize coordinates in the adapter and test rotated pages.
2. PyMuPDF `find_tables()` is not equivalent to pdfplumber table extraction. Borderless tables, merged cells and sparse financial tables are the largest regression risks.
3. pdfplumber text ordering/font metadata may differ from PyMuPDF's span order. Preserve heading detection only after golden-corpus comparison.
4. Image detection cannot rely only on `page.images`: vector-only scans, background images and mixed text/image pages need explicit tests.
5. PDFium rendering should use the same DPI and white background as the current OCR pipeline to avoid OCR confidence changes.
6. pypdfium2 bundles PDFium binaries in many wheels. Include the exact wheel's PDFium and third-party license files in the packaged application.
7. Validate PDF password support, corrupted-file exceptions, file handles and cleanup on Windows.
8. Use a fixed pypdfium2 version and wheel hash in the eventual lockfile; do not resolve latest on a release build.

## Proof-of-concept sequence

1. Add the adapter in an isolated spike branch, leaving current PyMuPDF implementation available behind the test harness.
2. Select a small, representative set of existing PDFs (born-digital text, financial tables, scanned Russian/English, mixed pages, rotated pages, multi-column layout, malformed/password protected).
3. Run both engines over identical inputs and serialize comparable outputs.
4. Compare:
   - normalized page text and heading order;
   - table count, header names, row/cell values;
   - extracted metrics, units, periods and page numbers;
   - OCR text, confidence and numeric accuracy;
   - preview dimensions and image output;
   - runtime and peak memory.
5. Expand to the complete existing regression corpus only if the first set passes.
6. Do not switch the default engine until all critical cases pass and the Windows desktop build is verified.

## Decision at this checkpoint

**Recommended candidate:** pdfplumber/pdfminer.six for text and tables + pypdfium2 for PDFium rendering + existing pytesseract/Tesseract OCR path.

**Not approved yet:** removing PyMuPDF from production dependencies. The candidate must first pass a real regression corpus. Keep the current production code and public `main` branch unchanged until then.

## Official technical references

- pypdfium2 API and examples: https://pypdfium2-team.github.io/pypdfium2/readme.html
- pypdfium2 licensing and bundled dependency notices: https://pypi.org/project/pypdfium2/
- pdfplumber: https://pypi.org/project/pdfplumber/
- pdfminer.six: https://pypi.org/project/pdfminer.six/
