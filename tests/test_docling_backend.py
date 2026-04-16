"""Docling backend smoke test. Python 3.10+ only."""
import sys

import pytest

import convert
from report import ConversionReport
from tests import fixtures


@pytest.fixture(autouse=True)
def _skip_on_old_python():
    if sys.version_info < (3, 10):
        pytest.skip("docling backend requires Python 3.10+")
    try:
        import docling  # noqa: F401
    except ImportError:
        pytest.skip("docling not installed in this interpreter")


def test_docling_backend_returns_report(tmp_path):
    pdf = fixtures.build_text_pdf(tmp_path, pages=1, body="Unique docling marker xyz42.")
    out_dir = tmp_path / "out"
    out_dir.mkdir()

    result = convert.convert_with_docling(pdf, out_dir)
    assert isinstance(result, ConversionReport)
    assert result.method == "docling"
    assert result.total_pages == 1


def test_docling_backend_writes_markdown(tmp_path):
    pdf = fixtures.build_text_pdf(tmp_path, pages=1, body="Unique docling marker xyz42.")
    out_dir = tmp_path / "out"
    out_dir.mkdir()

    convert.convert_with_docling(pdf, out_dir)
    md = (out_dir / f"{pdf.stem}.md").read_text(encoding="utf-8")
    assert md.startswith("# ")
    assert "xyz42" in md


def test_docling_backend_writes_sidecar(tmp_path):
    pdf = fixtures.build_text_pdf(tmp_path, pages=1)
    out_dir = tmp_path / "out"
    out_dir.mkdir()

    convert.convert_with_docling(pdf, out_dir)
    assert (out_dir / f"{pdf.stem}.report.json").exists()
