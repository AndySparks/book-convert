"""Synthetic PDF builders for tests.

Every test that needs a PDF calls one of these builders instead of
committing a binary fixture to the repo. Each builder returns a Path
to a file inside the tmp_path fixture directory.
"""
from pathlib import Path

import fitz


def build_text_pdf(tmp_path: Path, pages: int = 3, body: str = "Lorem ipsum dolor sit amet.") -> Path:
    """Build a plain-text PDF with N pages of the given body text."""
    out = tmp_path / "text.pdf"
    doc = fitz.open()
    for i in range(pages):
        page = doc.new_page(width=612, height=792)
        page.insert_text((72, 72), f"Page {i + 1}")
        page.insert_text((72, 120), body)
    doc.save(str(out))
    doc.close()
    return out


def build_figure_pdf(tmp_path: Path) -> Path:
    """Build a PDF with one page containing body text, a drawn rectangle
    standing in for a figure, and a 'Figure 1.1' caption below it.
    """
    out = tmp_path / "figure.pdf"
    doc = fitz.open()
    page = doc.new_page(width=612, height=792)
    page.insert_text((72, 72), "Introduction to Thinking")
    page.insert_text((72, 120),
                     "This chapter presents the basic model we will use.")
    # Draw a rectangle that stands in for a figure.
    rect = fitz.Rect(150, 200, 460, 450)
    page.draw_rect(rect, color=(0, 0, 0), width=2)
    page.draw_line((150, 325), (460, 325), color=(0, 0, 0), width=1)
    page.draw_line((305, 200), (305, 450), color=(0, 0, 0), width=1)
    # Caption.
    page.insert_text((72, 480), "Figure 1.1 The four-quadrant model.")
    page.insert_text((72, 520),
                     "The quadrants represent the two primary axes.")
    doc.save(str(out))
    doc.close()
    return out


def build_foliated_pdf(
    tmp_path: Path,
    pages: int = 8,
    offset: int = -4,
    skip_folios_on: tuple = (),
    name: str = "foliated.pdf",
) -> Path:
    """Build a PDF whose pages carry a printed folio in the footer.

    Sheet i (1-based) prints folio i + offset. With the default offset of
    -4, sheet 5 prints "1" — i.e. four pages of unnumbered front matter,
    the common real-world shape. Pages whose computed folio is < 1 print
    no footer at all, standing in for a cover and title page.

    `skip_folios_on` names sheets that print NO footer even though their
    folio would be >= 1 — standing in for the real-world case where the
    printed number was lost to extraction (OCR miss, figure-covered
    footer). Those sheets are the ones interpolation must fill in.
    """
    out = tmp_path / name
    doc = fitz.open()
    skip = set(skip_folios_on)
    for i in range(1, pages + 1):
        page = doc.new_page(width=612, height=792)
        page.insert_text((72, 100), f"Body text for sheet {i}.")
        folio = i + offset
        if folio >= 1 and i not in skip:
            page.insert_text((300, 740), str(folio))
    doc.save(str(out))
    doc.close()
    return out


def build_renumbering_pdf(tmp_path: Path, name: str = "renumber.pdf") -> Path:
    """Build a PDF whose printed numbering RESTARTS partway through.

    Sheets 3-8 print folios 1-6 (offset -2). Sheet 9 onward is a second
    section restarting at 1 (offset -8), the shape of endnotes or a
    part-opener that resets. No single constant offset explains both runs,
    so `_derive_folio_offset` must refuse and NOTHING may be interpolated.

    Sheets 12 and 14 print no footer at all — those are the uncaptured
    sheets a buggy implementation would fill with confident wrong numbers.
    """
    out = tmp_path / name
    doc = fitz.open()
    for i in range(1, 17):
        page = doc.new_page(width=612, height=792)
        page.insert_text((72, 100), f"Body text for sheet {i}.")
        if i in (12, 14):
            continue  # printed number lost to extraction
        if 3 <= i <= 8:
            page.insert_text((300, 740), str(i - 2))
        elif i >= 9:
            page.insert_text((300, 740), str(i - 8))
    doc.save(str(out))
    doc.close()
    return out


def build_raster_image_pdf(tmp_path: Path) -> Path:
    """Build a PDF with one page containing a real embedded raster image.

    Uses a tiny 4x4 solid-colored PNG so the test runs fast.
    """
    out = tmp_path / "raster.pdf"
    doc = fitz.open()
    page = doc.new_page(width=612, height=792)
    page.insert_text((72, 72), "Chapter 1")
    # Create a 4x4 red PNG in-memory via a pixmap.
    pix = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 4, 4))
    pix.clear_with(255)  # white background
    img_bytes = pix.tobytes("png")
    rect = fitz.Rect(200, 150, 400, 350)
    page.insert_image(rect, stream=img_bytes)
    page.insert_text((72, 380), "Figure 1.1 A square.")
    page.insert_text((72, 420), "The image above is the square we will study.")
    doc.save(str(out))
    doc.close()
    return out


def build_scanned_pdf(tmp_path: Path) -> Path:
    """Build a PDF whose pages contain ONLY images (no extractable text).

    Used to test that extraction-only backends fail cleanly and that the
    OCR fallback routing picks it up.
    """
    out = tmp_path / "scanned.pdf"
    doc = fitz.open()
    for i in range(2):
        page = doc.new_page(width=612, height=792)
        pix = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 612, 792))
        pix.clear_with(240)
        img_bytes = pix.tobytes("png")
        page.insert_image(page.rect, stream=img_bytes)
    doc.save(str(out))
    doc.close()
    return out
