"""The public library API ``edibert.api`` and the layering rule (library never imports UI or publisher)."""

import ast
import json
import subprocess
import sys
from pathlib import Path

import pytest

from edibert import api

SRC = Path(__file__).resolve().parents[1] / "src"
PACKAGE = SRC / "edibert"
PRODUCT = ("edibert.ui", "edibert.publish")
PRODUCT_ENTRY = ("edibert.cli", "edibert.__main__")  # command line: starts the editor and the publisher


def _module_name(path: Path) -> str:
    parts = path.relative_to(SRC).with_suffix("").parts
    return ".".join(parts[:-1] if parts[-1] == "__init__" else parts)


def _is_product(module: str) -> bool:
    return module in PRODUCT_ENTRY or any(module == p or module.startswith(p + ".") for p in PRODUCT)


def _imported(tree: ast.AST) -> set[str]:
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            names.add(node.module)
            names.update(f"{node.module}.{alias.name}" for alias in node.names)
    return names


def test_library_modules_never_import_ui_or_publish():
    offenders = []
    for path in sorted(PACKAGE.rglob("*.py")):
        module = _module_name(path)
        if _is_product(module):
            continue
        for name in _imported(ast.parse(path.read_text(encoding="utf-8"))):
            if _is_product(name):
                offenders.append(f"{module} -> {name}")
    assert offenders == []


def test_importing_the_api_loads_no_product_module():
    code = "import sys, edibert.api; print([m for m in sys.modules if m.startswith(('edibert.ui', 'edibert.publish'))])"
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True, env={"PYTHONPATH": str(SRC), "SYSTEMROOT": "C:\\Windows", "PATH": ""})
    assert out.stdout.strip() == "[]"


def test_api_exports_exactly_the_documented_names():
    assert api.API_VERSION == 2
    for name in api.__all__:
        assert hasattr(api, name), name


def test_load_tariffs_keeps_the_origin_and_tolerates_a_missing_user_file(tmp_path):
    catalog = tmp_path / "tariffs.json"
    user = tmp_path / "user_tariffs.json"
    fixed = {"label": "x", "type": "fixed_cent", "land": "AT", "currency": "EUR", "supplier_id": "s", "fix_cent_kwh": 20.0, "vat_percent": 20, "prices_include_vat": False}
    catalog.write_text(json.dumps({"tariff_format": 1, "import_tariffs": [{**fixed, "id": "cat_a"}]}), encoding="utf-8")
    only_catalog = api.load_tariffs(catalog, user)
    assert list(only_catalog.imports) == ["cat_a"]
    user.write_text(json.dumps({"tariff_format": 1, "import_tariffs": [{**fixed, "id": "user_b"}]}), encoding="utf-8")
    both = api.load_tariffs(catalog, user)
    assert both.origin == {(api.IMPORT, "cat_a"): "catalog", (api.IMPORT, "user_b"): "user"}


def test_a_missing_catalog_file_is_an_error(tmp_path):
    with pytest.raises(api.EdibertError) as err:
        api.load_tariffs(tmp_path / "tariffs.json")
    assert err.value.code == api.ErrorCode.FILE_INVALID


def test_pricing_context_checks_the_region_up_front():
    assert api.pricing_context("Europe/Vienna", "AT", "9").region == "9"
    assert api.pricing_context("Europe/Vienna", "AT").region is None
    with pytest.raises(api.EdibertError) as err:
        api.pricing_context("Europe/Vienna", "AT", "XX")
    assert err.value.code == api.ErrorCode.HOLIDAY_REGION_UNKNOWN
    assert err.value.params == {"land": "AT", "region": "XX"}
    with pytest.raises(api.EdibertError) as err:
        api.pricing_context("Europe/Vienna", None, "9")
    assert err.value.code == api.ErrorCode.FIELD_MISSING
