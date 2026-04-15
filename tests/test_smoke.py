"""Smoke test to verify pytest wiring, EPUB helpers, and fixture imports."""
from pathlib import Path

import convert  # noqa: F401  — verifies conftest.py path setup
from tests import fixtures


def test_smoke():
    assert 1 + 1 == 2


def test_convert_imports():
    """convert.py imports cleanly from the test environment."""
    assert hasattr(convert, "convert_book")
    assert hasattr(convert, "convert_pdf")  # alias used by new plan tasks
    assert hasattr(convert, "convert_with_pandoc")
    assert hasattr(convert, "collect_books")


# --- synthetic PDF fixtures ---


def test_fixtures_import():
    assert hasattr(fixtures, "build_text_pdf")
    assert hasattr(fixtures, "build_figure_pdf")
    assert hasattr(fixtures, "build_raster_image_pdf")
    assert hasattr(fixtures, "build_scanned_pdf")


def test_build_text_pdf_runs(tmp_path):
    path = fixtures.build_text_pdf(tmp_path, pages=2)
    assert path.exists()
    assert path.suffix == ".pdf"


# --- pandoc / EPUB helpers (introduced in b6aea28) ---


def test_strip_pandoc_frontmatter_with_yaml():
    body = (
        "---\n"
        "title: Foo\n"
        "author: Bar\n"
        "---\n"
        "\n"
        "# Chapter 1\n"
        "\n"
        "Text."
    )
    assert convert._strip_pandoc_frontmatter(body) == "# Chapter 1\n\nText."


def test_strip_pandoc_frontmatter_without_yaml():
    body = "# Chapter 1\n\nText."
    assert convert._strip_pandoc_frontmatter(body) == body


def test_clean_pandoc_output_strips_html_comments():
    body = (
        "# Chapter 1\n"
        "\n"
        "<!--Licensed to Someone (someone@example.com)-->\n"
        "\n"
        "First paragraph.\n"
    )
    cleaned = convert._clean_pandoc_output(body)
    assert "Licensed to" not in cleaned
    assert "# Chapter 1" in cleaned
    assert "First paragraph." in cleaned


def test_clean_pandoc_output_strips_empty_alt_images():
    body = "# Chapter 1\n\n![](images/decorative.png)\n\nText.\n"
    cleaned = convert._clean_pandoc_output(body)
    assert "decorative.png" not in cleaned
    assert "Text." in cleaned


def test_clean_pandoc_output_preserves_captioned_images():
    body = "# Chapter 1\n\n![Figure 2: diagram](fig.png)\n\nText.\n"
    cleaned = convert._clean_pandoc_output(body)
    assert "Figure 2: diagram" in cleaned


def test_clean_pandoc_output_collapses_blank_line_runs():
    body = "# Chapter 1\n\n\n\n\nText.\n"
    cleaned = convert._clean_pandoc_output(body)
    assert "\n\n\n" not in cleaned


def test_collect_books_accepts_epub(tmp_path):
    (tmp_path / "book.epub").write_bytes(b"fake")
    (tmp_path / "paper.pdf").write_bytes(b"fake")
    (tmp_path / "notes.txt").write_bytes(b"fake")
    found = convert.collect_books(tmp_path)
    names = sorted(p.name for p in found)
    assert names == ["book.epub", "paper.pdf"]


def test_collect_books_single_epub(tmp_path):
    epub = tmp_path / "book.epub"
    epub.write_bytes(b"fake")
    assert convert.collect_books(epub) == [epub]
