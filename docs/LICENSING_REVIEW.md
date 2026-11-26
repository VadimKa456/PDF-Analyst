# Licensing review for commercial distribution

This document records technical licensing facts and open decisions. It is not
legal advice and does not determine whether a particular distribution complies
with every license obligation.

## What the repository license covers

The repository's `LICENSE` file is MIT. It governs the original PDF-Analyst
project code contributed under that license. It does not replace the licenses
of third-party libraries bundled into the Windows application or their
transitive native components.

## High-priority dependency: PyMuPDF / MuPDF

PyMuPDF and its MuPDF engine are offered under either the GNU AGPLv3 or a
separate commercial license from Artifex:

- https://pymupdf.io/licensing
- https://pymupdf.readthedocs.io/en/latest/about.html
- https://github.com/pymupdf/PyMuPDF

The current dependency declaration is `PyMuPDF>=1.24,<2.0`. Earlier builds did
not record an exact Python environment snapshot, so the exact PyMuPDF version
inside the published `v1.1.0` installer has not been established.

Before selling a new installer, choose and document one compliant route:

1. Obtain an Artifex commercial license that explicitly covers the intended
   desktop redistribution and deployment model; retain the license grant and
   its conditions with release records.
2. Distribute under the applicable AGPLv3 terms and provide the complete
   corresponding source and notices required for the exact way the application
   is distributed. Confirm the licensing of the combined work with counsel.
3. Replace PyMuPDF/MuPDF with an alternative whose license is suitable for the
   product, then re-run extraction, OCR, table, preview, export, and regression
   tests before changing the dependency.

Do not describe the complete installer as "MIT-only" while this dependency
remains unresolved.

## Other components to review

- `opencv-python-headless`: the Python wheel declares an OpenCV license, but
  the wheel may also include native third-party components (including FFmpeg
  builds). Inspect the exact wheel and bundled DLLs and preserve applicable
  notices/licenses.
- NumPy, pandas, Pillow, pdfplumber, ReportLab, Matplotlib, FastAPI, and the
  remaining Python dependencies have their own licenses and may include
  transitive dependencies. Review the actual version inventory, not only the
  top-level requirements.
- Frontend versions and package license declarations are captured in
  `frontend/package-lock.json`. Retain the npm SBOM and available license texts
  for each release.
- PyInstaller uses GPLv2 with an exception for generated applications; its
  official documentation says the exception permits shipping commercial
  bundles, subject to the licenses of bundled dependencies:
  https://pyinstaller.org/en/stable/license.html

## Build inventory

The desktop build now generates a `compliance/` folder in the portable app and
includes it in the Inno Setup installer. It contains:

- `sbom-python.cdx.json`: installed Python build-environment component list;
- `python-environment.txt`: exact package versions from `pip freeze --all`;
- `sbom-frontend.cdx.json`: exact npm package versions from
  `frontend/package-lock.json`;
- `THIRD_PARTY_NOTICES.md`: declared license metadata, inventory scope, and
  components requiring manual review;
- `license-texts/`: license/notice files that could be located in the installed
  Python distributions and, when `frontend/node_modules` is available, npm
  package folders.

This is an environment/lockfile inventory, not a guarantee that PyInstaller
bundled every listed library or that every third-party license obligation has
been met. The Python SBOM includes build and test tools, marked with an
`excluded` scope. Unknown license metadata and missing license texts are
reported rather than guessed.

## Release checklist

- [ ] Build from a clean Python 3.12 virtual environment and run
      `build_desktop.bat`.
- [ ] Archive the exact compliance folder and SHA256 of the installer alongside
      the release tag.
- [ ] Resolve PyMuPDF/MuPDF licensing for the actual distribution model.
- [ ] Inspect OpenCV and all native DLL license notices from the actual build.
- [ ] Review every UNKNOWN or missing license text in
      `THIRD_PARTY_NOTICES.md`.
- [ ] Confirm the `LICENSE` and third-party notices are accessible to users of
      the installed application.
- [ ] Complete the Windows 10/11 installer smoke test before publishing.
