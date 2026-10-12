from pathlib import Path

DOCS = Path(__file__).resolve().parent.parent / "docs" / "user"


def test_every_english_user_page_has_a_german_counterpart():
    english = sorted(p.relative_to(DOCS / "en") for p in (DOCS / "en").rglob("*.md"))
    assert english, "no English user pages found"
    missing = [str(p) for p in english if not (DOCS / "de" / p).exists()]
    assert missing == [], f"German counterpart missing: {missing}"


def test_german_pages_name_their_english_source():
    for page in (DOCS / "de").rglob("*.md"):
        head = page.read_text(encoding="utf-8")[:300]
        assert "source: docs/user/en/" in head, f"{page.name}: source comment missing"


def test_readme_translation_exists():
    root = DOCS.parent.parent
    assert (root / "README.md").exists()
    assert (root / "README.de.md").exists()
