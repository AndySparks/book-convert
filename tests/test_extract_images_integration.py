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


def test_extract_images_default_off(tmp_path):
    """Without --extract-images, no asset dir should be produced."""
    pdf = fixtures.build_figure_pdf(tmp_path)
    out_dir = tmp_path / "out"
    out_dir.mkdir()

    convert.convert_with_pymupdf(pdf, out_dir)
    asset_dir = out_dir / f"{pdf.stem}_assets"
    assert not asset_dir.exists()
