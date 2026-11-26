"""Tests for collection of third-party license texts."""
from __future__ import annotations

import importlib.util
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[2]
MODULE_PATH = ROOT_DIR / "tools" / "generate_compliance_inventory.py"
SPEC = importlib.util.spec_from_file_location("compliance_inventory", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
COMPLIANCE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(COMPLIANCE)


def test_find_licence_files_includes_pdfium_license_directories() -> None:
    paths = [
        "pypdfium2/BUILD_LICENSES/abseil.txt",
        "pypdfium2/BUILD_LICENSES/pdfium-binaries.txt",
        "pypdfium2/LICENSES/Apache-2.0.txt",
        "example.dist-info/licenses/LICENSE",
        "package/README.md",
        "package/data/readme.txt",
    ]

    result = {str(path).replace("\\", "/") for path in COMPLIANCE.find_licence_files(paths)}

    assert "pypdfium2/BUILD_LICENSES/abseil.txt" in result
    assert "pypdfium2/BUILD_LICENSES/pdfium-binaries.txt" in result
    assert "pypdfium2/LICENSES/Apache-2.0.txt" in result
    assert "example.dist-info/licenses/LICENSE" in result
    assert "package/README.md" not in result
    assert "package/data/readme.txt" not in result


def test_find_licence_files_keeps_named_license_files_outside_license_dirs() -> None:
    paths = [
        "package/LICENSE",
        "package/COPYING.txt",
        "package/NOTICE.md",
        "package/README.txt",
    ]

    result = {str(path) for path in COMPLIANCE.find_licence_files(paths)}

    assert result == {
        "package/LICENSE",
        "package/COPYING.txt",
        "package/NOTICE.md",
    }
