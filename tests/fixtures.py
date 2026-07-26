"""Synthetic PDF builders for tests.

Every test that needs a PDF calls one of these builders instead of
committing a binary fixture to the repo. Each builder returns a Path
to a file inside the tmp_path fixture directory.
"""
import zipfile
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


def build_page_printed_pdf(
    tmp_path: Path,
    pages: int = 8,
    offset: int = -4,
    skip_page_printed_on: tuple = (),
    body_only_footer_on: tuple = (),
    name: str = "page_printed.pdf",
) -> Path:
    """Build a PDF whose pages carry a printed page number in the footer.

    PDF page i (1-based) prints page number i + offset. With the default
    offset of -4, PDF page 5 prints "1" — i.e. four pages of unnumbered
    front matter, the common real-world shape. Pages whose computed
    printed number is < 1 print no footer at all, standing in for a cover
    and title page.

    `skip_page_printed_on` names PDF pages that print NO footer even
    though their printed number would be >= 1 — standing in for the
    real-world case where the printed number was lost to extraction (OCR
    miss, figure-covered footer). Those pages are the ones interpolation
    must fill in.

    `body_only_footer_on` names PDF pages that carry their printed footer
    but NO body text — the numbered-but-blank verso of a part divider.
    After header stripping those pages clean to nothing and are dropped
    before a locator is emitted, so they must not count toward the
    page_printed_coverage denominator.
    """
    out = tmp_path / name
    doc = fitz.open()
    skip = set(skip_page_printed_on)
    footer_only = set(body_only_footer_on)
    for i in range(1, pages + 1):
        page = doc.new_page(width=612, height=792)
        if i not in footer_only:
            page.insert_text((72, 100), f"Body text for page {i}.")
        page_printed = i + offset
        if page_printed >= 1 and i not in skip:
            page.insert_text((300, 740), str(page_printed))
    doc.save(str(out))
    doc.close()
    return out


def build_trailing_number_pdf(
    tmp_path: Path,
    pages: int = 8,
    name: str = "trailing.pdf",
) -> Path:
    """Build a PDF whose body text legitimately ENDS in a number.

    No page carries a printed page number. Every page's last line of prose
    ends with a year, standing in for the very common real-world shape
    where a page's closing sentence ends in a number and the real footer
    never survived extraction. Nothing here was ever printed as a page
    number, so every page must report `page_printed=none`.

    The closing sentences deliberately DIFFER from page to page. An
    identical closing line would be detected as a repeating running footer
    and removed whole, so the trailing-number branch this fixture exists to
    exercise would never be reached.
    """
    prose = [
        "The study was published in",
        "The print run sold roughly",
        "The trial ran for",
        "The firm employed some",
        "The division grew to",
        "The strike lasted about",
        "The audience reached nearly",
        "The revision shipped in",
        "The survey covered exactly",
        "The programme spanned some",
        "The refit cost about",
        "The agency hired around",
    ]
    out = tmp_path / name
    doc = fitz.open()
    for i in range(1, pages + 1):
        page = doc.new_page(width=612, height=792)
        page.insert_text((72, 100), f"Body text for page {i}.")
        page.insert_text(
            (72, 130), f"{prose[(i - 1) % len(prose)]} {1990 + i}"
        )
    doc.save(str(out))
    doc.close()
    return out


def build_roman_wordlike_pdf(tmp_path: Path, name: str = "romanish.pdf") -> Path:
    """Build a PDF with standalone lines that LOOK like roman numerals.

    "I", "ill" and "civil" are all matched by the loose roman stripping
    regex `[ivxlc]{1,7}`, but they are English words sitting on their own
    line (a dropped caption, a hyphenation artifact, a one-word line). No
    page here carries a printed number, so the book must come out
    pdf_only.
    """
    out = tmp_path / name
    doc = fitz.open()
    words = ["I", "ill", "civil", "ill", "civil", "I", "ill", "civil"]
    for i in range(1, 9):
        page = doc.new_page(width=612, height=792)
        page.insert_text((72, 100), words[(i - 1) % len(words)])
        page.insert_text((72, 130), f"Body text for page {i}.")
    doc.save(str(out))
    doc.close()
    return out


def build_renumbering_pdf(tmp_path: Path, name: str = "renumber.pdf") -> Path:
    """Build a PDF whose printed numbering RESTARTS partway through.

    Pages 3-8 print page numbers 1-6 (offset -2). Page 9 onward is a
    second section restarting at 1 (offset -8), the shape of endnotes or a
    part-opener that resets. No single constant offset explains both runs,
    so `_derive_page_offset` must refuse and NOTHING may be interpolated.

    Pages 12 and 14 print no footer at all — those are the uncaptured
    pages a buggy implementation would fill with confident wrong numbers.
    """
    out = tmp_path / name
    doc = fitz.open()
    for i in range(1, 17):
        page = doc.new_page(width=612, height=792)
        page.insert_text((72, 100), f"Body text for page {i}.")
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


def build_minimal_epub(tmp_path: Path, name: str = "minimal.epub") -> Path:
    """Build the smallest valid EPUB 2 that pandoc will convert.

    An EPUB is a zip with an uncompressed `mimetype` entry first, a
    META-INF/container.xml pointing at the OPF package, and at least one
    XHTML content document. Synthesized rather than committed so the repo
    keeps no binary fixtures.
    """
    out = tmp_path / name

    container = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<container version="1.0" '
        'xmlns="urn:oasis:names:tc:opendocument:xmlns:container">\n'
        '  <rootfiles>\n'
        '    <rootfile full-path="OEBPS/content.opf" '
        'media-type="application/oebps-package+xml"/>\n'
        '  </rootfiles>\n'
        '</container>\n'
    )
    opf = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<package xmlns="http://www.idpf.org/2007/opf" version="2.0" '
        'unique-identifier="bookid">\n'
        '  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">\n'
        '    <dc:title>Minimal Book</dc:title>\n'
        '    <dc:language>en</dc:language>\n'
        '    <dc:identifier id="bookid">urn:uuid:bookconvert-test</dc:identifier>\n'
        '  </metadata>\n'
        '  <manifest>\n'
        '    <item id="ch1" href="ch1.xhtml" media-type="application/xhtml+xml"/>\n'
        '    <item id="ncx" href="toc.ncx" '
        'media-type="application/x-dtbncx+xml"/>\n'
        '  </manifest>\n'
        '  <spine toc="ncx">\n'
        '    <itemref idref="ch1"/>\n'
        '  </spine>\n'
        '</package>\n'
    )
    ncx = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<ncx xmlns="http://www.daisy.org/z3986/2005/ncx/" version="2005-1">\n'
        '  <head><meta name="dtb:uid" content="urn:uuid:bookconvert-test"/></head>\n'
        '  <docTitle><text>Minimal Book</text></docTitle>\n'
        '  <navMap>\n'
        '    <navPoint id="np1" playOrder="1">\n'
        '      <navLabel><text>Chapter One</text></navLabel>\n'
        '      <content src="ch1.xhtml"/>\n'
        '    </navPoint>\n'
        '  </navMap>\n'
        '</ncx>\n'
    )
    ch1 = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<html xmlns="http://www.w3.org/1999/xhtml">\n'
        '  <head><title>Chapter One</title></head>\n'
        '  <body>\n'
        '    <h1>Chapter One</h1>\n'
        '    <p>An epub is reflowable, so it has no printed page numbers.</p>\n'
        '  </body>\n'
        '</html>\n'
    )

    with zipfile.ZipFile(out, "w") as zf:
        # The mimetype entry must be first and stored uncompressed.
        zf.writestr(
            zipfile.ZipInfo("mimetype"),
            "application/epub+zip",
            compress_type=zipfile.ZIP_STORED,
        )
        zf.writestr("META-INF/container.xml", container)
        zf.writestr("OEBPS/content.opf", opf)
        zf.writestr("OEBPS/toc.ncx", ncx)
        zf.writestr("OEBPS/ch1.xhtml", ch1)
    return out
