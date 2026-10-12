import json
from pathlib import Path

import edbert

EXAMPLES = Path(__file__).resolve().parent.parent / "examples"


def test_package_has_version():
    assert edbert.__version__


def test_examples_are_valid_json():
    files = sorted(EXAMPLES.glob("*.json"))
    assert files, "no example files found"
    for path in files:
        json.loads(path.read_text(encoding="utf-8"))
