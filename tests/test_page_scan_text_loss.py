"""A full-page scan image must never suppress the page's text layer.

WHY THIS EXISTS

2026-08-31. Andy dropped William James's *Principles of Psychology* Vol 1
(704 pages, a scan with a good OCR text layer) into the ingest inbox. The
pymupdf backend produced 9,350 words -- roughly 1% of the book -- and
emitted every single page as `![Figure on page N]` with no prose at all.

The mechanism: `assets.find_raster_regions` reported the page-scan bitmap as
a figure region covering the entire page, and `_extract_page_text_with_regions`
walks the page top-to-bottom emitting region markdown in place of the text
underneath it. A region spanning the full page therefore consumed every
character on it.

What makes this the dangerous class of bug rather than an annoying one is
that NOTHING caught it. `quality_score` read 1.0, the degenerate-text gate
was clean, and the locator gate was clean. `--no-clean` produced byte-identical
output, so the cleanup pass was not involved. The board was green on a 99%
content loss.
"""
import fitz
import pytest

import assets
from tests.fixtures import build_scanned_ocr_pdf, build_figure_pdf


def test_full_page_scan_is_not_reported_as_a_figure(tmp_path):
    """The bad case: a page-scan bitmap over a text layer is not a figure."""
    pdf = build_scanned_ocr_pdf(tmp_path)
    doc = fitz.open(str(pdf))
    page = doc[0]
    # Sanity: the fixture really does have a full-page raster and real text.
    raster = assets.find_raster_regions(page)
    assert raster, "fixture must carry a raster image"
    assert len(page.get_text().strip()) > 200, "fixture must carry a text layer"

    assert assets.detect_page_scan_document(doc), (
        "a book of page bitmaps with a text layer is a scanned document"
    )
    extracted = assets.extract_page_assets(
        page, "scan", tmp_path / "a", 1, page_scan_document=True
    )
    doc.close()
    assert extracted == [], (
        "a full-page scan bitmap over a text layer is the page itself, not a "
        "figure; emitting it as one costs the page its text"
    )


def test_scanned_book_conversion_keeps_its_text(tmp_path):
    """End to end: the words in the book survive into the markdown."""
    import convert

    pdf = build_scanned_ocr_pdf(tmp_path, pages=5)
    outdir = tmp_path / "out"
    convert.convert_with_pymupdf(pdf, outdir, extract_images=True)
    md = (outdir / f"{pdf.stem}.md").read_text()

    assert "cannon" in md, "body text was dropped by the figure splicer"
    # One occurrence per page, not one image reference per page.
    assert md.count("cannon") == 5, f"expected 5 pages of body, got {md.count('cannon')}"
    assert "Figure on page" not in md, (
        "page scans must not be emitted as figures"
    )


def test_a_real_figure_is_still_extracted(tmp_path):
    """The other half of the gate: legitimate figures must still be found.

    Without this, 'drop full-page regions' could be implemented as 'drop
    every region' and the bad-case test above would still pass.
    """
    pdf = build_figure_pdf(tmp_path)
    doc = fitz.open(str(pdf))
    page = doc[0]
    assert not assets.detect_page_scan_document(doc), (
        "a prose page with a drawn figure is not a scanned document"
    )
    extracted = assets.extract_page_assets(page, "fig", tmp_path / "b", 1)
    doc.close()
    assert len(extracted) == 1, (
        "a genuine sub-page figure must still be extracted"
    )
    _rect, md = extracted[0]
    assert "Figure 1.1" in md, "the caption must still be matched"


def test_image_only_page_still_emits_its_image(tmp_path):
    """A full-page image with NO text layer has nothing else to emit.

    A plate, a fold-out, or a scan that was never OCR'd. Dropping the image
    there would lose the only content the page has.
    """
    pdf = tmp_path / "plate.pdf"
    doc = fitz.open()
    page = doc.new_page(width=334, height=559)
    src = fitz.open()
    tmp_page = src.new_page(width=100, height=160)
    tmp_page.draw_rect(fitz.Rect(0, 0, 100, 160), color=(0.2, 0.2, 0.2),
                       fill=(0.2, 0.2, 0.2))
    png = tmp_page.get_pixmap(dpi=72).tobytes("png")
    src.close()
    page.insert_image(fitz.Rect(0, 0, 334, 559), stream=png)
    doc.save(str(pdf))
    doc.close()

    doc = fitz.open(str(pdf))
    assert not assets.detect_page_scan_document(doc), (
        "no text layer means this is not a scanned-and-OCR'd book, so its "
        "images are the only content it has"
    )
    extracted = assets.extract_page_assets(
        doc[0], "plate", tmp_path / "c", 1,
        page_scan_document=assets.detect_page_scan_document(doc),
    )
    doc.close()
    assert len(extracted) == 1, (
        "an un-OCR'd full-page image is the page's only content and must "
        "still be emitted"
    )
