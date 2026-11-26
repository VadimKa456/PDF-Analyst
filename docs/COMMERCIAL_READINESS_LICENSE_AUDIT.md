# Commercial readiness audit — licensing (draft)

**Status:** preliminary technical audit; not legal advice  
**Reviewed:** 2026-11-26  
**Repository baseline:** `main`, PDF Analyst 1.1.0  
**Working branch:** `commercial-readiness/license-audit`

## Executive summary

Do not publish a paid Windows installer or claim that the complete installer is MIT-licensed until the third-party licensing review is complete.

The repository's own `LICENSE` is MIT. That license covers the project code to the extent the project authors own it; it does not relicense third-party dependencies included in the application bundle.

## Confirmed findings

1. `requirements.txt` declares PyMuPDF (`PyMuPDF>=1.24`) as a runtime dependency without an upper bound or an exact version pin.
2. `backend/app/services/pdf_processor.py` imports `pymupdf` and uses it for PDF opening, page text extraction, table detection, page rendering and related operations. It is a core runtime dependency, not an unused optional package.
3. `pdf_analyst.spec` explicitly collects `pymupdf` and `fitz` modules/data/binaries for the PyInstaller application.
4. `build_desktop.bat` builds the Windows desktop bundle and installer from the installed Python environment.
5. `requirements-desktop.txt` also uses version ranges for PyInstaller and pywebview.
6. `frontend/package-lock.json` exists and records npm dependency versions and license metadata. Python dependencies do not currently have an equivalent committed lock/SBOM in the reviewed root files.
7. No `THIRD_PARTY_NOTICES.md` or `NOTICE` file was found at the repository root in this review.

## PyMuPDF licensing blocker

The official PyMuPDF licensing information describes two licensing routes: AGPLv3 or a commercial license from Artifex. The project currently bundles PyMuPDF into a Windows installer while presenting the repository's own license as MIT.

This is not enough information to conclude that the current distribution is compliant or non-compliant. The exact obligations depend on the selected PyMuPDF license, how the combined application is distributed, and whether the project can satisfy the applicable AGPL terms. Obtain qualified legal advice or written confirmation from Artifex before commercial distribution if retaining PyMuPDF.

Official references:
- https://pymupdf.io/licensing
- https://pymupdf.readthedocs.io/en/latest/about.html

## Distribution decision gate

Until this issue is resolved:

- Do not sell or distribute the existing Windows installer as an MIT-only product.
- Do not remove or replace the project's MIT license as a shortcut.
- Do not claim that all bundled components are MIT.
- Keep the public `main` branch and existing release unchanged.

## Options to evaluate

### Option A — replace PyMuPDF

Run a focused proof of concept using permissively licensed PDF libraries for each required capability:

- text extraction and layout/coordinates;
- page rendering to images;
- table detection/reconstruction;
- OCR image preparation and integration;
- regression accuracy on the project's existing PDF/OCR fixtures.

Potential candidates for investigation include pypdf, pdfplumber/pdfminer.six and a separately licensed PDF rendering engine. Their exact licenses, binary redistribution terms, platform support and feature coverage must be verified independently before selection.

Acceptance criteria: existing test suite and golden PDF fixtures retain equivalent output quality; no material regression in speed, OCR, page references or table extraction; dependency licenses and notices are documented.

### Option B — obtain a commercial PyMuPDF license

Ask Artifex for written terms and a quote covering the intended use:

- bundling PyMuPDF/MuPDF in a paid Windows desktop installer;
- redistribution to end customers;
- number/type of products and distribution channels;
- whether the existing public MIT source repository can remain as-is;
- whether development, CI and end-user installations are all covered.

Do not assume a license quote covers all these uses until confirmed in writing.

### Option C — distribute under AGPLv3

This is a separate product/licensing decision, not an automatic consequence of the current MIT license. It requires a careful review of the combined work, source-code availability, notices, user rights and any other dependency licenses. Do not switch licenses without an explicit owner decision and legal review.

## Next audit steps

1. Determine the exact PyMuPDF version used for the v1.1.0 Windows build, including the wheel/build environment if recoverable.
2. Generate a Python SBOM from a clean, reproducible environment and a license inventory for all direct and transitive dependencies.
3. Inspect the complete PyInstaller bundle and all embedded native binaries/data for license notices.
4. Audit the frontend production bundle and its transitive dependencies using the committed npm lockfile.
5. Check fonts, icons, OCR language data and other assets shipped or downloaded by the installer.
6. Decide between Option A and Option B only after a technical comparison and, where needed, written licensing clarification.

## Scope and limitations

This review inspected the repository's root dependency manifests, README, desktop build scripts/specification, main PDF processor and installer configuration. It did not reproduce the historical v1.1.0 build, inspect every byte of the released executable, resolve the complete Python dependency graph, or provide a legal opinion. Findings must be revalidated against the exact release artifact before a paid release.
