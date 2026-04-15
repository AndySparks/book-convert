"""Smoke test to verify pytest wiring + fixture imports."""
import convert  # noqa: F401
from tests import fixtures


def test_smoke():
    assert 1 + 1 == 2


def test_convert_imports():
    assert hasattr(convert, "convert_pdf")


def test_fixtures_import():
    assert hasattr(fixtures, "build_text_pdf")
    assert hasattr(fixtures, "build_figure_pdf")
    assert hasattr(fixtures, "build_raster_image_pdf")
    assert hasattr(fixtures, "build_scanned_pdf")


def test_build_text_pdf_runs(tmp_path):
    path = fixtures.build_text_pdf(tmp_path, pages=2)
    assert path.exists()
    assert path.suffix == ".pdf"
