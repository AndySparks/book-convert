"""Tests for assets.py — image region detection and rendering."""
import fitz
import pytest

import assets
from tests import fixtures


# --- caption regex ---


def test_caption_regex_matches_figure_with_number():
    assert assets.CAPTION_RE.match("Figure 1.1 The quadrant model.")
    assert assets.CAPTION_RE.match("Figure 6.1 Relational activity diagram")
    assert assets.CAPTION_RE.match("FIGURE 3 The outsider CEOs")
    assert assets.CAPTION_RE.match("Exhibit 2.4 Revenue over time")
    assert assets.CAPTION_RE.match("Diagram 5 The loop")


def test_caption_regex_rejects_body_text():
    assert not assets.CAPTION_RE.match("This is about the figure we mentioned.")
    assert not assets.CAPTION_RE.match("As shown above, figure 1.1 is the model.")
    assert not assets.CAPTION_RE.match("Figure")


# --- raster image detection ---


def test_find_raster_regions_finds_embedded_image(tmp_path):
    pdf = fixtures.build_raster_image_pdf(tmp_path)
    with fitz.open(str(pdf)) as doc:
        regions = assets.find_raster_regions(doc[0])
    assert len(regions) >= 1
    # Each region is a fitz.Rect; the embedded image was drawn at (200, 150, 400, 350).
    x0, y0, x1, y1 = regions[0]
    assert 150 <= x0 <= 250
    assert 100 <= y0 <= 200


def test_find_raster_regions_empty_on_text_only_pdf(tmp_path):
    pdf = fixtures.build_text_pdf(tmp_path, pages=1)
    with fitz.open(str(pdf)) as doc:
        regions = assets.find_raster_regions(doc[0])
    assert regions == []


# --- vector drawing detection ---


def test_find_vector_regions_finds_rectangle_cluster(tmp_path):
    """A drawn rectangle on a page should produce exactly one vector region."""
    pdf = fixtures.build_figure_pdf(tmp_path)
    with fitz.open(str(pdf)) as doc:
        regions = assets.find_vector_regions(doc[0])
    assert len(regions) >= 1
    # The rectangle was drawn at (150, 200, 460, 450).
    rect = regions[0]
    assert 140 <= rect.x0 <= 160
    assert 190 <= rect.y0 <= 210
    assert 450 <= rect.x1 <= 470
    assert 440 <= rect.y1 <= 460


def test_find_vector_regions_empty_on_text_only_pdf(tmp_path):
    pdf = fixtures.build_text_pdf(tmp_path, pages=1)
    with fitz.open(str(pdf)) as doc:
        regions = assets.find_vector_regions(doc[0])
    assert regions == []


# --- extract_page_assets end-to-end ---


def test_extract_page_assets_renders_png_and_returns_markdown(tmp_path):
    pdf = fixtures.build_figure_pdf(tmp_path)
    asset_dir = tmp_path / "assets"
    with fitz.open(str(pdf)) as doc:
        results = assets.extract_page_assets(
            doc[0], stem="figure", asset_dir=asset_dir, page_num=1
        )
    assert len(results) >= 1
    rect, md = results[0]

    # Rendered PNG exists on disk.
    assert asset_dir.exists()
    pngs = list(asset_dir.glob("*.png"))
    assert len(pngs) >= 1

    # Markdown is an image reference pointing into the asset dir.
    assert md.startswith("![")
    assert "figure_assets" in md or str(asset_dir.name) in md


def test_extract_page_assets_associates_caption(tmp_path):
    pdf = fixtures.build_figure_pdf(tmp_path)
    asset_dir = tmp_path / "assets"
    with fitz.open(str(pdf)) as doc:
        results = assets.extract_page_assets(
            doc[0], stem="figure", asset_dir=asset_dir, page_num=1
        )
    rect, md = results[0]
    # The caption "Figure 1.1 The four-quadrant model." should be the alt text.
    assert "Figure 1.1" in md


def test_extract_page_assets_empty_on_text_only_pdf(tmp_path):
    pdf = fixtures.build_text_pdf(tmp_path, pages=1)
    asset_dir = tmp_path / "assets"
    with fitz.open(str(pdf)) as doc:
        results = assets.extract_page_assets(
            doc[0], stem="text", asset_dir=asset_dir, page_num=1
        )
    assert results == []
