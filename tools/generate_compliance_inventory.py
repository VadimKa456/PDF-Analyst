#!/usr/bin/env python3
"""Generate build-time software inventories and third-party license notices.

Uses Python's standard library only. The Python SBOM describes the installed
build virtual environment; the npm SBOM is derived from package-lock.json.
Available license texts are copied for review and redistribution.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import sys
import uuid
from datetime import datetime, timezone
from importlib import metadata
from pathlib import Path
from urllib.parse import quote


ROOT = Path(__file__).resolve().parents[1]
PRODUCT_NAME = "PDF Analyst"
PRODUCT_VERSION = "unknown"
CONFIG_PATH = ROOT / "backend" / "app" / "config.py"
VERSION_MATCH = re.search(
    r'app_version\s*:\s*str\s*=\s*"([^"]+)"',
    CONFIG_PATH.read_text(encoding="utf-8") if CONFIG_PATH.exists() else "",
)
if VERSION_MATCH:
    PRODUCT_VERSION = VERSION_MATCH.group(1)

MAX_LICENSE_BYTES = 2 * 1024 * 1024
LICENSE_PREFIXES = ("license", "licence", "copying", "notice", "patents")
BUILD_ONLY_PYTHON = {
    "pip",
    "setuptools",
    "wheel",
    "pytest",
    "pyinstaller",
    "pyinstaller-hooks-contrib",
    "altgraph",
    "pefile",
}


def slug(value: str) -> str:
    return re.sub(r"[^a-zA-Z0-9._-]+", "-", value).strip("-._") or "unknown"


def normalise_pypi_name(value: str) -> str:
    return re.sub(r"[-_.]+", "-", value).lower()


def licence_choice(name: str, version: str, meta: metadata.PackageMetadata) -> list[dict]:
    expression = (meta.get("License-Expression") or "").strip()
    if expression:
        return [{"license": {"expression": expression}}]

    classifiers = meta.get_all("Classifier") or []
    license_classifiers = [
        item.split("::", 2)[-1].strip()
        for item in classifiers
        if item.startswith("License ::")
    ]
    raw = (meta.get("License") or "").strip()
    raw_one_line = " ".join(raw.split())

    known = {
        "mit": "MIT",
        "mit license": "MIT",
        "apache 2.0": "Apache-2.0",
        "apache license, version 2.0": "Apache-2.0",
        "apache software license": "Apache-2.0",
        "isc license (iscl)": "ISC",
        "isc license": "ISC",
        "mozilla public license 2.0 (mpl 2.0)": "MPL-2.0",
        "mozilla public license 2.0": "MPL-2.0",
        "gnu lesser general public license v3 (lgplv3)": "LGPL-3.0-only",
        "gnu lesser general public license v2 or later (lgplv2+)": "LGPL-2.1-or-later",
        "gnu affero general public license v3 (agplv3)": "AGPL-3.0-only",
        "gnu affero general public license v3": "AGPL-3.0-only",
        "gnu general public license v3 (gplv3)": "GPL-3.0-only",
        "gnu general public license v2 (gplv2)": "GPL-2.0-only",
        "python software foundation license": "PSF-2.0",
        "bsd 3-clause license": "BSD-3-Clause",
        "bsd 2-clause license": "BSD-2-Clause",
    }

    candidates = [raw_one_line.lower()] if raw_one_line else []
    candidates.extend(item.lower() for item in license_classifiers)
    for candidate in candidates:
        if candidate in known:
            return [{"license": {"id": known[candidate]}}]

    if raw_one_line and len(raw_one_line) <= 160 and "unknown" not in raw_one_line.lower():
        return [{"license": {"name": raw_one_line}}]
    if license_classifiers:
        return [{"license": {"name": "; ".join(sorted(set(license_classifiers)))}}]
    return []


def find_licence_files(files) -> list:
    """Find license files by name and standard bundled-license directories.

    Some wheels (notably PDFium-based packages) keep third-party notices in
    BUILD_LICENSES/ or LICENSES/ with names such as "abseil.txt" and
    "pdfium.txt". Those files are still required notices even though their
    filenames do not begin with LICENSE/COPYING/NOTICE.
    """
    result = []
    for item in files or []:
        path = Path(str(item))
        filename = path.name.lower()
        parent_parts = {part.lower() for part in path.parts[:-1]}
        in_license_directory = bool(parent_parts & {"licenses", "build_licenses"})
        if not filename.startswith(LICENSE_PREFIXES) and not in_license_directory:
            continue
        if path.suffix.lower() not in {"", ".txt", ".md", ".rst", ".html"}:
            continue
        result.append(item)
    return result


def copy_licence_texts(distribution, output_root: Path, component_folder: str) -> list[str]:
    copied = []
    prefix = Path(sys.prefix).resolve()
    for item in find_licence_files(distribution.files):
        try:
            source = Path(distribution.locate_file(item)).resolve()
            source.relative_to(prefix)
            if not source.is_file() or source.stat().st_size > MAX_LICENSE_BYTES:
                continue
            relative = Path(str(item))
            filename = slug(relative.name)
            target_dir = output_root / "license-texts" / component_folder
            target_dir.mkdir(parents=True, exist_ok=True)
            target = target_dir / filename
            if target.exists():
                suffix = hashlib.sha256(str(relative).encode("utf-8")).hexdigest()[:8]
                target = target_dir / f"{target.stem}-{suffix}{target.suffix}"
            shutil.copyfile(source, target)
            copied.append(target.relative_to(output_root).as_posix())
        except (OSError, ValueError):
            continue
    return copied


def make_cyclonedx(components: list[dict], name: str) -> dict:
    return {
        "bomFormat": "CycloneDX",
        "specVersion": "1.6",
        "serialNumber": f"urn:uuid:{uuid.uuid4()}",
        "version": 1,
        "metadata": {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "tools": [{
                "vendor": "VADIJI | AI Creative Studio",
                "name": "PDF Analyst build inventory generator",
                "version": "1.0.0",
            }],
            "component": {
                "type": "application",
                "name": PRODUCT_NAME,
                "version": PRODUCT_VERSION,
                "bom-ref": f"pdf-analyst@{PRODUCT_VERSION}#{name}",
            },
        },
        "components": sorted(components, key=lambda x: (x.get("name", "").lower(), x.get("version", ""))),
    }


def write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def collect_python(output_root: Path, report_rows: list[str]) -> None:
    distributions = list(metadata.distributions())
    components = []
    freeze_lines = subprocess.check_output(
        [sys.executable, "-m", "pip", "freeze", "--all"],
        text=True,
        encoding="utf-8",
        errors="replace",
    ).splitlines()
    (output_root / "python-environment.txt").write_text(
        "\n".join(sorted(freeze_lines, key=str.lower)) + "\n",
        encoding="utf-8",
    )

    for distribution in distributions:
        meta = distribution.metadata
        name = meta.get("Name") or "unknown"
        version = distribution.version or "unknown"
        canonical = normalise_pypi_name(name)
        licenses = licence_choice(name, version, meta)
        scope = "excluded" if canonical in BUILD_ONLY_PYTHON else "required"
        component = {
            "type": "library",
            "name": name,
            "version": version,
            "scope": scope,
            "bom-ref": f"pkg:pypi/{quote(canonical, safe='-._')}@{version}",
            "purl": f"pkg:pypi/{quote(canonical, safe='-._')}@{version}",
        }
        if licenses:
            component["licenses"] = licenses
        project_urls = meta.get_all("Project-URL") or []
        if project_urls:
            references = []
            for item in project_urls:
                label, separator, url = item.partition(",")
                if separator and url.strip().startswith(("https://", "http://")):
                    references.append({
                        "type": "website" if "home" in label.lower() else "other",
                        "url": url.strip(),
                        "comment": label.strip(),
                    })
            if references:
                component["externalReferences"] = references[:5]
        components.append(component)

        copied = copy_licence_texts(distribution, output_root, f"python/{slug(canonical)}-{slug(version)}")
        license_label = (
            licenses[0]["license"].get("id")
            or licenses[0]["license"].get("expression")
            or licenses[0]["license"].get("name")
            if licenses else "UNKNOWN — manual review required"
        )
        report_rows.append(
            f"| Python | {name} | {version} | {license_label} | "
            f"{'excluded build/test tool' if scope == 'excluded' else 'included in environment inventory'} | "
            f"{', '.join(copied) if copied else 'no license text found'} |"
        )

    write_json(output_root / "sbom-python.cdx.json", make_cyclonedx(components, "python-environment"))


def package_name_from_lock_path(package_path: str, package: dict) -> str:
    if package.get("name"):
        return str(package["name"])
    marker = "node_modules/"
    index = package_path.rfind(marker)
    return package_path[index + len(marker):] if index >= 0 else package_path


def copy_frontend_licences(
    package_path: str,
    package_name: str,
    node_modules: Path | None,
    output_root: Path,
) -> list[str]:
    if node_modules is None:
        return []
    relative = package_path
    if relative.startswith("node_modules/"):
        relative = relative[len("node_modules/"):]
    source_dir = (node_modules / relative).resolve()
    try:
        source_dir.relative_to(node_modules.resolve())
    except ValueError:
        return []
    if not source_dir.is_dir():
        return []

    candidates = []
    try:
        for entry in source_dir.iterdir():
            if not entry.is_file():
                continue
            lower = entry.name.lower()
            if lower.startswith(LICENSE_PREFIXES) and entry.suffix.lower() in {"", ".txt", ".md", ".rst", ".html"}:
                candidates.append(entry)
        licenses_dir = source_dir / "licenses"
        if licenses_dir.is_dir():
            for entry in licenses_dir.iterdir():
                if entry.is_file() and entry.stat().st_size <= MAX_LICENSE_BYTES:
                    candidates.append(entry)
    except OSError:
        return []

    copied = []
    target_dir = output_root / "license-texts" / "npm" / slug(package_name)
    for source in candidates:
        try:
            if source.stat().st_size > MAX_LICENSE_BYTES:
                continue
            target_dir.mkdir(parents=True, exist_ok=True)
            target = target_dir / slug(source.name)
            if target.exists():
                suffix = hashlib.sha256(str(source).encode("utf-8")).hexdigest()[:8]
                target = target_dir / f"{target.stem}-{suffix}{target.suffix}"
            shutil.copyfile(source, target)
            copied.append(target.relative_to(output_root).as_posix())
        except OSError:
            continue
    return copied


def collect_frontend(output_root: Path, report_rows: list[str], node_modules: Path | None) -> None:
    lock_path = ROOT / "frontend" / "package-lock.json"
    if not lock_path.is_file():
        report_rows.append("| npm | package-lock.json | — | UNKNOWN | lockfile missing | — |")
        return
    lock = json.loads(lock_path.read_text(encoding="utf-8"))
    packages = lock.get("packages") or {}
    components = []
    for package_path, package in packages.items():
        if not package_path:
            continue
        name = package_name_from_lock_path(package_path, package)
        version = str(package.get("version") or "unknown")
        raw_license = package.get("license")
        scope = "excluded" if package.get("dev") else ("optional" if package.get("optional") else "required")
        licenses = []
        if isinstance(raw_license, str) and raw_license.strip():
            license_value = raw_license.strip()
            if re.fullmatch(r"[A-Za-z0-9.+-]+", license_value):
                licenses = [{"license": {"id": license_value}}]
            else:
                licenses = [{"license": {"name": license_value}}]
        elif isinstance(raw_license, dict):
            license_value = raw_license.get("type") or raw_license.get("url") or ""
            if license_value:
                licenses = [{"license": {"name": str(license_value)}}]

        encoded_name = quote(name, safe="/-._~")
        component = {
            "type": "library",
            "name": name,
            "version": version,
            "scope": scope,
            "bom-ref": f"pkg:npm/{encoded_name}@{version}",
            "purl": f"pkg:npm/{encoded_name}@{version}",
        }
        if licenses:
            component["licenses"] = licenses
        if package.get("resolved"):
            component["externalReferences"] = [{
                "type": "distribution",
                "url": str(package["resolved"]),
            }]
        components.append(component)

        copied = copy_frontend_licences(package_path, name, node_modules, output_root)
        license_label = licenses[0]["license"].get("id") or licenses[0]["license"].get("name") if licenses else "UNKNOWN — manual review required"
        report_rows.append(
            f"| npm | {name} | {version} | {license_label} | {scope} | "
            f"{', '.join(copied) if copied else 'license text not copied'} |"
        )

    write_json(output_root / "sbom-frontend.cdx.json", make_cyclonedx(components, "frontend-lockfile"))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir",
        default=str(ROOT / "dist" / "PDF Analyst" / "compliance"),
        help="Output directory (default: dist/PDF Analyst/compliance)",
    )
    parser.add_argument("--frontend-node-modules", default=str(ROOT / "frontend" / "node_modules"))
    parser.add_argument("--python-only", action="store_true")
    parser.add_argument("--frontend-only", action="store_true")
    args = parser.parse_args()

    if args.python_only and args.frontend_only:
        parser.error("Choose at most one of --python-only or --frontend-only")

    output_root = Path(args.output_dir).resolve()
    output_root.mkdir(parents=True, exist_ok=True)
    report_rows = [
        "# PDF Analyst — third-party component inventory",
        "",
        f"- Product version: {PRODUCT_VERSION}",
        f"- Generated (UTC): {datetime.now(timezone.utc).isoformat()}",
        "- Python SBOM: installed build virtual environment; build/test tools are marked excluded.",
        "- Frontend SBOM: exact versions and license declarations from frontend/package-lock.json.",
        "- License-text collection is best-effort. Missing texts or UNKNOWN metadata require manual review.",
        "- This inventory is not a legal opinion and does not by itself establish license compliance.",
        "",
        "| Ecosystem | Component | Version | Declared license | Scope | License text |",
        "|---|---|---:|---|---|---|",
    ]

    if not args.frontend_only:
        collect_python(output_root, report_rows)

    if not args.python_only:
        node_modules = Path(args.frontend_node_modules).resolve()
        if not node_modules.is_dir():
            node_modules = None
        collect_frontend(output_root, report_rows, node_modules)

    report_rows.extend([
        "",
        "## Manual license review required before commercial distribution",
        "",
        "- **PyMuPDF / MuPDF:** Artifex offers the library under AGPLv3 or a separate commercial license. The wheel's COPYING file may only be a short dual-license pointer, not the full AGPLv3 terms. Add the full applicable license text or retain evidence of the commercial grant for the exact release.",
        "- **OpenCV wheels:** the inspected opencv-python-headless 5.1.0.95 wheel's LICENSE-3RD-PARTY.txt states that FFmpeg is redistributed; that notice also contains LGPL 2.1 license text. Review the actual DLLs, notices and corresponding obligations for the exact wheel used by the installer.",
        "- Review every row marked UNKNOWN and every component whose license text was not copied. Do not treat package metadata alone as proof of redistribution rights.",
        "",
        "The Python environment snapshot is in `python-environment.txt`; the machine-readable inventories are CycloneDX JSON.",
    ])
    (output_root / "THIRD_PARTY_NOTICES.md").write_text(
        "\n".join(report_rows) + "\n",
        encoding="utf-8",
    )
    print(f"Compliance inventory written to: {output_root}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
