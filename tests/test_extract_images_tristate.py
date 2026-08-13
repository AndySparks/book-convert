"""`extract_images` is tri-state, and None must not reach a PDF backend.

None means "unspecified": PDF backends extract, epub does not. The trap is that
every PDF backend tests the flag with a plain truthiness check, so passing None
through would silently turn PDF image extraction OFF while looking exactly like
a default. `convert_book` resolves it; these tests hold it to that.
"""
import pytest

import convert


@pytest.fixture
def spy(monkeypatch):
    """Record the extract_images each backend is handed, run nothing."""
    seen = {}

    def record(name):
        def fake(book_path, output_dir, *a, **kw):
            seen[name] = kw.get("extract_images", "NOT-PASSED")
            return True
        return fake

    monkeypatch.setattr(convert, "convert_with_pymupdf", record("pymupdf"))
    monkeypatch.setattr(convert, "convert_with_marker", record("marker"))
    monkeypatch.setattr(convert, "convert_with_pymupdf4llm", record("pymupdf4llm"))
    monkeypatch.setattr(convert, "convert_with_pandoc", record("pandoc"))
    monkeypatch.setattr(convert, "check_dependencies", lambda *a, **kw: None)
    monkeypatch.setattr(convert, "_apply_cleanup", lambda r: r)
    return seen


def _pdf(tmp_path):
    p = tmp_path / "b.pdf"
    p.write_bytes(b"%PDF-1.4\n")
    return p


def _epub(tmp_path):
    p = tmp_path / "b.epub"
    p.write_bytes(b"PK\x03\x04")
    return p


@pytest.mark.parametrize("passed,expected", [
    (None, True),    # the regression: unspecified must still extract
    (True, True),
    (False, False),
])
def test_pdf_backend_never_receives_none(spy, tmp_path, passed, expected):
    convert.convert_book(_pdf(tmp_path), tmp_path, method="pymupdf",
                         extract_images=passed, clean=False)
    assert spy["pymupdf"] is expected


@pytest.mark.parametrize("passed,expected", [
    (None, True),
    (True, True),
    (False, False),
])
def test_marker_never_receives_none(spy, tmp_path, passed, expected):
    convert.convert_book(_pdf(tmp_path), tmp_path, method="marker",
                         extract_images=passed, clean=False)
    assert spy["marker"] is expected


@pytest.mark.parametrize("passed,expected", [
    (None, None),    # epub's default is text-only, and None is how it hears that
    (True, True),    # the escape hatch for a figure-bearing epub
    (False, False),
])
def test_epub_keeps_the_raw_tristate(spy, tmp_path, passed, expected):
    convert.convert_book(_epub(tmp_path), tmp_path,
                         extract_images=passed, clean=False)
    assert spy["pandoc"] is expected


def test_the_two_formats_disagree_on_unspecified(spy, tmp_path):
    """The whole point of the tri-state, stated once."""
    convert.convert_book(_pdf(tmp_path), tmp_path, method="pymupdf",
                         extract_images=None, clean=False)
    convert.convert_book(_epub(tmp_path), tmp_path,
                         extract_images=None, clean=False)
    assert spy["pymupdf"] is True and spy["pandoc"] is None
