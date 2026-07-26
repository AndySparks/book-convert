"""Tests for typed page locators: PDF page index + printed page number capture."""
import json
from pathlib import Path

import pytest

from report import ConversionReport, write_report


def test_report_defaults_to_no_locator():
    r = ConversionReport(source="in.pdf", output="out.md", method="pymupdf")
    assert r.page_numbering == "none"
    assert r.page_printed_count == 0
    assert r.page_locator_count == 0
    assert r.page_printed_coverage == 0.0
    assert r.page_printed_offset is None
    assert r.page_printed_offset_consistent is False


def test_report_locator_fields_round_trip(tmp_path):
    r = ConversionReport(
        source="in.pdf", output="out.md", method="pymupdf",
        page_numbering="printed", page_printed_count=20, page_locator_count=319,
        page_printed_coverage=0.0627, page_printed_offset=-12,
        page_printed_offset_consistent=True,
    )
    p = tmp_path / "out.report.json"
    write_report(p, r)
    data = json.loads(p.read_text(encoding="utf-8"))
    assert data["page_numbering"] == "printed"
    assert data["page_printed_count"] == 20
    assert data["page_printed_offset"] == -12
    assert data["page_printed_offset_consistent"] is True


def test_strip_running_headers_returns_three_tuples():
    import convert
    pages = [(i, f"Body text page {i}.\n{i + 10}") for i in range(1, 8)]
    result = convert._strip_running_headers(pages)
    assert all(len(t) == 3 for t in result)


def test_captures_bottom_standalone_page_printed():
    import convert
    # PDF page i carries printed page number i+10 as a standalone bottom line.
    pages = [(i, f"Body text for page {i}.\n{i + 10}") for i in range(1, 8)]
    result = convert._strip_running_headers(pages)
    page_printeds = [page_printed for _, _, page_printed in result]
    assert page_printeds == ["11", "12", "13", "14", "15", "16", "17"]
    # And the printed page number must be gone from the body.
    assert "11" not in result[0][1]


def test_captures_roman_page_printed():
    import convert
    romans = ["i", "ii", "iii", "iv", "v", "vi"]
    pages = [(i + 1, f"Front matter {i}.\n{r}") for i, r in enumerate(romans)]
    result = convert._strip_running_headers(pages)
    assert [f for _, _, f in result] == romans


def test_page_with_no_page_printed_yields_none():
    import convert
    pages = [(i, f"Body text page {i} with no page number.") for i in range(1, 8)]
    result = convert._strip_running_headers(pages)
    assert all(page_printed is None for _, _, page_printed in result)


def test_short_document_early_return_still_three_tuples():
    """The len < 5 early return must not leak 2-tuples to the caller."""
    import convert
    pages = [(1, "Only one page."), (2, "Second page.")]
    result = convert._strip_running_headers(pages)
    assert all(len(t) == 3 for t in result)
    assert all(page_printed is None for _, _, page_printed in result)


def test_pymupdf_emits_two_field_locator(tmp_path):
    import convert
    from tests import fixtures

    pdf = fixtures.build_page_printed_pdf(tmp_path, pages=8, offset=-4)
    out_dir = tmp_path / "out"
    out_dir.mkdir()

    report = convert.convert_with_pymupdf(pdf, out_dir)
    md = (out_dir / f"{pdf.stem}.md").read_text(encoding="utf-8")

    # PDF page 5 carries printed page number 1.
    assert "<!-- page_pdf=5 page_printed=1 -->" in md
    assert "<!-- page_pdf=8 page_printed=4 -->" in md
    # PDF pages 1-4 have no printed page number.
    assert "<!-- page_pdf=1 page_printed=none -->" in md
    # The old single-field format must be gone.
    assert "<!-- Page 5 -->" not in md


def test_pymupdf_reports_page_printed_coverage(tmp_path):
    import convert
    from tests import fixtures

    pdf = fixtures.build_page_printed_pdf(tmp_path, pages=8, offset=-4)
    out_dir = tmp_path / "out"
    out_dir.mkdir()

    report = convert.convert_with_pymupdf(pdf, out_dir)
    assert report.page_locator_count == 8
    assert report.page_printed_count == 4          # pdf pages 5,6,7,8
    assert report.page_printed_coverage == pytest.approx(0.5)
    assert report.page_numbering == "printed"


def test_pymupdf_declares_pdf_only_when_no_page_printed(tmp_path):
    """An ebook-derived PDF has no printed page number; it must say so."""
    import convert
    from tests import fixtures

    pdf = fixtures.build_text_pdf(tmp_path, pages=6, body="No page number here.")
    out_dir = tmp_path / "out"
    out_dir.mkdir()

    report = convert.convert_with_pymupdf(pdf, out_dir)
    assert report.page_printed_count == 0
    assert report.page_numbering == "pdf_only"


def test_derive_offset_constant():
    import convert
    samples = {5: "1", 20: "16", 100: "96"}
    offset, consistent = convert._derive_page_offset(samples)
    assert offset == -4
    assert consistent is True


def test_derive_offset_inconsistent_is_rejected():
    """A book that renumbers partway through must not be interpolated."""
    import convert
    samples = {5: "1", 20: "16", 100: "40"}
    offset, consistent = convert._derive_page_offset(samples)
    assert consistent is False


def test_derive_offset_ignores_roman_page_printed():
    import convert
    samples = {2: "ii", 3: "iii", 10: "6", 20: "16", 30: "26"}
    offset, consistent = convert._derive_page_offset(samples)
    assert offset == -4
    assert consistent is True


def test_derive_offset_needs_at_least_three_samples():
    import convert
    offset, consistent = convert._derive_page_offset({5: "1", 20: "16"})
    assert consistent is False


def test_interpolates_page_printed_on_unnumbered_pages(tmp_path):
    """A page whose printed page number was lost to OCR still gets an address."""
    import convert
    from tests import fixtures

    pdf = fixtures.build_page_printed_pdf(tmp_path, pages=12, offset=-4)
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    report = convert.convert_with_pymupdf(pdf, out_dir)
    md = (out_dir / f"{pdf.stem}.md").read_text(encoding="utf-8")

    assert report.page_printed_offset == -4
    assert report.page_printed_offset_consistent is True
    # PDF pages 1-4 are genuinely before page 1 — they must stay `none`,
    # never a zero or negative printed page number.
    assert "<!-- page_pdf=1 page_printed=none -->" in md
    assert "page_printed=0" not in md
    assert "page_printed=-" not in md


def test_derive_offset_tolerates_non_ascii_digit_page_printed():
    """A superscript footnote marker must not crash the conversion.

    `"²".isdigit()` is True but `int("²")` raises ValueError. The arabic
    test is `.isascii() and .isdecimal()`, so the marker is simply ignored.
    """
    import convert
    samples = {5: "²", 10: "6", 20: "16", 30: "26"}
    offset, consistent = convert._derive_page_offset(samples)
    assert offset == -4
    assert consistent is True


def test_derive_offset_ignores_arabic_indic_digits():
    import convert
    # U+0666 ARABIC-INDIC DIGIT SIX: isdigit() True, not ASCII decimal.
    samples = {5: "٦", 10: "6", 20: "16", 30: "26"}
    offset, consistent = convert._derive_page_offset(samples)
    assert offset == -4
    assert consistent is True


def test_interpolates_missing_mid_body_page_printed(tmp_path):
    """PDF pages whose printed page number was lost to extraction get filled in."""
    import convert
    from tests import fixtures

    # PDF pages 5-12 print page numbers 1-8; pages 7 and 9 lost their footer.
    pdf = fixtures.build_page_printed_pdf(
        tmp_path, pages=12, offset=-4, skip_page_printed_on=(7, 9)
    )
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    report = convert.convert_with_pymupdf(pdf, out_dir)
    md = (out_dir / f"{pdf.stem}.md").read_text(encoding="utf-8")

    assert report.page_printed_offset == -4
    assert report.page_printed_offset_consistent is True
    # The two gaps are interpolated to their true printed numbers.
    assert "<!-- page_pdf=7 page_printed=3 -->" in md
    assert "<!-- page_pdf=9 page_printed=5 -->" in md
    # page_printed_count counts CAPTURED page numbers only: pdf pages 5,6,8,10,11,12.
    assert report.page_printed_count == 6
    # Front matter still refuses to invent a printed page number.
    assert "<!-- page_pdf=1 page_printed=none -->" in md
    assert "page_printed=0" not in md
    assert "page_printed=-" not in md


def test_no_extrapolation_past_the_last_captured_sample(tmp_path):
    """Beyond the captured span there is no evidence the offset holds.

    A real book's endnotes often restart at 1 and never survive extraction;
    they contribute no samples, so they cannot disagree. Extrapolating there
    would emit confident wrong numbers, so we clamp to [min, max] sample.
    """
    import convert
    from tests import fixtures

    # PDF pages 5-12 print page numbers 1-8. PDF pages 13-16 print nothing.
    pdf = fixtures.build_page_printed_pdf(
        tmp_path, pages=16, offset=-4, skip_page_printed_on=(13, 14, 15, 16)
    )
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    report = convert.convert_with_pymupdf(pdf, out_dir)
    md = (out_dir / f"{pdf.stem}.md").read_text(encoding="utf-8")

    assert report.page_printed_offset == -4
    assert report.page_printed_offset_consistent is True
    for page_pdf in (13, 14, 15, 16):
        assert f"<!-- page_pdf={page_pdf} page_printed=none -->" in md
    # The would-be extrapolated numbers must appear nowhere.
    for bad in ("page_printed=9", "page_printed=10", "page_printed=11", "page_printed=12"):
        assert bad not in md


def test_renumbering_book_gets_no_interpolation_in_markdown(tmp_path):
    """The emission layer, not just the helper, must refuse an inconsistent book."""
    import convert
    from tests import fixtures

    pdf = fixtures.build_renumbering_pdf(tmp_path)
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    report = convert.convert_with_pymupdf(pdf, out_dir)
    md = (out_dir / f"{pdf.stem}.md").read_text(encoding="utf-8")

    assert report.page_printed_offset_consistent is False
    assert report.page_printed_offset is None
    # PDF pages 12 and 14 lost their printed number. With two disagreeing
    # numbering runs we must emit `none`, never a guess.
    assert "<!-- page_pdf=12 page_printed=none -->" in md
    assert "<!-- page_pdf=14 page_printed=none -->" in md
    # PDF pages 1-2 carry no printed number at all and stay `none`.
    assert "<!-- page_pdf=1 page_printed=none -->" in md
    assert "<!-- page_pdf=2 page_printed=none -->" in md


# ---------------------------------------------------------------------------
# A number that merely TRAILS the last line was never printed as a page number.
# ---------------------------------------------------------------------------

# Each page's closing sentence is DIFFERENT prose that happens to end in a
# number. Identical closing lines would be caught earlier as a repeating
# running-footer pattern and removed whole, never reaching the trailing
# number branch this section exists to pin down.
TRAILING_PROSE = [
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


def _trailing_number_page(i):
    """Body whose last line is prose legitimately ending in a year."""
    return f"Body text for page {i}.\n{TRAILING_PROSE[i - 1]} {1990 + i}"


def test_trailing_number_on_last_line_is_not_a_page_printed():
    """"...published in 1991" must not become printed page number 1991."""
    import convert
    pages = [(i, _trailing_number_page(i)) for i in range(1, 9)]
    result = convert._strip_running_headers(pages)
    assert [page_printed for _, _, page_printed in result] == [None] * 8


def test_trailing_number_is_still_stripped_from_the_body():
    """Capture goes away; the stripping behavior must not change."""
    import convert
    pages = [(i, _trailing_number_page(i)) for i in range(1, 9)]
    result = convert._strip_running_headers(pages)
    for i, (_, text, _) in enumerate(result, start=1):
        # The prose survives; only the trailing number is removed.
        assert text.rstrip().endswith(TRAILING_PROSE[i - 1])
        assert str(1990 + i) not in text


def test_trailing_number_does_not_poison_the_offset():
    """A trailing year must not enter _derive_page_offset at all.

    With PDF pages 5-12 carrying real printed page numbers AND every page's
    prose ending in a year, capturing the year would hand the derivation a
    set of wildly disagreeing offsets and interpolation would be refused
    for the whole book.
    """
    import convert
    pages = []
    for i in range(1, 13):
        body = _trailing_number_page(i)
        page_printed = i - 4
        if page_printed >= 1:
            body += f"\n{page_printed}"
        pages.append((i, body))

    result = convert._strip_running_headers(pages)
    page_printed_by_pdf_index = {s: f for s, _, f in result if f}
    # Only the genuinely printed footers were captured.
    assert page_printed_by_pdf_index == {5: "1", 6: "2", 7: "3", 8: "4", 9: "5",
                                          10: "6", 11: "7", 12: "8"}
    offset, consistent = convert._derive_page_offset(page_printed_by_pdf_index)
    assert offset == -4
    assert consistent is True


def test_trailing_number_pdf_emits_no_page_printed(tmp_path):
    """End to end: a book with no printed page numbers must declare pdf_only."""
    import convert
    from tests import fixtures

    pdf = fixtures.build_trailing_number_pdf(tmp_path, pages=8)
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    report = convert.convert_with_pymupdf(pdf, out_dir)
    md = (out_dir / f"{pdf.stem}.md").read_text(encoding="utf-8")

    assert report.page_printed_count == 0
    assert report.page_numbering == "pdf_only"
    for page_pdf in range(1, 9):
        assert f"<!-- page_pdf={page_pdf} page_printed=none -->" in md
    for year in range(1991, 1999):
        assert f"page_printed={year}" not in md


# ---------------------------------------------------------------------------
# The roman path: real numerals only, and never on a single sighting.
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("value", [
    "i", "ii", "iii", "iv", "v", "vi", "ix", "x", "xii", "xl", "lix", "Li",
    "XVIII", "cx",
])
def test_is_roman_page_number_accepts_real_numerals(value):
    import convert
    assert convert._is_roman_page_number(value) is True


@pytest.mark.parametrize("value", [
    "ill", "civil", "vill", "lil", "ivi", "", "iiii", "vv", "ic", "xx1",
])
def test_is_roman_page_number_rejects_english_words_and_malformed(value):
    import convert
    assert convert._is_roman_page_number(value) is False


def test_english_words_are_never_captured_as_page_printed():
    """`ill` and `civil` match the loose stripping regex; neither is a printed page number."""
    import convert
    words = ["I", "ill", "civil", "ill", "civil", "I", "ill", "civil"]
    pages = [
        (i, f"{words[i - 1]}\nBody text for page {i}.")
        for i in range(1, 9)
    ]
    result = convert._strip_running_headers(pages)
    assert [page_printed for _, _, page_printed in result] == [None] * 8


def test_english_words_are_still_stripped_from_the_body():
    """Capture narrows; stripping stays exactly as it was."""
    import convert
    words = ["I", "ill", "civil", "ill", "civil", "I", "ill", "civil"]
    pages = [
        (i, f"{words[i - 1]}\nBody text for page {i}.")
        for i in range(1, 9)
    ]
    result = convert._strip_running_headers(pages)
    for i, (_, text, _) in enumerate(result, start=1):
        assert text.strip() == f"Body text for page {i}."


def test_a_single_roman_capture_is_not_believed():
    """One standalone `I` is the English pronoun far more often than page 1."""
    import convert
    pages = [(i, f"Body text for page {i}.") for i in range(1, 9)]
    pages[2] = (3, "I\nBody text for page 3.")
    result = convert._strip_running_headers(pages)
    assert [page_printed for _, _, page_printed in result] == [None] * 8


def test_two_distinct_roman_captures_are_believed():
    """A genuine front-matter run corroborates itself."""
    import convert
    romans = ["i", "ii", "iii", "iv", "v", "vi"]
    pages = [(i + 1, f"Front matter {i}.\n{r}") for i, r in enumerate(romans)]
    result = convert._strip_running_headers(pages)
    assert [f for _, _, f in result] == romans


def test_wordlike_romans_do_not_flip_page_numbering(tmp_path):
    """A book with zero printed page numbers must not declare `printed`."""
    import convert
    from tests import fixtures

    pdf = fixtures.build_roman_wordlike_pdf(tmp_path)
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    report = convert.convert_with_pymupdf(pdf, out_dir)

    assert report.page_printed_count == 0
    assert report.page_numbering == "pdf_only"


def test_page_locator_count_counts_only_emitted_locators(tmp_path):
    """The coverage denominator must not include pages that were skipped.

    PDF pages 6 and 10 are numbered-but-blank part-divider versos: they
    carry a printed footer and nothing else, so they clean to empty and
    are dropped before any locator is written. Counting them inflates the
    denominator and under-reports page_printed_coverage.
    """
    import convert
    from tests import fixtures

    pdf = fixtures.build_page_printed_pdf(
        tmp_path, pages=12, offset=-4, body_only_footer_on=(6, 10)
    )
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    report = convert.convert_with_pymupdf(pdf, out_dir)
    md = (out_dir / f"{pdf.stem}.md").read_text(encoding="utf-8")

    emitted = md.count("<!-- page_pdf=")
    # The two footer-only pages produced no locator at all.
    assert emitted == 10
    assert "<!-- page_pdf=6 " not in md
    assert "<!-- page_pdf=10 " not in md
    assert report.page_locator_count == emitted
    # Both terms are counted over the SAME population. PDF pages 5-12 all
    # carried a printed footer, but 6 and 10 never emitted a locator, so
    # the numerator is 6 -- not the 8 page numbers that were captured.
    assert report.page_printed_count == 6
    assert report.page_printed_coverage == pytest.approx(6 / 10)
    assert report.page_printed_coverage <= 1.0


def test_page_printed_coverage_never_exceeds_one(tmp_path):
    """The ratio is a coverage fraction; >1.0 is meaningless by construction.

    Worth asserting outright because a >1.0 value is not merely wrong, it is
    wrong in the unsafe direction: it sails through the ingestion gate's
    `>= threshold` check while describing nothing real.

    Every PDF page that carries a printed page number here is also
    body-less, so it is dropped before a locator is written. A numerator
    counted over captured page numbers (8) against a denominator counted
    over emitted locators (4) yields 2.0.
    """
    import convert
    from tests import fixtures

    pdf = fixtures.build_page_printed_pdf(
        tmp_path, pages=12, offset=-4,
        body_only_footer_on=tuple(range(5, 13)),
    )
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    report = convert.convert_with_pymupdf(pdf, out_dir)
    md = (out_dir / f"{pdf.stem}.md").read_text(encoding="utf-8")

    assert report.page_locator_count == md.count("<!-- page_pdf=") == 4
    assert report.page_printed_count == 0
    assert report.page_printed_coverage == 0.0
    assert 0.0 <= report.page_printed_coverage <= 1.0
    # A book whose every captured page number was dropped has no citable
    # printed address left, and must not claim otherwise.
    assert report.page_numbering == "pdf_only"


PAGE_NUMBERING_VALUES = {"printed", "pdf_only", "none"}


@pytest.mark.parametrize("method,expected", [
    ("marker", "none"),
    ("pandoc", "none"),
    ("docling", "none"),
    ("ocr", "pdf_only"),
    ("pymupdf4llm", "pdf_only"),
])
def test_backend_page_numbering_declarations(method, expected):
    import convert
    report = convert.ConversionReport(
        source="in.pdf", output="out.md", method=method,
    )
    convert._apply_backend_page_numbering(report)
    assert report.page_numbering == expected
    assert report.page_numbering in PAGE_NUMBERING_VALUES


def test_pandoc_epub_conversion_writes_a_none_locator_sidecar(tmp_path):
    """An EPUB can never carry a printed page number — say so in the sidecar.

    This is the case the ingestion gate most needs to detect. A pandoc run
    that wrote no sidecar at all would be indistinguishable from a
    conversion that never ran, which is the original bug this bet exists to
    kill.
    """
    import shutil

    import convert
    from tests import fixtures

    if shutil.which("pandoc") is None:
        pytest.skip("pandoc not installed")

    epub = fixtures.build_minimal_epub(tmp_path)
    out_dir = tmp_path / "out"
    out_dir.mkdir()

    report = convert.convert_with_pandoc(epub, out_dir)

    # Pandoc now returns a ConversionReport like every other backend.
    assert isinstance(report, ConversionReport)
    assert report.method == "pandoc"
    assert report.page_numbering == "none"

    sidecar = out_dir / f"{epub.stem}.report.json"
    assert sidecar.exists()
    data = json.loads(sidecar.read_text(encoding="utf-8"))
    assert data["method"] == "pandoc"
    assert data["page_numbering"] == "none"
    # Page counts stay at their defaults; an epub has no pages to count.
    assert not data.get("total_pages")


def test_convert_book_epub_route_produces_a_sidecar(tmp_path):
    """The dispatch path, not just the backend, must leave a sidecar behind."""
    import shutil

    import convert
    from tests import fixtures

    if shutil.which("pandoc") is None:
        pytest.skip("pandoc not installed")

    epub = fixtures.build_minimal_epub(tmp_path, name="dispatch.epub")
    out_dir = tmp_path / "out"

    assert convert.convert_book(epub, out_dir) is True

    sidecar = out_dir / "dispatch.report.json"
    assert sidecar.exists()
    data = json.loads(sidecar.read_text(encoding="utf-8"))
    assert data["page_numbering"] == "none"
    # Cleanup is deliberately skipped on the epub route (it repairs PDF
    # extraction artifacts), so the sidecar must not claim it ran.
    assert not data.get("cleaned")
