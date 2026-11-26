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

### Artifex commercial options to request

Artifex's public licensing page describes two commercial models:

- **OEM Distribution:** customer-facing redistribution without AGPL source
  disclosure, annual distribution-volume reporting, support, and a per-copy
  charge with a quarterly minimum.
- **Subscription:** also described as per-copy with a quarterly minimum;
  internal-use subscriptions do not require a distribution report.

Artifex states that commercial licenses are tailored to the individual use
case. The public page does not list a price. Sources:
- https://artifex.com/licensing
- https://pymupdf.io/licensing

For PDF Analyst, request a written quote for the standalone Windows desktop
application, including bundling PyMuPDF/MuPDF 1.28.2 in a PyInstaller portable
folder and Inno Setup installer, sales to end users, updates, trial copies,
and expected annual copy volume. Ask Artifex to confirm in writing which
commercial model covers this distribution. OEM Distribution is the first model
to ask about because the product is redistributed to customers, but this is
not a legal conclusion or a purchase decision. Do not publish or sell a new
installer until the scope and fee are clear.

## Versions observed in the 26 Nov 2026 Windows CI inventory

The successful Windows/Python 3.12 compliance artifacts on 26 Nov 2026 recorded these resolved versions (the same major set is present in the hash-pinned desktop build):

| Component | CI-resolved version | License finding |
|---|---:|---|
| PyMuPDF | 1.28.2 | Package metadata: dual licensed AGPLv3 / Artifex commercial |
| opencv-python-headless | 5.1.0.95 | Package metadata: Apache-2.0; bundled third-party notice requires separate review |
| numpy | 2.5.5 | BSD-3-Clause plus bundled third-party license expressions |
| pandas | 3.1.1 | BSD-3-Clause |
| FastAPI | 0.165.0 | MIT |
| SQLAlchemy | 2.1.9 | MIT |

These are versions resolved in the CI environment on 26 Nov 2026, **not a
reconstruction of the libraries inside the published 19 Nov 2026 `v1.1.0`
installer**. That earlier installer was not accompanied by a Python environment
snapshot, so its exact PyMuPDF version remains unknown.

In the inspected PyMuPDF 1.28.2 wheel, `COPYING` is only a 64-byte dual-license
notice ("GNU AGPL 3.0 or Artifex Commercial License"), not the complete AGPLv3
license text. The new compliance generator reports the missing/full-text issue;
the release process must provide the applicable full license text and required
source notices, or retain the applicable commercial entitlement.

In the inspected opencv-python-headless 5.1.0.95 wheel, `LICENSE-3RD-PARTY.txt`
states that FFmpeg is redistributed inside the package and includes an LGPL 2.1
license text. The installer process must retain the applicable third-party
notices and verify the actual native binaries included by PyInstaller.

## Additional findings from the 26 Nov 2026 Run #60 inventory

The latest portable-build compliance artifact identifies three smaller
third-party review items:

- **`clr_loader==0.3.1`:** its wheel metadata does not declare a license, so
  the generated SBOM labels the license as UNKNOWN. However, the exact wheel's
  copied `LICENSE` file begins with the MIT License and identifies
  Benedikt Reinartz (2019–2026). Retain that full text in the installer and
  record the metadata omission; do not treat the UNKNOWN label as evidence that
  the source license is absent. Reference: [PyPI release
  0.3.1](https://pypi.org/project/clr_loader/0.3.1/).
- **`proxy_tools==0.1.0`:** PyPI reports MIT, but the upstream repository's
  `LICENSE.txt` is a BSD license with copyright notices for Armin Ronacher and
  Jonathan Tushman. The CI wheel inventory did not find a license file. This is
  a metadata/source discrepancy, not a resolved MIT conclusion. Confirm the
  licensing of the exact PyPI source distribution with the maintainer or
  replace the dependency before making a definitive statement. References:
  [PyPI metadata](https://pypi.org/project/proxy_tools/0.1.0/) and
  [upstream LICENSE.txt](https://github.com/jtushman/proxy_tools/blob/master/LICENSE.txt).
- **`pypdfium2==5.15.2`:** package metadata declares BSD-3-Clause / Apache-2.0
  and additional PDFium dependency licenses. Its release documentation
  explicitly says PDFium's license and bundled dependency licenses must ship
  with binary distributions. The corresponding source tag contains
  `BUILD_LICENSES/` and `LICENSES/` directories (including PDFium and
  third-party component notices). The inventory generator now scans these
  directory trees as well as filenames beginning with LICENSE/COPYING/NOTICE;
  confirm the next clean CI artifact actually contains the Windows wheel's
  complete applicable files. References:
  [pypdfium2 5.15.2 on PyPI](https://pypi.org/project/pypdfium2/5.15.2/) and
  [its 5.15.2 BUILD_LICENSES tree](https://github.com/pypdfium2-team/pypdfium2/tree/5.15.2/BUILD_LICENSES).

The package-level license statement is not enough by itself where a wheel
contains native binaries or redistributed third-party code. Release review
must match the actual wheel and binaries used by PyInstaller, not only upstream
repository files or package classifiers.

### Verification from the latest Windows portable-build artifact (Run #69)

The Run #69 compliance artifact (26 Nov 2026, commit `156b1eec2835f91a46609ec54cee9d0ffed35063`)
was inspected after the generator change. It now contains the pypdfium2 5.15.2
license files from both `BUILD_LICENSES/` and `LICENSES/`, including
`pdfium.txt`, `pdfium-binaries.txt`, Abseil, FreeType, HarfBuzz, ICU, JPEG,
OpenJPEG, PNG, TIFF, zlib, Brotli, V8 and other dependency notices. This
confirms the license-directory traversal fix works in the actual Windows build
environment, rather than only in a unit test.

The same artifact also confirms:
- `clr_loader 0.3.1` still has UNKNOWN license metadata in the SBOM, but an
  MIT `LICENSE` text is included in the artifact and should be reviewed as the
  license evidence for that exact wheel.
- `proxy_tools 0.1.0` still declares MIT in PyPI metadata but has no license
  text in the built inventory. Upstream source contains a BSD license file.
  Keep this as an unresolved metadata/source discrepancy until the exact
  source distribution is reconciled with its maintainer or the dependency is
  replaced.

The pypdfium2 notice collection issue is therefore resolved at the inventory
level for this CI build. This does not by itself establish that every listed
native component is actually linked into the Windows binary or replace a
release-specific legal review.

### Verification from Run #71 portable build (26 Nov 2026)

The latest Windows/Python 3.12 run for commit
`789550563e2ad0dd1759cbfa592839b3da72a506` passed Backend, Frontend, hash-lock
installation, `pip check`, the locked-environment test suite, PyInstaller
portable packaging, and checks for required compliance files. The build
artifact is a portable folder; CI intentionally skipped the Inno Setup
installer and did not run an interactive WebView2 session.

The Run #71 Python compliance ZIP was inspected directly:
- `pymupdf==1.28.2` has only a 64-byte `COPYING` file containing the dual-license
  pointer; it does not include the full AGPLv3 license text.
- `opencv-python-headless==5.1.0.95` includes a 184,724-byte
  `LICENSE-3RD-PARTY.txt`; it explicitly says FFmpeg is redistributed in the
  wheel and includes LGPL 2.1 text.
- `pypdfium2==5.15.2` includes its PDFium and third-party license texts.
- `clr_loader==0.3.1` still has UNKNOWN SBOM metadata, although its copied
  wheel `LICENSE` file contains MIT text.
- `proxy_tools==0.1.0` still has a metadata/source discrepancy and no copied
  license text in the wheel inventory.

Artifact references:
- https://github.com/VadimKa456/PDF-Analyst/actions/runs/45809014870
- Python inventory: https://github.com/VadimKa456/PDF-Analyst/actions/runs/45809014870/artifacts/15110937671
- Portable Windows build: https://github.com/VadimKa456/PDF-Analyst/actions/runs/45809014870/artifacts/15111520762

This run confirms the package build and inventory steps. It does not prove
interactive operation on Windows 10/11 or settle any third-party license
obligation.

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
