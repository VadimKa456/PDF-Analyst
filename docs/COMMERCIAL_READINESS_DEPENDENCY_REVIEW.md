# Commercial readiness — dependency and installer review

**Status:** preliminary engineering/licensing inventory; not legal advice  
**Reviewed:** 2026-11-26  
**Repository baseline:** `main`, PDF Analyst 1.1.0  
**Working branch:** `commercial-readiness/license-audit`

## Executive result

The first review identified PyMuPDF as a distribution blocker requiring a deliberate AGPL-compliance or commercial-license decision. A second pass found a separate commercial-use consideration in the Windows installer toolchain: Inno Setup now requests commercial licenses from commercial users. Its official purchase FAQ says deploying an installer built by Inno Setup does not itself count as using Inno Setup; compiling it does.

No dependency or application code was changed in this review. This document records a candidate replacement architecture and the remaining checks.

## Repository facts checked

### Python dependency manifest

The root `requirements.txt` uses version ranges rather than a fully pinned, hashed lockfile. The reviewed direct requirements are:

- API/runtime: FastAPI, Uvicorn, Pydantic, pydantic-settings, SQLAlchemy, python-multipart, httpx.
- PDF/OCR: PyMuPDF, pdfplumber, pytesseract, Pillow, opencv-python-headless.
- Data/reporting: pandas, numpy, openpyxl, reportlab, matplotlib.
- Matching/tests: rapidfuzz, pytest.

The separate `requirements-desktop.txt` contains PyInstaller and pywebview, also as version ranges.

No `uv.lock`, `poetry.lock`, `Pipfile.lock`, or `pyproject.toml` was present at the repository root in this review. Therefore the exact resolved Python dependency graph for release v1.1.0 cannot be reconstructed from the manifests alone.

### Frontend

The frontend has a committed npm lockfile (lockfile v3). Its package metadata records versions, integrity hashes and license fields for the npm dependency graph. This is a useful foundation for an automated license report, but the generated production bundle and all asset/font/icon notices still need inspection.

### Windows installer

The checked-in `installer.iss` creates a Windows x64 installer and copies the PyInstaller output. It downloads/installs Microsoft WebView2 Runtime and Visual C++ Redistributable at installation time if missing. It does not bundle Tesseract: it opens the UB Mannheim Tesseract download page and asks the user to install Russian/English language data.

The installer script uses Inno Setup 6. The exact compiler version used to create the published v1.1.0 installer was not established from the repository files.

## Preliminary license inventory

This is a triage list, not a complete SBOM. Transitive dependencies, exact versions, wheel-specific native binaries, data files and notices must be checked against the actual resolved build.

| Component | Declared/official licensing information | Commercial-readiness note |
|---|---|---|
| Project source | MIT in repository `LICENSE` | Applies to project-owned code, not automatically to bundled dependencies. |
| PyMuPDF / MuPDF | AGPLv3 or Artifex commercial license | **High-priority blocker** for the paid desktop distribution until selected license route and obligations are documented. |
| pdfplumber | MIT on current PyPI metadata | Candidate to retain for layout and table extraction; check its pinned release and transitive pdfminer.six metadata. |
| pdfminer.six | MIT | Candidate for text/layout extraction; preserve required notices. |
| pypdfium2 | Apache-2.0 / BSD-3-Clause for binding; PDFium is BSD-style; wheel may include additional dependency licenses | Strong candidate for rendering and text primitives. Must ship the license files/notices for the exact Windows wheel and inspect any platform-specific linked runtime. |
| pypdf | BSD-3-Clause | Permissive general PDF operations; not a direct replacement for PyMuPDF's geometry, table finding and rendering APIs. |
| pytesseract | Apache-2.0 | Python wrapper; separate from the OCR engine. |
| Tesseract OCR | Apache-2.0 | Current installer does not bundle it; if bundling later, include engine and trained-data licensing/notices and verify the distributor package. |
| Pillow | MIT-CMU | Preserve its notice. |
| opencv-python-headless | Wrapper scripts MIT; OpenCV Apache-2.0; wheel includes FFmpeg under LGPLv2.1 and additional third-party components | **Needs binary-level notice review.** Headless avoids the non-headless Qt component but does not mean there are no bundled third-party licenses. |
| PyInstaller | GPL-2.0 with an exception for bundling commercial applications; selected files Apache-2.0 | Official exception allows bundling commercial applications, subject to dependency licenses. Preserve/inspect the applicable PyInstaller license files if redistributing its own components. |
| pywebview | BSD-3-Clause | Include BSD notice in third-party notices. |
| Inno Setup | Current vendor asks commercial users to purchase a commercial license | **Commercial build-tool consideration.** Confirm the actual version and obtain a license for the person/team compiling commercial installers as applicable. The vendor states that merely deploying a previously built installer does not count as using Inno Setup. |
| npm dependencies | Mixed license expressions in `frontend/package-lock.json` (including MIT, BSD, Apache-2.0, ISC and others) | Generate a full report from the lockfile and preserve notices; verify assets/fonts/icons separately. |

## Candidate replacement architecture for PyMuPDF

Do not replace the current engine by a blind package swap. The code uses PyMuPDF deeply:

- `pymupdf.open()` and page iteration;
- `page.get_text("dict")`, `get_text("text")`, and `get_text("words")`;
- `page.find_tables()` and table cell bounding boxes;
- page dimensions and image detection for OCR decisions;
- `page.get_pixmap()` for OCR rasterization and PNG page previews.

A more realistic permissive-license proof of concept is:

1. **pdfplumber / pdfminer.six** for text, character/word coordinates, font sizes, layout and table extraction.
2. **pypdfium2** for page rendering to images and PDFium-backed page inspection.
3. **pytesseract + externally installed Tesseract** for OCR, preserving the existing OCR pipeline and avoiding redistribution of the Tesseract engine in the first desktop pilot.
4. Keep the current metric normalization, table post-processing, evidence references and report generation code unchanged wherever possible.

This combination is promising because pdfplumber already exists in the current project as a secondary table extractor, and pypdfium2 provides rendering without the PyMuPDF AGPL/commercial licensing route. However, it is not a drop-in replacement. The page adapter and extraction behavior need to be rewritten and validated.

### Required proof-of-concept checks

- Born-digital PDFs: reading order, headings, coordinates, page numbers and text fidelity.
- Tables: multi-row headers, merged cells, sparse tables, financial values with decimal/thousands separators, borderless tables.
- Scanned PDFs: page image detection, DPI, orientation correction, OCR language handling and numeric accuracy.
- Mixed PDFs: text pages and image pages in the same document.
- Password-protected, malformed and unusually large PDFs.
- Rendered page previews and PNG export.
- Windows 10/11 x64 PyInstaller build, runtime DLL loading, clean-machine smoke test.
- Performance and memory use against a fixed golden corpus.

Acceptance criterion: no regression in the existing golden fixtures for extracted metrics, source page references, table cell values, OCR numeric accuracy and report exports. If a test cannot be made equivalent, document the difference and get owner approval before merging.

## Newly identified Inno Setup consideration

Official vendor pages:
- https://jrsoftware.org/inno-setup/purchase
- https://jrsoftware.org/files/is6-whatsnew.htm

The vendor's current guidance asks commercial users to purchase a license. The vendor FAQ clarifies that running/deploying an already-built installer does not itself count as using Inno Setup. The exact compiler version used for the v1.1.0 installer is not recorded in the repository, so retrieve the original build-machine/toolchain information if available.

This is separate from the end-user right to run the installer. It concerns the toolchain user/team compiling a commercial installer.

## Recommended next actions

1. Keep `main` and v1.1.0 unchanged.
2. Record the exact Python and Inno Setup versions used for the release if available.
3. Add a reproducible Python lockfile with hashes for the next build, then generate an SPDX or CycloneDX SBOM from the actual environment.
4. Generate a frontend license report from `package-lock.json`.
5. Build a narrow PDF-engine adapter prototype in a separate branch or isolated experiment; do not yet change production `pdf_processor.py`.
6. Run golden-corpus comparisons against current PyMuPDF output.
7. In parallel, request written commercial terms from Artifex and verify Inno Setup commercial licensing for the build operator/team.
8. Only after evidence is available, choose between the permissive replacement route and the PyMuPDF commercial-license route.

## Scope and limitations

This review is based on repository manifests, the PDF processor, PyInstaller spec, desktop build script, installer script and desktop build documentation. It did not reproduce the v1.1.0 build, inspect every file in the published installer, resolve the complete Python environment, or audit every bundled native binary, font, model or data file. This is not a legal opinion.
