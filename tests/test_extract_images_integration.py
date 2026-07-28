"""End-to-end test for --extract-images."""
import json

import convert
from tests import fixtures


def test_extract_images_writes_png_and_references_in_markdown(tmp_path):
    pdf = fixtures.build_figure_pdf(tmp_path)
    out_dir = tmp_path / "out"
    out_dir.mkdir()

    report = convert.convert_with_pymupdf(pdf, out_dir, extract_images=True)
    assert report.extracted_assets >= 1

    md = (out_dir / f"{pdf.stem}.md").read_text(encoding="utf-8")
    # Markdown has an image reference pointing into the asset dir.
    assert "![" in md
    assert f"{pdf.stem}_assets/" in md

    # Asset dir exists and contains at least one PNG.
    asset_dir = out_dir / f"{pdf.stem}_assets"
    assert asset_dir.exists()
    pngs = list(asset_dir.glob("*.png"))
    assert len(pngs) >= 1

    # Sidecar has extracted_assets populated.
    sidecar = out_dir / f"{pdf.stem}.report.json"
    data = json.loads(sidecar.read_text(encoding="utf-8"))
    assert data["extracted_assets"] >= 1


def test_extract_images_default_on(tmp_path):
    """Extraction is the default as of issue #34.

    The old default found the figures, emitted references to them, and threw
    the files away — a caller had to know a flag existed to avoid producing
    broken output. Keeping the figures costs nothing that was not already
    spent finding them.
    """
    pdf = fixtures.build_figure_pdf(tmp_path)
    out_dir = tmp_path / "out"
    out_dir.mkdir()

    report = convert.convert_with_pymupdf(pdf, out_dir)
    assert (out_dir / f"{pdf.stem}_assets").is_dir()
    assert report.extracted_assets >= 1


def test_extract_images_opt_out(tmp_path):
    """With extraction explicitly off, no asset dir should be produced."""
    pdf = fixtures.build_figure_pdf(tmp_path)
    out_dir = tmp_path / "out"
    out_dir.mkdir()

    convert.convert_with_pymupdf(pdf, out_dir, extract_images=False)
    asset_dir = out_dir / f"{pdf.stem}_assets"
    assert not asset_dir.exists()
