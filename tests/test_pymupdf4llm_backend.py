"""Tests for the pymupdf4llm backend. Only runs on Python 3.10+."""
import re
import sys

import pytest

import convert
from report import ConversionReport
from tests import fixtures


@pytest.fixture(autouse=True)
def _skip_on_old_python():
    if sys.version_info < (3, 10):
        pytest.skip("pymupdf4llm backend requires Python 3.10+")
    try:
        import pymupdf4llm  # noqa: F401
    except ImportError:
        pytest.skip("pymupdf4llm not installed in this interpreter")


def test_pymupdf4llm_backend_returns_report(tmp_path):
    pdf = fixtures.build_text_pdf(tmp_path, pages=2, body="Hello world from pymupdf4llm.")
    out_dir = tmp_path / "out"
    out_dir.mkdir()

    result = convert.convert_with_pymupdf4llm(pdf, out_dir)
    assert isinstance(result, ConversionReport)
    assert result.method == "pymupdf4llm"
    assert result.total_pages == 2


def test_pymupdf4llm_backend_writes_markdown(tmp_path):
    pdf = fixtures.build_text_pdf(tmp_path, pages=1, body="Unique marker abcxyz.")
    out_dir = tmp_path / "out"
    out_dir.mkdir()

    convert.convert_with_pymupdf4llm(pdf, out_dir)
    md = (out_dir / f"{pdf.stem}.md").read_text(encoding="utf-8")
    assert md.startswith("# ")
    assert "abcxyz" in md


def test_pymupdf4llm_image_refs_are_relative_to_markdown(tmp_path):
    # Regression: pymupdf4llm embeds the full image_path (which includes the
    # output dir, possibly absolute / symlink-canonicalized) as the ref prefix,
    # breaking refs relative to the md file. We rewrite them to
    # `{stem}_images/...` — relative to the markdown. Uses a PDF with a real
    # embedded image so at least one ref is actually emitted.
    pdf = fixtures.build_raster_image_pdf(tmp_path)
    out_dir = tmp_path / "output"
    out_dir.mkdir()

    convert.convert_with_pymupdf4llm(pdf, out_dir)
    md = (out_dir / f"{pdf.stem}.md").read_text(encoding="utf-8")

    safe_stem = re.sub(r"\s+", "_", pdf.stem)
    refs = [r for r in re.findall(r"!\[[^\]]*\]\(([^)]+)\)", md)
            if "_images/" in r]
    assert refs, "expected at least one image ref to exercise the rewrite"
    for ref in refs:
        # Must be relative to the markdown, not absolute or output-dir-prefixed.
        assert ref.startswith(f"{safe_stem}_images/"), ref
        assert not ref.startswith("/"), f"absolute ref leaked: {ref}"
        assert "output/" not in ref, f"output-dir prefix leaked: {ref}"
        assert (out_dir / ref).exists(), f"ref does not resolve: {ref}"


def test_pymupdf4llm_backend_writes_sidecar(tmp_path):
    pdf = fixtures.build_text_pdf(tmp_path, pages=1)
    out_dir = tmp_path / "out"
    out_dir.mkdir()

    convert.convert_with_pymupdf4llm(pdf, out_dir)
    sidecar = out_dir / f"{pdf.stem}.report.json"
    assert sidecar.exists()
